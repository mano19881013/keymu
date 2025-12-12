# frontend/recorder.py
import time
import threading
from pynput import mouse, keyboard
from PySide6.QtCore import QObject, Signal

class ActionRecorder(QObject):
    # 定義訊號：當錄製停止時，回傳錄到的指令列表
    finished_signal = Signal(list)

    def __init__(self):
        super().__init__()
        self.is_recording = False
        self.start_time = 0
        self.recorded_steps = []
        self.mouse_listener = None
        self.key_listener = None

    def start(self):
        """開始錄製"""
        self.is_recording = True
        self.recorded_steps = []
        self.start_time = time.time()
        
        # 為了避免重複啟動，先嘗試停止舊的監聽器
        self.stop_listeners()
        
        # 啟動監聽器 (Non-blocking)
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.key_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        
        self.mouse_listener.start()
        self.key_listener.start()
        print("[錄製] 開始監聽鍵鼠操作... (按 F12 或 Esc 停止)")

    def stop(self):
        """停止錄製並回傳數據"""
        if self.is_recording:
            self.is_recording = False
            self.stop_listeners()
                
            print(f"[錄製] 結束，共錄製 {len(self.recorded_steps)} 個動作")
            
            # 發送結果給主視窗
            self.finished_signal.emit(self.recorded_steps)

    def stop_listeners(self):
        """安全停止監聽器"""
        if self.mouse_listener: 
            self.mouse_listener.stop()
            self.mouse_listener = None
        if self.key_listener: 
            self.key_listener.stop()
            self.key_listener = None

    def _record_wait(self):
        """
        計算距離上一個動作經過了多久，自動加入 Wait 指令
        """
        current_time = time.time()
        diff = current_time - self.start_time
        
        # 門檻設為 0.1 秒，過濾極短的抖動
        if diff > 0.1:
            self.recorded_steps.append({
                'type': 'Wait',
                'val': str(round(diff, 2)),
                'text': f"⏳ 等待 {round(diff, 2)} 秒"
            })
        
        self.start_time = current_time

    def on_click(self, x, y, button, pressed):
        if not self.is_recording: return
        
        if pressed and button == mouse.Button.left:
            self._record_wait()
            self.recorded_steps.append({
                'type': 'Click',
                'val': f"{x},{y}",
                'text': f"🖱️ 點擊座標 {x},{y}"
            })

    def on_press(self, key):
        if not self.is_recording: return
        
        # --- 🛑 停止錄製判斷區 ---
        stop_recording = False
        
        # 1. 判斷 F12
        if key == keyboard.Key.f12:
            stop_recording = True
            
        # 2. 判斷 Esc (備用方案)
        elif key == keyboard.Key.esc:
            stop_recording = True
            
        if stop_recording:
            print("[錄製] 🛑 偵測到停止熱鍵 (F12/Esc)")
            self.stop()
            return
        # ------------------------

        try:
            # 處理特殊鍵
            if hasattr(key, 'vk') and key.vk is not None:
                vk = key.vk
                
                # 過濾掉 Shift/Ctrl/Alt 單獨按下的情況 (避免垃圾訊號)
                if 160 <= vk <= 165: return 

                self._record_wait()
                
                # 這裡記錄的是 Virtual Key Code
                self.recorded_steps.append({
                    'type': 'Key',
                    'val': str(vk),
                    'text': f"⌨️ 按下按鍵碼 {vk}"
                })
                
            # 處理普通字元
            elif hasattr(key, 'char') and key.char:
                self._record_wait()
                char_code = ord(key.char)
                self.recorded_steps.append({
                    'type': 'Key',
                    'val': str(char_code),
                    'text': f"⌨️ 按下按鍵 '{key.char}'"
                })
                
        except Exception as e:
            # 忽略無法識別的按鍵錯誤
            pass

    def on_release(self, key):
        pass