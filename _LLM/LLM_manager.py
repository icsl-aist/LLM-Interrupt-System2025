"""
    LLM_manager.py
    行動計画生成スクリプト(task_generate.py)と会話文生成スクリプト(talk_generate.py)
    の二つで共通して用いる関数を定義しているプログラム
"""
import openai
import os
import json
import config 
from datetime import datetime

openai.api_key = os.getenv("OPENAI_API_KEY")

def read_file(filepath):
    """ ファイルの内容を読み込む """
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()
 
def read_json(filepath):
    """ JSONファイルの内容を読み込む """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def get_chat_response(prompt, model=config.OPENAI_MODEL, temperature=config.OPENAI_TEMPERATURE):
    """
    ChatGPT APIでpromptを入力して返信を受け取る
    戻り値: (message_object, usage_object) のタプル
    """
    try:
        response = openai.chat.completions.create(
            model = model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature = temperature
        )
        # メッセージ本体と、トークン使用量の両方を返す
        return response.choices[0].message, response.usage
    except Exception as e:
        print(f"❌ OpenAI API Error: {e}")
        return None, None

def save_response_to_file(res, filepath):
    """ 返信の内容を.txtファイルに書いて保存 """
    if res and hasattr(res, 'content'):
        with open(filepath, "w", encoding="utf-8") as f:
            code = res.content.strip()
            code = code.replace("```python\n", "")
            code = code.replace("```", "")
            f.write(code)
    else:
        print("⚠️ Warning: No valid content to save.")

def append_to_script_log(filename, log_filename, max_entries=3):
    """ スクリプトの内容をログに追記 """
    if not os.path.exists(filename):
        return

    with open(filename, "r", encoding="utf-8") as f:
        script_content = f.read().strip()

    entries = []
    if os.path.exists(log_filename):
        with open(log_filename, "r", encoding="utf-8") as f:
            raw = f.read()
            entries = [e.strip() for e in raw.split("============ New Script Entry ============") if e.strip()]

    entries.append(script_content)
    entries = entries[-max_entries:]

    with open(log_filename, "w", encoding="utf-8") as f:
        for i, entry in enumerate(entries):
            if i != 0:
                f.write("\n\n\n\n")
            f.write("============ New Script Entry ============\n\n")
            f.write(entry.strip())

def append_token_usage_log(usage, filepath, model_name=config.OPENAI_MODEL):
    """
    トークン使用量と概算コストをログに記録する
    """
    if usage is None:
        print("⚠️ Token usage data is missing.")
        return

    log_entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens} {model_name}\n"

    total_tokens = 0
    total_prompt = 0
    total_completion = 0
    log_lines = []

    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            log_lines = f.readlines()

        # トークン数計算と重複行削除のための一時リスト
        filtered_lines = []
        prev_line = None

        for line in log_lines:
            # 累積行は除去
            if line.startswith("累積") or line.startswith("推定使用金額"):
                continue

            # 重複チェック
            if line == prev_line:
                continue
            prev_line = line

            filtered_lines.append(line)

            # トークン数抽出
            if "Prompt:" in line and "Completion:" in line and "Total:" in line:
                try:
                    prompt = int(line.split("Prompt:")[1].split(",")[0].strip())
                    completion = int(line.split("Completion:")[1].split(",")[0].strip())
                    total = int(line.split("Total:")[1].split()[0].strip())
                    total_prompt += prompt
                    total_completion += completion
                    total_tokens += total
                except Exception:
                    pass

        log_lines = filtered_lines

    # 新しい値を加算
    total_prompt += usage.prompt_tokens
    total_completion += usage.completion_tokens
    total_tokens += usage.total_tokens

    # 料金計算（gpt-4oの概算レートなどを想定している場合、必要に応じて係数を調整してください）
    cost = (total_prompt * 0.000005 + total_completion * 0.000015)

    # ログを更新
    with open(filepath, "w") as f:
        for line in log_lines:
            f.write(line)
        f.write(log_entry)
        f.write(f"累積トークン数: {total_tokens}\n")
        f.write(f"累積Prompt: {total_prompt}, Completion: {total_completion}\n")
        f.write(f"推定使用金額: {cost*157:.2f} 円\n") # 小数点2桁までに整形