""" 
    function_list_akari.py
    Akariが実行できるメソッドを定義しているコード
"""

import asyncio
import paho.mqtt.client as mqtt
from functools import wraps
from akari_client import AkariClient
from akari_client.color import Colors
from akari_client.config import (
    AkariClientConfig,
    JointManagerGrpcConfig,
    M5StackGrpcConfig,
)
from akari_client.position import Positions

# ★ configをインポート
import config

class AkariModule:
    def __init__(self):
        """ Akariクライアントを初期化 """
        # --- Configから設定を読み込み ---
        # Akari PCのアドレス (M5制御には m5_address を使う)
        self.address = config.ROBOTS["akari"]["address"]
        self.m5_address = config.ROBOTS["akari"]["m5_address"]
        
        # MQTT接続設定 (config.pyのMQTT_BROKERを使用)
        # ※もしAkari自身をブローカーにするなら self.address を使うよう書き換えてください
        self.mqtt_broker = config.ROBOTS["akari"]["address"] # ここではAkariPCをブローカーと想定
        self.mqtt_port = config.MQTT_PORT

        # トピック設定
        self.topic_chat = config.ROBOTS["akari"]["topics"]["chat"]
        self.topic_result = config.ROBOTS["akari"]["topics"]["result"]

        # --- タスク管理用変数 ---
        self.pending_task = None       # 一時停止時に中断したタスク情報
        self.current_task = None       # 現在実行中のタスク情報
        self.running_asyncio_task = None # 現在実行中の非同期タスク実体

        # --- 制御フラグ ---
        self.stop_flag = False         # 停止フラグ
        self.pause_event = asyncio.Event()
        self.pause_event.set()         # set=実行可能, clear=一時停止中

        # --- MQTTクライアント設定 (Akari PCとの通信用) ---
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_completion_event = asyncio.Event()
        self.mqtt_completion_event.set()

        try:
            print(f"🚀 MQTTブローカーに接続中 {self.mqtt_broker}:{self.mqtt_port}...")
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start() 
        except Exception as e:
            print(f"❌ AkariModule内部MQTTクライアント接続エラー: {e}")

        # Akariクライアント実体 (initialize_akari_robotで生成)
        self.akari = None


    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("🔌 MQTTブローカーに接続しました -> AKARI PC")
            # Configから取得したトピックを購読
            client.subscribe(self.topic_result)
        else:
            print(f"❌ 接続失敗: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        payload = msg.payload.decode('utf-8')
        print(f"📥 AkariPCから受信: {payload}")
        
        # Configから取得したトピックと比較
        if msg.topic == self.topic_result:
            if payload in ["0", "1", "4"]: # 成功/完了/終了
                print("✅ Akari側の処理完了を受信")
                self.mqtt_completion_event.set()
            elif payload in ["-1", "2"]: # エラー系
                print(f"❌ Akari側エラー受信: {payload}")
                self.mqtt_completion_event.set()

    # =================================================================
    #  1. Wrapper Function (Execution Guard)
    # =================================================================
    def decorated_execution(func):
        """ 実行ガードデコレータ """
        
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            print(f"\n☑️  {func.__name__}: 実行準備")

            # --- {Pre-Execution Phase} ---
            if self.stop_flag:
                print(f"⚠️ {func.__name__} をスキップします（停止フラグが有効）")
                return None

            self.current_task = (func.__name__, args, kwargs)
            self.running_asyncio_task = asyncio.current_task()
            result = None

            # --- {Execution Phase} ---
            try:
                result = await func(self, *args, **kwargs)
            
            except asyncio.CancelledError:
                print(f"⚠️ {func.__name__} がキャンセルされました")
                # Akariの場合、キャンセル時は停止メッセージを送るのが安全
                await self.send_message_to_akari("stop")
                result = None
            
            except Exception as e:
                print(f"❌ {func.__name__} でエラーが発生しました: {e}")
                self.pending_task = None
                await self.send_message_to_akari("finish")
                raise

            finally:
                self.current_task = None
                self.running_asyncio_task = None

            # --- {Post-Execution Phase} ---
            await self.handle_pause_and_recovery()

            return result

        return wrapper

    # =================================================================
    #  2. Recovery Handler
    # =================================================================
    async def handle_pause_and_recovery(self):
        """ 一時停止とリカバリー（再実行）を処理するハンドラ """
        
        if not self.pause_event.is_set():
            print("⏸️  一時停止中... 再開コマンド(RESUME)を待機しています")
            await self.pause_event.wait()
            print("▶️  再開しました")

        if self.pending_task is not None:
            method_name, saved_args, saved_kwargs = self.pending_task
            self.pending_task = None

            print(f"🔁 中断されていたタスク '{method_name}' を再開します...")
            
            method = getattr(self, method_name, None)
            if method:
                # 再実行
                await method(*saved_args, **saved_kwargs)
            else:
                print(f"❌ 再実行しようとしたメソッド '{method_name}' が見つかりません")


    # ========== Akari用関数定義 (デコレータ適用) ==========

    @decorated_execution  
    async def initialize_akari_robot(self):
        """ Akariクライアントの初期化と接続 """
        # Configのm5_addressを使用
        joint_config = JointManagerGrpcConfig(type="grpc", endpoint=self.m5_address, timeout=3.0)
        m5_config = M5StackGrpcConfig(type="grpc", endpoint=self.m5_address, timeout=3.0)
        config = AkariClientConfig(joint_manager=joint_config, m5stack=m5_config)
        self.akari = AkariClient(config)
        return self.akari

    @decorated_execution
    async def get_joint_names(self):
        """ ジョイント名を取得 """
        print("Joint Names:", self.akari.joints.get_joint_names())

    @decorated_execution
    async def get_joint_limits(self):
        """ ジョイントリミットを取得 """
        joint_limits = self.akari.joints.get_joint_limits()
        print("Joint Limits:")
        for joint, lim in joint_limits.items():
            print(f"{joint}: min={lim.min}, max={lim.max}")

    @decorated_execution
    async def move_to_initial_position(self):
        """ 初期位置へ移動 """
        pan_initial = 0.032221462577581406
        tilt_initial = 0.19793184101581573
        limits = self.akari.joints.get_joint_limits()

        if limits['pan'].min <= pan_initial <= limits['pan'].max and \
           limits['tilt'].min <= tilt_initial <= limits['tilt'].max:
            self.akari.joints.disable_all_servo()
            await self._express_emotion('running')
            await self._display_message('running')
            self.akari.joints.set_joint_velocities(pan=10, tilt=8)
            await asyncio.sleep(0.5)
            await asyncio.to_thread(self.akari.joints.move_joint_positions, pan=pan_initial, tilt=tilt_initial, sync=True)
            await self._express_emotion('completed')
            await self._display_message('completed')
            print("Moved to initial position.")
        else:
            await self._express_emotion('error')
            await self._display_message('error')
            print("Initial position is out of joint limits.")

    @decorated_execution
    async def stop_all_tasks(self):
        """ 全タスク停止 """
        try:
            await self._express_emotion('running')
            await self._display_message("Stopping tasks...")
            self.akari.joints.disable_all_servo()
            await self._express_emotion('completed')
            await self._display_message("Tasks stopped")
            print("Tasks stopped.")
        except Exception as e:
            await self._express_emotion('error')
            await self._display_message('Error stopping tasks')
            print(f"Error: {e}")

    @decorated_execution
    async def state_object_akari(self):
        """ 状態取得 """
        try:
            moving = self.akari.joints.get_moving_state()
            return "READY" if all(not m for m in moving.values()) else "RUNNING"
        except:
            return "Dormant"

    @decorated_execution  
    async def chat_bot(self):
        """ チャットボットモード起動 """
        print(f"🤖 AKARI: chat_bot")
        self.mqtt_completion_event.clear()
        
        await self.send_message_to_akari("chat_bot")
        try:
            print("☑️  Akari側の処理待機中...")
            await asyncio.wait_for(self.mqtt_completion_event.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            print("⚠️ タイムアウト: chat_botが指定時間内に応答しませんでした")
            await self.send_message_to_akari("TimeoutError")

    @decorated_execution  
    async def speak_akari(self, message):
        """ 音声発話 """
        print(f"🤖 AKARI: {message}")
        self.mqtt_completion_event.clear()

        await self.send_message_to_akari(f"speak {message}")
        try:
            print("☑️  発話完了待機中...")
            await asyncio.wait_for(self.mqtt_completion_event.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            print("⚠️ タイムアウト: 発話完了メッセージが届きませんでした")
            await self.send_message_to_akari("TimeoutError")

    # --- 内部ヘルパー関数 ---
    async def _express_emotion(self, state):
        colors = {'running': Colors.YELLOW, 'completed': Colors.GREEN, 'error': Colors.RED}
        color = colors.get(state, Colors.WHITE)
        self.akari.m5stack.set_display_color(color)
        asyncio.create_task(self._reset_color(self.akari.m5stack, 10))

    async def _reset_color(self, m5, delay):
        await asyncio.sleep(delay)
        m5.set_display_color(Colors.WHITE)

    async def _display_message(self, state):
        messages = {
            'running': ("実行中", Colors.YELLOW),
            'completed': ("完了", Colors.GREEN),
            'error': ("エラー", Colors.RED)
        }
        if isinstance(state, str) and state not in messages:
            text, back_color = (state, Colors.BLACK)
        else:
            text, back_color = messages.get(state, ("", Colors.BLACK))

        self.akari.m5stack.set_display_text(
            text=text,
            pos_x=Positions.CENTER,
            pos_y=Positions.CENTER,
            size=5,
            text_color=Colors.WHITE,
            back_color=back_color,
            refresh=True,
            sync=True
        )

    # ========== 割り込み制御関数 ==========

    async def stop(self):
        """ Akari停止要求 """
        print("\n⏹️  Akari: 停止(STOP)要求を受信しました")
        
        # Akari PCへ停止信号送信
        await self.send_message_to_akari("stop")

        self.stop_flag = True
        self.pause_event.set() # 停止時は一時停止待ちを解除
        self.pending_task = None
        
        if self.running_asyncio_task:
             self.running_asyncio_task.cancel()

    async def pause(self):
        """ Akari一時停止要求 """
        if self.stop_flag:
            print("⛔ Akari: 停止中のためPAUSEは無視します")
            return
        
        if not self.pause_event.is_set():
            print("⚠️ Akari: 既に一時停止中です")
            return
        
        self.pause_event.clear()
        print("\n⏸️  Akari: 一時停止(PAUSE)要求を受信しました")

        # 現在のタスクを保存
        if self.current_task and self.pending_task is None:
            self.pending_task = self.current_task
            print(f"📌 Akari: タスクを保存しました: {self.pending_task[0]}")
            
            # Akari PCへ一時停止信号送信
            await self.send_message_to_akari("pause")
            
            # タスクキャンセル
            if self.running_asyncio_task:
                 self.running_asyncio_task.cancel()

    async def resume(self):
        """ 再開要求 """
        print("▶️  Akari: 再開(RESUME)要求を受信しました")
        self.stop_flag = False
        self.pause_event.set() # 待機解除

    async def skip(self):
        """ スキップ要求 """
        print("⏭️  Akari: スキップ(SKIP)要求を受信しました")
        self.stop_flag = False
        self.pause_event.set() 

        if self.current_task:
            await self.send_message_to_akari("skip")
            if self.running_asyncio_task:
                self.running_asyncio_task.cancel()

    async def reset(self):
        """ リセット要求 """
        print("🔁 Akari: リセット(RESET)要求を受信しました")
        self.stop_flag = False 
        self.pending_task = None 
        self.current_task = None  
        self.pause_event.set()
    
    async def send_message_to_akari(self, message: str):
        """ MQTTメッセージ送信ヘルパー """
        if self.mqtt_client.is_connected():
            # Configからトピックを取得して送信
            self.mqtt_client.publish(self.topic_chat, message)
            print(f"📤 Akari送信: '{message}'")
        else:
            print("❌ MQTT未接続のため送信できません")