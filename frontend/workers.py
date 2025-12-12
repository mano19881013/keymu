# frontend/workers.py
import time
import os
import json
import cv2
import numpy as np
import difflib
import re
import importlib.util
import traceback 
import datetime 
import random 

from PySide6.QtCore import QThread, Signal
from pynput import keyboard
import pyautogui

from backend.logic_plugin import LogicPluginBase
from backend.plugin_base import PluginBase

# --- 鍵盤監聽 ---
class KeyListener(QThread):
    finished_signal = Signal(object) 
    def __init__(self, mode='point'):
        super().__init__()
        self.mode = mode
    def run(self):
        def on_press(key):
            try:
                if key == keyboard.Key.f8: return False 
            except: pass
        with keyboard.Listener(on_press=on_press) as listener: listener.join()
        x, y = pyautogui.position()
        if self.mode == 'point': self.finished_signal.emit((x, y))
        elif self.mode == 'color':
            try: r, g, b = pyautogui.pixel(x, y); self.finished_signal.emit((r, g, b))
            except: self.finished_signal.emit(None)

# --- 看門狗監控 ---
class WatchdogThread(QThread):
    warning_signal = Signal(str)
    emergency_signal = Signal()
    
    def __init__(self, vision):
        super().__init__()
        self.vision = vision
        self.is_running = True
        self.last_img = None
        self.static_count = 0
        self.check_interval = 60 
        self.max_static_minutes = 5 

    def run(self):
        self.warning_signal.emit("[看門狗] 🛡️ 安全監控已啟動...")
        while self.is_running:
            try:
                current_img = self.vision.capture_screen()
                if self.last_img is not None:
                    gray1 = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)
                    gray2 = cv2.cvtColor(self.last_img, cv2.COLOR_BGR2GRAY)
                    err = np.sum((gray1.astype("float") - gray2.astype("float")) ** 2)
                    err /= float(gray1.shape[0] * gray1.shape[1])
                    if err < 50: 
                        self.static_count += 1
                        self.warning_signal.emit(f"[看門狗] ⚠️ 警告：畫面已靜止 {self.static_count} 分鐘")
                    else:
                        if self.static_count > 0:
                            self.warning_signal.emit("[看門狗] ✅ 畫面恢復變動，計數歸零")
                        self.static_count = 0
                self.last_img = current_img
                if self.static_count >= self.max_static_minutes:
                    self.warning_signal.emit(f"[看門狗] 🚨 緊急：偵測到卡死超過 {self.max_static_minutes} 分鐘！強制停止！")
                    self.emergency_signal.emit()
                    self.static_count = 0 
            except Exception: pass
            for _ in range(self.check_interval):
                if not self.is_running: break
                time.sleep(1)

    def stop(self):
        self.is_running = False

# --- 引擎橋接器 ---
class EngineBridge:
    def __init__(self, hardware, vision, log_callback, stop_check_callback):
        self.hw = hardware; self.vision = vision; self.log = log_callback; self.should_stop = stop_check_callback

