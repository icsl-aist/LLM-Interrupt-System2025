"""
    task_generate.py
    「ユーザータスク」、「ログコンテンツ」に基づいて、
    ChatGPT APIを使用して行動計画を生成し、保存する
"""
import os
import json
import config

from .LLM_manager import ( 
    read_file, read_json, get_chat_response, 
    save_response_to_file,
    append_to_script_log,
    append_token_usage_log
)

def main(user_msg):
    print(f"🤖 [Task Generate] 行動計画の生成を開始します...")

    # ===== 1. プロンプト読み込み =====
    prompt_path = config.PROMPTS["task"]
    ext = os.path.splitext(prompt_path)[1].lower()
    
    try:
        if ext == '.json':
            create_task_prompt = read_json(prompt_path)
            system_prompt_str = json.dumps(create_task_prompt, indent=2, ensure_ascii=False)
        else:
            system_prompt_str = read_file(prompt_path)
    except FileNotFoundError:
        print(f"❌ プロンプトファイルが見つかりません: {prompt_path}")
        return

    # ===== 2. ログコンテンツ =====
    log_path = config.LOGS["task"]
    log_content = "" 
    # if os.path.exists(log_path):
    #     log_content = read_file(log_path)
    
    # ===== 3. プロンプト結合 =====
    combined_prompt = (
        f"{system_prompt_str}\n\n"
        f"### User Task ###\n{user_msg}\n\n"
        f"### Log Content ###\n{log_content}"
    )
    
    # ===== 4. レスポンス取得 =====
    # (res=メッセージ, usage=トークン情報)
    res, usage = get_chat_response(combined_prompt)

    # ===== 5. レスポンス保存 =====
    output_path = config.LLM_TASK_SCRIPT_PATH
    save_response_to_file(res, output_path)

    # ===== 6. ログファイル追記 =====
    append_to_script_log(output_path, log_path)

    # ===== 7. トークンログ記録 =====
    append_token_usage_log(usage, config.LOGS["token"])
    
    print(f"✅ 生成されたスクリプトを保存しました: {output_path}")