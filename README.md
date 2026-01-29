# LLM-Interrupt-System2026
## プロジェクト名

山本研究室（知的制御研究室）LLMチーム2026卒業研究制作物

## ディレクトリ構成

### 📂 ルートディレクトリ
システムを実行するためのメインスクリプトと設定ファイル群です。

| ファイル名 | 説明 |
|------------|------|
| `manager.py` | **【操作用】** ユーザーがコマンドを入力し、ロボットへ指令を送る送信機プログラム |
| `robots_client.py` | **【ロボット用】** ロボット側で動作し、指令を受け取ってタスクを実行する受信機プログラム |
| `config.py` | IPアドレス、APIキー、ファイルパスなどのシステム全体設定 |
| `robot_api_manager.py` | KachakaとAkariの接続・初期化を管理するシングルトンクラス |
| `requirements.txt` | 必要なPythonライブラリの一覧 |
| `akari_mqtt_subscriber.py` | **⚠️【Akari本体用（制御PC内では扱いません）】** Akari内部で動作し、MQTT経由で発話や制御コマンドを受け取る常駐プログラム |
| `speak_audio.py` | **⚠️【Akari本体用（制御PC内では扱いません）】** Google Cloud TTSを使用した音声合成・再生機能を提供するモジュール（上記で使用） |

---

### 📂 `_LLM/` (LLM制御・生成ロジック)
LLM（ChatGPT）との通信、プロンプト管理、ログ保存を行うモジュール群です。

| ファイル名 | 説明 |
|------------|------|
| `LLM_manager.py` | OpenAI API通信、ログ保存、トークン計算を行う共通機能 |
| `task_generate.py` | ユーザー指示から「行動計画（Pythonコード）」を生成するスクリプト |
| `talk_generate.py` | 行動計画に基づき「ロボットの発話内容」を生成するスクリプト |

#### 📂 `_LLM/prompt/` (プロンプト定義)
LLMへの指示書（システムプロンプト）が格納されています。
本システムでは主に以下の **_en.json** ファイルを使用します。

| ファイル名 | 説明 |
|------------|------|
| `re_create_task_en.json` | **【行動生成用】** ユーザーの指示をPythonコード（移動・運搬）に変換するためのプロンプト |
| `re_create_talk_en.json` | **【会話生成用】** 生成された行動に合わせて、ロボットが話す内容を生成するためのプロンプト |

#### 📂 `_LLM/log/` (実行ログ)
システムの実行履歴やコスト管理用のログファイルです。

| ファイル名 | 説明 |
|------------|------|
| `task_log.txt` | LLMが生成した「行動計画スクリプト」の履歴 |
| `talk_log.txt` | LLMが生成した「会話スクリプト」の履歴 |
| `token_log.txt` | OpenAI APIのトークン使用量と概算コストの記録 |

---

### 📂 `_robot_function/` (ロボット制御定義)
各ロボットの具体的な動作メソッドを定義したライブラリです。

| ファイル名 | 説明 |
|------------|------|
| `function_list_kachaka.py` | Kachaka用機能（移動、棚運び、発話、ガード処理） |
| `function_list_akari.py` | Akari用機能（M5Stack表情、首振り、発話） |

### 📂 `_robot_programs/` (生成コード保存先)
LLMによって自動生成されたスクリプトが保存されます。

| ファイル名 | 説明 |
|------------|------|
| `llm_task.txt` | 一時的に生成された行動計画スクリプト（会話生成の入力として使用） |
| `llm_final.txt` | 会話文が付与された、最終的に実行されるスクリプト |

---

## 主要スクリプトの詳細

### 1. `manager.py` (指令用)
ユーザーがPCのターミナルからロボットに命令を送るためのインターフェースです。
MQTTブローカーを介して `robots_client.py` と通信します。

**主なコマンド:**
- **基本操作**
    - `order <指示内容>` : LLMに行動生成を依頼します
    - `start <ファイル名>` : 指定したタスクファイルを実行します
