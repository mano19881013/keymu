# backend/hardware.py
import serial
import serial.tools.list_ports
import time
import random
import math
import threading
import ctypes
from backend.cognitive import CognitiveSystem

# Windows 座標結構
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class HardwareController:
    def __init__(self, port="COM3", auto_connect=True):
        self.lock = threading.Lock()
        self.mock_mode = False
        self.arduino = None
        self.port = port
        
        # 初始化疲勞系統
        self.brain = CognitiveSystem()
        
        # 用於回傳路徑給 UI 繪圖的 Callback
        self.debug_callback = None
        
        # 取得螢幕解析度 (供邊界檢查用)
        user32 = ctypes.windll.user32
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)
        
        if auto_connect:
            self.connect(port)

    @staticmethod
    def get_available_ports():
        ports = serial.tools.list_ports.comports()
        result = []
        for p in ports:
            result.append(f"{p.device} - {p.description}")
        return result

    def get_real_position(self):
        """取得絕對座標 (Windows API)"""
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def set_debug_callback(self, callback):
        """設定用於回傳路徑點的 callback"""
        self.debug_callback = callback

    def connect(self, port):
        self.port = port
        self.mock_mode = False
        if self.arduino and self.arduino.is_open:
            self.arduino.close()
        try:
            # 加入 write_timeout 防止卡死
            self.arduino = serial.Serial(port, 115200, timeout=0.01, write_timeout=1.0)
            time.sleep(2) 
            print(f"[系統] ✅ Arduino 連接成功 (Port: {port})")
            return True
        except Exception as e:
            self.mock_mode = True
            print(f"[系統] ⚠️ 連接失敗 ({e})，切換至【虛擬 Mock 模式】")
            return False

    def close(self):
        if self.arduino and self.arduino.is_open:
            self.arduino.close()

    def _arduino_write(self, command):
        """安全寫入指令"""
        if not self.arduino or not self.arduino.is_open: return
        try:
            self.arduino.write(command)
        except serial.SerialTimeoutException:
            print("[硬體] ⚠️ 寫入超時 (緩衝區滿)，略過指令")
        except Exception as e:
            print(f"[硬體] ❌ 寫入錯誤: {e}")

    def _arduino_move_step(self, dx, dy):
        """單次微小移動，限制最大步幅"""
        if not self.arduino or not self.arduino.is_open: return

        limit = 20 
        step_x = max(-limit, min(limit, int(dx)))
        step_y = max(-limit, min(limit, int(dy)))
        
        if step_x != 0 or step_y != 0:
            self._arduino_write(f"M,{step_x},{step_y}\n".encode())
            time.sleep(0.002) 

    def _calculate_bezier_path(self, start_x, start_y, end_x, end_y):
        """生成二階或三階貝塞爾曲線的路徑點"""
        path = []
        dist = math.hypot(end_x - start_x, end_y - start_y)
        steps = max(10, int(dist / 20)) 
        
        offset_scale = min(dist * 0.5, 300) 
        ctrl1_x = start_x + (end_x - start_x) * 0.25 + random.uniform(-offset_scale, offset_scale)
        ctrl1_y = start_y + (end_y - start_y) * 0.25 + random.uniform(-offset_scale, offset_scale)
        ctrl2_x = start_x + (end_x - start_x) * 0.75 + random.uniform(-offset_scale, offset_scale)
        ctrl2_y = start_y + (end_y - start_y) * 0.75 + random.uniform(-offset_scale, offset_scale)

        for i in range(steps + 1):
            t = i / steps
            u = 1 - t
            tt = t * t
            uu = u * u
            uuu = uu * u
            ttt = tt * t
            
            p_x = uuu * start_x + 3 * uu * t * ctrl1_x + 3 * u * tt * ctrl2_x + ttt * end_x
            p_y = uuu * start_y + 3 * uu * t * ctrl1_y + 3 * u * tt * ctrl2_y + ttt * end_y
            
            safe_x = max(1, min(int(p_x), self.screen_w - 2))
            safe_y = max(1, min(int(p_y), self.screen_h - 2))
            path.append((safe_x, safe_y))
            
        return path

    def _execute_path_move(self, start_x, start_y, end_x, end_y):
        """內部函式：執行一段貝塞爾曲線移動"""
        waypoints = self._calculate_bezier_path(start_x, start_y, end_x, end_y)
        
        if self.debug_callback:
            try: self.debug_callback(waypoints)
            except: pass

        total_points = len(waypoints)
        for i, (wp_x, wp_y) in enumerate(waypoints):
            is_last_point = (i == total_points - 1)
            progress = i / total_points
            
            if 0.2 < progress < 0.8: tolerance = 30 
            elif progress < 0.2: tolerance = 15 
            else: tolerance = 5 
            if is_last_point: tolerance = 3 
            
            self._move_converging(wp_x, wp_y, tolerance=tolerance)
            
            base_sleep = 0.001 
            if 0.2 < progress < 0.8: time.sleep(base_sleep)
            else: time.sleep(base_sleep + random.uniform(0.001, 0.003))

    def move(self, target_x, target_y):
        """
        ★ 擬人化核心：常駐慣性過頭 (Overshoot) 機制
        """
        with self.lock: 
            # 1. 邊界與目標鎖定
            target_x = max(1, min(target_x, self.screen_w - 2))
            target_y = max(1, min(target_y, self.screen_h - 2))

            # 加入終點微小隨機 (模擬手不穩)
            jitter_x = random.randint(-2, 2)
            jitter_y = random.randint(-2, 2)
            final_target_x = max(1, min(target_x + jitter_x, self.screen_w - 2))
            final_target_y = max(1, min(target_y + jitter_y, self.screen_h - 2))

            start_x, start_y = self.get_real_position()
            dist = math.hypot(final_target_x - start_x, final_target_y - start_y)

            # 2. 如果距離極短，直接移動 (不搞花樣)
            if dist < 20:
                self._move_converging(final_target_x, final_target_y, strict=True)
                if self.arduino: self.arduino.reset_input_buffer()
                return

            # 3. ★ 慣性過頭邏輯
            # 只有當移動距離夠長 (例如 > 250px) 時才觸發，模擬甩滑鼠的慣性
            if dist > 250:
                # 計算過頭量：距離的 3% ~ 8%，上限 50px
                overshoot_ratio = random.uniform(0.03, 0.08)
                overshoot_px = min(50, dist * overshoot_ratio)
                
                # 計算向量方向
                vec_x = final_target_x - start_x
                vec_y = final_target_y - start_y
                
                # 計算「虛擬過頭點」
                over_x = int(final_target_x + (vec_x / dist) * overshoot_px)
                over_y = int(final_target_y + (vec_y / dist) * overshoot_px)
                
                # 確保虛擬點不出界
                over_x = max(1, min(over_x, self.screen_w - 2))
                over_y = max(1, min(over_y, self.screen_h - 2))

                # A. 快速甩向過頭點
                self._execute_path_move(start_x, start_y, over_x, over_y)
                
                # B. 擬人化停頓 (煞車反應時間)
                reaction_time = random.uniform(0.05, 0.15) * self.brain.get_reaction_multiplier()
                time.sleep(reaction_time)
                
                # C. 修正回真實目標 (拉回)
                self._move_converging(final_target_x, final_target_y, tolerance=2, strict=True)
                
            else:
                # 4. 短中距離：標準貝塞爾移動
                self._execute_path_move(start_x, start_y, final_target_x, final_target_y)
            
            # ★ 移動結束後，清空輸入緩衝
            if self.arduino: 
                self.arduino.reset_input_buffer()

    def _move_converging(self, target_x, target_y, tolerance=5, strict=False):
        """漸進逼近法 (PID概念)"""
        start_time = time.time()
        max_duration = 1.5 if strict else 0.5 
        
        while time.time() - start_time < max_duration:
            curr_x, curr_y = self.get_real_position()
            diff_x = target_x - curr_x
            diff_y = target_y - curr_y
            dist = math.hypot(diff_x, diff_y)
            
            if dist <= tolerance: break
            
            speed_factor = 0.45 
            step_x = int(diff_x * speed_factor)
            step_y = int(diff_y * speed_factor)
            
            if step_x == 0 and abs(diff_x) > 0: step_x = 1 if diff_x > 0 else -1
            if step_y == 0 and abs(diff_y) > 0: step_y = 1 if diff_y > 0 else -1
            
            self._arduino_move_step(step_x, step_y)
            
            if not strict and dist < (tolerance * 1.5): break

    def click(self):
        with self.lock:
            fatigue_factor = self.brain.get_reaction_multiplier()
            if self.mock_mode:
                print(f"[Mock] 👆 點擊")
                time.sleep(0.1)
            else:
                self._arduino_write(b"C")
                time.sleep(random.uniform(0.05, 0.1) * fatigue_factor)

    def drag(self, start_x, start_y, end_x, end_y):
        MOUSE_LEFT = 1 
        with self.lock:
            self.move(start_x, start_y)
            time.sleep(random.uniform(0.15, 0.25))

            if not self.mock_mode:
                self._arduino_write(f"D,{MOUSE_LEFT}\n".encode())
                time.sleep(random.uniform(0.05, 0.1))
            else: print("[Mock] Drag Start")

            self.move(end_x, end_y)
            time.sleep(random.uniform(0.15, 0.25))

            if not self.mock_mode:
                self._arduino_write(f"U,{MOUSE_LEFT}\n".encode())
                time.sleep(random.uniform(0.05, 0.1))
            else: print("[Mock] Drag End")

    def key_down(self, key_code):
        with self.lock:
            if not self.mock_mode:
                self._arduino_write(f"D,{key_code}\n".encode())
                time.sleep(0.01)

    def key_up(self, key_code):
        with self.lock:
            if not self.mock_mode:
                self._arduino_write(f"U,{key_code}\n".encode())
                time.sleep(0.01)

    def release_all(self):
        with self.lock:
            if not self.mock_mode: self._arduino_write(b"A\n")

    def press(self, key_code):
        """
        ★ 擬人化指法 (Keystroke Dynamics)
        """
        with self.lock:
            fatigue_factor = self.brain.get_reaction_multiplier()
            
            # 1. 功能鍵與方向鍵 (Shift, Ctrl, Alt, Arrows) -> 按最久 (0.15 ~ 0.25s)
            if key_code in [128, 129, 130, 218, 217, 216, 215]: 
                base_time = random.uniform(0.15, 0.25)
                
            # 2. 常用功能 (Enter, Esc, Space, Backspace, Tab) -> 紮實按壓 (0.10 ~ 0.18s)
            elif key_code in [176, 177, 32, 178, 179]: 
                base_time = random.uniform(0.10, 0.18)
                
            # 3. 技能與數字鍵 (0-9, F1-F12) -> 一般按壓 (0.08 ~ 0.14s)
            elif (48 <= key_code <= 57) or (194 <= key_code <= 205):
                base_time = random.uniform(0.08, 0.14)
                
            # 4. 文字鍵 (A-Z) -> 輕快敲擊 (0.05 ~ 0.11s)
            else:
                base_time = random.uniform(0.05, 0.11)
            
            # 套用疲勞度並加上極小波動
            hold_time = base_time * fatigue_factor
            
            if self.mock_mode:
                print(f"[Mock] ⌨️ 按鍵 {key_code} (按住 {hold_time:.3f}s)")
                time.sleep(hold_time)
            else:
                self._arduino_write(f"D,{key_code}\n".encode())
                time.sleep(hold_time) 
                self._arduino_write(f"U,{key_code}\n".encode())
                
            # ★ 手指抬起延遲 (Human Release Latency)
            # 避免兩個按鍵指令黏在一起
            time.sleep(random.uniform(0.02, 0.05))