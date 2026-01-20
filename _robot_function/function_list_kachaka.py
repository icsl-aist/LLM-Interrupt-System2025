"""
    function_list_kachaka.py
    Kachakaが実行できるメソッドを定義しているコード
"""

import asyncio
import kachaka_api
from functools import wraps
import math
import config

class KachakaModule:
    def __init__(self):
        """ Kachakaクライアントを初期化 """
        address = config.ROBOTS["kachaka"]["address"]
        print(f"KachakaModule_address: {address}")
        self.stub = kachaka_api.aio.KachakaApiClient(address)
        self.client = self.stub

        # --- タスク管理用変数 ---
        self.pending_task = None       # 一時停止時に中断したタスク情報 (func_name, args, kwargs)
        self.current_task = None       # 現在実行中のタスク情報 (func_name, args, kwargs)
        self.running_asyncio_task = None # 現在実行中の非同期タスク実体

        # --- 制御フラグ ---
        self.stop_flag = False         # 停止フラグ (Trueなら実行しない)
        self.pause_event = asyncio.Event()
        self.pause_event.set()         # set=実行可能, clear=一時停止中

        # --- 設定値 ---
        self.starting_volume = config.ROBOTS["kachaka"]["default_volume"]

        # --- エラーコード定義 ---
        self.safety_error = config.ROBOTS["kachaka"]["error_codes"]["safety"]
        self.interrupt_error = config.ROBOTS["kachaka"]["error_codes"]["interrupt"]

    # =================================================================
    #  1. Wrapper Function (Execution Guard)
    # =================================================================
    def decorated_execution(func):
        """ 実行ガードデコレータ """
        
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            print(f"\n☑️  {func.__name__}: 実行準備")

            # --- {Pre-Execution Phase} ---
            # 停止フラグが立っている場合は実行をスキップ
            if self.stop_flag:
                print(f"⚠️ {func.__name__} をスキップします（停止フラグが有効）")
                return None

            # 現在実行中のタスク情報を保存 (中断時の復帰用)
            self.current_task = (func.__name__, args, kwargs)
            self.running_asyncio_task = asyncio.current_task()

            result = None

            # --- {Execution Phase} ---
            try:
                # 関数を実行
                result = await func(self, *args, **kwargs)
            
            except asyncio.CancelledError:
                # キャンセル（割り込み）発生時の処理
                print(f"⚠️ {func.__name__} がキャンセルされました")
                await self.cancel_command()
                result = None
            
            except Exception as e:
                # 予期せぬエラーの処理
                print(f"❌ {func.__name__} でエラーが発生しました: {e}")
                self.pending_task = None # エラー時は再開情報を破棄
                raise

            finally:
                # 実行終了後の後処理 (タスク情報のクリア)
                self.current_task = None
                self.running_asyncio_task = None

            # --- {Post-Execution Phase} ---
            # 一時停止・回復処理の確認
            await self.handle_pause_and_recovery()

            return result

        return wrapper

    # =================================================================
    #  2. Recovery Handler
    # =================================================================
    async def handle_pause_and_recovery(self):
        """ 一時停止とリカバリー（再実行）を処理するハンドラ """
        
        # 一時停止フラグが解除されるまで待機
        if not self.pause_event.is_set():
            print("⏸️  一時停止中... 再開コマンド(RESUME)を待機しています")
            await self.pause_event.wait()
            print("▶️  再開しました")

        # 中断されたタスクがある場合は再実行
        if self.pending_task is not None:
            # 保存されたタスク情報を取得
            method_name, saved_args, saved_kwargs = self.pending_task
            
            # ペンディング情報をクリア
            self.pending_task = None

            print(f"🔁 中断されていたタスク '{method_name}' を再開します...")
            
            # メソッドの取得と実行
            method = getattr(self, method_name, None)
            if method:
                # 再帰的にタスクを再実行 (ここでも decorated_execution が呼ばれる)
                await method(*saved_args, **saved_kwargs)
            else:
                print(f"❌ 再実行しようとしたメソッド '{method_name}' が見つかりません")


    # ==========  Kachaka用関数定義 (デコレータ適用)  ==========

    @decorated_execution
    async def get_kachaka_situation(self):
        """ Kachakaのシリアル番号とソフトウェアバージョンを取得 """
        serial_number = await self.client.get_robot_serial_number()
        print(f"シリアル番号: {serial_number}")
        version = await self.client.get_robot_version()
        print(f"ソフトウェアバージョン: {version}")

    @decorated_execution
    async def get_id(self):
        """ 登録されている家具（棚）の情報を取得"""
        return await self.client.get_shelves()

    @decorated_execution
    async def get_location(self):
        """ 登録されているロケーションの情報を取得 """
        return await self.client.get_locations()
    
    @decorated_execution
    async def stop_task_kachaka(self):
        """ ロボットタスクを停止 """
        await self.stop()
    
    @decorated_execution
    async def show_things(self):
        """ 登録されている家具とロケーションを表示 """
        shelves = await self.get_id()
        locations = await self.get_location()
        print(shelves, locations)
    
    @decorated_execution
    async def get_locations_kachaka(self):
        """ Kachakaに登録されているロケーションの座標情報を取得"""
        locations = await self.client.get_locations()
        xyz_coordinates = []
        for location in locations:
            pose = location.pose
            if pose:
                coordinates = {
                    'id': location.id,
                    'name': location.name,
                    'x': pose.x,
                    'y': pose.y,
                    'z': getattr(pose, 'z', None)
                }
                xyz_coordinates.append(coordinates)
        return xyz_coordinates

    @decorated_execution
    async def docking_akari(self):
        """ KachakaをAkariの初期位置にドッキング"""
        shelf_id = config.ROBOTS["kachaka"]["locations"]["obstacle_shelf"] # 障害物 "S03"
        shelf_home_id = config.ROBOTS["kachaka"]["locations"]["living"] # リビング "L03"
        print(f"shelf_homeid = {shelf_home_id}, shelf_id = {shelf_id}")

        # キャッシュ更新用
        await self.client.get_locations()
        await self.client.get_shelves()

        dis = await self.get_dist("障害物") 
        dis_home = await self.get_dist("リビング", "障害物")
        
        # 距離計算が失敗した場合のガード
        if dis is None: dis = 0
        if dis_home is None: dis_home = 0
        
        total_dist = dis + dis_home
        timeout = await self.moving_timeout(total_dist, "docking")
        result = None

        try:
            move_shelf_task = self.client.move_shelf(shelf_id, shelf_home_id)
            result = await asyncio.wait_for(move_shelf_task, timeout=timeout)
        except asyncio.TimeoutError:
            await self.client.cancel_command()
            result = "TIMEOUT_ERROR"
        except Exception as e:
            print(f"❌ コマンド実行エラー: {e}")
    
        await self.judge_result("docking_akari", result)


    @decorated_execution
    async def pick_up(self, furniture_name, destination_name):
        """ 指定した家具を目的地まで運ぶ"""
        shelves = await self.client.get_shelves()
        locations = await self.client.get_locations()
        furniture_mapping = {shelf.name: shelf.id for shelf in shelves}
        location_mapping = {location.name: location.id for location in locations}

        if furniture_name in furniture_mapping and destination_name in location_mapping:
            furniture_id = furniture_mapping[furniture_name]
            destination_id = location_mapping[destination_name]

            result = await self.client.move_shelf(furniture_id, destination_id)
            
            print(f"家具 {furniture_name} を目的地 {destination_name} へ運びました。")
            await self.judge_result("move_shelf", result)
        else:
            print(f"❌ 指定された家具または目的地が見つかりません: {furniture_name} -> {destination_name}")

    @decorated_execution
    async def undock_shelf(self):
        """ 現在ドッキングしている家具をその場に置く """
        print("家具をその場に置きます。")
        result = await self.client.undock_shelf()
        await self.judge_result("undock_shelf", result)

    @decorated_execution
    async def put_away(self, shelf_name=None):
        """ 家具を元の位置に片付ける """
        shelves = await self.client.get_shelves()
        shelf_mapping = {shelf.name: shelf.id for shelf in shelves}
        
        result = None
        if shelf_name:
            if shelf_name in shelf_mapping:
                result = await self.client.return_shelf(shelf_mapping[shelf_name])
            else:
                print(f"❌ 指定された家具 '{shelf_name}' が見つかりません。")
                return
        else:
            print("現在ドッキングしている家具を片付けます。")
            result = await self.client.return_shelf()
            
        await self.judge_result("return_shelf", result)

    @decorated_execution
    async def move_to_location(self, location_name):
        """ 指定したロケーションへKachakaを移動させる """
        await self.client.update_resolver()
        locations = await self.client.get_locations()
        location_mapping = {loc.name: loc.id for loc in locations}
    
        if location_name in location_mapping:
            dis = await self.get_dist(location_name)
            if dis is None: dis = 0
            
            timeout = await self.moving_timeout(dis)
            result = None

            try:
                task = self.client.move_to_location(location_mapping[location_name])
                result = await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                await self.client.cancel_command()
                result = "TIMEOUT_ERROR"
            except Exception as e:
                print(f"❌ エラー: {e}")

            await self.judge_result("move_to_location", result)
        else:
            print(f"❌ 指定された場所 '{location_name}' が見つかりません。")

    @decorated_execution
    async def state_object_kachaka(self):
        """ Kachakaの現在の状態を取得（RUNNING、READYなど）"""
        running_command = await self.client.get_running_command()
        if running_command:
            return "RUNNING"
        if await self.client.get_manual_control_enabled() or await self.client.get_auto_homing_enabled():
            return "READY"
        if await self.client.get_history_list():
            return "Waiting"
        return "Dormant"

    @decorated_execution
    async def speak_kachaka(self, message):
        """ Kachakaに音声で発話させる """
        await self.volume_control(self.starting_volume)
        result = await self.client.speak(message)
        await self.judge_result("speak", result)
        await self.volume_control()

    @decorated_execution
    async def return_home(self):
        """ Kachakaを充電ドックへ戻す """
        print("充電ドックに戻ります")
        result = await self.client.return_home()
        await self.judge_result("return_home", result)
    
    @decorated_execution
    async def get_running_command(self):
        """ 実行中のコマンドを返す """
        return await self.client.get_running_command()
    
    @decorated_execution
    async def get_pose(self):
        """ マップ上の姿勢の取得 """
        return await self.client.get_robot_pose()
    
    # ========== ユーティリティ・制御関数 ==========

    async def volume_control(self, vol: int=0):
        await self.client.set_speaker_volume(vol)
    
    async def speak(self, msg):
        """ タスク外での発話用 """
        await self.volume_control(self.starting_volume)
        await self.client.speak(msg)
        await self.volume_control()

    async def get_dist(self, fin_name=None, st_name="kachaka"):
        """ 直線距離を計算 """
        if fin_name is None:
            return None
        
        locations = await self.client.get_locations()
        shelves = await self.client.get_shelves()
        all_targets = list(locations) + list(shelves)

        st_pose = None
        fin_pose = None

        if st_name == "kachaka":
            st_pose = await self.client.get_robot_pose()
        else:
            for part in all_targets:
                if st_name in part.name:
                    st_pose = part.pose
                    break
        
        for part in all_targets:
            if fin_name in part.name:
                fin_pose = part.pose
                break

        if fin_pose is None or st_pose is None:
            print(f"⚠️ ターゲットが見つかりません: {st_name} -> {fin_name}")
            return None
        
        dx = st_pose.x - fin_pose.x
        dy = st_pose.y - fin_pose.y
        distance = math.sqrt(dx*dx + dy*dy)
        print(f"📏 距離計測 ({st_name}->{fin_name}): {distance:.1f}m")
        return distance

    async def moving_timeout(self, dist=None, act_name=None):
        """ タイムアウト時間の計算 """
        default = 30
        timeout = default
        if dist is None:
            return timeout
        
        timeout += dist * 5
        if act_name == "docking":
            timeout += 30
        
        print(f"⏳ タイムアウト設定: {timeout:.1f}秒")
        return timeout
    
    async def cancel_command(self):
        """ コマンドキャンセル """
        await self.client.cancel_command()

    # ========== 割り込み制御関数 (Clientから呼ばれる) ==========

    async def stop(self):
        """ kachakaの動きを停止 """
        print("\n⏹️  Kachaka: 停止(STOP)要求を受信しました")
        await self.cancel_command()
        
        if self.running_asyncio_task:
            print("☑️  実行中のタスクをキャンセルします")
            self.running_asyncio_task.cancel()

        self.stop_flag = True
        self.pause_event.set() # 停止時はpause待ちを解除する
        self.pending_task = None

    async def pause(self):
        """ pauseイベントをclear (一時停止) する """
        if self.stop_flag:
            print("⛔ Kachaka: 停止中のためPAUSEは無視します")
            return
        
        if not self.pause_event.is_set():
            print("⚠️ Kachaka: 既に一時停止中です")
            return
        
        self.pause_event.clear()
        print("\n⏸️  Kachaka: 一時停止(PAUSE)要求を受信しました")

        # 実行中のタスクがあれば pending_task に退避
        if self.current_task and self.pending_task is None:
            self.pending_task = self.current_task
            print(f"📌 Kachaka: タスクを保存しました: {self.pending_task[0]}")
            
            # コマンド停止
            if await self.client.is_command_running():
                await self.cancel_command()
            else:
                # コマンドが走ってないならPython処理自体を止める
                if self.running_asyncio_task:
                    self.running_asyncio_task.cancel()

    async def resume(self):
        """ pauseイベントを解除する """
        print("▶️  Kachaka: 再開(RESUME)要求を受信しました")
        self.stop_flag = False
        self.pause_event.set() # 待機解除 -> handle_pause_and_recoveryが進む

    async def skip(self):
        """ 実行中の関数をスキップする """
        print("⏭️  Kachaka: スキップ(SKIP)要求を受信しました")
        self.stop_flag = False
        self.pause_event.set() # 待機解除

        if self.current_task:
            await self.cancel_command()
            if self.running_asyncio_task:
                self.running_asyncio_task.cancel()
    
    async def reset(self):
        """ コマンド受付を全てリセット """
        print("🔁 Kachaka: リセット(RESET)要求を受信しました")
        self.stop_flag = False 
        self.pending_task = None 
        self.current_task = None  
        self.pause_event.set()

    # ========== 結果判定 ==========
    async def judge_result(self, label: str, result: str):
        result_str = str(result)
        
        if "error_code" in result_str.lower():
            print(f"🔴 {label} 失敗 (Error): {result_str}")
            try:
                error_code = int(result_str.split()[1])
                if error_code in self.interrupt_error:
                    return # 割り込みによるエラーは無視
                
            except ValueError:
                pass

            if error_code in self.safety_error:
                self.pause_event.clear()
                if self.current_task and self.pending_task is None:
                    self.pending_task = self.current_task
                    print(f"📌 Kachaka: タスクを保存しました: {self.pending_task[0]}")
                return # kachakaの警告感知の場合は無視
            
            # 詳細表示
            all_errors = await self.client.get_robot_error_code()
            err = all_errors.get(error_code)
            if err:
                print(f"   [{err.code}] {err.title}: {err.description}")
                await self.speak(err.description)
            
            raise Exception(f"Kachaka Error: {result_str}")

        elif "success" in result_str.lower():
            print(f"🟢 {label} 成功")

        elif "timeout_error" in result_str.lower():
            print(f"🟠 {label} タイムアウト")
            await self.speak("移動に時間がかかりすぎています。経路を確認してください。")
            # タイムアウト時も一時停止状態にする
            self.pause_event.clear()
            
            if self.current_task and self.pending_task is None:
                self.pending_task = self.current_task
                print(f"📌 Kachaka: タスクを保存しました: {self.pending_task[0]}")
            
        else:
            print(f"⚪️ {label} 結果: {result_str}")

    async def jf(self):
        """ お片付け・ホーム帰還 """
        is_docking = await self.client.get_moving_shelf_id()
        if is_docking:
            await self.client.return_shelf()
        await self.client.return_home()