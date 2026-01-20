"""
    robots_client.py
    manager.py からメッセージを受信し、ロボットのコード実行や割り込み制御を行う
"""

import asyncio
import aiomqtt
import os
import sys

# ===== 設定の読み込み =====
try:
    import config
    print(f"✅ config.py を読み込みました (Broker: {config.MQTT_BROKER})")
except ImportError:
    print("❌ Critical Error: 'config.py' が見つかりません。実行を中止します。")
    sys.exit(1)

from _LLM import task_generate, talk_generate
from robot_api_manager import get_robot_api_manager

class RobotClient:
    def __init__(self):
        # タスク実行管理フラグ (set=実行可能/待機中, clear=実行中)
        self.running_task = asyncio.Event()
        self.running_task.set()

        # ロボットクライアント (async_initで初期化)
        self.api_manager = None
        self.kachaka_client = None
        self.akari_client = None

    async def async_init(self):
        """ ロボットAPIとの接続初期化 """
        # シングルトンマネージャーからクライアントを取得（引数不要）
        self.api_manager = get_robot_api_manager()
        self.kachaka_client = self.api_manager.get_kachaka_client()
        self.akari_client = self.api_manager.get_akari_client()

    async def running_robots_task(self, filepath):
        """ 生成されたロボットタスクファイルを実行する """
        print(f"\n====================  ☑️  タスク開始: {filepath}  ====================")
        
        if self.kachaka_client is None or self.akari_client is None:
            print("🚫 クライアントが利用できません。タスクを開始できません。")
            return
        
        # フラグを下ろして「実行中」にする
        self.running_task.clear()

        try:
            # ファイル読み込み
            if not os.path.exists(filepath):
                 # カレントディレクトリからの相対パスでも探してみる
                 filepath = os.path.join(config.BASE_DIR, filepath)
                 
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
            
            # コードを関数 _main() にラップする
            # ※ LLMが生成するコードはインデントされていない前提のため、インデントを追加
            # a -> kachaka , b -> akari
            wrapped_code = (
                "async def _main(a,b):\n"
                + "\n".join("    " + line for line in code.splitlines())
            )
            
            # 動的コード実行
            # globals() を渡すことで、このスクリプト内のコンテキストでコードを実行可能にする
            exec(wrapped_code, globals())
            
            # 定義された _main 関数を非同期実行
            await globals()["_main"](self.kachaka_client, self.akari_client)

        except asyncio.CancelledError:
            print("⚠️ タスクがキャンセルされました (asyncio.CancelledError)")
        except Exception as e:
            print(f"❌ タスク実行中にエラーが発生しました: {e}")
            # エラー時は安全のため停止させる
            await self.kachaka_client.stop()
            await self.akari_client.stop()
        finally:
            # 終了処理（成功・失敗に関わらず実行）
            await self.kachaka_client.reset()
            await self.akari_client.reset()
            
            # フラグを上げて「待機中」に戻す
            self.running_task.set()
            print("====================  ✅ タスク終了 ====================")

    async def start_robot_task(self, filename):
        """ 指定されたファイル名のタスク実行をスケジュールする """
        if not self.running_task.is_set():
            print("⚠️ 他のタスクが実行中のため、開始できません。")
            return

        # configで定義されたパスを使うか、引数をそのまま使うか柔軟に対応
        # 基本は _robot_programs フォルダ内を探す
        path = filename
        if not os.path.dirname(filename): # ファイル名だけの場合
             path = os.path.join("_robot_programs", filename)
             
        if not os.path.isfile(path):
            print(f"❌ ファイルが存在しません: {path}")
            return

        # 別タスクとして実行（メインループをブロックしないため）
        asyncio.create_task(self.running_robots_task(path))
        print(f"✅ ロボットタスク '{filename}' を開始しました。")

    async def _handle_interrupt_command(self, client, command: str):
        """ 割り込み処理 """
        print(f"🛑 割り込みコマンド受信: {command}")
        
        # KachakaとAkari両方に同じメソッドがあれば実行する
        kachaka_method = getattr(self.kachaka_client, command.lower(), None)
        akari_method = getattr(self.akari_client, command.lower(), None)
        
        if kachaka_method:
            await kachaka_method()
            await client.publish(config.MQTT_TOPICS["return"], f"🛑 kachaka: {command}を実行")
        else:
            print(f"⚠️ kachaka に対する '{command}' が見つかりません")
            
        if akari_method:
            await akari_method()
            await client.publish(config.MQTT_TOPICS["return"], f"🛑 akari: {command}を実行")
        else:
            print(f"⚠️ akari に対する '{command}' が見つかりません")

    async def manual_command(self, robot_client_instance, client, msg_parts):
        """ 特定のロボットに対して手動コマンドを実行する (例: kachaka speak こんにちは) """
        if not msg_parts:
            return

        method_name = msg_parts[0]
        args = msg_parts[1:]
        args_str = " ".join(args)
        
        print(f"▶️  個別コマンド実行: {method_name} (引数: {args_str})")

        method = getattr(robot_client_instance, method_name, None)
        if method:
            try:
                self.running_task.clear() # 他のタスクが走らないようにブロック
                if args_str:
                    await method(args_str)
                else:
                    await method()
                
                # 終了後はリセット
                await self.kachaka_client.reset()
                await self.akari_client.reset()
                print(f"✅ 個別コマンド完了: {method_name}")

            except Exception as e:
                print(f"❌ 個別コマンド実行エラー: {e}")
            finally:
                self.running_task.set()
        else:
            print(f"❌ 指定されたメソッド '{method_name}' は存在しません。")

    async def main_loop(self):
        """ MQTTメッセージ受信のメインループ """
        if self.kachaka_client is None or self.akari_client is None:
            print("❌ クライアント初期化失敗のため終了します。")
            return

        try:
            print(f"🔌 MQTTブローカー接続開始: {config.MQTT_BROKER}")
            async with aiomqtt.Client(config.MQTT_BROKER) as client:
                # トピックの購読
                await client.subscribe(config.MQTT_TOPICS["status"])
                await client.subscribe(config.MQTT_TOPICS["command"])
                await client.subscribe(config.MQTT_TOPICS["order"])

                print("📥 メッセージ待機中...")

                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload.decode()
                    print(f"\n📥 受信 [{topic}]: {payload}")

                    # --- ステータス受信 ---
                    if topic == config.MQTT_TOPICS["status"]:
                        if payload == "fin":
                            await self.akari_client.send_message_to_akari("finish")
                        elif payload == "finish":
                            return # プログラム終了

                    # --- コマンド受信 (manager.py から) ---
                    elif topic == config.MQTT_TOPICS["command"]:
                        
                        # ファイル指定実行 (START filename)
                        if payload.startswith("START "):
                            filename = payload.split()[1]
                            await self.start_robot_task(filename)
                            await client.publish(config.MQTT_TOPICS["return"], f"Task started: {filename}")

                        # KACHAKA 直接操作
                        elif payload.startswith("KACHAKA "):
                            if not self.running_task.is_set():
                                print("⚠️ 実行中のタスクを停止して割り込みます")
                                await self._handle_interrupt_command(client, "STOP")
                                await self.running_task.wait()
                            
                            func_parts = payload.split()[1:]
                            asyncio.create_task(self.manual_command(self.kachaka_client, client, func_parts))

                        # AKARI 直接操作
                        elif payload.startswith("AKARI "):
                            if not self.running_task.is_set():
                                print("⚠️ 実行中のタスクを停止して割り込みます")
                                await self._handle_interrupt_command(client, "STOP")
                                await self.running_task.wait()

                            func_parts = payload.split()[1:]
                            asyncio.create_task(self.manual_command(self.akari_client, client, func_parts))

                        # 割り込み指示 (STOP, PAUSE, RESUME, etc.)
                        elif payload in ["STOP", "RESET", "PAUSE", "RESUME", "SKIP"]:
                            # タスク実行中かどうかに関わらず、コマンド自体はメソッドとして存在するなら実行を試みる
                            asyncio.create_task(self._handle_interrupt_command(client, payload))
                            

                    # --- LLM オーダー受信 ---
                    elif topic == config.MQTT_TOPICS["order"]:
                        if not self.running_task.is_set():
                            print("🛑 タスク実行中のため、強制停止して新しいオーダーを処理します")
                            await self._handle_interrupt_command(client, "STOP")
                            await self.running_task.wait()

                        print("🤖 1. 行動計画の生成中...")
                        await asyncio.to_thread(task_generate.main, payload)
                        
                        print("💬 2. 会話スクリプトの生成中...")
                        await asyncio.to_thread(talk_generate.main, payload)
                        
                        output_file = config.LLM_FINAL_SCRIPT_PATH
                        print(f"✅ 生成完了。タスクを実行します: {output_file}")
                        
                        await client.publish(config.MQTT_TOPICS["return"], f"Generated & Starting: {output_file}")
                        await self.start_robot_task(output_file)

        except Exception as e:
            print(f"❌ main_loop で致命的なエラー: {e}")
        finally:
            print("プログラムを終了します")

# アプリケーションのエントリーポイント
if __name__ == "__main__":
    print("🚀 Robots Client 起動")

    async def app():
        robot_client = RobotClient()
        await robot_client.async_init()
        await robot_client.main_loop()

    try:
        asyncio.run(app())
    except KeyboardInterrupt:
        print("\n🛑 終了操作 (Ctrl+C)")
    except Exception as e:
        print(f"❌ 予期せぬエラー: {e}")