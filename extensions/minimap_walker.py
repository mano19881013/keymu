# extensions/minimap_walker.py
import time  # ★ 補上這行，解決 "time is not defined" 錯誤
import math
import random
import json
import os
import sys
import traceback

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, 
                               QComboBox, QSpinBox, QFormLayout, QFileDialog, 
                               QMessageBox, QApplication)
from PySide6.QtCore import Qt, QTimer

from backend.plugin_base import PluginBase

# 修正路徑問題
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# 嘗試載入截圖工具
try:
    from frontend.snipping_tool import SnippingWidget
except ImportError:
    SnippingWidget = None

CONFIG_FILE = "minimap_config.json"

class MinimapSettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("🗺️ 小地圖導航設定")
        self.resize(400, 300)
        self.settings = settings or {}
        self.snipper = None 
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 1. 小地圖範圍
        self.lbl_region = QLabel(self.settings.get('region', "尚未設定"))
        self.btn_region = QPushButton("🔍 框選小地圖範圍")
        self.btn_region.clicked.connect(self.select_region)
        form.addRow("小地圖區域:", self.lbl_region)
        form.addRow("", self.btn_region)

        # 2. Boss 圖示
        self.lbl_icon = QLabel(self.settings.get('icon', "尚未選擇"))
        self.btn_icon = QPushButton("📂 選擇 Boss 小圖示")
        self.btn_icon.clicked.connect(self.select_icon)
        form.addRow("目標圖示:", self.lbl_icon)
        form.addRow("", self.btn_icon)

        # 3. 移動模式
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["mouse", "keyboard"])
        self.combo_mode.setCurrentText(self.settings.get('mode', 'mouse'))
        form.addRow("移動模式:", self.combo_mode)

        # 4. 到達距離
        self.spin_dist = QSpinBox()
        self.spin_dist.setRange(5, 100)
        self.spin_dist.setValue(int(self.settings.get('arrival_dist', 15)))
        self.spin_dist.setSuffix(" px")
        form.addRow("到達判定距離:", self.spin_dist)

        layout.addLayout(form)

        btn_save = QPushButton("💾 儲存設定")
        btn_save.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 10px;")
        btn_save.clicked.connect(self.save_and_close)
        layout.addWidget(btn_save)

    def select_region(self):
        print("[DEBUG] 準備隱藏視窗 (變透明)...")
        self.setWindowOpacity(0)
        QApplication.processEvents()
        
        print("[DEBUG] 等待 0.3 秒...")
        QTimer.singleShot(300, self._delayed_snip)

    def _delayed_snip(self):
        print("[DEBUG] 開始啟動 SnippingWidget...")
        try:
            if SnippingWidget is None:
                raise ImportError("無法載入 SnippingWidget")

            self.snipper = SnippingWidget(mode='region')
            self.snipper.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
            self.snipper.setWindowModality(Qt.ApplicationModal)
            
            self.snipper.on_snipping_finish.connect(self.on_region_selected)
            self.snipper.show()
            print("[DEBUG] SnippingWidget 已顯示")
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print(f"[ERROR] 截圖工具啟動失敗: {error_msg}")
            
            self.setWindowOpacity(1)
            QMessageBox.critical(self, "啟動失敗", f"截圖工具啟動失敗：\n{e}")

    def on_region_selected(self, rect_str):
        print(f"[DEBUG] 截圖完成: {rect_str}")
        self.setWindowOpacity(1)
        self.activateWindow()
        
        if rect_str:
            self.lbl_region.setText(rect_str)
        self.snipper = None

    def select_icon(self):
        f, _ = QFileDialog.getOpenFileName(self, "選擇圖示", "assets", "Images (*.png)")
        if f:
            self.lbl_icon.setText(os.path.relpath(f))

    def save_and_close(self):
        data = {
            'region': self.lbl_region.text(),
            'icon': self.lbl_icon.text(),
            'mode': self.combo_mode.currentText(),
            'arrival_dist': self.spin_dist.value()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"存檔失敗: {e}")
            
        self.accept()

class MinimapWalker(PluginBase):
    name = "🗺️ 小地圖長途導航"

    def __init__(self):
        super().__init__()
        self.config = {}
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except: pass

    def edit_settings(self, parent_widget):
        self.load_config()
        dlg = MinimapSettingsDialog(parent_widget, self.config)
        if dlg.exec():
            self.load_config()

    def run(self, engine):
        self.load_config()
        
        region_str = self.config.get('region')
        icon_path = self.config.get('icon')
        mode = self.config.get('mode', 'mouse')
        arrival_dist = self.config.get('arrival_dist', 15)

        if not region_str or not icon_path or not os.path.exists(icon_path):
            engine.log("❌ [導航] 設定不完整，請在腳本列表點兩下此插件進行設定。")
            return

        try:
            region = tuple(map(int, region_str.split(',')))
        except:
            engine.log("❌ [導航] 區域格式錯誤")
            return

        center_x = region[2] // 2
        center_y = region[3] // 2
        
        engine.log(f"[導航] 🚀 啟動！目標: {icon_path}")
        
        keys = {'W': 87, 'A': 65, 'S': 83, 'D': 68} 
        max_attempts = 100 
        
        for i in range(max_attempts):
            pos = engine.vision.find_image(icon_path, confidence=0.7, region=region)
            
            if not pos:
                engine.log("[導航] ⚠️ 小地圖丟失目標")
                break
            
            abs_center_x = region[0] + center_x
            abs_center_y = region[1] + center_y
            dx = pos[0] - abs_center_x
            dy = pos[1] - abs_center_y
            dist = math.hypot(dx, dy)
            
            if dist < arrival_dist:
                engine.log("[導航] ✅ 到達目的地")
                engine.hw.release_all()
                return True
            
            if mode == 'keyboard':
                keys_to_press = []
                threshold = 10
                if dy < -threshold: keys_to_press.append(keys['W'])
                if dy > threshold:  keys_to_press.append(keys['S'])
                if dx < -threshold: keys_to_press.append(keys['A'])
                if dx > threshold:  keys_to_press.append(keys['D'])
                
                for k in keys_to_press: engine.hw.key_down(k)
                time.sleep(random.uniform(0.3, 0.6))
                for k in keys_to_press: engine.hw.key_up(k)
            else:
                step = 200
                screen_cx, screen_cy = engine.hw.screen_w // 2, engine.hw.screen_h // 2
                angle = math.atan2(dy, dx)
                tx = int(screen_cx + math.cos(angle) * step)
                ty = int(screen_cy + math.sin(angle) * step)
                
                engine.hw.move(tx, ty)
                time.sleep(0.1)
                engine.hw.click()
                time.sleep(engine.hw.brain.get_human_wait(1.0))

            if engine.should_stop(): break
            
        engine.hw.release_all()