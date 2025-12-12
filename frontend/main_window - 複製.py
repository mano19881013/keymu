# frontend/main_window.py
import sys
import time
import os
import traceback
import importlib.util 
import difflib 
import re 
import json
import mss
import cv2 
import numpy as np 
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QListWidget, QLabel, 
                               QMessageBox, QInputDialog, QFrame, QTextEdit, 
                               QAbstractItemView, QFileDialog, QDialog, QLineEdit, 
                               QColorDialog, QTabWidget, QListWidgetItem, QCheckBox, 
                               QComboBox, QFormLayout, QSpinBox, QDialogButtonBox)
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QCursor, QDrag, QPixmap
from PySide6.QtCore import QThread, Signal, Qt, QRect, QPoint, QMimeData
from pynput import keyboard
import pyautogui

from backend.hardware import HardwareController
from backend.vision import VisionEye
from backend.plugin_base import PluginBase
from backend.logic_plugin import LogicPluginBase
from frontend.snipping_tool import SnippingWidget
from frontend.recorder import ActionRecorder
from frontend.overlay import OverlayWidget
from frontend.dialogs import SmartActionDialog, VisualPicker

# --- 樣式表 (CSS) ---
DARK_THEME = """
QMainWindow { background-color: #1e1e1e; }
QWidget { color: #ffffff; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
QTabWidget::pane { border: 1px solid #444; }
QTabBar::tab { background: #2d2d30; color: #aaa; padding: 8px 15px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
QTabBar::tab:selected { background: #3e3e42; color: #fff; border-bottom: 2px solid #0d6efd; }
QPushButton { background-color: #3e3e42; border: 1px solid #555; border-radius: 5px; padding: 8px; }
QPushButton:hover { background-color: #505050; }
QPushButton:pressed { background-color: #0d6efd; }
QPushButton#RunBtn { background-color: #198754; font-weight: bold; }
QPushButton#StopBtn { background-color: #dc3545; font-weight: bold; }
QPushButton#ConnectBtn { background-color: #0d6efd; font-weight: bold; } 
QPushButton#RecBtn { background-color: #333333; border: 1px solid #ff4444; color: #ff4444; font-weight: bold; }
QPushButton#RecBtn:checked { background-color: #ff4444; color: white; }
QPushButton#PickBtn { background-color: #0dcaf0; font-weight: bold; color: black;}
QPushButton#SnipBtn { background-color: #d68a00; font-weight: bold; color: black;}
QPushButton#InsertBtn { background-color: #6f42c1; font-weight: bold; color: white; }
QPushButton#OpenBtn { background-color: #0d6efd; font-weight: bold; color: white; } 
QPushButton#SmartBtn { background-color: #ffc107; font-weight: bold; color: black; }
QPushButton#LogicBtn { background-color: #6610f2; font-weight: bold; }
QPushButton#OcrBtn { background-color: #d63384; font-weight: bold; }
QPushButton#ColorBtn { background-color: #fd7e14; font-weight: bold; }
QListWidget { background-color: #252526; border: 1px solid #444; border-radius: 5px; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background-color: #0d6efd; color: white; }
QTextEdit { background-color: #000000; color: #00ff00; font-family: Consolas; border: 1px solid #444; }
QFrame#Panel { background-color: #2d2d30; border-radius: 8px; padding: 10px; }
QDialog { background-color: #2d2d30; }
QMessageBox { background-color: #2d2d30; }
QInputDialog { background-color: #2d2d30; }
QColorDialog { background-color: #2d2d30; }
QLineEdit { background-color: #1e1e1e; color: #ffffff; border: 1px solid #555; border-radius: 4px; padding: 5px; }
QComboBox { background-color: #1e1e1e; color: #ffffff; border: 1px solid #555; padding: 5px; border-radius: 4px; }
QComboBox QAbstractItemView { background-color: #2d2d30; color: #ffffff; selection-background-color: #0d6efd; selection-color: #ffffff; border: 1px solid #555; }
QDoubleSpinBox, QSpinBox { background-color: #1e1e1e; color: #ffffff; border: 1px solid #555; border-radius: 4px; padding: 5px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { background-color: #3e3e42; }
QCheckBox { color: #ffffff; }
"""

class DraggableButton(QPushButton):
    def __init__(self, text, action_type, main_window, obj_name=None):
        super().__init__(text)
        self.action_type = action_type
        self.main_window = main_window 
        if obj_name: self.setObjectName(obj_name)
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton:
            drag = QDrag(self); mime = QMimeData(); mime.setText(self.action_type); drag.setMimeData(mime); drag.exec_(Qt.CopyAction)
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)

class DropListWidget(QListWidget):
    itemDropped = Signal(str) 
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True); self.setDragDropMode(QAbstractItemView.DragDrop); self.setDefaultDropAction(Qt.MoveAction)
    def dragEnterEvent(self, event):
        if event.mimeData().hasText(): event.accept()
        else: super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasText(): event.accept()
        else: super().dragMoveEvent(event)
    def dropEvent(self, event):
        if event.mimeData().hasText():
            action_type = event.mimeData().text()
            if action_type in ['Click', 'FindImg', 'OCR', 'FindColor', 'Wait', 'Key', 'SmartAction', 'IfImage', 'Label', 'Goto', 'LogicPlugin', 'Snip']:
                event.accept(); self.itemDropped.emit(action_type)
            else: super().dropEvent(event)
        else: super().dropEvent(event)

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

