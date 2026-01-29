import os
import sys
import numpy as np
import sounddevice as sd
from google.cloud import texttospeech
import asyncio
import datetime
from google.api_core import exceptions

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/xxxxxxxxxxx" 
INTERRUPT_FILE = "/home/aitclab2011/AKARI_LLM/interrupt.flag" # 割り込みフラグファイルのパス
RATE = 24000 # サンプリングレート　
PITCH = 0
SPEAKING_RATE = 1

TIMEOUT = 5 # 音声変換のタイムアウト時間

SAVE_DIR = "/home/aitclab2011/AKARI_LLM/"
TEXT_LOG_FILE = os.path.join(SAVE_DIR, "log_te" "axt.txt")

# 発話中かどうかを示すフラグ
_is_speaking = False
stop_speak_flag = False

timeout_flag = False

# 音声合成を行う非同期関数
async def synthesize_speech(text, speaking_rate=SPEAKING_RATE):
    global _is_speaking, stop_speak_flag
    _is_speaking = True # 発話開始時にフラグを立てる
    stop_speak_flag = False

    # Google Cloud Text-to-Speech のクライアントを作成
    client = texttospeech.TextToSpeechClient()

    # 入力テキストを指定（読み上げたい文章）
    input_text = texttospeech.SynthesisInput(text=text)

    # 音声設定（日本語・話者「ja-JP-Wavenet-A」）
    voice = texttospeech.VoiceSelectionParams(
        language_code="ja-JP",  # 日本語を指定
        name="ja-JP-Wavenet-A"  # 特定の日本語話者を選択
    )

    # 音声出力の設定（LINEAR16形式、話す速さを指定）
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,  # 無圧縮PCM形式
        speaking_rate=speaking_rate,  # 話すスピード（1.0が標準）
    )

    # 音声合成リクエストを送信し、レスポンス（音声データ）を取得
    response = client.synthesize_speech(
        input=input_text,
        voice=voice,
        audio_config=audio_config
    )

    # 音声データが空であればエラーメッセージを表示して終了
    if not response.audio_content:
        print("音声が生成されませんでした")
        _is_speaking = False # 発話終了
        return
    
    # 音声を再生
    print("\UTF{2713} 音声再生を開始します")
    result = await play_audio(response.audio_content)
    if result == 0:
        print("\UTF{2705} 音声再生が正常に完了しました")
    elif result == 1:
        print("\CID{1931} stop命令により強制終了しました")
    else:
        print("\UTF{274C} speak_audio.py -> 異常な終了をしました1")
    _is_speaking = False # 発話終了時にフラグを下ろす
    stop_speak_flag = False
    return result

from google.api_core import exceptions
import time

async def synthesize_speech_2(text, speaking_rate=SPEAKING_RATE, max_retries = 3):
    global _is_speaking, stop_speak_flag
    _is_speaking = True # 発話開始時にフラグを立てる
    stop_speak_flag = False

    try:
        # Google Cloud Text-to-Speech のクライアントを作成
        client = texttospeech.TextToSpeechClient()

        # 入力テキストを指定（読み上げたい文章）
        input_text = texttospeech.SynthesisInput(text=text)

        # 音声設定（日本語・話者「ja-JP-Wavenet-A」）
        voice = texttospeech.VoiceSelectionParams(
            language_code="ja-JP",  # 日本語を指定
            name="ja-JP-Wavenet-A"  # 特定の日本語話者を選択
        )

        # 音声出力の設定（LINEAR16形式、話す速さを指定）
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,  # 無圧縮PCM形式
            speaking_rate=speaking_rate,  # 話すスピード（1.0が標準）
            sample_rate_hertz=RATE,
            pitch=PITCH,
        )

        # 音声合成リクエストを送信し、レスポンス（音声データ）を取得
        response = client.synthesize_speech(
            input=input_text,
            voice=voice,
            audio_config=audio_config,
            timeout=TIMEOUT,
        )

        # 音声データが空であればエラーメッセージを表示して終了
        if not response.audio_content:
            print("音声が生成されませんでした")
            _is_speaking = False # 発話終了
            return 2
        
    
    except exceptions.DeadlineExceeded:
        # タイムアウトした場合
        print(f"\UTF{26A0} 音声変換の際にタイムアウトしました ({TIMEOUT}秒)")
        return -1 
    except Exception as e:
        print(f"\UTF{274C} speak_audio.py -> error: {e}")
        return 2
    
        
    # 音声を再生
    print("\UTF{2713} 音声再生を開始します")
    result = await play_audio(response.audio_content)
    if result == 0:
        print("\UTF{2705} 音声再生が正常に完了しました")
    elif result == 1:
        print("\CID{1931} stop命令により強制終了しました")
    elif result == -1:
        print("● timeoutError")
        return("timeout -> 強制終了しました")
    else:
        print("\UTF{274C} speak_audio.py -> 異常な終了をしました")
    _is_speaking = False # 発話終了時にフラグを下ろす
    stop_speak_flag = False
    return result



async def synthesize_speech_from_mqtt(text):
    result = await synthesize_speech_2(text)
    import __main__  # 呼び出し元のスクリプトから send_message を取る
    __main__.send_message(result)



async def play_audio(audio_content, chunk_size=1024):
    global stop_speak_flag
    global timeout_flag
    audio_np = np.frombuffer(audio_content, dtype=np.int16)
    
    with sd.OutputStream(samplerate=RATE, channels=1, dtype='int16') as stream:
        pos = 0
        while pos < len(audio_np):
            # 割り込みファイルが存在するかチェック
            if timeout_flag:
                _is_speaking = False
                timeout_flag = False
                return -1
            if stop_speak_flag:
                _is_speaking = False
                return 1 # 再生中断して戻る

            chunk = audio_np[pos:pos + chunk_size]
            stream.write(chunk)
            await asyncio.sleep(0) # 他のasyncioタスクに制御を渡す
            pos += chunk_size

        sd.wait() # 再生が完了するまで待機
    
    return 0



async def stop_speaking(timeout=None):
    """
    現在発話中の音声があれば、それを停止するための関数。
    割り込みフラグファイルを生成することで、play_audio関数に停止を指示します。
    """
    global stop_speak_flag
    global timeout_flag

    if timeout is not None:
        timeout_flag = True

    if _is_speaking:
        stop_speak_flag = True
        print("\CID{2452} ストップフラグを立てました")
    else:
        print("\UTF{274C} 現在発話中の音声はありません。")

# 以下はspeak_audio.pyを直接実行した場合のテスト用コードなので、
# 他のスクリプトからimportして使う場合はコメントアウトまたは削除してください。
async def main():
    if len(sys.argv) < 2:
        text = "こんにちは、AKARIです。これはテストの長い文章です。"
    else:
        text = " ".join(sys.argv[1:])
    
    await synthesize_speech_2(text) # 通常の発話テスト

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが停止されました。")