- **実行制御・割り込み**
    - `stop` : 全ロボットを緊急停止します
    - `pause` : 実行中のタスクを一時停止します
    - `resume` : 一時停止したタスクを再開します
    - `skip` : 現在実行中のアクションをスキップします
    - `reset` : ロボットの状態やフラグをリセットします
- **直接操作**
    - `kachaka <コマンド>` / `akari <コマンド>` : 各ロボットの機能を直接実行します

### 2. `robots_client.py` (実行用)
ロボットを制御するPC上で常駐させるメインプログラムです。
`manager.py` からの指令を待ち受け、以下の処理を行います。
1. **LLM生成**: `_LLM/prompt/re_create_task_en.json` 等を使用してコードを生成
2. **動的実行**: `_robot_programs/llm_final.txt` を読み込み、ロボット実機を制御
3. **割り込み制御**: 実行中のタスクに対して、STOP, PAUSE等の割り込み処理を優先的に実行

---

## 使用方法

### 必要な環境
- Python 3.10 以上推奨
- OpenAI API Key (GPT-4o利用のため)
- MQTTブローカー (Mosquitto等が稼働していること)
- `requirements.txt` に記載されたライブラリ

### セットアップ手順

1. **ライブラリのインストール**
   ```bash
   pip install -r requirements.txt
   ```

2. **OpenAI APIキーの設定**
   システムはGPT-4oを使用するため、APIキーが必要です。環境変数として設定してください。（APIキーは研究室のデスクトップPC内に保存）

   Mac/Linux:

   ```bash
   export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
   ```
   
### ⚠️ 重要：ネットワーク設定とIPアドレス
本システムはWi-Fiまたは有線LANを介して通信します。
通信エラーを防ぐため、以下の設定を確認してください。

#### 1. 推奨ネットワーク環境
* **Akari本体 (AKARI-PC)** は、実行確認をする場合には **有線LAN接続** で運用することを推奨します。
    * 無線接続の場合、IPアドレスの変動や通信断絶により、Akariの制御が不能になるリスクが高まります。

#### 2. IPアドレスの整合性チェック
実行前に、以下のアドレス設定が現在のネットワーク環境と一致しているか確認してください。

**① Akari側のMQTT設定確認**
Akari本体内にある `akari_mqtt_subscriber.py` を開き、以下の変数が正しいアドレスになっているか確認してください。
```python
# akari_mqtt_subscriber.py 内
BROKER_ADDRESS = "XXX.XX.XX.XX"
```

**② システム設定ファイル (Akari) の確認**
本システムの config.py を開き、AkariのIPアドレスが **①のアドレス** と一致しているか確認してください。
```python
# config.py 内
ROBOTS = {
    "akari": {
        "address": "XXX.XX.XX.XX",
        # ...
    }
}
```

**③ システム設定ファイル (Kachaka) の確認**
同様に config.py 内で、KachakaのAPI接続アドレスが正しいか確認してください。
```python
# config.py 内
ROBOTS = {
    "kachaka": {
        "address": "XXX.XX.XX.XX:XXXXX",
        # ...
    }
}
```

### 実行手順

**1. ロボットクライアントの起動 (受信側)**
ロボットを制御するPCで実行します。

```bash
python robots_client.py
```

**2. マネージャーの起動 (送信側)**
別のターミナルで実行します。

```bash
python manager.py
```

**3. Akari側の準備**
本システムを実行する前に、**Akari本体のPC（内部Linux）** でMQTT受信プログラムを起動しておく必要があります。
これを行わないと、Akariへの指示（発話や表情制御）が反映されません。

Akari PCで以下のコマンドを実行し、待機状態にしてください。

```bash
cd AKARI_llm
source /home/aitclab2011/AKARI_llm/venv_grpc/bin/activate
/bin/python /home/aitclab2011/AKARI_llm/akari_mqtt_subscriber.py
```

**4. 指示の入力**
`manager.py` を実行しているターミナルで、`order` コマンドに続けて実行したいユーザータスクを入力します。

```bash
🧑 指令入力 > order AKARIを冷蔵庫に連れてって
```