# --- 任務屬性設定對話框 ---
class TaskSettingsDialog(QDialog):
    def __init__(self, parent=None, current_priority=1, current_interval=0):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 任務屬性設定")
        self.resize(300, 200)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.combo_priority = QComboBox()
        self.combo_priority.addItems(["🔥 高 (High)", "⏺ 一般 (Normal)", "💤 低 (Low)"])
        self.combo_priority.setCurrentIndex(current_priority)
        
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(0, 99999)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setValue(current_interval)
        self.spin_interval.setSingleStep(5)
        
        form.addRow("優先等級:", self.combo_priority)
        form.addRow("定時執行 (間隔):", self.spin_interval)
        
        layout.addLayout(form)
        layout.addWidget(QLabel("提示：高優先級任務冷卻結束後會優先插隊執行。"))
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_data(self):
        return self.combo_priority.currentIndex(), self.spin_interval.value()

# --- 看門狗監控執行緒 ---
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

class EngineBridge:
    def __init__(self, hardware, vision, log_callback, stop_check_callback):
        self.hw = hardware; self.vision = vision; self.log = log_callback; self.should_stop = stop_check_callback

class ScriptRunner(QThread):
    log_signal = Signal(str); finished_signal = Signal(); draw_rect_signal = Signal(int, int, int, int); draw_target_signal = Signal(int, int)
    
    def __init__(self, task_objects, hardware, vision):
        super().__init__()
        self.hw = hardware
        self.vision = vision
        self.is_running = True
        
        # ★ 修復核心：資料格式防呆 (V17.2 FIX)
        # 確保 self.tasks 必定是字典列表，避免 TypeError
        self.tasks = []
        if task_objects and len(task_objects) > 0:
            if isinstance(task_objects[0], str):
                # 舊版相容：如果是字串列表，轉為預設字典
                for path in task_objects:
                    self.tasks.append({
                        'path': path,
                        'priority': 1, # 預設一般
                        'interval': 0, # 預設無CD
                        'last_run': 0
                    })
            else:
                # 新版：直接使用字典
                self.tasks = task_objects

    def smart_sleep(self, duration):
        start = time.time()
        while time.time() - start < duration:
            if not self.is_running: return False
            time.sleep(0.05)
        return True
    
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
        clean_t = re.sub(r'\s+', '', str(target))
        clean_d = re.sub(r'\s+', '', str(detected_text))
        if not clean_t or not clean_d: return False
        if clean_t in clean_d: return True
        hits = sum(1 for c in clean_t if c in clean_d)
        simple_ratio = hits / len(clean_t) if len(clean_t) > 0 else 0
        matcher = difflib.SequenceMatcher(None, clean_t, clean_d)
        diff_ratio = matcher.ratio()
        return diff_ratio >= threshold or simple_ratio >= threshold

    def execute_steps(self, steps, engine_bridge, depth=0):
        if depth > 3: self.log_signal.emit("❌ 錯誤: 腳本巢狀層數過深"); return
        i = 0
        while i < len(steps):
            if not self.is_running: break
            step = steps[i]; action = step['type']; val = step['val']; real_val, region = self.parse_val_region(val); region_msg = f" (範圍: {region})" if region else ""

            fatigue = self.hw.brain.get_reaction_multiplier()

            if action == 'Label': pass
            elif action == 'Goto':
                target = real_val; found = False
                for idx, s in enumerate(steps):
                    if s['type'] == 'Label' and s['val'] == target: i = idx; found = True; self.log_signal.emit(f"🔀 跳轉至: {target}"); break
                if not found: self.log_signal.emit(f"❌ 錯誤: 找不到標籤 {target}")
            elif action == 'LogicPlugin':
                try:
                    parts = str(val).split('|'); script_file = parts[0]; jump_label = parts[1]
                    self.log_signal.emit(f"🧠 載入邏輯: {script_file}")
                    file_path = os.path.join("logic", script_file)
                    if os.path.exists(file_path):
                        spec = importlib.util.spec_from_file_location("logic_mod", file_path); logic_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(logic_mod)
                        logic_instance = None
                        for attr_name in dir(logic_mod):
                            attr = getattr(logic_mod, attr_name)
                            if isinstance(attr, type) and issubclass(attr, LogicPluginBase) and attr is not LogicPluginBase: logic_instance = attr(); break
                        if logic_instance:
                            if logic_instance.check(engine_bridge):
                                self.log_signal.emit(f"   ✅ 條件成立！跳轉至 {jump_label}")
                                for idx, s in enumerate(steps):
                                    if s['type'] == 'Label' and s['val'] == jump_label: i = idx; break
                            else: self.log_signal.emit("   ❌ 條件不成立")
                except Exception as e: self.log_signal.emit(f"❌ 邏輯錯誤: {e}")
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
                        res = self.vision.ocr_screen(region=region)
                        self.log_signal.emit(f"   📋 OCR: {res}")
                        if any(self.is_text_match(target, t, threshold=threshold_val) for t in res): found_pos = (0, 0)
                    elif cond_type == 'FindColor':
                        rgb = tuple(map(int, target.split(',')))
                        found_pos = self.vision.find_color(rgb, tolerance=int(threshold_val), region=region)
                    if found_pos:
                        self.log_signal.emit(f"   ✅ 執行: {succ_act}")
                        if succ_act == 'ClickTarget' and found_pos: self.draw_target_signal.emit(found_pos[0], found_pos[1]); self.hw.move(found_pos[0], found_pos[1]); self.hw.click()
                        elif succ_act == 'ClickOffset' and found_pos:
                            off_x, off_y = map(int, succ_param.split(',')); final_x = found_pos[0] + off_x; final_y = found_pos[1] + off_y; self.draw_target_signal.emit(final_x, final_y); self.hw.move(final_x, final_y); self.hw.click()
                        elif succ_act == 'RunScript':
                            if os.path.exists(succ_param):
                                with open(succ_param, 'r', encoding='utf-8') as f: sub_steps = json.load(f); self.execute_steps(sub_steps, engine_bridge, depth + 1)
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
                                with open(fail_param, 'r', encoding='utf-8') as f: sub_steps = json.load(f); self.execute_steps(sub_steps, engine_bridge, depth + 1)
                        elif fail_act == 'Stop': self.is_running = False
                except Exception as e: self.log_signal.emit(f"❌ 智慧錯誤: {e}")
            elif action == 'Click':
                try: coords = real_val.split(','); x, y = int(coords[0]), int(coords[1]); self.draw_target_signal.emit(x, y); self.hw.move(x, y); self.hw.click()
                except: pass
            elif action == 'Wait':
                if not self.smart_sleep(float(real_val)): break
            elif action == 'Key': self.hw.press(int(real_val))
            elif action == 'FindImg':
                if os.path.exists(real_val):
                    self.log_signal.emit(f"👁️ 尋找: {real_val}{region_msg}")
                    if region: self.draw_rect_signal.emit(*region)
                    pos = self.vision.find_image(real_val, region=region)
                    if pos: self.draw_target_signal.emit(pos[0], pos[1]); self.hw.move(pos[0], pos[1]); self.hw.click()
                    else: self.log_signal.emit("⚠️ 沒找到")
            elif action == 'OCR':
                target_text = str(real_val).strip(); self.log_signal.emit(f"🔤 OCR: '{target_text}'{region_msg}...")
                try:
                    res = self.vision.ocr_screen(region=region); self.log_signal.emit(f"   📋 讀到: {res}")
                    found = False
                    for text in res:
                        if self.is_text_match(target_text, text, threshold=0.5): found = True; break
                    if found: self.log_signal.emit(f"✅ 發現！")
                    else: self.log_signal.emit(f"⚠️ 未發現")
                except Exception as e: self.log_signal.emit(f"❌ OCR 錯誤: {e}")
            elif action == 'FindColor':
                try:
                    rgb = tuple(map(int, real_val.split(','))); self.log_signal.emit(f"🎨 找色: RGB{rgb}{region_msg}")
                    pos = self.vision.find_color(rgb, tolerance=20, region=region)
                    if pos: self.draw_target_signal.emit(pos[0], pos[1]); self.hw.move(pos[0], pos[1]); self.hw.click(); self.log_signal.emit(f"✅ 發現顏色！")
                    else: self.log_signal.emit("⚠️ 未發現")
                except Exception as e: self.log_signal.emit(f"❌ 找色錯誤: {e}")
            elif action == 'Plugin': val.run(engine_bridge)

            # Wait 指令隨機化
            elif action == 'Wait':
                try:
                    base_wait = float(real_val)
                    jitter = np.random.uniform(0, base_wait * 0.1) 
                    final_wait = (base_wait * fatigue) + jitter
                    self.log_signal.emit(f"⏳ 等待 {base_wait}s (擬人修正->{final_wait:.2f}s)")
                    if not self.smart_sleep(final_wait): break
                except: pass

            should_inc = True
            if action == 'Goto': should_inc = False
            if action == 'SmartAction': pass
            if should_inc: i += 1
            
            step_gap = np.random.uniform(0.05, 0.2) * fatigue
            if not self.smart_sleep(step_gap): break

    def run(self):
        self.log_signal.emit(">>> 🚀 智慧排程器啟動 (Scheduler Mode)")
        engine_bridge = EngineBridge(self.hw, self.vision, lambda msg: self.log_signal.emit(msg), lambda: not self.is_running)
        
        while self.is_running:
            current_time = time.time()
            task_to_run = None
            
            # 1. 篩選
            available_tasks = []
            for task in self.tasks:
                if current_time - task['last_run'] >= task['interval']:
                    available_tasks.append(task)
            
            # 2. 排序
            if available_tasks:
                available_tasks.sort(key=lambda t: t['priority'])
                task_to_run = available_tasks[0]
            
            # 3. 執行
            if task_to_run:
                script_file = task_to_run['path']
                p_text = ["🔥高", "⏺中", "💤低"][task_to_run['priority']]
                
                self.log_signal.emit(f"--------------------------------")
                self.log_signal.emit(f"⚡ 執行任務 [{p_text}]: {os.path.basename(script_file)}")
                
                if os.path.exists(script_file):
                    try:
                        with open(script_file, 'r', encoding='utf-8') as f: steps = json.load(f)
                        self.execute_steps(steps, engine_bridge)
                        task_to_run['last_run'] = time.time()
                    except Exception as e:
                        self.log_signal.emit(f"❌ 失敗 {script_file}: {e}")
                
                # 隨機冷卻
                cooldown_jitter = np.random.uniform(1.0, 3.0)
                self.log_signal.emit(f"--- 冷卻休息 {cooldown_jitter:.1f} 秒 ---")
                if not self.smart_sleep(cooldown_jitter): break
            else:
                if not self.smart_sleep(1.0): break
                
        self.finished_signal.emit()
    
    def stop(self): self.is_running = False

