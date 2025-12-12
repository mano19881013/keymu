# main.py
import sys
import os

# 1. 先單獨引入 QApplication
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    # 2. ★ 關鍵步驟：在引入任何後端邏輯之前，先建立 Qt 應用程式
    # 這樣 Qt 就能搶先設定好 DPI，不會被 pyautogui 搶走
    app = QApplication(sys.argv)

    # 3. 建立好 App 後，才引入我們的主視窗 (這裡面包含了 pyautogui 等庫)
    # 這樣做可以延後後端套件的載入時間
    from frontend.main_window import MainWindow

    # 4. 顯示視窗
    window = MainWindow()
    window.show()
    
    # 5. 執行
    sys.exit(app.exec())