# --- 腳本執行器 ---
class ScriptRunner(QThread):
    log_signal = Signal(str); finished_signal = Signal(); draw_rect_signal = Signal(int, int, int, int); draw_target_signal = Signal(int, int)
    
    def __init__(self, task_objects, hardware, vision):
        super().__init__()
        self.hw = hardware
        self.vision = vision
        self.is_running = True
        
        self.tasks = []
        for t in task_objects:
            t_obj = t.copy()
            t_obj.setdefault('mode', 0)
            t_obj.setdefault('sch_start', "00:00")
            t_obj.setdefault('sch_end', "23:59")
            t_obj['last_success_date'] = None
            self.tasks.append(t_obj)
            
        self.scheduled_tasks = []
        self.loop_counters = {} 
        self.executed_mission_ids = set()
        self.current_priority = 999 

    def add_scheduled_task(self, task_info):
        boss_name = task_info.get('variables', {}).get('BOSS_NAME', 'Unknown')
        spawn_time = str(task_info.get('spawn_time', ''))
        mission_id = f"{boss_name}|{spawn_time}"

        if mission_id in self.executed_mission_ids:
            return

        for t in self.scheduled_tasks:
            t_id = f"{t.get('variables', {}).get('BOSS_NAME')}|{str(t.get('spawn_time', ''))}"
            if t_id == mission_id:
                return 

        self.scheduled_tasks.append(task_info)
        self.scheduled_tasks.sort(key=lambda x: x['start_time'])

    def _apply_variables(self, val_str, variables):
        if not variables or not isinstance(val_str, str):
            return val_str
        result = val_str
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result

    def check_for_interruption(self):
        if not self.scheduled_tasks: return False
        
        next_task = self.scheduled_tasks[0]
        now = datetime.datetime.now()
        
        if next_task['start_time'] <= now:
            next_prio = next_task.get('priority', 0)
            if next_prio < self.current_priority:
                self.log_signal.emit(f"⚡ 偵測到高優先級任務 ({next_prio} < {self.current_priority})，請求插隊...")
                return True
        return False

    def smart_sleep(self, duration):
        start = time.time()
        next_jitter_time = start + random.uniform(2.0, 5.0)
        while time.time() - start < duration:
            if not self.is_running: return False
            if self.check_for_interruption(): return False 
            
            if duration > 2.0 and time.time() > next_jitter_time:
                self._perform_idle_behavior()
                next_jitter_time = time.time() + random.uniform(3.0, 8.0)
            time.sleep(0.05)
        return True

    def _perform_idle_behavior(self):
        try:
            curr_x, curr_y = self.hw.get_real_position()
            action_type = random.choice(['micro', 'micro', 'micro', 'drift'])
            if action_type == 'micro':
                dx = random.randint(-5, 5); dy = random.randint(-5, 5); self.hw.move(curr_x + dx, curr_y + dy)
            elif action_type == 'drift':
                dx = random.randint(-20, 20); dy = random.randint(-20, 20); self.hw.move(curr_x + dx, curr_y + dy)
        except Exception: pass
    
    def parse_val_region(self, val_str):
        if "|" in str(val_str) and len(str(val_str).split("|")) >= 2:
            parts = val_str.split("|"); possible_region = parts[-1]
            if "," in possible_region and len(possible_region.split(',')) == 4:
                try: rx, ry, rw, rh = map(int, possible_region.split(',')); main_val = "|".join(parts[:-1]); return main_val, (rx, ry, rw, rh)
                except: pass
        return val_str, None

    def parse_smart_val(self, val_str):
        parts = val_str.split('|'); region = None
        if len(parts) >= 1 and "," in parts[-1] and len(parts[-1].split(',')) == 4:
            try: map(int, parts[-1].split(',')); region = tuple(map(int, parts[-1].split(','))); parts = parts[:-1]
            except: pass
        while len(parts) < 7: parts.append("")
        return parts, region

    def is_text_match(self, target, detected_text, threshold=0.5):
        clean_t = re.sub(r'\s+', '', str(target)); clean_d = re.sub(r'\s+', '', str(detected_text))
        if not clean_t or not clean_d: return False
        if clean_t in clean_d: return True
        hits = sum(1 for c in clean_t if c in clean_d)
        simple_ratio = hits / len(clean_t) if len(clean_t) > 0 else 0
        matcher = difflib.SequenceMatcher(None, clean_t, clean_d)
        diff_ratio = matcher.ratio()
        return diff_ratio >= threshold or simple_ratio >= threshold

    # ★ 新增：動態載入插件的 helper
    def _load_plugin_instance(self, filename):
        try:
            name = os.path.splitext(os.path.basename(filename))[0]
            path = os.path.join("extensions", filename)
            if not os.path.exists(path): return None
            
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    return attr()
        except: pass
        return None

    def execute_steps(self, steps, engine_bridge, depth=0, variables=None):
        if depth > 3: self.log_signal.emit("❌ 錯誤: 腳本巢狀層數過深"); return
        i = 0
        while i < len(steps):
            if not self.is_running: break
            
            if self.check_for_interruption():
                self.log_signal.emit("🛑 腳本已中斷 (讓位給緊急任務)")
                return

            step = steps[i]; action = step['type']; raw_val = step['val']
            val = self._apply_variables(raw_val, variables)
            real_val, region = self.parse_val_region(val); region_msg = f" (範圍: {region})" if region else ""
            fatigue = self.hw.brain.get_reaction_multiplier()

            if action == 'Label': pass
            elif action == 'Goto':
                target = real_val; found = False
                for idx, s in enumerate(steps):
                    if s['type'] == 'Label' and s['val'] == target: i = idx; found = True; self.log_signal.emit(f"🔀 跳轉至: {target}"); break
                if not found: self.log_signal.emit(f"❌ 錯誤: 找不到標籤 {target}")
            
            elif action == 'Loop':
                try:
                    parts = val.split('|')
                    target_label = parts[0]
                    max_count = int(parts[1])
                    fail_act = parts[2] if len(parts) > 2 else "Stop"
                    fail_param = parts[3] if len(parts) > 3 else ""

                    current = self.loop_counters.get(target_label, 0) + 1
                    
                    if current <= max_count:
                        self.loop_counters[target_label] = current
                        self.log_signal.emit(f"🔁 循環: {target_label} ({current}/{max_count})")
                        found = False
                        for idx, s in enumerate(steps):
                            if s['type'] == 'Label' and s['val'] == target_label:
                                i = idx; found = True; break
                        if not found: self.log_signal.emit(f"❌ 錯誤: 找不到標籤 {target_label}")
                        should_inc = False 
                    else:
                        self.log_signal.emit(f"🛑 循環上限 ({max_count})，執行: {fail_act}")
                        self.loop_counters[target_label] = 0 
                        if fail_act == "Stop":
                            self.is_running = False
                            self.log_signal.emit(">>> 因循環超時，腳本強制停止")
                        elif fail_act == "Goto":
                             found = False
                             for idx, s in enumerate(steps):
                                 if s['type'] == 'Label' and s['val'] == fail_param:
                                     i = idx; found = True; self.log_signal.emit(f"🔀 [超時] 跳轉至例外處理: {fail_param}"); break
                             if found: should_inc = False
                             else: self.log_signal.emit(f"❌ 錯誤: 找不到失敗跳轉標籤 {fail_param}")
                except Exception as e: self.log_signal.emit(f"❌ 循環錯誤: {e}")

            elif action == 'LogicPlugin': pass
            elif action == 'IfImage':
                parts = str(val).split('|'); img_path = parts[0]; jump_label = parts[-1]; chk_region = None
                if len(parts) > 2:
                    try: chk_region = tuple(map(int, parts[1].split(',')))
                    except: pass
                if region: self.draw_rect_signal.emit(*region)
                if os.path.exists(img_path):
                    self.log_signal.emit(f"❓ 判斷: {img_path}")
                    if self.vision.find_image(img_path, region=chk_region):
                        self.log_signal.emit(f"✅ 條件成立！跳至 {jump_label}")
                        for idx, s in enumerate(steps):
                            if s['type'] == 'Label' and s['val'] == jump_label: i = idx; break
                    else: self.log_signal.emit("❌ 條件不成立")
            elif action == 'SmartAction':
                try:
                    parts, region = self.parse_smart_val(val)
                    cond_type, target = parts[0], parts[1]
                    succ_act, succ_param = parts[2], parts[3]
                    fail_act, fail_param = parts[4], parts[5]
                    try: threshold_val = float(parts[6])
                    except: threshold_val = 0.8 
                    
                    self.log_signal.emit(f"🧠 智慧判斷: {cond_type} '{target}' (閥值:{threshold_val})...")
                    
                    found_pos = None
                    if cond_type == 'FindImg':
                        if os.path.exists(target):
                            if region: self.draw_rect_signal.emit(*region)
                            found_pos = self.vision.find_image(target, confidence=threshold_val, region=region)
                    elif cond_type == 'OCR':
                        if region: self.draw_rect_signal.emit(*region)
                        res = self.vision.ocr_screen(region=region)
                        detected_texts = [item[1] for item in res]
                        self.log_signal.emit(f"   📋 OCR: {detected_texts}")
                        for item in res:
                            bbox, text, conf = item
                            if self.is_text_match(target, text, threshold=threshold_val):
                                anchor_x = int(bbox[0][0] / 3) 
                                anchor_y = int((bbox[0][1] + bbox[2][1]) / 2 / 3)
                                if region: found_pos = (region[0] + anchor_x, region[1] + anchor_y)
                                else:
                                    offset_x = self.vision.monitor_rect['left']
                                    offset_y = self.vision.monitor_rect['top']
                                    found_pos = (offset_x + anchor_x, offset_y + anchor_y)
                                break
                    elif cond_type == 'FindColor':
                        rgb = tuple(map(int, target.split(',')))
                        found_pos = self.vision.find_color(rgb, tolerance=int(threshold_val), region=region)
                    
                    if found_pos:
                        self.log_signal.emit(f"   ✅ 執行: {succ_act}")
                        if succ_act == 'ClickTarget' and found_pos: 
                            self.draw_target_signal.emit(found_pos[0], found_pos[1]); 
                            self.hw.move(found_pos[0], found_pos[1]); 
                            time.sleep(0.15) # ★ 安全緩衝
                            self.hw.click()
                        elif succ_act == 'ClickOffset' and found_pos:
                            off_x, off_y = map(int, succ_param.split(',')); final_x = found_pos[0] + off_x; final_y = found_pos[1] + off_y; 
                            self.draw_target_signal.emit(final_x, final_y); 
                            self.hw.move(final_x, final_y); 
                            time.sleep(0.15) # ★ 安全緩衝
                            self.hw.click()
                        elif succ_act == 'RunScript':
                            if os.path.exists(succ_param):
                                with open(succ_param, 'r', encoding='utf-8') as f: sub_steps = json.load(f)
                                self.execute_steps(sub_steps, engine_bridge, depth + 1, variables)
                        elif succ_act == 'Goto':
                            for idx, s in enumerate(steps):
                                if s['type'] == 'Label' and s['val'] == succ_param: i = idx; break
                        elif succ_act == 'Stop': self.is_running = False
                    else: 
                        self.log_signal.emit("   ⚠️ 條件未成立")
                        if fail_act == 'Goto':
                            for idx, s in enumerate(steps):
                                if s['type'] == 'Label' and s['val'] == fail_param: i = idx; break
                        elif fail_act == 'RunScript':
                            if os.path.exists(fail_param):
                                with open(fail_param, 'r', encoding='utf-8') as f: sub_steps = json.load(f)
                                self.execute_steps(sub_steps, engine_bridge, depth + 1, variables)
                        elif fail_act == 'Stop': self.is_running = False
                except Exception as e: self.log_signal.emit(f"❌ 智慧錯誤: {e}")

            elif action == 'Click':
                try: coords = real_val.split(','); x, y = int(coords[0]), int(coords[1]); self.draw_target_signal.emit(x, y); self.hw.move(x, y); self.hw.click()
                except: pass
            elif action == 'Key': self.hw.press(int(real_val))
            elif action == 'Drag':
                try:
                    parts = val.split('|')
                    start_coords = parts[0].split(',')
                    end_coords = parts[1].split(',')
                    start_x, start_y = int(start_coords[0]), int(start_coords[1])
                    end_x, end_y = int(end_coords[0]), int(end_coords[1])
                    self.log_signal.emit(f"↔️ 拖曳: ({start_x},{start_y}) -> ({end_x},{end_y})")
                    self.hw.drag(start_x, start_y, end_x, end_y)
                except Exception as e: self.log_signal.emit(f"❌ 拖曳錯誤: {e}")
            elif action == 'FindImg':
                if os.path.exists(real_val):
                    self.log_signal.emit(f"👁️ 尋找: {real_val}{region_msg}")
                    if region: self.draw_rect_signal.emit(*region)
                    pos = self.vision.find_image(real_val, region=region)
                    if pos: 
                        self.draw_target_signal.emit(pos[0], pos[1]); 
                        self.hw.move(pos[0], pos[1]); 
                        time.sleep(0.15) # ★ 安全緩衝
                        self.hw.click()
                    else: self.log_signal.emit("⚠️ 沒找到")
            elif action == 'OCR':
                target_text = str(real_val).strip(); self.log_signal.emit(f"🔤 OCR: '{target_text}'{region_msg}...")
                try:
                    if region: self.draw_rect_signal.emit(*region)
                    res = self.vision.ocr_screen(region=region)
                    detected_texts = [item[1] for item in res]
                    self.log_signal.emit(f"   📋 讀到: {detected_texts}")
                    found_pos = None
                    for item in res:
                        bbox, text, conf = item
                        if self.is_text_match(target_text, text, threshold=0.5):
                            anchor_x = int(bbox[0][0] / 3) 
                            anchor_y = int((bbox[0][1] + bbox[2][1]) / 2 / 3)
                            if region: found_pos = (region[0] + anchor_x, region[1] + anchor_y)
                            else:
                                offset_x = self.vision.monitor_rect['left']
                                offset_y = self.vision.monitor_rect['top']
                                found_pos = (offset_x + anchor_x, offset_y + anchor_y)
                            break
                    if found_pos: 
                        self.log_signal.emit(f"✅ 發現！點擊: {found_pos}")
                        self.draw_target_signal.emit(found_pos[0], found_pos[1])
                        self.hw.move(found_pos[0], found_pos[1])
                        time.sleep(0.15) # ★ 安全緩衝
                        self.hw.click()
                    else: self.log_signal.emit(f"⚠️ 未發現")
                except Exception as e: self.log_signal.emit(f"❌ OCR 錯誤: {e}")
            elif action == 'FindColor':
                try:
                    rgb = tuple(map(int, real_val.split(','))); self.log_signal.emit(f"🎨 找色: RGB{rgb}{region_msg}")
                    pos = self.vision.find_color(rgb, tolerance=20, region=region)
                    if pos: 
                        self.draw_target_signal.emit(pos[0], pos[1]); 
                        self.hw.move(pos[0], pos[1]); 
                        time.sleep(0.15) # ★ 安全緩衝
                        self.hw.click(); 
                        self.log_signal.emit(f"✅ 發現顏色！")
                    else: self.log_signal.emit("⚠️ 未發現")
                except Exception as e: self.log_signal.emit(f"❌ 找色錯誤: {e}")
            
            # ★ 修改：現在 Plugin 存的是「檔名 (String)」，不是物件
            # 我們需要動態載入它
            elif action == 'Plugin': 
                plugin_instance = self._load_plugin_instance(str(real_val))
                if plugin_instance:
                    plugin_instance.run(engine_bridge)
                else:
                    self.log_signal.emit(f"❌ 錯誤: 無法載入插件 {real_val}")

            elif action == 'Wait':
                try:
                    base_wait = float(real_val)
                    final_wait = self.hw.brain.get_human_wait(base_wait)
                    self.log_signal.emit(f"⏳ 等待 {base_wait}s (擬人化->{final_wait:.2f}s)")
                    if not self.smart_sleep(final_wait):
                        if not self.is_running: break 
                        else: return # 插隊中斷
                except: pass
            
            elif action == 'Comment': pass 

            should_inc = True
            if action == 'Goto' or action == 'Loop': should_inc = False
            if action == 'SmartAction': pass
            if should_inc: i += 1
            
            # 間隔時間
            base_gap = 0.1
            if action in ['FindImg', 'OCR', 'FindColor', 'SmartAction', 'IfImage']:
                base_gap = random.uniform(0.5, 0.8)
            elif action in ['Click', 'Key', 'Drag']:
                base_gap = random.uniform(0.1, 0.3)
            elif action in ['Label', 'Goto', 'Loop', 'Comment']:
                base_gap = 0.01

            step_gap = self.hw.brain.get_human_wait(base_gap)
            
            if not self.smart_sleep(step_gap):
                 if not self.is_running: break
                 else: return # 插隊中斷

    def run(self):
        self.log_signal.emit(">>> 🚀 智慧排程器啟動 (Scheduler Mode)")
        engine_bridge = EngineBridge(self.hw, self.vision, lambda msg: self.log_signal.emit(msg), lambda: not self.is_running)
        
        while self.is_running:
            current_time = time.time()
            now_dt = datetime.datetime.now()
            today_str = now_dt.strftime("%Y-%m-%d")
            
            task_to_run = None
            task_vars = None 

            if self.scheduled_tasks:
                next_task = self.scheduled_tasks[0]
                if now_dt >= next_task['start_time']:
                    self.current_priority = next_task.get('priority', 0)
                    active_task = self.scheduled_tasks.pop(0)
                    
                    boss_name = active_task.get('variables', {}).get('BOSS_NAME', 'Unknown')
                    spawn_time = str(active_task.get('spawn_time', ''))
                    mission_id = f"{boss_name}|{spawn_time}"
                    
                    if mission_id in self.executed_mission_ids:
                        self.log_signal.emit(f"⚠️ 跳過重複任務: {boss_name}")
                        self.current_priority = 999 
                        continue
                    
                    self.executed_mission_ids.add(mission_id)
                    if len(self.executed_mission_ids) > 50: self.executed_mission_ids.pop()

                    script_file = active_task['script_path']
                    task_vars = active_task.get('variables', {})
                    
                    self.log_signal.emit(f"⏰ 定時任務觸發！執行: {os.path.basename(script_file)}")
                    if task_vars: self.log_signal.emit(f"   ↳ 參數: {task_vars}")
                    
                    if os.path.exists(script_file):
                        try:
                            with open(script_file, 'r', encoding='utf-8') as f: steps = json.load(f)
                            self.loop_counters = {} 
                            self.execute_steps(steps, engine_bridge, variables=task_vars)
                        except Exception as e:
                             self.log_signal.emit(f"❌ 預約任務失敗: {e}")
                    
                    self.current_priority = 999 
                    continue 

            available_tasks = []
            for task in self.tasks:
                mode = task.get('mode', 0)
                if mode == 0:
                    if current_time - task['last_run'] >= task['interval']:
                        available_tasks.append(task)
                elif mode == 1:
                    sch_start_str = task.get('sch_start', "00:00")
                    sch_end_str = task.get('sch_end', "23:59")
                    try:
                        t_start = datetime.datetime.strptime(sch_start_str, "%H:%M").time()
                        t_end = datetime.datetime.strptime(sch_end_str, "%H:%M").time()
                        dt_start = datetime.datetime.combine(now_dt.date(), t_start)
                        dt_end = datetime.datetime.combine(now_dt.date(), t_end)
                        is_in_window = dt_start <= now_dt <= dt_end
                        if is_in_window and task['last_success_date'] != today_str:
                            available_tasks.append(task)
                    except: pass
            
            if available_tasks:
                available_tasks.sort(key=lambda t: t['priority'])
                task_to_run = available_tasks[0]
            
            if task_to_run:
                script_file = task_to_run['path']
                p_text = ["🔥高", "⏺中", "💤低"][task_to_run['priority']]
                self.current_priority = task_to_run.get('priority', 1)

                self.log_signal.emit(f"--------------------------------")
                self.log_signal.emit(f"⚡ 執行任務 [{p_text}]: {os.path.basename(script_file)}")
                
                if os.path.exists(script_file):
                    try:
                        with open(script_file, 'r', encoding='utf-8') as f: steps = json.load(f)
                        self.loop_counters = {} 
                        self.execute_steps(steps, engine_bridge)
                        task_to_run['last_run'] = time.time()
                        if task_to_run.get('mode') == 1:
                            task_to_run['last_success_date'] = today_str 
                            self.log_signal.emit(f"✅ 時段任務已完成 ({task_to_run['sch_start']}~{task_to_run['sch_end']})")
                    except Exception as e:
                        self.log_signal.emit(f"❌ 失敗 {script_file}: {e}")
                
                self.current_priority = 999 
                
                cooldown_jitter = np.random.uniform(1.0, 3.0)
                self.log_signal.emit(f"--- 冷卻休息 {cooldown_jitter:.1f} 秒 ---")
                if not self.smart_sleep(cooldown_jitter):
                    if not self.is_running: break 
                    else: continue
            else:
                if not self.smart_sleep(1.0):
                    if not self.is_running: break
                    else: continue
                
        self.finished_signal.emit()
    
    def stop(self): self.is_running = False