"""
    config.py
    システム全体の設定ファイル
"""
import os

# ==========================================
#  ファイルパスの自動設定
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_path(*args):
    return os.path.join(BASE_DIR, *args)





# ==========================================
# OpenAI (LLM) 設定
# ==========================================
# 使用するAIモデルの名前
OPENAI_MODEL = "gpt-4o"

# AIの「創造性」を決めるパラメータ（0.0〜2.0）
# 0に近いほど毎回同じ答え、大きいほどランダム性が増します。
OPENAI_TEMPERATURE = 1.0

# --- プロンプト（AIへの指令書）のファイルパス ---
PROMPTS = {
    # 行動計画生成用のプロンプト
    "task": get_path("_LLM", "prompt", "re_create_task_en.json"),
    # 会話生成用のプロンプト
    "talk": get_path("_LLM", "prompt", "re_create_talk_en.json"),
}

# --- ログファイルの保存先 ---
LOGS = {
    "task":  get_path("_LLM", "log", "task_log.txt"),   # 行動計画の履歴
    "talk":  get_path("_LLM", "log", "talk_log.txt"),   # 会話の履歴
    "token": get_path("_LLM", "log", "token_log.txt"),  # 課金計算用のトークン使用量
}

# --- 生成されたPythonスクリプトの保存先 ---
# LLMが生成した「行動計画スクリプト」の一時保存先
LLM_TASK_SCRIPT_PATH = get_path("_robot_programs", "llm_task.txt")

# 最終的に実行される「会話付きスクリプト」の保存先
LLM_FINAL_SCRIPT_PATH = get_path("_robot_programs", "llm_final.txt")





# ==========================================
#  MQTT接続設定
# ==========================================
# MQTTブローカー（サーバー）のアドレス
# ローカルPCでmosquittoなどを動かしている場合は "localhost"
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# --- トピック（通信チャンネル）の定義 ---
# ロボットへの指示や状態確認に使うトピック名です。
MQTT_TOPICS = {
    "command": "command/robot1",  # 指示を送る
    "status":  "status/robot1",   # 状態を受け取る
    "return":  "return/robot1",   # 完了報告を受け取る
    "order":   "order/robot1",    # 注文情報など
}





# ==========================================
#  ロボット設定
# ==========================================
# 各ロボットのIPアドレスや、場所の名前（ID）を定義します。
ROBOTS = {
    # --- Kachaka (移動ロボット) の設定 ---
    "kachaka": {
        # Kachaka APIへの接続アドレス
        "address": "172.31.14.25:26400",
        
        # 音量の初期値
        "default_volume": 7,

        "error_codes": {
            # 安全機能による停止 -> 一時停止扱いにしたいもの
            "safety": {
                11005, # 障害物検知? (Obstacle detected)
                11009, # 経路なし? (No path found)
                22002  # 衝突防止? (Collision avoidance)
            },
            # ユーザー指示によるキャンセル -> エラーとして扱わないもの
            "interrupt": {
                10001  # キャンセルコマンド (Command cancelled)
            }
        },
        
        # --- 場所定義 (Locations) ---
        "locations": {
            # 家具・棚 (Shelves) - Kachakaが潜り込める家具
            "akari_shelf": "S02",      # ID: S02 (名前: Akari搭載用シェルフ)
            "obstacle_shelf": "S03",   # ID: S03 (名前: 障害物) - ドッキング練習用
            "arm_robot": "S04",        # ID: S04 (名前: アームロボット)
            
            # 場所 (Locations) - 移動目的地
            "fridge": "L01",           # ID: L01 (名前: 冷蔵庫)
            "dining": "L02",           # ID: L02 (名前: ダイニング)
            "living": "L03",           # ID: L03 (名前: リビング)
            "evacuation": "L04",       # ID: L04 (名前: 避難場所)
            "obstacle_area": "L05",    # ID: L05 (名前: 障害物置き場)
            
            "charger": "home",         # 充電ドック
        }
    },

    # --- Akari (卓上ロボット) の設定 ---
    "akari": {
        # Akari本体のIPアドレス
        "address": "172.31.14.45",
        
        # M5Stack（Akariに接続された制御マイコン）のアドレス
        # gRPC通信などで使用します
        "m5_address": "172.31.14.45:51001",

        # Akari専用のトピック
        "topics": {
            "chat": "chat/message",   # Akariに喋らせる内容を送る
            "result": "akari/result"  # Akariの動作完了通知
        }
    }
}