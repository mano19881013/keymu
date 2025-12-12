# extensions/boss_plugin.py
import time
import json
import os
import datetime
import traceback
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLabel, QFileDialog, QCheckBox, QMessageBox, QWidget, QFrame, QSpinBox)

# 用來記錄「上次選的檔案路徑」的設定檔
SERVICE_CONFIG_FILE = "boss_service_config.json"

class BossDashboard(QDialog):
    """
    Boss 戰術儀表板介面
    """
    # 定義訊號
    reset_paths_signal = Signal()
    force_run_signal = Signal(dict) # 強制執行訊號

    def __init__(self, parent=None, profile_data=None, timer_path=None, config_file="boss_plugin_config.json"):
        super().__init__(parent)
        self.setWindowTitle("🛡️ Boss 戰術儀表板 (Ultimate)")
        self.resize(950, 720) 
        
        self.profile_data = profile_data
        self.timer_path = timer_path 
        self.config_file = config_file 
        
        self.mapping = {} 
        self.active_bosses = set() 
        self.confirmed = False
        self.test_script_path = None
        
        # 預設值
        self.expiration_minutes = 60
        self.allow_interrupt = True 
        
        # 1. 先讀取設定到變數
        self.load_config()
        # 2. 再建立介面 (會使用變數)
        self.init_ui()
        # 3. 最後刷新表格
        self.refresh_table()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- 資訊區 ---
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #2d2d30; border-radius: 5px; padding: 5px;")
        info_layout = QVBoxLayout(info_frame)
        
        info_label = QLabel("💡 全功能版：支援插隊開關、過期設定、持續補單與心跳回報。\n等級高的 Boss 擁有預設優先權。")
        info_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        info_layout.addWidget(info_label)
        
        path_text = self.timer_path if self.timer_path else "❌ 未偵測到 (無法監控)"
        path_label = QLabel(f"📂 監控目標: {path_text}")
        path_label.setStyleSheet("color: #aaa; font-size: 12px;")
        info_layout.addWidget(path_label)
        
        layout.addWidget(info_frame)
        
        # --- 設定區 ---
        setting_layout = QHBoxLayout()
        
        # 1. 過期時間
        setting_layout.addWidget(QLabel("⏳ 過期時間(分):"))
        self.spin_expiration = QSpinBox()
        self.spin_expiration.setRange(10, 300)
        # ★ 這裡會使用 load_config 讀到的值
        self.spin_expiration.setValue(self.expiration_minutes)
        self.spin_expiration.setSuffix(" 分鐘")
        setting_layout.addWidget(self.spin_expiration)
        
        setting_layout.addSpacing(20)

        # 2. 插隊開關
        self.chk_interrupt = QCheckBox("⚡ 允許插隊 (優先執行)")
        # ★ 這裡會使用 load_config 讀到的值
        self.chk_interrupt.setChecked(self.allow_interrupt)
        self.chk_interrupt.setStyleSheet("color: #ffc107; font-weight: bold;")
        self.chk_interrupt.setToolTip("若勾選，Boss 任務會中斷目前的掛機腳本。\n若取消，Boss 任務會排隊等待當前腳本跑完。")
        setting_layout.addWidget(self.chk_interrupt)

        setting_layout.addStretch()
        layout.addLayout(setting_layout)

        # --- 表格區 ---
        self.table = QTableWidget()
        self.table.setColumnCount(7) 
        self.table.setHorizontalHeaderLabels(["啟用", "Boss", "等級", "ID", "指定腳本", "設定", "測試"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Name
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch) # Script
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # --- 按鈕區 ---
        btn_layout = QHBoxLayout()
        
        self.btn_set_all = QPushButton("📂 全部套用通用腳本")
        self.btn_set_all.clicked.connect(self.set_all_scripts)
        
        self.btn_reset = QPushButton("🔄 重選檔案")
        self.btn_reset.setStyleSheet("background-color: #6c757d; color: white;")
        self.btn_reset.clicked.connect(self.on_reset_clicked)

        self.btn_save = QPushButton("💾 儲存設定")
        self.btn_save.clicked.connect(self.on_save_clicked)
        
        self.btn_test = QPushButton("🧪 測試 (1分後)")
        self.btn_test.setStyleSheet("background-color: #17a2b8; color: white;")
        self.btn_test.clicked.connect(self.on_test_clicked)
        
        self.btn_start = QPushButton("🚀 開始監控")
        self.btn_start.setStyleSheet("background-color: #198754; color: white; font-weight: bold; font-size: 14px; padding: 10px;")
        self.btn_start.clicked.connect(self.on_start)
        
        btn_layout.addWidget(self.btn_set_all)
        btn_layout.addWidget(self.btn_reset) 
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_test)
        btn_layout.addWidget(self.btn_save)  
        btn_layout.addWidget(self.btn_start)
        layout.addLayout(btn_layout)

    def on_test_clicked(self):
        f, _ = QFileDialog.getOpenFileName(self, "選擇測試用的腳本", "scripts", "JSON (*.json)")
        if f:
            self.test_script_path = f
            QMessageBox.information(self, "測試", f"已排程測試任務！\n按下「開始監控」後，將在 1 分鐘後執行：\n{os.path.basename(f)}")

    def refresh_table(self):
        self.table.setRowCount(0)
        timers = self.profile_data.get('timers', [])
        
        bosses = [t for t in timers if t.get('type') == 'floating']
        bosses.sort(key=lambda x: x.get('level', 0), reverse=True)
        
        self.table.setRowCount(len(bosses))
        
        for row, boss in enumerate(bosses):
            boss_id = boss['id']
            boss_name = boss['name']
            boss_level = boss.get('level', 0)
            
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget); chk_layout.setContentsMargins(0,0,0,0); chk_layout.setAlignment(Qt.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(boss_id in self.active_bosses)
            chk.stateChanged.connect(lambda state, bid=boss_id: self.toggle_boss(bid, state))
            chk_layout.addWidget(chk)
            self.table.setCellWidget(row, 0, chk_widget)

            self.table.setItem(row, 1, QTableWidgetItem(boss_name))
            self.table.setItem(row, 2, QTableWidgetItem(str(boss_level)))
            self.table.setItem(row, 3, QTableWidgetItem(boss_id))
            
            current_script = self.mapping.get(boss_id, "")
            script_name = os.path.basename(current_script) if current_script else "⚠️ 未設定"
            item_script = QTableWidgetItem(script_name)
            if not current_script: item_script.setForeground(Qt.red)
            self.table.setItem(row, 4, item_script)
            
            btn = QPushButton("選擇...")
            btn.clicked.connect(lambda _, r=row, bid=boss_id: self.select_script(r, bid))
            self.table.setCellWidget(row, 5, btn)
            
            btn_force = QPushButton("⚡"); btn_force.setToolTip("立即執行"); btn_force.setStyleSheet("background-color: #ffc107; color: black; font-weight: bold;")
            btn_force.clicked.connect(lambda _, bid=boss_id, bname=boss_name: self.force_run_boss(bid, bname))
            self.table.setCellWidget(row, 6, btn_force)

    def force_run_boss(self, boss_id, boss_name):
        script_path = self.mapping.get(boss_id)
        if not script_path or not os.path.exists(script_path):
            QMessageBox.warning(self, "錯誤", f"尚未設定 {boss_name} 的腳本，或檔案不存在。")
            return
            
        task = {
            'script_path': script_path,
            'start_time': datetime.datetime.now(), 
            'spawn_time': datetime.datetime.now(),
            'variables': {'BOSS_NAME': boss_name},
            'priority': 0 
        }
        
        self.force_run_signal.emit(task)
        QMessageBox.information(self, "發送成功", f"已發送【{boss_name}】的立即執行指令！\n請確認主程式已按下「開始掛機」。")

    def toggle_boss(self, boss_id, state):
        if state == 2: self.active_bosses.add(boss_id)
        else:
            if boss_id in self.active_bosses: self.active_bosses.remove(boss_id)
    def select_script(self, row, boss_id):
        f, _ = QFileDialog.getOpenFileName(self, f"選擇 [{boss_id}] 的腳本", "scripts", "JSON (*.json)")
        if f:
            self.mapping[boss_id] = f
            self.table.setItem(row, 4, QTableWidgetItem(os.path.basename(f)))
            self.active_bosses.add(boss_id)
            self.refresh_table_row_check(row, True)
    def set_all_scripts(self):
        f, _ = QFileDialog.getOpenFileName(self, "選擇通用腳本 (套用到全部)", "scripts", "JSON (*.json)")
        if f:
            for row in range(self.table.rowCount()):
                boss_id = self.table.item(row, 3).text()
                self.mapping[boss_id] = f
                self.table.setItem(row, 4, QTableWidgetItem(os.path.basename(f)))
                self.active_bosses.add(boss_id)
                self.refresh_table_row_check(row, True)
    def refresh_table_row_check(self, row, checked):
        cell_widget = self.table.cellWidget(row, 0)
        if cell_widget: cell_widget.findChild(QCheckBox).setChecked(checked)

    # ★ 關鍵修正：只讀取資料，不操作介面
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.mapping = data.get('mapping', {})
                    self.active_bosses = set(data.get('active_bosses', []))
                    self.expiration_minutes = data.get('expiration', 60)
                    self.allow_interrupt = data.get('allow_interrupt', True)
            except: pass

    def save_config(self):
        self.expiration_minutes = self.spin_expiration.value()
        self.allow_interrupt = self.chk_interrupt.isChecked()
        data = {
            'mapping': self.mapping, 
            'active_bosses': list(self.active_bosses),
            'expiration': self.expiration_minutes,
            'allow_interrupt': self.allow_interrupt
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e: QMessageBox.warning(self, "錯誤", f"存檔失敗: {e}")

    def on_reset_clicked(self):
        if QMessageBox.question(self, "重設", "確定要重選檔案路徑？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            self.reset_paths_signal.emit()
            self.reject()

    def on_save_clicked(self):
        self.save_config()
        QMessageBox.information(self, "儲存", "設定已儲存！")

    def on_start(self):
        self.save_config()
        self.confirmed = True
        self.accept()


class BossPluginService(QThread):
    log_signal = Signal(str)
    schedule_signal = Signal(dict) 
    
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.json_path = None     
        self.profile_path = None
        self.universal_script = None
        self.profile_data = None  
        self.mapping = {}         
        self.active_bosses = set()
        self.pre_notify_minutes = 2
        self.expiration_minutes = 60 
        self.allow_interrupt = True 
        self.last_mtime = 0
        self.id_name_map = {} 
        self.id_level_map = {} 
        self.test_script = None 
        self.sent_tasks_cache = set()
        self.last_sent_time = {} 
        self.heartbeat_counter = 0

    def load_service_settings(self):
        if os.path.exists(SERVICE_CONFIG_FILE):
            try:
                with open(SERVICE_CONFIG_FILE, 'r', encoding='utf-8') as f: data = json.load(f); self.json_path = data.get('timers_file'); self.profile_path = data.get('profile_file'); self.universal_script = data.get('script_file'); self.pre_notify_minutes = data.get('pre_notify', 2); return True
            except: pass
        return False
    def save_service_settings(self):
        try:
            with open(SERVICE_CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump({'timers_file': self.json_path, 'profile_file': self.profile_path, 'script_file': self.universal_script, 'pre_notify': self.pre_notify_minutes}, f, indent=2, ensure_ascii=False)
        except: pass
    def clear_service_settings(self):
        if os.path.exists(SERVICE_CONFIG_FILE): os.remove(SERVICE_CONFIG_FILE)
        self.json_path = None; self.profile_path = None

    def setup(self, parent_widget):
        self.load_service_settings()
        files_valid = (self.json_path and os.path.exists(self.json_path) and self.profile_path and os.path.exists(self.profile_path))
        if not files_valid:
            f, _ = QFileDialog.getOpenFileName(parent_widget, "步驟 1/2: 選擇 timers_data.json", "", "JSON (*.json)"); 
            if not f: return False
            self.json_path = f
            p, _ = QFileDialog.getOpenFileName(parent_widget, "步驟 2/2: 選擇 game_profile.json", os.path.dirname(f), "JSON (*.json)")
            if not p: return False
            self.profile_path = p
            self.save_service_settings()
            
        try:
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                self.profile_data = json.load(f)
            for t in self.profile_data.get('timers', []):
                if t.get('type') == 'floating': 
                    self.id_name_map[t['id']] = t['name']
                    self.id_level_map[t['id']] = t.get('level', 0)
        except Exception as e:
            QMessageBox.critical(parent_widget, "錯誤", f"讀取設定檔失敗: {e}"); self.clear_service_settings(); return False

        while True: 
            dashboard = BossDashboard(parent_widget, self.profile_data, self.json_path)
            dashboard.reset_paths_signal.connect(self.clear_service_settings)
            dashboard.force_run_signal.connect(self.on_force_run)
            result = dashboard.exec()
            if result: 
                self.mapping = dashboard.mapping; self.active_bosses = dashboard.active_bosses; self.test_script = dashboard.test_script_path
                self.expiration_minutes = dashboard.expiration_minutes
                self.allow_interrupt = dashboard.allow_interrupt
                return True
            if not os.path.exists(SERVICE_CONFIG_FILE): return self.setup(parent_widget)
            return False 
    
    def on_force_run(self, task):
        self.schedule_signal.emit(task)
        self.log_signal.emit(f"[插件] ⚡ 已發送立即執行指令：{task['variables']['BOSS_NAME']}")

    def run(self):
        self.log_signal.emit(f"[插件] 🛡️ Boss 戰術中心已啟動 (Pro)")
        self.log_signal.emit(f"[插件] 監控檔案: {os.path.basename(self.json_path)}")
        self.log_signal.emit(f"[插件] 監控目標: {len(self.active_bosses)} 隻 Boss")
        
        if self.test_script:
            test_time = datetime.datetime.now() + datetime.timedelta(seconds=60)
            test_task = {'script_path': self.test_script, 'start_time': test_time, 'spawn_time': test_time, 'variables': {'BOSS_NAME': '測試員'}, 'priority': 0}
            self.schedule_signal.emit(test_task)
            self.log_signal.emit(f"[插件] 🧪 測試任務發送成功！ (1分鐘後執行)")
            self.test_script = None

        while self.is_running:
            try:
                if self.json_path and os.path.exists(self.json_path):
                    mtime = os.path.getmtime(self.json_path)
                    if mtime != self.last_mtime:
                        self.last_mtime = mtime
                        self.check_timers(report=True) 
                    elif self.heartbeat_counter % 6 == 0:
                         self.check_timers(report=True) 
                else:
                    self.log_signal.emit(f"[插件] ⚠️ 找不到時間檔: {self.json_path}")
            except Exception as e:
                self.log_signal.emit(f"[插件] 監控迴圈錯誤: {e}")
            
            self.heartbeat_counter += 1
            for _ in range(10): 
                if not self.is_running: break
                time.sleep(1)

    def check_timers(self, report=False):
        try:
            data = None
            for _ in range(3):
                try:
                    with open(self.json_path, 'r', encoding='utf-8') as f: data = json.load(f)
                    break
                except: time.sleep(0.5)
            
            if not data: return

            now = datetime.datetime.now()
            count = 0
            upcoming_bosses = [] 
            
            expiration_seconds = self.expiration_minutes * 60

            for boss_id, info in data.items():
                if boss_id not in self.active_bosses: continue
                
                script_path = self.mapping.get(boss_id)
                if not script_path or not os.path.exists(script_path): continue

                boss_name = self.id_name_map.get(boss_id, boss_id)
                boss_level = self.id_level_map.get(boss_id, 0)
                
                t_str, d_str = info.get('time'), info.get('date')
                if not t_str or t_str == "待確認" or not d_str: continue
                
                try:
                    spawn_dt = datetime.datetime.strptime(f"{d_str} {t_str}", "%Y-%m-%d %H:%M")
                except: continue
                
                start_dt = spawn_dt - datetime.timedelta(minutes=self.pre_notify_minutes)
                
                left_min = (spawn_dt - now).total_seconds() / 60
                if 0 < left_min < 120:
                    upcoming_bosses.append((left_min, f"{boss_name}({int(left_min)}分)"))

                should_send = False
                is_active_window = False
                
                if start_dt <= now and (now - start_dt).total_seconds() < expiration_seconds:
                    is_active_window = True
                elif start_dt > now and (start_dt - now).total_seconds() < 600:
                    is_active_window = True
                
                if is_active_window:
                    last_send = self.last_sent_time.get(boss_id, 0)
                    if (time.time() - last_send) > 60:
                        should_send = True

                if should_send:
                    priority = 2 # 預設低優先 (排隊)
                    
                    if self.allow_interrupt:
                        if boss_level >= 80: priority = 0
                        elif boss_level >= 60: priority = 1

                    task = {
                        'script_path': script_path,
                        'start_time': start_dt,
                        'spawn_time': spawn_dt,
                        'variables': {'BOSS_NAME': boss_name},
                        'priority': priority
                    }
                    self.schedule_signal.emit(task)
                    self.last_sent_time[boss_id] = time.time()
                    
                    prio_text = "⚡插隊" if priority < 2 else "🐢排隊"
                    self.log_signal.emit(f"[插件] 🔔 排程成功: {boss_name} -> {start_dt.strftime('%H:%M:%S')}")
                    count += 1
            
            if report and upcoming_bosses:
                upcoming_bosses.sort(key=lambda x: x[0])
                msg = ", ".join([x[1] for x in upcoming_bosses[:3]]) 
                self.log_signal.emit(f"[插件] 💓 監控中... 下一批: {msg}")
                
        except Exception as e:
            self.log_signal.emit(f"[插件] 解析錯誤: {e}")