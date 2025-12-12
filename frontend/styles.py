# frontend/styles.py

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
QTableWidget { background-color: #2d2d30; gridline-color: #555; }
QHeaderView::section { background-color: #3e3e42; padding: 4px; border: 1px solid #555; }
"""