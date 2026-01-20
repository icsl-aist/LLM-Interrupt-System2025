"""
    robot_api_manager.py
    kachakaとakariの初期化を行う
"""
import asyncio
import grpc
from grpc import StatusCode
import threading

# 既存のKachakaModuleとAkariModuleをインポート
from _robot_function.function_list_kachaka import KachakaModule
from _robot_function.function_list_akari import AkariModule

class RobotAPIManager:
    _instance = None
    _kachaka_client: KachakaModule | None = None
    _akari_client: AkariModule | None = None
    _lock = threading.Lock() # スレッドセーフのためのロック

    def __new__(cls):
        # シングルトンパターンを実装
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(RobotAPIManager, cls).__new__(cls)
                    cls._instance._initialize_clients()
        return cls._instance

    def _initialize_clients(self):
        # Kachakaクライアントの初期化
        try:
            print("☑️  Kachakaクライアントの初期化を実施")
            # 引数なしで初期化（内部でconfig.pyを参照）
            self._kachaka_client = KachakaModule()
            print("✅ Kachakaクライアントを初期化しました。")
        except grpc.aio.AioRpcError as e:
            if e.code() == StatusCode.UNAVAILABLE:
                print("🚫 Kachakaに接続できません（StatusCode.UNAVAILABLE）。IPやネットワークを確認してください。")
            else:
                print(f"❌ gRPC エラー: {e}")
            self._kachaka_client = None 
        except Exception as e:
            print(f"❌ Kachakaクライアントの初期化中に予期せぬエラーが発生しました: {e}")
            self._kachaka_client = None

        # AKARIクライアントの初期化
        try:
            print("☑️  AKARIクライアントの初期化を実施")
            # ★ 引数なしで初期化（内部でconfig.pyを参照）
            self._akari_client = AkariModule()
            print("✅ AKARIクライアントを初期化しました。")
        except Exception as e:
            print(f"❌ AKARIクライアントの初期化中にエラーが発生しました: {e}")
            self._akari_client = None

    def get_kachaka_client(self) -> KachakaModule | None:
        """KachakaModuleのインスタンスを取得します。"""
        if self._kachaka_client is None:
            print("⚠️ Kachakaクライアントが初期化されていません。初期化を試みます。")
            self._initialize_clients() 
        return self._kachaka_client

    def get_akari_client(self) -> AkariModule | None:
        """AkariModuleのインスタンスを取得します。"""
        if self._akari_client is None:
            print("⚠️ AKARIクライアントが初期化されていません。初期化を試みます。")
            self._initialize_clients() 
        return self._akari_client

# シングルトンインスタンスを取得するためのヘルパー関数
def get_robot_api_manager() -> RobotAPIManager:
    return RobotAPIManager()