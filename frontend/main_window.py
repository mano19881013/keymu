# frontend/main_window.py
import sys
import os
import time
import json
import mss
import traceback
from datetime import datetime

# PySide6 元件
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QListWidget, QLabel, 
                               QMessageBox, QInputDialog, QFrame, QTextEdit, 
                               QAbstractItemView, QFileDialog, QTabWidget, 
                               QListWidgetItem, QCheckBox, QComboBox, QColorDialog,
                               QMenu)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QCursor, QAction

# 後端與工具引用
from backend.hardware import HardwareController
from backend.vision import VisionEye
from backend.plugin_base import PluginBase
from frontend.snipping_tool import SnippingWidget
from frontend.recorder import ActionRecorder
from frontend.overlay import OverlayWidget
from frontend.dialogs import SmartActionDialog, VisualPicker

# 拆分後的模組引用
from frontend.styles import DARK_THEME
from frontend.ui_components import DraggableButton, DropListWidget, TaskSettingsDialog
from frontend.workers import KeyListener, WatchdogThread, ScriptRunner, EngineBridge

from pynput import keyboard
import importlib.util

# ★ 新增：任務屬性設定檔路徑
TASKS_CONFIG_FILE = "tasks_config.json"

class MainWindow(QMainWindow):
    path_signal = Signal(list)
    stop_signal = Signal() 

    def __init__(self):
        super().__init__()
        self.setWindowTitle("系統計算機 - Pro Editor (Auto-Save Config)") 
        self.resize(1300, 800)
        self.setStyleSheet(DARK_THEME)

        self.hw = HardwareController(auto_connect=False)
        self.vision = VisionEye(monitor_index=1) 
        self.watchdog = None 
        self.ext_service = None 
        self.stop_listener = None 
        self.runner = None 

        self.script_data = [] 
        self.plugins = [] 
        self.snipper = None 
        self.picker = None 
        self.pending_region_action = None 
        self.pending_val = None
        self.task_buffer = [] 
        self.pending_drag_start = None
        
        # ★ 新增：任務設定字典
        self.tasks_config = {}
        self.load_tasks_config()

        self.recorder = ActionRecorder()
        self.recorder.finished_signal.connect(self.on_record_finished)
        self.overlay = OverlayWidget()
        self.overlay.show()

        self.path_signal.connect(self.overlay.draw_path)
        self.hw.set_debug_callback(self.path_signal.emit)
        
        self.stop_signal.connect(self.stop_all_tasks)

        for f in ["scripts", "extensions", "logic"]:
            if not os.path.exists(f): os.makedirs(f)

        self.tabs = QTabWidget(); self.setCentralWidget(self.tabs)
        self.tab_dashboard = QWidget(); self.init_dashboard(); self.tabs.addTab(self.tab_dashboard, "🎮 戰術儀表板")
        self.tab_editor = QWidget(); self.init_editor(); self.tabs.addTab(self.tab_editor, "📝 腳本編輯器")

    # ★ 新增：讀取任務設定檔
    def load_tasks_config(self):
        if os.path.exists(TASKS_CONFIG_FILE):
            try:
                with open(TASKS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.tasks_config = json.load(f)
            except:
                self.tasks_config = {}

    # ★ 新增：儲存任務設定檔
    def save_tasks_config(self):
        try:
            with open(TASKS_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.tasks_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"設定儲存失敗: {e}")

    def init_dashboard(self):
        layout = QHBoxLayout(self.tab_dashboard)
        
        left_layout = QVBoxLayout(); left_layout.addWidget(QLabel("📋 任務排程"))
        self.task_list_widget = DropListWidget()
        self.task_list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.refresh_tasks() 
        left_layout.addWidget(self.task_list_widget)
        
        btn_layout = QHBoxLayout()
        btn_up = QPushButton("⬆️"); btn_up.clicked.connect(self.dashboard_move_up)
        btn_down = QPushButton("⬇️"); btn_down.clicked.connect(self.dashboard_move_down)
        btn_settings = QPushButton("⚙️ 設定屬性"); btn_settings.clicked.connect(self.open_task_settings)
        btn_del_task = QPushButton("🗑️ 刪除"); btn_del_task.clicked.connect(self.dashboard_delete_script)
        
        btn_layout.addWidget(btn_up); btn_layout.addWidget(btn_down); btn_layout.addWidget(btn_settings); btn_layout.addWidget(btn_del_task)
        left_layout.addLayout(btn_layout)
        
        btn_refresh = QPushButton("🔄 重新整理"); btn_refresh.clicked.connect(self.refresh_tasks); left_layout.addWidget(btn_refresh)
        layout.addLayout(left_layout, 2)
        
        right_layout = QVBoxLayout(); right_panel = QFrame(); right_panel.setObjectName("Panel"); panel_layout = QVBoxLayout(right_panel)
        panel_layout.addWidget(QLabel("🔌 硬體連線設定"))
        hw_layout = QHBoxLayout()
        self.combo_ports = QComboBox(); self.btn_refresh_ports = QPushButton("🔄 掃描"); self.btn_refresh_ports.clicked.connect(self.refresh_ports)
        self.btn_connect_hw = QPushButton("🔗 連線"); self.btn_connect_hw.setObjectName("ConnectBtn"); self.btn_connect_hw.clicked.connect(self.connect_hardware)
        hw_layout.addWidget(self.combo_ports, 3); hw_layout.addWidget(self.btn_refresh_ports, 1); hw_layout.addWidget(self.btn_connect_hw, 1)
        panel_layout.addLayout(hw_layout)
        
        panel_layout.addSpacing(10); panel_layout.addWidget(QLabel("🖥️ 螢幕選擇"))
        self.combo_monitors = QComboBox()
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                if i == 0: continue 
                self.combo_monitors.addItem(f"螢幕 {i}: {m['width']}x{m['height']}", i)
        self.combo_monitors.currentIndexChanged.connect(self.on_monitor_changed)
        panel_layout.addWidget(self.combo_monitors)

        panel_layout.addSpacing(10); panel_layout.addWidget(QLabel("🎛️ 腳本控制"))
        self.btn_load_service = QPushButton("🔌 載入背景服務 (插件)")
        self.btn_load_service.setStyleSheet("background-color: #6f42c1; color: white;")
        self.btn_load_service.clicked.connect(self.load_external_service)
        panel_layout.addWidget(self.btn_load_service)

        self.chk_watchdog = QCheckBox("🐕 啟用安全監控"); self.chk_watchdog.setChecked(True); panel_layout.addWidget(self.chk_watchdog)
        self.chk_overlay = QCheckBox("👁️ 顯示視覺導引"); self.chk_overlay.setChecked(True); self.chk_overlay.stateChanged.connect(lambda: self.overlay.setVisible(self.chk_overlay.isChecked())); panel_layout.addWidget(self.chk_overlay)

        self.btn_run_all = QPushButton("▶ 開始掛機"); self.btn_run_all.setObjectName("RunBtn"); self.btn_run_all.clicked.connect(self.run_all_tasks)
        self.btn_stop_all = QPushButton("⏹ 全域停止"); self.btn_stop_all.setObjectName("StopBtn"); self.btn_stop_all.clicked.connect(self.stop_all_tasks); self.btn_stop_all.setEnabled(False)
        
        self.log_text_main = QTextEdit(); self.log_text_main.setReadOnly(True)
        panel_layout.addWidget(self.btn_run_all); panel_layout.addWidget(self.btn_stop_all); panel_layout.addWidget(QLabel("運行日誌:")); panel_layout.addWidget(self.log_text_main)
        
        right_layout.addWidget(right_panel); layout.addLayout(right_layout, 1)
        self.refresh_ports()

    # ★ 修改：刷新列表時，同時載入設定檔中的參數
    def refresh_tasks(self):
        self.task_list_widget.clear()
        # 重新載入設定檔以確保最新
        self.load_tasks_config()
        
        if os.path.exists("scripts"):
            for f in os.listdir("scripts"):
                if f.endswith(".json"): 
                    # 從 config 讀取參數，若無則使用預設值
                    conf = self.tasks_config.get(f, {})
                    priority = conf.get('priority', 1)
                    interval = conf.get('interval', 0)
                    mode = conf.get('mode', 0)
                    start_t = conf.get('start', "00:00")
                    end_t = conf.get('end', "23:59")
                    
                    # 組合顯示文字
                    p_icon = ["🔥", "⏺", "💤"][priority]
                    if mode == 0:
                        info_text = f" [🔁 {interval}s]" if interval > 0 else " [🔁 無冷卻]"
                    else:
                        info_text = f" [⏰ {start_t}-{end_t}]"
                    
                    item = QListWidgetItem(f"{p_icon}{info_text} {f}")
                    item.setData(Qt.UserRole, f)
                    item.setData(Qt.UserRole+1, priority)
                    item.setData(Qt.UserRole+2, interval)
                    item.setData(Qt.UserRole+3, mode)
                    item.setData(Qt.UserRole+4, start_t)
                    item.setData(Qt.UserRole+5, end_t)
                    
                    item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
                    # 預設不勾選，或可考慮也存下勾選狀態(進階)
                    item.setCheckState(Qt.Unchecked)
                    self.task_list_widget.addItem(item)

    def run_all_tasks(self):
        if self.runner and self.runner.isRunning(): return 

        task_objects = []
        for i in range(self.task_list_widget.count()):
            item = self.task_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                task_objects.append({
                    'path': os.path.join("scripts", item.data(Qt.UserRole)), 
                    'priority': item.data(Qt.UserRole+1) or 1, 
                    'interval': item.data(Qt.UserRole+2) or 0,
                    'mode': item.data(Qt.UserRole+3) or 0,
                    'sch_start': item.data(Qt.UserRole+4) or "00:00", 
                    'sch_end': item.data(Qt.UserRole+5) or "23:59",   
                    'last_run': 0
                })
        
        self.log_text_main.clear()
        self.btn_run_all.setEnabled(False)
        self.btn_stop_all.setEnabled(True)
        
        if not task_objects:
            self.log_text_main.append("[系統] 未選擇任務，進入待機模式 (等待插件或預約)...")

        if self.task_buffer:
            reply = QMessageBox.question(self, "暫存任務確認", 
                                         f"發現 {len(self.task_buffer)} 個來自插件的暫存任務。\n是否要執行？\n(選擇 No 將清除緩衝區)", 
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                self.task_buffer = []
                self.log_text_main.append("[系統] 已手動清除暫存任務。")

        self.runner = ScriptRunner(task_objects, self.hw, self.vision)
        self.runner.log_signal.connect(self.log_text_main.append)
        self.runner.draw_rect_signal.connect(self.overlay.draw_search_area)
        self.runner.draw_target_signal.connect(self.overlay.draw_target)
        self.runner.finished_signal.connect(self.on_all_finished)
        
        if self.task_buffer:
            added_count = 0
            now = datetime.now()
            for t in self.task_buffer:
                if (now - t['spawn_time']).total_seconds() < 3600:
                    self.runner.add_scheduled_task(t)
                    added_count += 1
            if added_count > 0: self.log_text_main.append(f"[系統] 已載入 {added_count} 個暫存的預約任務！")
            self.task_buffer = [] 

        self.start_emergency_listener()
        self.runner.start()
        
        if self.chk_watchdog.isChecked():
            self.watchdog = WatchdogThread(self.vision)
            self.watchdog.warning_signal.connect(self.log_text_main.append)
            self.watchdog.emergency_signal.connect(self.stop_all_tasks)
            self.watchdog.start()
        else:
            self.watchdog = None
            self.log_text_main.append("[系統] 看門狗已停用 (使用者設定)")
    
    # ★ 修改：設定完成後，立即寫入設定檔
    def open_task_settings(self):
        row = self.task_list_widget.currentRow()
        if row < 0: return
        item = self.task_list_widget.item(row)
        
        # 讀取現有值
        curr_p = item.data(Qt.UserRole + 1) or 1
        curr_i = item.data(Qt.UserRole + 2) or 0
        curr_m = item.data(Qt.UserRole + 3) or 0
        curr_s = item.data(Qt.UserRole + 4) or "00:00"
        curr_e = item.data(Qt.UserRole + 5) or "23:59"
        
        dlg = TaskSettingsDialog(self, curr_p, curr_i, curr_m, curr_s, curr_e)
        
        if dlg.exec():
            p, i, m, s, e = dlg.get_data()
            
            # 1. 更新 UI 上的資料
            item.setData(Qt.UserRole + 1, p)
            item.setData(Qt.UserRole + 2, i)
            item.setData(Qt.UserRole + 3, m)
            item.setData(Qt.UserRole + 4, s)
            item.setData(Qt.UserRole + 5, e)
            
            base_name = item.data(Qt.UserRole)
            p_icon = ["🔥", "⏺", "💤"][p]
            
            if m == 0:
                info_text = f" [🔁 {i}s]" if i > 0 else " [🔁 無冷卻]"
            else:
                info_text = f" [⏰ {s}-{e}]"
            item.setText(f"{p_icon}{info_text} {base_name}")
            
            # 2. 更新並儲存到 tasks_config.json
            self.tasks_config[base_name] = {
                'priority': p,
                'interval': i,
                'mode': m,
                'start': s,
                'end': e
            }
            self.save_tasks_config()
            self.log_text_main.append(f"[設定] 已儲存 {base_name} 的參數")

    def stop_all_tasks(self):
        if self.runner: 
            self.log_text_main.append(">>> 停止中...")
            if hasattr(self.runner, "scheduled_tasks") and self.runner.scheduled_tasks:
                valid_tasks = []
                now = datetime.now()
                for t in self.runner.scheduled_tasks:
                    if (now - t['spawn_time']).total_seconds() < 3600:
                        valid_tasks.append(t)
                if valid_tasks:
                    self.task_buffer.extend(valid_tasks)
                    self.log_text_main.append(f"[系統] 已將 {len(valid_tasks)} 個未執行任務存回緩衝區。")
            self.runner.stop()
            self.runner.wait()
            self.runner = None 
            
        if self.watchdog: self.watchdog.stop(); self.watchdog.wait(); self.log_text_main.append("[看門狗] 監控已結束")
        self.stop_emergency_listener() 
        self.btn_run_all.setEnabled(True)
        self.btn_stop_all.setEnabled(False)

    def on_all_finished(self):
        self.log_text_main.append(">>> 結束"); self.btn_run_all.setEnabled(True); self.btn_stop_all.setEnabled(False)
        if self.watchdog: self.watchdog.stop()
        self.stop_emergency_listener() 
        self.runner = None

    def start_emergency_listener(self):
        self.stop_listener = keyboard.Listener(on_press=self.on_emergency_key)
        self.stop_listener.start()
        self.log_text_main.append("[系統] 緊急停止監聽已啟動 (按 F12 停止)")

    def on_emergency_key(self, key):
        if key == keyboard.Key.f12:
            print("[系統] 偵測到 F12，執行緊急停止！")
            self.stop_signal.emit() 

    def stop_emergency_listener(self):
        if self.stop_listener:
            self.stop_listener.stop()
            self.stop_listener = None
    
    def dashboard_move_up(self):
        row = self.task_list_widget.currentRow()
        if row > 0: self.task_list_widget.insertItem(row-1, self.task_list_widget.takeItem(row)); self.task_list_widget.setCurrentRow(row-1)
    def dashboard_move_down(self):
        row = self.task_list_widget.currentRow()
        if row < self.task_list_widget.count()-1: self.task_list_widget.insertItem(row+1, self.task_list_widget.takeItem(row)); self.task_list_widget.setCurrentRow(row+1)
    def dashboard_delete_script(self):
        row = self.task_list_widget.currentRow()
        if row >= 0 and QMessageBox.question(self, "刪除", "確定刪除？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            try:
                os.remove(os.path.join("scripts", self.task_list_widget.item(row).data(Qt.UserRole)))
                self.refresh_tasks()
            except: pass
            
    def load_external_service(self):
        plugin_path, _ = QFileDialog.getOpenFileName(self, "選擇服務插件", "extensions", "Python (*.py)")
        if not plugin_path: return
        try:
            spec = importlib.util.spec_from_file_location("external_service", plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            service_class = None
            for attr_name in dir(module):
                if attr_name.endswith("Service") and attr_name != "QThread": service_class = getattr(module, attr_name); break
            if not service_class: QMessageBox.warning(self, "錯誤", "找不到合法的 Service 類別"); return
            self.ext_service = service_class()
            if hasattr(self.ext_service, 'setup'):
                if not self.ext_service.setup(self): return
            if hasattr(self.ext_service, 'log_signal'): self.ext_service.log_signal.connect(self.log_text_main.append)
            if hasattr(self.ext_service, 'schedule_signal'): self.ext_service.schedule_signal.connect(self.on_external_schedule)
            self.ext_service.start()
            self.btn_load_service.setText(f"🔌 運行中: {os.path.basename(plugin_path)}"); self.btn_load_service.setStyleSheet("background-color: #198754; color: white;")
        except Exception as e: QMessageBox.critical(self, "載入失敗", str(e)); traceback.print_exc()
        
    def on_external_schedule(self, task_info):
        boss_name = task_info.get('variables', {}).get('BOSS_NAME', '未知')
        if self.runner:
            self.runner.add_scheduled_task(task_info)
            wait_min = (task_info['start_time'] - datetime.now()).total_seconds() / 60
            if wait_min > 0: self.log_text_main.append(f"📅 [預約] {boss_name} 將在 {wait_min:.1f} 分鐘後執行")
            else: self.log_text_main.append(f"⚡ [緊急] {boss_name} 時間已到，立即插隊執行！")
        else:
            self.task_buffer.append(task_info)
            self.log_text_main.append(f"📥 [已暫存] 收到 {boss_name} 的任務 (等待開始掛機...)")
            
    def refresh_ports(self):
        self.combo_ports.clear(); ports = HardwareController.get_available_ports()
        if ports: self.combo_ports.addItems(ports)
        
    def connect_hardware(self):
        port_name = self.combo_ports.currentText().split(" - ")[0]
        if self.hw.connect(port_name): self.btn_connect_hw.setText("✅ 已連線"); self.btn_connect_hw.setStyleSheet("background-color: #198754;")
        else: self.btn_connect_hw.setText("❌ 失敗"); self.btn_connect_hw.setStyleSheet("background-color: #dc3545;")
        
    def on_monitor_changed(self, index): self.vision.set_monitor(self.combo_monitors.currentData())
    
    # ================= 編輯器區 (Editor) =================
    def init_editor(self):
        layout = QHBoxLayout(self.tab_editor)
        
        # 左側
        left_panel = QFrame(); left_panel.setObjectName("Panel"); self.left_layout = QVBoxLayout(left_panel); self.left_layout.addWidget(QLabel("🛠️ 基礎指令"))
        self.btn_rec = QPushButton("⏺ 錄製"); self.btn_rec.setObjectName("RecBtn"); self.btn_rec.setCheckable(True); self.btn_rec.clicked.connect(self.toggle_record); self.left_layout.addWidget(self.btn_rec)
        self.btn_insert = QPushButton("📂 插入"); self.btn_insert.setObjectName("InsertBtn"); self.btn_insert.clicked.connect(self.insert_saved_script); self.left_layout.addWidget(self.btn_insert)
        self.btn_open = QPushButton("📂 開啟"); self.btn_open.setObjectName("OpenBtn"); self.btn_open.clicked.connect(self.open_saved_script); self.left_layout.addWidget(self.btn_open)
        self.left_layout.addSpacing(10)
        
        self.add_drag_btn("🖱️ 新增點擊 (F8)", 'Click'); self.add_drag_btn("✂️ 截圖新增", 'Snip'); self.add_drag_btn("🖼️ 找圖點擊", 'FindImg')
        self.add_drag_btn("↔️ 新增拖曳", 'Drag')
        self.add_drag_btn("🔤 OCR 讀字", 'OCR'); self.add_drag_btn("🎨 找色點擊 (F8)", 'FindColor'); self.add_drag_btn("⏳ 新增等待", 'Wait'); self.add_drag_btn("⌨️ 新增按鍵", 'Key')
        self.add_drag_btn("🔁 循環限制", 'Loop')
        self.add_drag_btn("🏷️ 設定標籤", 'Label'); self.add_drag_btn("⤴️ 跳轉", 'Goto')
        self.add_drag_btn("📝 新增備註", 'Comment')
        
        self.left_layout.addStretch(); btn_save = QPushButton("💾 儲存"); btn_save.clicked.connect(self.save_current_script); self.left_layout.addWidget(btn_save)
        
        # 中間
        center_panel = QFrame(); center_panel.setObjectName("Panel"); center_layout = QVBoxLayout(center_panel); center_layout.addWidget(QLabel("📜 編輯區 (右鍵可測試)"))
        
        self.list_widget = DropListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self.edit_step)
        self.list_widget.itemDropped.connect(self.handle_dropped_item)
        
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        center_layout.addWidget(self.list_widget)
        
        # 底部按鈕 + 快捷鍵
        edit_layout = QHBoxLayout(); 
        btn_up = QPushButton("⬆️"); btn_up.clicked.connect(self.move_up); btn_up.setShortcut("Ctrl+Up")
        btn_down = QPushButton("⬇️"); btn_down.clicked.connect(self.move_down); btn_down.setShortcut("Ctrl+Down")
        btn_dup = QPushButton("📋 複製"); btn_dup.setStyleSheet("background-color: #17a2b8; color: white;"); btn_dup.clicked.connect(self.duplicate_step); btn_dup.setShortcut("Ctrl+D")
        btn_del = QPushButton("🗑️"); btn_del.setStyleSheet("background-color: #8B0000;"); btn_del.clicked.connect(self.delete_step); btn_del.setShortcut("Delete")
        
        edit_layout.addWidget(btn_up); edit_layout.addWidget(btn_down); edit_layout.addWidget(btn_dup); edit_layout.addWidget(btn_del)
        center_layout.addLayout(edit_layout)
        
        # 右側
        right_tabs = QTabWidget(); right_tabs.setStyleSheet("QTabBar::tab { font-size: 12px; padding: 5px; }")
        self.tab_plugins = QWidget(); plugin_layout = QVBoxLayout(self.tab_plugins); plugin_layout.addWidget(QLabel("🧩 插件庫")); self.plugin_list_widget = QListWidget(); self.plugin_list_widget.itemDoubleClicked.connect(self.add_plugin_from_list); plugin_layout.addWidget(self.plugin_list_widget); btn_refresh_plugins = QPushButton("🔄 重新整理"); btn_refresh_plugins.clicked.connect(self.refresh_plugin_list); plugin_layout.addWidget(btn_refresh_plugins); self.refresh_plugin_list(); right_tabs.addTab(self.tab_plugins, "🧩 插件")
        self.tab_logic = QWidget(); logic_layout = QVBoxLayout(self.tab_logic); logic_layout.addWidget(QLabel("🔀 邏輯指令")); self.logic_list_widget = QListWidget(); self.logic_list_widget.itemDoubleClicked.connect(self.add_logic_from_list)
        logic_items = [("🧠 智慧判斷", 'SmartAction'), ("🧠 插入邏輯插件", 'LogicPlugin'), ("❓ 若看到圖...", 'IfImage'), ("🏷️ 設定標籤", 'Label'), ("⤴️ 跳轉", 'Goto')]
        for name, code in logic_items: item = QListWidgetItem(name); item.setData(Qt.UserRole, code); self.logic_list_widget.addItem(item)
        logic_layout.addWidget(self.logic_list_widget); right_tabs.addTab(self.tab_logic, "🔀 邏輯")
        layout.addWidget(left_panel, 1); layout.addWidget(center_panel, 2); layout.addWidget(right_tabs, 1)

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return

        row = self.list_widget.row(item)
        menu = QMenu(self)

        action_test = QAction("⚡ 立即測試此行 (Test)", self)
        action_test.triggered.connect(lambda: self.test_single_step(row))
        menu.addAction(action_test)

        curr_data = self.script_data[row]
        is_disabled = curr_data.get('disabled', False)
        action_toggle = QAction("✅ 啟用" if is_disabled else "🚫 禁用 (Skip)", self)
        action_toggle.triggered.connect(lambda: self.toggle_step_enable(row))
        menu.addAction(action_toggle)
        
        menu.addSeparator()

        action_edit = QAction("✏️ 編輯 (Edit)", self)
        action_edit.triggered.connect(lambda: self.edit_step(item))
        menu.addAction(action_edit)

        action_dup = QAction("📋 複製 (Duplicate)", self)
        action_dup.triggered.connect(self.duplicate_step)
        menu.addAction(action_dup)

        menu.exec(self.list_widget.mapToGlobal(pos))

    def test_single_step(self, row):
        step = self.script_data[row]
        if step.get('disabled'):
            QMessageBox.warning(self, "略過", "此步驟已被禁用")
            return

        bridge = EngineBridge(self.hw, self.vision, lambda msg: print(f"[測試] {msg}"), lambda: False)
        try:
            print(f">>> 正在測試第 {row+1} 行: {step['type']}...")
            self.overlay.draw_search_area(0, 0, 100, 20) 
            
            temp_runner = ScriptRunner([{'path': 'temp'}], self.hw, self.vision)
            temp_runner.is_running = True
            temp_runner.execute_steps([step], bridge)
            
            QMessageBox.information(self, "測試完成", "指令已發送完畢 (請觀察遊戲畫面)")
        except Exception as e:
            QMessageBox.critical(self, "測試失敗", str(e))

    def toggle_step_enable(self, row):
        item = self.list_widget.item(row)
        curr = self.script_data[row]
        
        if curr.get('disabled', False):
            curr['disabled'] = False
            item.setForeground(Qt.white) 
            text = item.text().replace("[已停用] ", "")
            item.setText(text)
        else:
            curr['disabled'] = True
            item.setForeground(Qt.gray) 
            item.setText(f"[已停用] {item.text()}")

    def duplicate_step(self):
        row = self.list_widget.currentRow()
        if row < 0: return
        curr = self.script_data[row]
        new_data = curr.copy()
        self.script_data.insert(row + 1, new_data)
        item_text = self.list_widget.item(row).text()
        self.list_widget.insertItem(row + 1, item_text)
        self.list_widget.setCurrentRow(row + 1)
    
    def add_drag_btn(self, text, action_type, obj_name=None):
        btn = DraggableButton(text, action_type, self, obj_name)
        if action_type == 'Click': btn.clicked.connect(self.start_picking)
        elif action_type == 'Snip': btn.clicked.connect(lambda: self.start_snipping('save'))
        elif action_type == 'FindColor': btn.clicked.connect(self.start_picking_color)
        elif action_type == 'Drag': btn.clicked.connect(self.start_picking_drag) 
        else: btn.clicked.connect(lambda: self.add_step_handler(action_type))
        self.left_layout.addWidget(btn)
        
    def handle_btn_click(self, action_type):
        if action_type == 'Click': self.start_picking()
        elif action_type == 'Snip': self.start_snipping('save')
        elif action_type == 'FindColor': self.start_picking_color()
        elif action_type == 'Drag': self.start_picking_drag() 
        else: self.add_step_handler(action_type)
        
    def handle_dropped_item(self, action_type): self.handle_btn_click(action_type)
    
    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0: self.script_data[row], self.script_data[row-1] = self.script_data[row-1], self.script_data[row]; item = self.list_widget.takeItem(row); self.list_widget.insertItem(row-1, item); self.list_widget.setCurrentRow(row-1)
        
    def move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1: self.script_data[row], self.script_data[row+1] = self.script_data[row+1], self.script_data[row]; item = self.list_widget.takeItem(row); self.list_widget.insertItem(row+1, item); self.list_widget.setCurrentRow(row+1)
        
    def delete_step(self):
        row = self.list_widget.currentRow()
        if row >= 0: self.list_widget.takeItem(row); self.script_data.pop(row)
        
    def save_current_script(self):
        name, ok = QInputDialog.getText(self, "儲存", "名稱:")
        if ok and name:
            with open(f"scripts/{name}.json", 'w', encoding='utf-8') as f: json.dump(self.script_data, f, indent=4); self.refresh_tasks()
            
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

    def edit_step(self, item):
        row = self.list_widget.row(item)
        if row < 0: return
        curr = self.script_data[row]
        
        if curr['type'] == 'Plugin':
            plugin_filename = str(curr['val'])
            plugin_obj = self._load_plugin_instance(plugin_filename)
            if plugin_obj and hasattr(plugin_obj, 'edit_settings'):
                plugin_obj.edit_settings(self)
                item.setText(f"🧩 [插件] {plugin_obj.name}")
            else:
                QMessageBox.information(self, "資訊", "此插件沒有設定介面 (使用預設值)")
            return

        if curr['type'] == 'SmartAction':
            dlg = SmartActionDialog(self)
            dlg.set_data(curr['val'])
            if dlg.exec():
                new_val = dlg.get_data(); self.script_data[row]['val'] = new_val; parts = new_val.split('|'); item.setText(f"🧠 智慧: {parts[0]} '{parts[1]}'...")
        elif curr['type'] == 'Loop':
            old_parts = curr['val'].split('|')
            label, ok1 = QInputDialog.getText(self, "修改循環", "標籤名稱:", text=old_parts[0])
            if ok1 and label:
                count, ok2 = QInputDialog.getInt(self, "修改次數", "次數:", value=int(old_parts[1]))
                if ok2:
                    new_val = f"{label}|{count}"
                    self.script_data[row]['val'] = new_val
                    item.setText(f"🔁 循環至 '{label}' (限 {count} 次)")
        else:
            new_val, ok = QInputDialog.getText(self, f"修改 {curr['type']}", "參數:", text=str(curr['val']))
            if ok: 
                self.script_data[row]['val'] = new_val
                if curr['type'] == 'Comment': item.setText(f"📝 備註: {new_val}")
                elif curr['type'] == 'Click': item.setText(f"🖱️ 點擊座標 {new_val}")
                elif curr['type'] == 'Wait': item.setText(f"⏳ 等待 {new_val} 秒")
                elif curr['type'] == 'Key': item.setText(f"⌨️ 按鍵 {new_val}")
                elif curr['type'] == 'Drag': item.setText(f"↔️ 拖曳 ({new_val.replace('|', ') -> (')})")
                else: item.setText(item.text().replace(str(curr['val']), new_val))

    def insert_saved_script(self):
        filename, _ = QFileDialog.getOpenFileName(self, "選腳本", "scripts", "JSON (*.json)")
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f: steps = json.load(f)
                for step in steps: self.add_step_directly(step['type'], step['val'], step['text'])
            except Exception as e: QMessageBox.critical(self, "錯誤", f"{e}")
            
    def open_saved_script(self):
        filename, _ = QFileDialog.getOpenFileName(self, "開啟", "scripts", "JSON (*.json)")
        if filename:
            try:
                self.script_data = []; self.list_widget.clear()
                with open(filename, 'r', encoding='utf-8') as f: steps = json.load(f)
                for step in steps: 
                    text = step.get('text', f"{step['type']} {step['val']}")
                    self.add_step_directly(step['type'], step['val'], text)
            except Exception as e: QMessageBox.critical(self, "錯誤", f"{e}")
            
    def toggle_record(self):
        if self.btn_rec.isChecked(): self.btn_rec.setText("⏹ 停止"); self.showMinimized(); self.recorder.start()
        else: self.btn_rec.setText("⏺ 錄製"); self.recorder.stop()
        
    def on_record_finished(self, steps):
        self.showNormal(); self.btn_rec.setChecked(False); self.btn_rec.setText("⏺ 錄製")
        if steps:
            fname, _ = QFileDialog.getSaveFileName(self, "存檔", "scripts/rec.json", "JSON (*.json)")
            if fname:
                with open(fname, 'w', encoding='utf-8') as f: json.dump(steps, f, indent=4); self.refresh_tasks()
                
    def add_logic_from_list(self, item): self.add_step_handler(item.data(Qt.UserRole))
    
    def refresh_plugin_list(self):
        self.plugin_list_widget.clear()
        if not os.path.exists("extensions"): return
        for f in os.listdir("extensions"):
            if f.endswith(".py"):
                try:
                    spec = importlib.util.spec_from_file_location("module.name", os.path.join("extensions", f)); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase: 
                            item = QListWidgetItem(f"🧩 {attr.name}")
                            item.setData(Qt.UserRole, f) 
                            self.plugin_list_widget.addItem(item)
                except: pass
                
    def add_plugin_from_list(self, item): self.add_step_handler('Plugin', item.data(Qt.UserRole))
    
    def start_picking_color(self): self.showMinimized(); self.color_picker = KeyListener(mode='color'); self.color_picker.finished.connect(self.on_color_picked); self.color_picker.start()
    def on_color_picked(self, rgb): self.showNormal(); QMessageBox.information(self, "RGB", str(rgb))
    def start_picking(self): self.showMinimized(); self.picker = VisualPicker(mode='point'); self.picker.finished.connect(self.on_picked); self.picker.exec()
    def on_picked(self, val): self.showNormal(); self.add_step_directly('Click', val, f"🖱️ 點擊座標 {val}")
    def start_picking_drag(self): self.pending_drag_start = True; self.log_text_main.append(">>> [拖曳] 請選擇【起點】..."); self.showMinimized(); QTimer.singleShot(500, self._launch_picker)
    def _launch_picker(self): self.picker = VisualPicker(mode='point'); self.picker.finished_data.connect(self.on_picked); self.picker.exec()
    def start_snipping(self, mode='save'): self.showMinimized(); QTimer.singleShot(500, lambda: self._launch_snipper(mode))
    def _launch_snipper(self, mode): self.snipper = SnippingWidget(mode=mode); self.snipper.on_snipping_finish.connect(self.on_snipped); self.snipper.show()
    
    def on_snipped(self, result):
        self.showNormal(); self.activateWindow()
        if not result: return
        if self.snipper.mode == 'save': self.add_step_directly('FindImg', result, f"🖼️ 找圖 {result}")
        elif self.snipper.mode == 'region':
            if self.pending_region_action and self.pending_val:
                final_val = f"{self.pending_val}|{result}"
                if self.pending_region_action == 'SmartAction': self.add_step_directly('SmartAction', final_val, f"🧠 智慧動作 (含區域)")
                else: self.add_step_directly(self.pending_region_action, final_val, f"{self.pending_region_action} (區域: {result})")
            self.pending_region_action = None
            
    def add_step_directly(self, action_type, val, text_display):
        curr_row = self.list_widget.currentRow(); data = {'type': action_type, 'val': val, 'text': text_display}
        if curr_row >= 0: self.script_data.insert(curr_row + 1, data); self.list_widget.insertItem(curr_row + 1, text_display); self.list_widget.setCurrentRow(curr_row + 1)
        else: self.script_data.append(data); self.list_widget.addItem(text_display); self.list_widget.scrollToBottom()
        
    def add_step_handler(self, action_type, plugin_obj=None):
        val = None; text_display = ""
        if action_type == 'LogicPlugin':
            scripts = [f for f in os.listdir("logic") if f.endswith(".py") and f != "__init__.py"]
            item, ok = QInputDialog.getItem(self, "選擇", "邏輯腳本:", scripts, 0, False)
            if ok and item:
                label, ok2 = QInputDialog.getText(self, "跳轉", "成立跳至:")
                if ok2: val = f"{item}|{label}"; text_display = f"🧠 邏輯: {item} -> {label}"
        elif action_type == 'SmartAction':
            dlg = SmartActionDialog(self)
            if dlg.exec():
                val = dlg.get_data(); reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes: self.pending_region_action = 'SmartAction'; self.pending_val = val; self.start_snipping(mode='region'); return
                text_display = f"🧠 智慧動作"
        elif action_type == 'Key':
            from frontend.ui_components import KeySelectorDialog
            dlg = KeySelectorDialog(self)
            if dlg.exec(): name, code = dlg.get_selected(); val = code; text_display = f"⌨️ 按下 {name} ({code})"
        elif action_type == 'Wait': 
            val, ok = QInputDialog.getDouble(self, "等待", "秒:", value=0.3); text_display = f"⏳ 等待 {val} 秒" if ok else ""
        elif action_type == 'Loop':
            label, ok1 = QInputDialog.getText(self, "循環目標", "要跳回去的標籤名稱 (Label):")
            if ok1 and label:
                count, ok2 = QInputDialog.getInt(self, "循環次數", "最大執行次數:", value=5, minValue=1)
                if ok2: val = f"{label}|{count}"; text_display = f"🔁 循環至 '{label}' (限 {count} 次)"
        elif action_type == 'Comment': val, ok = QInputDialog.getText(self, "備註", "內容:"); 
        elif action_type == 'FindImg':
             img, _ = QFileDialog.getOpenFileName(self, "選圖", "assets", "Images (*.png)"); 
             if img: val = os.path.relpath(img); reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No)
             if reply == QMessageBox.Yes: self.pending_region_action = 'FindImg'; self.pending_val = val; self.start_snipping(mode='region'); return
             text_display = f"🖼️ 找圖 {val}"
        elif action_type == 'OCR':
             val, ok = QInputDialog.getText(self, "讀字", "關鍵字:"); 
             if ok: reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No)
             if reply == QMessageBox.Yes: self.pending_region_action = 'OCR'; self.pending_val = val; self.start_snipping(mode='region'); return
             text_display = f"🔤 OCR '{val}'"
        elif action_type == 'FindColor':
             color = QColorDialog.getColor()
             if color.isValid(): val = f"{color.red()},{color.green()},{color.blue()}"; reply = QMessageBox.question(self, "區域", "指定範圍？", QMessageBox.Yes | QMessageBox.No)
             if reply == QMessageBox.Yes: self.pending_region_action = 'FindColor'; self.pending_val = val; self.start_snipping(mode='region'); return
             text_display = f"🎨 找色 {val}"
        elif action_type == 'Plugin': 
            val = plugin_obj 
            temp = self._load_plugin_instance(val)
            text_display = f"🧩 [插件] {temp.name}" if temp else f"🧩 [插件] {val}"

        elif action_type == 'Label': val, ok = QInputDialog.getText(self, "標籤", "名稱:"); text_display = f"🏷️ 標籤: {val}" if ok else ""
        elif action_type == 'Goto': val, ok = QInputDialog.getText(self, "跳轉", "目標:"); text_display = f"⤴️ 跳轉至: {val}" if ok else ""
        elif action_type == 'IfImage':
             img, _ = QFileDialog.getOpenFileName(self, "圖片", "assets", "Images (*.png)"); 
             if img: label, ok = QInputDialog.getText(self, "成立後", "跳去:"); val = f"{os.path.relpath(img)}|{label}"; text_display = f"❓ 若見 '{os.path.basename(img)}' 跳至 '{label}'"
        if text_display: self.add_step_directly(action_type, val, text_display)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())