import sys
import os
from datetime import datetime
from PySide6.QtWidgets import QWidget, QApplication, QInputDialog
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QPixmap
from PySide6.QtCore import Qt, QRect, Signal, QPoint

class SnippingWidget(QWidget):
    on_snipping_finish = Signal(str)

    def __init__(self, mode='save'):
        """
        mode: 'save' (截圖存檔) 或 'region' (只回傳座標)
        """
        super().__init__()
        self.mode = mode # ★ 記錄模式
        
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        
        # 多螢幕處理
        self.virtual_geometry = QRect()
        screens = QGuiApplication.screens()
        for screen in screens:
            self.virtual_geometry = self.virtual_geometry.united(screen.geometry())
            
        self.setGeometry(self.virtual_geometry)
        self.setCursor(Qt.CrossCursor)
        
        self.full_screen_pixmap = QPixmap(self.virtual_geometry.size())
        self.full_screen_pixmap.fill(Qt.black)
        
        painter = QPainter(self.full_screen_pixmap)
        for screen in screens:
            screen_pixmap = screen.grabWindow(0)
            geo = screen.geometry()
            x = geo.x() - self.virtual_geometry.x()
            y = geo.y() - self.virtual_geometry.y()
            painter.drawPixmap(x, y, screen_pixmap)
        painter.end()
        
        self.start_point = None
        self.end_point = None
        self.is_snipping = False
        self.setWindowOpacity(1.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.full_screen_pixmap)
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())
        
        if self.start_point and self.end_point:
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawPixmap(rect, self.full_screen_pixmap, rect)
            
            pen = QPen(QColor(255, 0, 0), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            
            painter.setPen(QColor(255, 255, 255))
            # 顯示資訊：如果是選區模式，顯示座標
            if self.mode == 'region':
                info_text = f"Region: {rect.x()},{rect.y()},{rect.width()},{rect.height()}"
            else:
                info_text = f"{rect.width()} x {rect.height()}"
            painter.drawText(rect.topLeft() - QPoint(0, 5), info_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_snipping = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_snipping:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.end_point = event.pos()
            self.is_snipping = False
            self.capture_image()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            self.on_snipping_finish.emit("")

    def capture_image(self):
        if not self.start_point or not self.end_point: return

        rect = QRect(self.start_point, self.end_point).normalized()
        if rect.width() < 5 or rect.height() < 5: return

        # ★ 處理 DPI 偏移
        img_rect = self.full_screen_pixmap.rect()
        intersected_rect = rect.intersected(img_rect)
        
        # 隱藏自己
        self.setVisible(False)
        QApplication.processEvents()

        # === 分流邏輯 ===
        if self.mode == 'region':
            # ★ 如果是選區模式，直接回傳座標字串
            # 格式: x,y,w,h
            region_str = f"{intersected_rect.x()},{intersected_rect.y()},{intersected_rect.width()},{intersected_rect.height()}"
            print(f"[選區] 座標: {region_str}")
            self.on_snipping_finish.emit(region_str)
            self.close()
            
        else:
            # ★ 既有模式：截圖存檔
            cropped = self.full_screen_pixmap.copy(intersected_rect)
            default_name = f"img_{datetime.now().strftime('%H%M%S')}"
            text, ok = QInputDialog.getText(None, "截圖命名", "輸入圖片名稱:", text=default_name)
            
            if ok and text:
                if not os.path.exists("assets"): os.makedirs("assets")
                if not text.lower().endswith(".png"): text += ".png"
                filename = f"assets/{text}"
                cropped.save(filename, "PNG")
                self.on_snipping_finish.emit(filename)
            else:
                self.on_snipping_finish.emit("")
            
            self.close()