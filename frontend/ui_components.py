# frontend/ui_components.py
from PySide6.QtWidgets import (QPushButton, QListWidget, QAbstractItemView, QDialog, 
                               QVBoxLayout, QFormLayout, QComboBox, QSpinBox, 
                               QLabel, QDialogButtonBox, QTimeEdit, QWidget, QStackedWidget, QHBoxLayout)
from PySide6.QtCore import Qt, Signal, QMimeData, QTime
from PySide6.QtGui import QDrag

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
            if action_type in ['Click', 'FindImg', 'OCR', 'FindColor', 'Wait', 'Key', 'SmartAction', 'IfImage', 'Label', 'Goto', 'LogicPlugin', 'Snip', 'Comment', 'Drag', 'Loop']:
                event.accept(); self.itemDropped.emit(action_type)
            else: super().dropEvent(event)
        else: super().dropEvent(event)

# ★ V18.21 修改：支援「時段 (From-To)」設定
class TaskSettingsDialog(QDialog):
    def __init__(self, parent=None, current_priority=1, current_interval=0, current_mode=0, start_time="00:00", end_time="23:59"):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 任務屬性設定")
        self.resize(380, 280)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.combo_priority = QComboBox()
        self.combo_priority.addItems(["🔥 高 (High)", "⏺ 一般 (Normal)", "💤 低 (Low)"])
        self.combo_priority.setCurrentIndex(current_priority)
        
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["🔁 循環執行 (Interval)", "⏰ 時段執行 (Daily Range)"])
        self.combo_mode.setCurrentIndex(current_mode)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)

        self.stack = QStackedWidget()
        
        # Page 0: Interval
        page_interval = QWidget()
        layout_int = QVBoxLayout(page_interval); layout_int.setContentsMargins(0,0,0,0)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(0, 99999)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setValue(current_interval)
        self.spin_interval.setSingleStep(5)
        layout_int.addWidget(QLabel("執行冷卻時間 (秒):"))
        layout_int.addWidget(self.spin_interval)
        
        # Page 1: Time Range
        page_time = QWidget()
        layout_time = QVBoxLayout(page_time); layout_time.setContentsMargins(0,0,0,0)
        
        # 開始時間
        time_layout = QHBoxLayout()
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        # 結束時間
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")

        try:
            h1, m1 = map(int, start_time.split(':')); self.time_start.setTime(QTime(h1, m1))
            h2, m2 = map(int, end_time.split(':')); self.time_end.setTime(QTime(h2, m2))
        except:
            self.time_start.setTime(QTime(0, 0))
            self.time_end.setTime(QTime(23, 59))
            
        time_layout.addWidget(QLabel("從:"))
        time_layout.addWidget(self.time_start)
        time_layout.addWidget(QLabel("到:"))
        time_layout.addWidget(self.time_end)
        
        layout_time.addWidget(QLabel("每日執行時段 (範圍內只跑一次):"))
        layout_time.addLayout(time_layout)
        
        self.stack.addWidget(page_interval)
        self.stack.addWidget(page_time)
        self.stack.setCurrentIndex(current_mode)
        
        form.addRow("優先等級:", self.combo_priority)
        form.addRow("執行模式:", self.combo_mode)
        
        layout.addLayout(form)
        layout.addWidget(self.stack)
        
        self.lbl_hint = QLabel("")
        self.lbl_hint.setStyleSheet("color: gray; font-size: 11px;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)
        self.update_hint(current_mode)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def on_mode_changed(self, index):
        self.stack.setCurrentIndex(index)
        self.update_hint(index)
        
    def update_hint(self, index):
        if index == 0:
            self.lbl_hint.setText("循環模式：任務執行完畢後，休息指定秒數再重複執行。")
        else:
            self.lbl_hint.setText("時段模式：只有在「開始~結束」時間範圍內，且今天尚未執行過，才會啟動任務。\n(適合每日副本或限時活動)")

    def get_data(self):
        # 回傳: (priority, interval, mode, start_str, end_str)
        t1 = self.time_start.time()
        t2 = self.time_end.time()
        s_str = f"{t1.hour():02d}:{t1.minute():02d}"
        e_str = f"{t2.hour():02d}:{t2.minute():02d}"
        return self.combo_priority.currentIndex(), self.spin_interval.value(), self.combo_mode.currentIndex(), s_str, e_str

class KeySelectorDialog(QDialog):
    KEY_MAP = {
        "Enter (回車)": 176, "Esc (離開)": 177, "Backspace": 178, "Tab": 179, "Space (空白)": 32,
        "F1": 194, "F2": 195, "F3": 196, "F4": 197, "F5": 198, "F6": 199,
        "F7": 200, "F8": 201, "F9": 202, "F10": 203, "F11": 204, "F12": 205,
        "Up (上)": 218, "Down (下)": 217, "Left (左)": 216, "Right (右)": 215,
        "PageUp": 211, "PageDown": 214, "Home": 210, "End": 213, "Delete": 212,
        "Shift": 129, "Ctrl": 128, "Alt": 130,
        "A": 65, "B": 66, "C": 67, "D": 68, "E": 69, "F": 70, "G": 71, "H": 72, "I": 73,
        "J": 74, "K": 75, "L": 76, "M": 77, "N": 78, "O": 79, "P": 80, "Q": 81, "R": 82,
        "S": 83, "T": 84, "U": 85, "V": 86, "W": 87, "X": 88, "Y": 89, "Z": 90,
        "0": 48, "1": 49, "2": 50, "3": 51, "4": 52, "5": 53, "6": 54, "7": 55, "8": 56, "9": 57
    }
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("⌨️ 選擇按鍵"); self.resize(300, 150); layout = QVBoxLayout(self)
        form = QFormLayout(); self.combo_keys = QComboBox(); self.combo_keys.addItems(list(self.KEY_MAP.keys())); self.combo_keys.setCurrentText("F1")
        form.addRow("常用按鍵:", self.combo_keys); layout.addLayout(form)
        self.lbl_code = QLabel("代碼: 194"); self.lbl_code.setAlignment(Qt.AlignCenter); layout.addWidget(self.lbl_code)
        self.combo_keys.currentTextChanged.connect(self.on_key_changed)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); btn_box.accepted.connect(self.accept); btn_box.rejected.connect(self.reject); layout.addWidget(btn_box)
    def on_key_changed(self, text): code = self.KEY_MAP.get(text, 0); self.lbl_code.setText(f"代碼: {code}")
    def get_selected(self): text = self.combo_keys.currentText(); return text, self.KEY_MAP.get(text, 0)