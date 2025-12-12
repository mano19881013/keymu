# frontend/overlay.py
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication, QPolygon
from PySide6.QtCore import Qt, QRect, QTimer, QPoint

class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        # 設定視窗屬性：無邊框、置頂、滑鼠穿透(重要!)、工具視窗
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool | 
            Qt.WindowTransparentForInput # ★ 關鍵：讓滑鼠可以點穿這個視窗
        )
        self.setAttribute(Qt.WA_TranslucentBackground) # 背景透明
        
        # 覆蓋所有螢幕
        self.virtual_geometry = QRect()
        for screen in QGuiApplication.screens():
            self.virtual_geometry = self.virtual_geometry.united(screen.geometry())
        self.setGeometry(self.virtual_geometry)

        # 繪圖隊列
        self.shapes = [] 
        
        # 啟動刷新計時器 (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_shapes)
        self.timer.start(30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for shape in self.shapes:
            color = shape['color']
            
            # 根據生命週期計算透明度 (Fade out)
            alpha = int((shape['life'] / shape['max_life']) * 255)
            color.setAlpha(alpha)
            
            pen = QPen(color, 2)
            
            if shape['type'] == 'path':
                # ★ 繪製預判路徑 (白色折線)
                pen.setStyle(Qt.SolidLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                
                # 將座標列表轉換為 QPoint 列表
                points = [QPoint(int(x), int(y)) for x, y in shape['points']]
                if points:
                    painter.drawPolyline(points)

            elif shape['type'] == 'rect':
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(shape['geometry'])
                
            elif shape['type'] == 'cross':
                pen.setWidth(3)
                painter.setPen(pen)
                x, y = shape['x'], shape['y']
                size = 20
                painter.drawLine(x - size, y, x + size, y)
                painter.drawLine(x, y - size, x, y + size)
                painter.drawEllipse(QPoint(x, y), 15, 15)

    def update_shapes(self):
        # 讓圖形慢慢消失 (生命週期遞減)
        expired = []
        for shape in self.shapes:
            shape['life'] -= 1     
            if shape['life'] <= 0:
                expired.append(shape)
        
        for e in expired:
            self.shapes.remove(e)
            
        if self.shapes or expired:
            self.update() # 重繪

    # --- 外部呼叫介面 ---
    def draw_search_area(self, x, y, w, h):
        """畫紅色搜尋框 (持續 1 秒)"""
        self.shapes.append({
            'type': 'rect',
            'geometry': QRect(x, y, w, h),
            'color': QColor(255, 0, 0), # 紅色
            'life': 30, # 持續 30 幀 (約 1 秒)
            'max_life': 30
        })
        self.update()

    def draw_target(self, x, y):
        """畫綠色準心 (持續 2 秒)"""
        self.shapes.append({
            'type': 'cross',
            'x': x, 'y': y,
            'color': QColor(0, 255, 0), # 綠色
            'life': 60,
            'max_life': 60
        })
        self.update()

    def draw_path(self, points):
        """畫出預判路徑 (白色曲線)"""
        if not points or len(points) < 2: return
        self.shapes.append({
            'type': 'path',
            'points': points, # 格式 [(x1,y1), (x2,y2)...]
            'color': QColor(255, 255, 255), # 白色
            'life': 40, # 持續約 1.3 秒
            'max_life': 40
        })
        self.update()