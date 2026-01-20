"""
    manager.py
    ユーザーがコマンドを入力して、MQTTでロボット（クライアント）に指令を送るプログラム
"""

import paho.mqtt.client as mqtt

import config
MQTT_BROKER = config.MQTT_BROKER
MQTT_TOPICS = config.MQTT_TOPICS
    

class RobotRemoteController:
    def __init__(self, broker_address):
        self.broker_address = broker_address
        
        # Paho MQTT v2.0以降の推奨記述
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        # コールバック関数の登録
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        # 単純コマンド定義 (コマンド名: (送信メッセージ, 説明))
        self.simple_commands = {
            "stop":    ("STOP",    "全ロボット停止"),
            "pause":   ("PAUSE",   "一時停止"),
            "resume":  ("RESUME",  "再開"),
            "skip":    ("SKIP",    "現在のタスクをスキップ"),
            "reset":   ("RESET",   "状態リセット"),
        }

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """ 接続確立時に呼ばれるコールバック """
        if rc == 0:
            print(f"✅ MQTTブローカーに接続しました ({self.broker_address})")
            client.subscribe(MQTT_TOPICS["status"])
            client.subscribe(MQTT_TOPICS["return"])
        else:
            print(f"❌ 接続失敗: エラーコード {rc}")

    def _on_message(self, client, userdata, msg):
        """ メッセージ受信時に呼ばれるコールバック """
        try:
            message = msg.payload.decode()
            topic = msg.topic
            
            # 受信メッセージの表示
            prefix = "⚠️ " if message.startswith("ERROR:") else "📥 "
            print(f"\n{prefix}[{topic}] {message}")
            
            # 入力プロンプトの再表示
            print("🧑 指令入力 > ", end="", flush=True)
        except Exception as e:
            print(f"受信エラー: {e}")

    def start(self):
        """ クライアントの起動 """
        try:
            print(f"🚀 接続中... {self.broker_address}")
            self.client.connect(self.broker_address, 1883, 60)
            self.client.loop_start()
            self._input_loop()
        except KeyboardInterrupt:
            print("\n🛑 終了操作を検知しました。")
        except Exception as e:
            print(f"❌ 予期せぬエラー: {e}")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("👋 プログラムを終了します。")

    def _show_help(self):
        """ ヘルプ表示（コマンド変更に合わせて更新） """
        print("\n=============== コマンド一覧 ===============")
        print(" [基本コマンド]")
        for cmd, (_, desc) in self.simple_commands.items():
            print(f"  - {cmd.ljust(10)} : {desc}")
        print(" [引数付きコマンド]")
        print("  - start <file>   : 指定したタスクファイルを実行 ")
        print("  - order <msg>    : LLMに行動生成を依頼 ")
        print("  - kachaka <cmd>  : Kachakaに直接コマンド送信 ")
        print("  - akari <cmd>    : Akariに直接コマンド送信 ")
        print("  - help           : このヘルプを表示")
        print("  - exit           : 終了")
        print("============================================\n")

    def _input_loop(self):
        """ ユーザー入力を受け付けるメインループ """
        self._show_help()
        
        while True:
            try:
                user_input = input("🧑 指令入力 > ").strip()
                if not user_input:
                    continue
                
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                # --- 1. 単純コマンド (STOP, PAUSE等) ---
                if cmd in self.simple_commands:
                    msg, _ = self.simple_commands[cmd]
                    self.client.publish(MQTT_TOPICS["command"], msg)
                    print(f"📤 {msg} 指令送信")

                # --- 2. 引数が必要なコマンド ---
                elif cmd == "start": 
                    if arg:
                        msg = f"START {arg}"
                        self.client.publish(MQTT_TOPICS["command"], msg)
                        print(f"📤 START 指令送信: {arg}")
                    else:
                        print("⚠️ ファイル名を指定してください (例: start test.py)")

                elif cmd == "order":
                    if arg:
                        self.client.publish(MQTT_TOPICS["order"], arg)
                        print(f"📤 ORDER 指令送信: {arg}")
                    else:
                        print("⚠️ 指示内容を入力してください")

                # --- 3. ロボット直接指定 ---
                elif cmd == "kachaka":
                    if arg:
                        msg = f"KACHAKA {arg}"
                        self.client.publish(MQTT_TOPICS["command"], msg)
                        print(f"📤 KACHAKAへ送信: {arg}")
                    else:
                        print("⚠️ コマンドを指定してください (例: kachaka speak test)")
                
                elif cmd == "akari": 
                    if arg:
                        msg = f"AKARI {arg}"
                        self.client.publish(MQTT_TOPICS["command"], msg)
                        print(f"📤 AKARIへ送信: {arg}")
                    else:
                        print("⚠️ コマンドを指定してください (例: akari move_home)")

                # --- 4. その他 ---
                elif cmd == "help":
                    self._show_help()
                
                elif cmd == "exit":
                    break

                else:
                    # そのままステータスとして送信
                    self.client.publish(MQTT_TOPICS["status"], user_input)
                    print(f"📤 ステータス送信: {user_input}")

            except EOFError:
                break

if __name__ == "__main__":
    controller = RobotRemoteController(MQTT_BROKER)
    controller.start()