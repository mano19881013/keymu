# frontend/dialogs.py
import sys
import os
import time
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFrame, QLabel, QFormLayout, 
                               QComboBox, QHBoxLayout, QLineEdit, QPushButton, 
                               QFileDialog, QWidget, QApplication, QMessageBox, 
                               QColorDialog, QDoubleSpinBox)
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QCursor
from PySide6.QtCore import Qt, QRect, Signal, QPoint

# --- 視覺化抓點器 (修復版：繼承 QDialog 以解決卡死) ---
class VisualPicker(QDialog):
    finished_data = Signal(str) 

    def __init__(self, mode='point'):
        super().__init__()
        self.mode = mode 
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        
        self.virtual_geometry = QRect()
        for screen in QGuiApplication.screens():
            self.virtual_geometry = self.virtual_geometry.united(screen.geometry())
            
        self.setGeometry(self.virtual_geometry)
        self.setWindowOpacity(0.3) 
        self.setStyleSheet("background-color: black;")
        
        self.start_pos = None 
        self.current_pos = None
        self.setModal(True) # 重要：模態視窗

    def paintEvent(self, event):
        if self.mode == 'offset' and self.start_pos and self.current_pos:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 255, 255), 2, Qt.DashLine))
            painter.drawLine(self.start_pos, self.current_pos)
            
            painter.setBrush(QColor(255, 0, 0))
            painter.drawEllipse(self.start_pos, 5, 5)
            
            painter.setBrush(QColor(0, 255, 0))
            painter.drawEllipse(self.current_pos, 5, 5)
            
            dx = self.current_pos.x() - self.start_pos.x()
            dy = self.current_pos.y() - self.start_pos.y()
            painter.setPen(QColor(255, 255, 0))
            painter.setFont(QGuiApplication.font())
            painter.drawText(self.current_pos + QPoint(15, 15), f"Offset: {dx},{dy}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.mode == 'point':
                pos = event.globalPos()
                self.finished_data.emit(f"{pos.x()},{pos.y()}")
                self.accept()
            elif self.mode == 'offset':
                if not self.start_pos:
                    self.start_pos = event.pos()
                    self.setWindowOpacity(0.5)
                    self.update()
                else:
                    end_pos = event.pos()
                    dx = end_pos.x() - self.start_pos.x()
                    dy = end_pos.y() - self.start_pos.y()
                    self.finished_data.emit(f"{dx},{dy}")
                    self.accept()

    def mouseMoveEvent(self, event):
        if self.mode == 'offset':
            self.current_pos = event.pos()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()

# --- 智慧動作設定視窗 ---
class SmartActionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 智慧動作設定 (含變數)")
        self.resize(600, 450)
        layout = QVBoxLayout(self)

        group_cond = QFrame()
        group_cond.setObjectName("Panel")
        l_cond = QVBoxLayout(group_cond)
        l_cond.addWidget(QLabel("🛑 觸發條件 & 模糊度設定"))
        
        form = QFormLayout()
        self.combo_cond = QComboBox()
        self.combo_cond.addItems(["FindImg (找圖)", "OCR (找字)", "FindColor (找色)"])
        self.combo_cond.currentTextChanged.connect(self.on_cond_changed)
        
        target_layout = QHBoxLayout()
        self.input_target = QLineEdit()
        self.input_target.setPlaceholderText("圖片 / 關鍵字 / RGB")
        
        self.combo_vars = QComboBox()
        self.combo_vars.addItem("➕ 插入變數...")
        self.combo_vars.addItems(["{BOSS_NAME}", "{BOSS_LEVEL}", "{BOSS_TIME}"])
        self.combo_vars.setFixedWidth(110)
        self.combo_vars.currentIndexChanged.connect(self.insert_variable)
        
        self.btn_browse_img = QPushButton("📂")
        self.btn_browse_img.clicked.connect(self.browse_image)
        self.btn_pick_color = QPushButton("🎨 F8")
        self.btn_pick_color.clicked.connect(self.start_color_picker)
        
        target_layout.addWidget(self.input_target)
        target_layout.addWidget(self.combo_vars)
        target_layout.addWidget(self.btn_browse_img)
        target_layout.addWidget(self.btn_pick_color)

        threshold_layout = QHBoxLayout()
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.1, 1.0)
        self.spin_threshold.setSingleStep(0.05)
        self.spin_threshold.setValue(0.8)
        self.lbl_threshold_desc = QLabel("相似度 (0.1~1.0)")
        threshold_layout.addWidget(self.spin_threshold)
        threshold_layout.addWidget(self.lbl_threshold_desc)
        
        form.addRow("偵測方式:", self.combo_cond)
        form.addRow("目標數值:", target_layout)
        form.addRow("模糊判斷:", threshold_layout)
        l_cond.addLayout(form)
        layout.addWidget(group_cond)

        layout.addSpacing(10)

        group_ok = QFrame()
        group_ok.setObjectName("Panel")
        group_ok.setStyleSheet("QFrame#Panel{border: 1px solid #198754;}")
        l_ok = QVBoxLayout(group_ok)
        l_ok.addWidget(QLabel("✅ 若成立 (True) 則:"))
        
        form_ok = QFormLayout()
        self.combo_act_ok = QComboBox()
        self.combo_act_ok.addItems(["ClickTarget (點擊目標)", "ClickOffset (偏移點擊)", "RunScript (執行腳本)", "Goto (跳轉標籤)", "Continue (繼續)"])
        self.combo_act_ok.currentTextChanged.connect(self.on_act_ok_changed)
        
        layout_param_ok = QHBoxLayout()
        self.input_param_ok = QLineEdit()
        self.btn_helper_ok = QPushButton("⚙️")
        self.btn_helper_ok.clicked.connect(lambda: self.action_helper('ok'))
        
        layout_param_ok.addWidget(self.input_param_ok)
        layout_param_ok.addWidget(self.btn_helper_ok)
        
        form_ok.addRow("動作:", self.combo_act_ok)
        form_ok.addRow("參數:", layout_param_ok)
        l_ok.addLayout(form_ok)
        layout.addWidget(group_ok)

        layout.addSpacing(10)

        group_fail = QFrame()
        group_fail.setObjectName("Panel")
        group_fail.setStyleSheet("QFrame#Panel{border: 1px solid #dc3545;}")
        l_fail = QVBoxLayout(group_fail)
        l_fail.addWidget(QLabel("❌ 若不成立 (False) 則:"))
        
        form_fail = QFormLayout()
        self.combo_act_fail = QComboBox()
        self.combo_act_fail.addItems(["Continue (繼續)", "Goto (跳轉標籤)", "RunScript (執行腳本)", "Stop (停止)"])
        self.combo_act_fail.currentTextChanged.connect(self.on_act_fail_changed)
        
        layout_param_fail = QHBoxLayout()
        self.input_param_fail = QLineEdit()
        self.btn_helper_fail = QPushButton("⚙️")
        self.btn_helper_fail.clicked.connect(lambda: self.action_helper('fail'))
        
        layout_param_fail.addWidget(self.input_param_fail)
        layout_param_fail.addWidget(self.btn_helper_fail)
        
        form_fail.addRow("動作:", self.combo_act_fail)
        form_fail.addRow("參數:", layout_param_fail)
        l_fail.addLayout(form_fail)
        layout.addWidget(group_fail)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("確定")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        self.on_act_ok_changed(self.combo_act_ok.currentText())
        self.on_act_fail_changed(self.combo_act_fail.currentText())
        self.on_cond_changed(self.combo_cond.currentText())

    # ★ 新增：設定回填資料 (讓編輯時可以還原設定)
    def set_data(self, val_str):
        try:
            parts = val_str.split('|')
            if len(parts) < 6: return
            
            # 設定偵測方式 (使用模糊比對查找項目)
            cond = parts[0]
            for i in range(self.combo_cond.count()):
                if self.combo_cond.itemText(i).startswith(cond):
                    self.combo_cond.setCurrentIndex(i)
                    break
            
            self.input_target.setText(parts[1])
            self.on_cond_changed(self.combo_cond.currentText()) 
            
            act_ok = parts[2]
            for i in range(self.combo_act_ok.count()):
                if self.combo_act_ok.itemText(i).startswith(act_ok):
                    self.combo_act_ok.setCurrentIndex(i)
                    break
            self.input_param_ok.setText(parts[3])
            
            act_fail = parts[4]
            for i in range(self.combo_act_fail.count()):
                if self.combo_act_fail.itemText(i).startswith(act_fail):
                    self.combo_act_fail.setCurrentIndex(i)
                    break
            self.input_param_fail.setText(parts[5])
            
            if len(parts) > 6 and parts[6]:
                self.spin_threshold.setValue(float(parts[6]))
        except: pass

    def insert_variable(self, index):
        if index == 0: return 
        self.input_target.setText(self.combo_vars.currentText())
        
    def update_helper_btn(self, combo_text, btn, input_field):
        mode = combo_text.split()[0]
        if mode == "ClickOffset":
            btn.setText("📏"); input_field.setEnabled(True); input_field.setPlaceholderText("x,y")
        elif mode == "RunScript":
            btn.setText("📂"); input_field.setEnabled(True); input_field.setPlaceholderText("script.json")
        elif mode == "Goto":
            btn.setText("-"); input_field.setEnabled(True); input_field.setPlaceholderText("標籤名稱")
        else:
            btn.setText("-"); input_field.setEnabled(mode not in ["ClickTarget", "Continue", "Stop"])
    
    def on_act_ok_changed(self, text): self.update_helper_btn(text, self.btn_helper_ok, self.input_param_ok)
    def on_act_fail_changed(self, text): self.update_helper_btn(text, self.btn_helper_fail, self.input_param_fail)
    
    def on_cond_changed(self, text):
        mode = text.split()[0]
        if mode == "FindColor":
            self.spin_threshold.setRange(0, 100); self.spin_threshold.setValue(20)
            self.lbl_threshold_desc.setText("RGB 容許誤差 (0~100)")
        elif mode == "OCR":
            self.spin_threshold.setRange(0.1, 1.0); self.spin_threshold.setValue(0.5)
            self.lbl_threshold_desc.setText("文字相似度 (0.1~1.0)")
        else: # FindImg
            self.spin_threshold.setRange(0.1, 1.0); self.spin_threshold.setValue(0.8)
            self.lbl_threshold_desc.setText("圖片信心度 (0.1~1.0)")

    def action_helper(self, target_type):
        combo = self.combo_act_ok if target_type == 'ok' else self.combo_act_fail
        inp = self.input_param_ok if target_type == 'ok' else self.input_param_fail
        mode = combo.currentText().split()[0]
        
        if mode == "ClickOffset":
            self.picker = VisualPicker(mode='offset')
            self.picker.finished_data.connect(lambda val: inp.setText(val))
            self.picker.exec() # 使用 exec() 避免視窗消失卡死
            
        elif mode == "RunScript":
            f, _ = QFileDialog.getOpenFileName(self, "選腳本", "scripts", "JSON (*.json)")
            if f: inp.setText(os.path.relpath(f, os.getcwd()))
    
    def browse_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "選圖", "assets", "Images (*.png)")
        if f:
            self.input_target.setText(os.path.relpath(f, os.getcwd()))

    def start_color_picker(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.input_target.setText(f"{c.red()},{c.green()},{c.blue()}")
            self.on_cond_changed("FindColor")

    def get_data(self):
        base = f"{self.combo_cond.currentText().split()[0]}|{self.input_target.text()}|{self.combo_act_ok.currentText().split()[0]}|{self.input_param_ok.text()}|{self.combo_act_fail.currentText().split()[0]}|{self.input_param_fail.text()}"
        return f"{base}|{self.spin_threshold.value()}"