class MainWindow(QMainWindow):
    path_signal = Signal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Py-Arduino 腳本大師 V17.2 (修復排程錯誤版)")
        self.resize(1300, 800)
        self.setStyleSheet(DARK_THEME)

        self.hw = HardwareController(auto_connect=False)
        self.vision = VisionEye(monitor_index=1) 
        self.watchdog = None 

        self.script_data = [] 
        self.plugins = [] 
        self.snipper = None 
        self.picker = None 
        self.pending_region_action = None 
        self.pending_val = None
        self.recorder = ActionRecorder()
        self.recorder.finished_signal.connect(self.on_record_finished)
        self.overlay = OverlayWidget()
        self.overlay.show()

        self.path_signal.connect(self.overlay.draw_path)
        self.hw.set_debug_callback(self.path_signal.emit)

        if not os.path.exists("scripts"): os.makedirs("scripts")
        if not os.path.exists("extensions"): os.makedirs("extensions")
        if not os.path.exists("logic"): os.makedirs("logic")

        self.tabs = QTabWidget(); self.setCentralWidget(self.tabs)
        self.tab_dashboard = QWidget(); self.init_dashboard(); self.tabs.addTab(self.tab_dashboard, "🎮 戰術儀表板")
        self.tab_editor = QWidget(); self.init_editor(); self.tabs.addTab(self.tab_editor, "📝 腳本編輯器")

    def init_dashboard(self):
        layout = QHBoxLayout(self.tab_dashboard)
        
        # --- 左側：任務排程 ---
        left_layout = QVBoxLayout(); left_layout.addWidget(QLabel("📋 任務排程"))
        self.task_list_widget = QListWidget(); self.task_list_widget.setDragDropMode(QAbstractItemView.InternalMove); self.refresh_tasks(); left_layout.addWidget(self.task_list_widget)
        
        # 按鈕區：排序 + 設定
        btn_layout = QHBoxLayout()
        btn_up = QPushButton("⬆️"); btn_up.clicked.connect(self.dashboard_move_up)
        btn_down = QPushButton("⬇️"); btn_down.clicked.connect(self.dashboard_move_down)
        btn_settings = QPushButton("⚙️ 設定屬性")
        btn_settings.clicked.connect(self.open_task_settings)
        btn_del_task = QPushButton("🗑️ 刪除檔案"); btn_del_task.clicked.connect(self.dashboard_delete_script)
        
        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        btn_layout.addWidget(btn_settings) 
        btn_layout.addWidget(btn_del_task)
        left_layout.addLayout(btn_layout)
        
        btn_refresh = QPushButton("🔄 重新整理列表"); btn_refresh.clicked.connect(self.refresh_tasks); left_layout.addWidget(btn_refresh)
        layout.addLayout(left_layout, 2)
        
        # --- 右側：指揮中心 ---
        right_layout = QVBoxLayout()
        right_panel = QFrame(); right_panel.setObjectName("Panel"); panel_layout = QVBoxLayout(right_panel)
        
        panel_layout.addWidget(QLabel("🔌 硬體連線設定"))
        hw_layout = QHBoxLayout()
        self.combo_ports = QComboBox()
        self.btn_refresh_ports = QPushButton("🔄 掃描")
        self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        self.btn_connect_hw = QPushButton("🔗 連線")
        self.btn_connect_hw.setObjectName("ConnectBtn")
        self.btn_connect_hw.clicked.connect(self.connect_hardware)
        hw_layout.addWidget(self.combo_ports, 3)
        hw_layout.addWidget(self.btn_refresh_ports, 1)
        hw_layout.addWidget(self.btn_connect_hw, 1)
        panel_layout.addLayout(hw_layout)
        
        panel_layout.addSpacing(10)
        panel_layout.addWidget(QLabel("🖥️ 螢幕選擇 (用於找圖)"))
        self.combo_monitors = QComboBox()
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                if i == 0: continue 
                self.combo_monitors.addItem(f"螢幕 {i}: {m['width']}x{m['height']} (Offset: {m['left']},{m['top']})", i)
        self.combo_monitors.currentIndexChanged.connect(self.on_monitor_changed)
        panel_layout.addWidget(self.combo_monitors)

        panel_layout.addSpacing(10)
        panel_layout.addWidget(QLabel("🎛️ 腳本控制"))

        self.chk_watchdog = QCheckBox("🐕 啟用安全監控 (Watchdog)")
        self.chk_watchdog.setChecked(True)
        panel_layout.addWidget(self.chk_watchdog)

        self.btn_run_all = QPushButton("▶ 開始掛機"); self.btn_run_all.setObjectName("RunBtn"); self.btn_run_all.clicked.connect(self.run_all_tasks)
        self.btn_stop_all = QPushButton("⏹ 全域停止"); self.btn_stop_all.setObjectName("StopBtn"); self.btn_stop_all.clicked.connect(self.stop_all_tasks); self.btn_stop_all.setEnabled(False)
        self.log_text_main = QTextEdit(); self.log_text_main.setReadOnly(True)
        panel_layout.addWidget(self.btn_run_all); panel_layout.addWidget(self.btn_stop_all); panel_layout.addWidget(QLabel("運行日誌:")); panel_layout.addWidget(self.log_text_main)
        right_layout.addWidget(right_panel); layout.addLayout(right_layout, 1)
        
        self.refresh_ports()

    # --- 任務屬性管理 ---
    def open_task_settings(self):
        row = self.task_list_widget.currentRow()
        if row < 0: return
        item = self.task_list_widget.item(row)
        
        curr_p = item.data(Qt.UserRole + 1) or 1 
        curr_i = item.data(Qt.UserRole + 2) or 0
        
        dlg = TaskSettingsDialog(self, curr_p, curr_i)
        if dlg.exec():
            p, i = dlg.get_data()
            item.setData(Qt.UserRole + 1, p)
            item.setData(Qt.UserRole + 2, i)
            base_name = item.data(Qt.UserRole)
            p_icon = ["🔥", "⏺", "💤"][p]
            i_text = f" [⏳{i}s]" if i > 0 else ""
            item.setText(f"{p_icon}{i_text} {base_name}")

    def dashboard_move_up(self):
        row = self.task_list_widget.currentRow()
        if row > 0:
            item = self.task_list_widget.takeItem(row)
            self.task_list_widget.insertItem(row-1, item)
            self.task_list_widget.setCurrentRow(row-1)
    def dashboard_move_down(self):
        row = self.task_list_widget.currentRow()
        if row < self.task_list_widget.count() - 1:
            item = self.task_list_widget.takeItem(row)
            self.task_list_widget.insertItem(row+1, item)
            self.task_list_widget.setCurrentRow(row+1)
    def dashboard_delete_script(self):
        row = self.task_list_widget.currentRow()
        if row < 0: return
        item = self.task_list_widget.item(row)
        fname = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "刪除", f"確定要永久刪除 {fname} 嗎？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                os.remove(os.path.join("scripts", fname))
                self.refresh_tasks()
                self.log_text_main.append(f"[系統] 已刪除 {fname}")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除失敗: {e}")

    def refresh_tasks(self):
        self.task_list_widget.clear()
        if os.path.exists("scripts"):
            for f in os.listdir("scripts"):
                if f.endswith(".json"): 
                    item = QListWidgetItem(f"⏺ {f}") 
                    item.setData(Qt.UserRole, f)     
                    item.setData(Qt.UserRole + 1, 1) 
                    item.setData(Qt.UserRole + 2, 0) 
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.task_list_widget.addItem(item)

    def run_all_tasks(self):
        task_objects = []
        for i in range(self.task_list_widget.count()):
            item = self.task_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                fname = item.data(Qt.UserRole)
                priority = item.data(Qt.UserRole + 1)
                interval = item.data(Qt.UserRole + 2)
                task_objects.append({
                    'path': os.path.join("scripts", fname),
                    'priority': priority,
                    'interval': interval,
                    'last_run': 0 
                })

        if task_objects: 
            self.log_text_main.clear(); self.btn_run_all.setEnabled(False); self.btn_stop_all.setEnabled(True)
            self.runner = ScriptRunner(task_objects, self.hw, self.vision)
            self.runner.log_signal.connect(self.log_text_main.append)
            self.runner.draw_rect_signal.connect(self.overlay.draw_search_area)
            self.runner.draw_target_signal.connect(self.overlay.draw_target)
            self.runner.finished_signal.connect(self.on_all_finished)
            self.runner.start()
            
            if self.chk_watchdog.isChecked():
                self.watchdog = WatchdogThread(self.vision)
                self.watchdog.warning_signal.connect(self.log_text_main.append)
                self.watchdog.emergency_signal.connect(self.stop_all_tasks)
                self.watchdog.start()
            else:
                self.watchdog = None
                self.log_text_main.append("[系統] 看門狗已停用 (使用者設定)")

    def stop_all_tasks(self):
        if self.runner: self.runner.stop(); self.log_text_main.append(">>> 停止中...")
        if self.watchdog:
            self.watchdog.stop()
            self.watchdog.wait()
            self.log_text_main.append("[看門狗] 監控已結束")

    def on_all_finished(self):
        self.log_text_main.append(">>> 結束"); self.btn_run_all.setEnabled(True); self.btn_stop_all.setEnabled(False)
        if self.watchdog:
            self.watchdog.stop()
            self.watchdog.wait()
    
    def on_monitor_changed(self, index):
        monitor_idx = self.combo_monitors.currentData()
        self.vision.set_monitor(monitor_idx)
        self.log_text_main.append(f"[系統] 已切換至螢幕 {monitor_idx}")

    def init_editor(self):
        layout = QHBoxLayout(self.tab_editor)
        left_panel = QFrame(); left_panel.setObjectName("Panel"); self.left_layout = QVBoxLayout(left_panel); self.left_layout.addWidget(QLabel("🛠️ 基礎指令 (可拖曳)"))
        self.btn_rec = QPushButton("⏺ 開始錄製"); self.btn_rec.setObjectName("RecBtn"); self.btn_rec.setCheckable(True); self.btn_rec.clicked.connect(self.toggle_record); self.left_layout.addWidget(self.btn_rec)
        self.btn_insert = QPushButton("📂 插入錄製腳本"); self.btn_insert.setObjectName("InsertBtn"); self.btn_insert.clicked.connect(self.insert_saved_script); self.left_layout.addWidget(self.btn_insert)
        self.btn_open = QPushButton("📂 開啟舊檔 (編輯)"); self.btn_open.setObjectName("OpenBtn"); self.btn_open.clicked.connect(self.open_saved_script); self.left_layout.addWidget(self.btn_open)
        self.left_layout.addSpacing(10)

        self.add_drag_btn("🖱️ 新增點擊 (F8)", 'Click', "PickBtn")
        self.add_drag_btn("✂️ 截圖新增", 'Snip', "SnipBtn")
        self.add_drag_btn("🖼️ 找圖點擊", 'FindImg')
        self.add_drag_btn("🔤 OCR 讀字", 'OCR', "OcrBtn")
        self.add_drag_btn("🎨 找色點擊 (F8)", 'FindColor', "ColorBtn")
        self.add_drag_btn("⏳ 新增等待", 'Wait')
        self.add_drag_btn("⌨️ 新增按鍵", 'Key')
        
        self.left_layout.addStretch()
        btn_save = QPushButton("💾 儲存腳本"); btn_save.clicked.connect(self.save_current_script); self.left_layout.addWidget(btn_save)
        
        center_panel = QFrame(); center_panel.setObjectName("Panel"); center_layout = QVBoxLayout(center_panel); center_layout.addWidget(QLabel("📜 編輯區"))
        self.list_widget = DropListWidget(); self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection); self.list_widget.itemDoubleClicked.connect(self.edit_step); self.list_widget.itemDropped.connect(self.handle_dropped_item); center_layout.addWidget(self.list_widget)
        edit_layout = QHBoxLayout()
        btn_up = QPushButton("⬆️"); btn_up.clicked.connect(self.move_up); btn_down = QPushButton("⬇️"); btn_down.clicked.connect(self.move_down); btn_del = QPushButton("🗑️"); btn_del.setStyleSheet("background-color: #8B0000;"); btn_del.clicked.connect(self.delete_step)
        edit_layout.addWidget(btn_up); edit_layout.addWidget(btn_down); edit_layout.addWidget(btn_del); center_layout.addLayout(edit_layout)
        
        right_tabs = QTabWidget(); right_tabs.setStyleSheet("QTabBar::tab { font-size: 12px; padding: 5px; }")
        self.tab_params = QWidget(); param_layout = QVBoxLayout(self.tab_params); param_layout.addWidget(QLabel("⚙️ 參數 (雙擊列表修改)")); param_layout.addStretch(); right_tabs.addTab(self.tab_params, "⚙️ 屬性")
        self.tab_plugins = QWidget(); plugin_layout = QVBoxLayout(self.tab_plugins); plugin_layout.addWidget(QLabel("🧩 插件庫 (雙擊加入)")); self.plugin_list_widget = QListWidget(); self.plugin_list_widget.itemDoubleClicked.connect(self.add_plugin_from_list); plugin_layout.addWidget(self.plugin_list_widget); btn_refresh_plugins = QPushButton("🔄 重新整理"); btn_refresh_plugins.clicked.connect(self.refresh_plugin_list); plugin_layout.addWidget(btn_refresh_plugins); self.refresh_plugin_list(); right_tabs.addTab(self.tab_plugins, "🧩 插件庫")
        
        self.tab_logic = QWidget(); logic_layout = QVBoxLayout(self.tab_logic); logic_layout.addWidget(QLabel("🔀 邏輯指令 (雙擊加入)")); self.logic_list_widget = QListWidget(); self.logic_list_widget.itemDoubleClicked.connect(self.add_logic_from_list)
        logic_items = [("🧠 智慧判斷 (If..Else)", 'SmartAction'), ("🧠 插入邏輯插件", 'LogicPlugin'), ("❓ 若看到圖... (If)", 'IfImage'), ("🏷️ 設定標籤", 'Label'), ("⤴️ 跳轉", 'Goto')]
        for name, code in logic_items: item = QListWidgetItem(name); item.setData(Qt.UserRole, code); self.logic_list_widget.addItem(item)
        logic_layout.addWidget(self.logic_list_widget); right_tabs.addTab(self.tab_logic, "🔀 邏輯庫")
        layout.addWidget(left_panel, 1); layout.addWidget(center_panel, 2); layout.addWidget(right_tabs, 1)

    def refresh_ports(self):
        self.combo_ports.clear()
        ports = HardwareController.get_available_ports()
        if ports:
            self.combo_ports.addItems(ports)
            self.log_text_main.append(f"[系統] 找到 {len(ports)} 個可用裝置")
        else:
            self.log_text_main.append("[系統] ⚠️ 未偵測到 COM Port (請確認驅動)")

    def connect_hardware(self):
        selected = self.combo_ports.currentText()
        if not selected:
            QMessageBox.warning(self, "錯誤", "請先選擇一個 COM Port")
            return
            
        port_name = selected.split(" - ")[0]
        
        self.log_text_main.append(f"[系統] 正在連線到 {port_name}...")
        QApplication.processEvents()
        
        if self.hw.connect(port_name):
            self.btn_connect_hw.setStyleSheet("background-color: #198754; color: white;")
            self.btn_connect_hw.setText("✅ 已連線")
            self.log_text_main.append("[系統] ✅ 硬體連線成功！")
        else:
            self.btn_connect_hw.setStyleSheet("background-color: #dc3545; color: white;")
            self.btn_connect_hw.setText("❌ 失敗")
            self.log_text_main.append("[系統] ❌ 連線失敗，請檢查被占用或拔插重試")

    def add_drag_btn(self, text, action_type, obj_name=None):
        btn = DraggableButton(text, action_type, self, obj_name)
        if action_type == 'Click': btn.clicked.connect(self.start_picking)
        elif action_type == 'Snip': btn.clicked.connect(lambda: self.start_snipping('save'))
        elif action_type == 'FindColor': btn.clicked.connect(self.start_picking_color)
        else: btn.clicked.connect(lambda: self.add_step_handler(action_type))
        self.left_layout.addWidget(btn)

    def handle_btn_click(self, action_type):
        if action_type == 'Click': self.start_picking()
        elif action_type == 'Snip': self.start_snipping('save')
        elif action_type == 'FindColor': self.start_picking_color()
        else: self.add_step_handler(action_type)

    def handle_dropped_item(self, action_type):
        if action_type == 'Click': self.start_picking()
        elif action_type == 'Snip': self.start_snipping('save')
        elif action_type == 'FindColor': self.start_picking_color()
        else: self.add_step_handler(action_type)

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            self.script_data[row], self.script_data[row-1] = self.script_data[row-1], self.script_data[row]
            item = self.list_widget.takeItem(row); self.list_widget.insertItem(row-1, item); self.list_widget.setCurrentRow(row-1)
    def move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1:
            self.script_data[row], self.script_data[row+1] = self.script_data[row+1], self.script_data[row]
            item = self.list_widget.takeItem(row); self.list_widget.insertItem(row+1, item); self.list_widget.setCurrentRow(row+1)
    def delete_step(self):
        row = self.list_widget.currentRow()
        if row >= 0: self.list_widget.takeItem(row); self.script_data.pop(row)

    def add_logic_from_list(self, item): self.add_step_handler(item.data(Qt.UserRole))
    def refresh_plugin_list(self):
        self.plugin_list_widget.clear()
        if not os.path.exists("extensions"): return
        for f in os.listdir("extensions"):
            if f.endswith(".py"):
                try:
                    file_path = os.path.join("extensions", f); spec = importlib.util.spec_from_file_location("module.name", file_path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                            item = QListWidgetItem(f"🧩 {attr.name}"); item.setData(Qt.UserRole, attr()); self.plugin_list_widget.addItem(item)
                except: pass
    def add_plugin_from_list(self, item): plugin = item.data(Qt.UserRole); self.add_step_handler('Plugin', plugin)
    def toggle_record(self):
        if self.btn_rec.isChecked(): self.btn_rec.setText("⏹ 停止錄製"); self.showMinimized(); self.recorder.start()
        else: self.btn_rec.setText("⏺ 開始錄製"); self.recorder.stop()
    def on_record_finished(self, steps):
        self.showNormal(); self.activateWindow(); self.btn_rec.setChecked(False); self.btn_rec.setText("⏺ 開始錄製")
        if not steps: return
        default_name = f"record_{datetime.now().strftime('%H%M%S')}"
        filename, _ = QFileDialog.getSaveFileName(self, "儲存", f"scripts/{default_name}.json", "JSON Files (*.json)")
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f: json.dump(steps, f, indent=4, ensure_ascii=False); QMessageBox.information(self, "成功", f"存檔成功"); self.refresh_tasks()
            except Exception as e: QMessageBox.critical(self, "錯誤", f"{e}")
    def insert_saved_script(self):
        filename, _ = QFileDialog.getOpenFileName(self, "選腳本", "scripts", "JSON (*.json)")
        if not filename: return
        try:
            with open(filename, 'r', encoding='utf-8') as f: steps = json.load(f)
            for step in steps: self.add_step_directly(step['type'], step['val'], step['text'])
            QMessageBox.information(self, "成功", f"插入 {len(steps)} 個動作")
        except Exception as e: QMessageBox.critical(self, "錯誤", f"{e}")
    
    def open_saved_script(self):
        filename, _ = QFileDialog.getOpenFileName(self, "開啟腳本", "scripts", "JSON (*.json)")
        if not filename: return
        self.script_data = []
        self.list_widget.clear()
        try:
            with open(filename, 'r', encoding='utf-8') as f: steps = json.load(f)
            for step in steps: 
                text = step.get('text', f"{step['type']} {step['val']}")
                self.add_step_directly(step['type'], step['val'], text)
            QMessageBox.information(self, "成功", f"已載入 {os.path.basename(filename)}")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"讀取失敗: {e}")

    def start_picking_color(self):
        self.showMinimized()
        self.color_picker = KeyListener(mode='color')
        self.color_picker.finished_signal.connect(self.on_color_picked)
        self.color_picker.start()
        print("請移動到目標顏色，按 F8 吸取...")
    def on_color_picked(self, rgb):
        self.showNormal(); self.activateWindow()
        if rgb:
            val = f"{rgb[0]},{rgb[1]},{rgb[2]}"; reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No); 
            if reply == QMessageBox.Yes: self.pending_region_action = 'FindColor'; self.pending_val = val; self.start_snipping(mode='region'); return; 
            self.add_step_directly('FindColor', val, f"🎨 找色 RGB({val})")
        else: QMessageBox.warning(self, "失敗", "吸色失敗")

    def start_picking(self):
        self.showMinimized(); self.picker = VisualPicker(mode='point'); self.picker.finished.connect(self.on_picked); self.picker.show()
    def on_picked(self, val):
        self.showNormal(); self.activateWindow(); self.add_step_directly('Click', val, f"🖱️ 點擊座標 {val}")
    def start_snipping(self, mode='save'):
        self.showMinimized(); time.sleep(0.3); self.snipper = SnippingWidget(mode=mode); self.snipper.on_snipping_finish.connect(self.on_snipped); self.snipper.show()
    def on_snipped(self, result):
        self.showNormal(); self.activateWindow(); 
        if not result: return
        if self.snipper.mode == 'save': self.add_step_directly('FindImg', result, f"🖼️ 找圖 {result}")
        elif self.snipper.mode == 'region':
            if self.pending_region_action and self.pending_val:
                final_val = f"{self.pending_val}|{result}"
                if self.pending_region_action == 'SmartAction':
                    # 直接串接資料
                    self.add_step_directly('SmartAction', final_val, f"🧠 智慧動作 (含區域)")
                elif self.pending_region_action == 'FindImg':
                    self.add_step_directly('FindImg', final_val, f"🖼️ 找圖 {self.pending_val} (區域: {result})")
                elif self.pending_region_action == 'OCR':
                    self.add_step_directly('OCR', final_val, f"🔤 OCR '{self.pending_val}' (區域: {result})")
                elif self.pending_region_action == 'FindColor':
                    self.add_step_directly('FindColor', final_val, f"🎨 找色 {self.pending_val} (區域: {result})")
            self.pending_region_action = None; self.pending_val = None
    
    def add_step_directly(self, action_type, val, text_display):
        curr_row = self.list_widget.currentRow()
        new_step_data = {'type': action_type, 'val': val, 'text': text_display}
        if curr_row >= 0: insert_idx = curr_row + 1; self.script_data.insert(insert_idx, new_step_data); self.list_widget.insertItem(insert_idx, text_display); self.list_widget.setCurrentRow(insert_idx)
        else: self.script_data.append(new_step_data); self.list_widget.addItem(text_display); self.list_widget.scrollToBottom()
    
    def add_step_handler(self, action_type, plugin_obj=None):
        val = None; text_display = ""
        if action_type == 'LogicPlugin':
            scripts = [f for f in os.listdir("logic") if f.endswith(".py") and f != "__init__.py"]
            if not scripts: QMessageBox.warning(self, "提示", "logic 資料夾是空的！"); return
            item, ok = QInputDialog.getItem(self, "選擇邏輯", "請選擇要使用的邏輯腳本:", scripts, 0, False)
            if ok and item:
                label, ok2 = QInputDialog.getText(self, "設定跳轉", "若條件成立，跳去哪個標籤？")
                if ok2: val = f"{item}|{label}"; text_display = f"🧠 邏輯: 若 {item} 成立 -> 跳至 {label}"
        elif action_type == 'Click': self.start_picking(); return 
        elif action_type == 'FindColor': self.start_picking_color(); return
        elif action_type == 'Label': val, ok = QInputDialog.getText(self, "標籤", "名稱:"); text_display = f"🏷️ 標籤: {val}" if ok else ""
        elif action_type == 'Goto': val, ok = QInputDialog.getText(self, "跳轉", "目標:"); text_display = f"⤴️ 跳轉至: {val}" if ok else ""
        elif action_type == 'SmartAction':
            dlg = SmartActionDialog(self); 
            if dlg.exec(): 
                val = dlg.get_data(); 
                reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No); 
                if reply == QMessageBox.Yes: 
                    self.pending_region_action = 'SmartAction'
                    self.pending_val = val
                    self.start_snipping(mode='region')
                    return
                text_display = f"🧠 智慧動作 (詳細參數隱藏)"
            else:
                return 
        elif action_type == 'FindImg':
            img, _ = QFileDialog.getOpenFileName(self, "選圖", "assets", "Images (*.png)"); 
            if img:
                try: val = os.path.relpath(img, os.getcwd())
                except: val = img
                reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes: 
                    self.pending_region_action = 'FindImg'
                    self.pending_val = val
                    self.start_snipping(mode='region')
                    return
                text_display = f"🖼️ 找圖 {val}"
            else:
                return 
        elif action_type == 'IfImage':
            img, _ = QFileDialog.getOpenFileName(self, "圖片", "assets", "Images (*.png)"); 
            if img:
                try: val = f"{os.path.relpath(img, os.getcwd())}"; 
                except: val = f"{img}"
                label, ok = QInputDialog.getText(self, "成立後", "跳去哪個標籤？")
                if ok: val += f"|{label}"; text_display = f"❓ 若看到 '{os.path.basename(img)}' 則跳至 '{label}'"
        elif action_type == 'OCR':
            val, ok = QInputDialog.getText(self, "讀字", "關鍵字:", text="Boss")
            if ok: 
                reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No); 
                if reply == QMessageBox.Yes: 
                    self.pending_region_action = 'OCR'
                    self.pending_val = val
                    self.start_snipping(mode='region')
                    return
                text_display = f"🔤 OCR '{val}' (全螢幕)"
            else:
                return
        elif action_type == 'FindColor':
            color = QColorDialog.getColor(); 
            if color.isValid(): 
                val = f"{color.red()},{color.green()},{color.blue()}"; 
                reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No); 
                if reply == QMessageBox.Yes: 
                    self.pending_region_action = 'FindColor'
                    self.pending_val = val
                    self.start_snipping(mode='region')
                    return
                text_display = f"🎨 找色 RGB({val})"
            else:
                return
        elif action_type == 'Wait': val, ok = QInputDialog.getDouble(self, "等待", "秒:", value=1.0); text_display = f"⏳ 等待 {val} 秒" if ok else ""
        elif action_type == 'Key': val, ok = QInputDialog.getInt(self, "按鍵", "Code:", value=194); text_display = f"⌨️ 按下按鍵 {val}" if ok else ""
        elif action_type == 'Plugin': val = plugin_obj; text_display = f"🧩 [插件] {val.name}"
        
        if text_display: self.add_step_directly(action_type, val, text_display)
    
    def edit_step(self, item):
        row = self.list_widget.row(item)
        if row < 0: return
        curr_data = self.script_data[row]
        curr_val = curr_data['val']
        curr_type = curr_data['type']
        if isinstance(curr_val, str) or isinstance(curr_val, int) or isinstance(curr_val, float):
            new_val, ok = QInputDialog.getText(self, f"修改 {curr_type}", "參數數值:", text=str(curr_val))
            if ok:
                self.script_data[row]['val'] = new_val
                item.setText(item.text().replace(str(curr_val), new_val))
        else:
             QMessageBox.information(self, "提示", "此項目為複雜物件，建議刪除後重新新增")

    def save_current_script(self):
        name, ok = QInputDialog.getText(self, "儲存", "名稱:")
        if ok and name:
            with open(f"scripts/{name}.json", 'w', encoding='utf-8') as f: json.dump(self.script_data, f, indent=4, ensure_ascii=False); self.refresh_tasks()
    def refresh_tasks(self):
        self.task_list_widget.clear()
        if os.path.exists("scripts"):
            for f in os.listdir("scripts"):
                if f.endswith(".json"): item = QListWidgetItem(f); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked); self.task_list_widget.addItem(item)
    def run_all_tasks(self):
        sel = [os.path.join("scripts", self.task_list_widget.item(i).text()) for i in range(self.task_list_widget.count()) if self.task_list_widget.item(i).checkState() == Qt.Checked]
        if sel: 
            self.log_text_main.clear(); self.btn_run_all.setEnabled(False); self.btn_stop_all.setEnabled(True)
            self.runner = ScriptRunner(sel, self.hw, self.vision)
            self.runner.log_signal.connect(self.log_text_main.append)
            self.runner.draw_rect_signal.connect(self.overlay.draw_search_area)
            self.runner.draw_target_signal.connect(self.overlay.draw_target)
            self.runner.finished_signal.connect(self.on_all_finished)
            self.runner.start()
            
            if self.chk_watchdog.isChecked():
                self.watchdog = WatchdogThread(self.vision)
                self.watchdog.warning_signal.connect(self.log_text_main.append)
                self.watchdog.emergency_signal.connect(self.stop_all_tasks)
                self.watchdog.start()
            else:
                self.watchdog = None
                self.log_text_main.append("[系統] 看門狗已停用 (使用者設定)")

    def stop_all_tasks(self):
        if self.runner: self.runner.stop(); self.log_text_main.append(">>> 停止中...")
        if self.watchdog:
            self.watchdog.stop()
            self.watchdog.wait()
            self.log_text_main.append("[看門狗] 監控已結束")

    def on_all_finished(self):
        self.log_text_main.append(">>> 結束"); self.btn_run_all.setEnabled(True); self.btn_stop_all.setEnabled(False)
        if self.watchdog:
            self.watchdog.stop()
            self.watchdog.wait()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())