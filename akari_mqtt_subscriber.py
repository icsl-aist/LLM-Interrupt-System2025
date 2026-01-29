#有線接続と無線だとアドレス変わるよ

import paho.mqtt.client as mqtt
import asyncio
import speak_audio

import socket # ネットワーク監視用

# MQTTブローカーのアドレスとポート
BROKER_ADDRESS = "172.31.14.45" 
#BROKER_ADDRESS = "172.31.14.46"
BROKER_PORT = 1883

# 購読するトピック名
#TOPIC = "return/robot1"
TOPIC = "chat/message"
STATUS_TOPIC = "akari/result"

# メッセージを非同期に処理するためのキュー
message_queue = asyncio.Queue()

# メインのasyncioイベントループへの参照を保持する変数
main_event_loop = None

# プログラム終了を通知するためのイベントオブジェクト
shutdown_event = asyncio.Event()

MQTT_KEEP_ALIVE_INTERVAL = 30

client = None

disconnect_in_progress = False

def send_message(msg):
    client.publish(STATUS_TOPIC,msg)
    print(f"{msg}を送りました")

# ブローカーに接続したときに呼び出されるコールバック関数
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected to MQTT broker with result code {rc}")
    if rc == 0:
        client.subscribe(TOPIC)
        print(f"Subscribed to topic: '{TOPIC}'")
    else:
        print(f"Failed to connect, return code {rc}")

# ブローカーから切断されたときに呼び出されるコールバック関数
# CallbackAPIVersion.VERSION2 の場合、on_disconnect は 5つの引数を受け取ります。
def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
    global disconnect_in_progress # グローバル変数を変更するために必要
    print(disconnect_in_progress)

    # 既に切断処理が進行中の場合は、何もしない
    if disconnect_in_progress:
        print("\CID{129} on_disconnectが多重に呼び出されましたが、既に処理中です。")
        return

    disconnect_in_progress = True # 処理開始をマーク
    print(disconnect_in_progress)

    # 正常な切断かを判断するフラグを初期化
    is_normal_disconnect = False

    try:

        # propertiesオブジェクトが提供されていて、その文字列表現に「Normal disconnection」が含まれる場合
        if properties and "Normal disconnection" in str(properties):
            is_normal_disconnect = True
        # または、rcがmqtt.ReasonCodeのインスタンスで、それがNORMAL_DISCONNECTIONの場合
        elif isinstance(rc, mqtt.ReasonCode) and rc == mqtt.ReasonCode.NORMAL_DISCONNECTION:
            is_normal_disconnect = True
        # 古い形式でrcが直接0の場合もカバー
        elif rc == 0:
            is_normal_disconnect = True

        if is_normal_disconnect:
            print("MQTTブローカーから正常に切断されました。")
        else:
            print(f"\CID{220} MQTT接続が予期せず切断されました。 (Result Code: {rc})")
            # 詳細情報があれば表示
            if properties:
                print(f"  Properties: {properties}")
                # properties に reasonCode がある場合は、それを表示
                if hasattr(properties, 'reasonCode') and isinstance(properties.reasonCode, mqtt.ReasonCode):
                    print(f"    Reason Code Details: {properties.reasonCode.getName()} ({properties.reasonCode.value})")
            if reason_code is not None:
                print(f"  Additional Info: {reason_code}")
            if main_event_loop: # メインイベントループへの参照があることを確認
                print("\CID{2047} 予期せぬ切断を検知しました。音声再生を停止します。")
                try:
                    # asyncio.create_task を asyncio.run_coroutine_threadsafe に変更
                    asyncio.run_coroutine_threadsafe(speak_audio.stop_speaking(), main_event_loop)
                except Exception as e:
                    print(f"\UTF{274C} speak_audio.stop_speaking()の実行中にエラーが発生しました: {e}")
            else:
                print("\UTF{274C} エラー: メインイベントループが設定されていません。音声停止をスキップします。")

    finally:
        disconnect_in_progress = False


# メッセージを受信したときのコールバック関数
def on_message(client, userdata, msg):
    message_payload = msg.payload.decode('utf-8')
    print(f"トピック上でメッセージを受信した '{msg.topic}': {message_payload}")
    
    if main_event_loop:
        asyncio.run_coroutine_threadsafe(message_queue.put((msg.topic, message_payload)), main_event_loop)
    else:
        print("\UTF{274C}　ERROR")

# ネットワーク状態監視用フラグ
is_network_available = asyncio.Event() # ネットワークが利用可能ならsetされる

# ネットワーク監視タスク
# ネットワーク監視タスク
async def network_watcher(host="172.31.14.45", port=1883, check_interval=0.1): # チェック間隔を短く
    print(f"ネットワーク監視を開始します ({host}:{port}, 間隔: {check_interval}秒)")
    # 連続して失敗するしきい値 (例: 2回連続で失敗したらオフラインと判断)
    fail_threshold = 2
    consecutive_failures = 0

    while True:
        reader = None
        writer = None
        try:
            # TCP接続を試みる方法 (最もシンプルでMQTTの状況に近い)
            reader, writer = await asyncio.open_connection(host, port)
            
            # 接続が成功したら、すぐにクローズ
            writer.close()
            await writer.wait_closed() # writerが閉じるのを待つ

            # readerにはclose()もwait_closed()も不要。writerが閉じればソケットは閉じられる。

            if not is_network_available.is_set():
                print("\UTF{2705} ネットワーク接続が回復しました。")
                is_network_available.set()
                consecutive_failures = 0 # 成功したらリセット

        except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
            consecutive_failures += 1
            if consecutive_failures >= fail_threshold:
                if is_network_available.is_set():
                    print(f"\UTF{274C} ネットワーク接続が失われました ({e})。発話を停止します。")
                    if main_event_loop:
                        try:
                            asyncio.run_coroutine_threadsafe(speak_audio.stop_speaking(), main_event_loop)
                        except Exception as stop_e:
                            print(f"\UTF{274C} speak_audio.stop_speaking()の実行中にエラーが発生しました: {stop_e}")
                    is_network_available.clear() # ネットワーク利用不可状態にセット
            # else: まだ失敗しきい値に達していない場合は何もせず待つ

        except Exception as e:
            # このブロックに来ることは稀ですが、デバッグのために残します
            print(f"\CID{220} ネットワーク監視中に予期せぬエラー: {e}")
            consecutive_failures += 1 # エラーも失敗としてカウント

        finally:
            # 念のため、writerが残っていたら閉じる（上記tryブロックで閉じているが、安全のため）
            if writer:
                writer.close()
                # await writer.wait_closed() は、finallyブロック内だと既に閉じられている場合があるため省略

        await asyncio.sleep(check_interval) # 設定された間隔でチェック


# メッセージキューからメッセージを取り出して処理する非同期タスク
async def message_processor():
    print("メッセージの処理を始めます")
    result = None
    while True:
        try:
            # タイムアウトを設定し、一定時間ごとにシャットダウンイベントをチェックできるようにする
            topic, message = await asyncio.wait_for(message_queue.get(), timeout=1.0) # 1秒ごとにチェック
        except asyncio.TimeoutError:
            continue # タイムアウトしたら再度ループの先頭

        print(f"トピックからのメッセージを処理中'{topic}': {message}")

        if message.startswith("speak "):
            text_to_speak = message[len("speak "):].strip()
            if text_to_speak:
                print(f"\CID{2047} 音声再生リクエストを受信: '{text_to_speak}'")
                # send_message(f"akari_mqtt_subscriber.py -> \CID{2047} 音声再生リクエストを受信: '{text_to_speak}'")
                try:
                    asyncio.create_task(speak_audio.synthesize_speech_from_mqtt(text_to_speak))
                except Exception as e:
                    print(f"\UTF{274C} speak_audio関数の実行中にエラーが発生しました: {e}")
                    send_message(f"akari_mqtt_subscriber.py -> \UTF{274C} speak_audio関数の実行中にエラーが発生しました: {e}")
            else:
                print("\CID{220} 'speak:' の後に再生するテキストがありません。")
                send_message("akari_mqtt_subscriber.py -> \CID{220} 'speak:' の後に再生するテキストがありません。")
                
        if message.startswith("chat_bot"):
            print("chat_botです")
            send_message(4)
            
        
        if message.startswith("TimeoutError"):
            asyncio.create_task(speak_audio.stop_speaking(1))

        elif message == "stop" or message == "pause" or message == "skip":
            asyncio.create_task(speak_audio.stop_speaking())

        elif message == "finish":
            print("\CID{1905} 'finish'メッセージを受信しました。akari_mqtt_subscriber.pyを終了します。")    
            send_message("akari_mqtt_subscriber.py -> \CID{1905} 'finish'メッセージを受信しました。akari_mqtt_subscriber.pyを終了します。")
            client.disconnect()
            break # message_processorループを抜ける
        else:
            print(f"通常のメッセージを受信: {message}")
        
        message_queue.task_done()
    
    

async def main():
    global main_event_loop, client
    main_event_loop = asyncio.get_running_loop()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"Connecting to MQTT broker at {BROKER_ADDRESS}:{BROKER_PORT}...")
    client.connect(BROKER_ADDRESS, BROKER_PORT, MQTT_KEEP_ALIVE_INTERVAL) # mqtt接続が切れた際のエラーがでるまでの許容時間

    client.loop_start() 
    # network_monitoring_task = asyncio.create_task(network_watcher(BROKER_ADDRESS, BROKER_PORT))
    
    try:
        await message_processor()
    except asyncio.CancelledError:
        print("Main loop cancelled.")
    except KeyboardInterrupt:
        print("\nSubscriber stopped by user (Ctrl+C).")
        # network_monitoring_task.cancel()
        # await network_monitoring_task
    except BaseException as e:
        send_message(f"akari_mqtt_subscriber.py -> 致命的なエラーが発生しました: {e}")
    finally:
        client.loop_stop()
        # if not network_monitoring_task.done(): # 既に完了/キャンセル済みでなければ
        #      network_monitoring_task.cancel()
        #      try:
        #          await network_monitoring_task
        #      except asyncio.CancelledError:
        #          pass # キャンセルは正常な終了
        print("Disconnected from MQTT broker.")
        

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("プログラムが手動で終了されました。")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally: 
        print("プログラムが正常に終了しました。")
