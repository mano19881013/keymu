import cv2
import numpy as np
import mss
import os
import easyocr

class VisionEye:
    def __init__(self, monitor_index=1):
        """
        初始化視覺模組
        """
        self.monitor_index = monitor_index
        self.reader = None 
        
        with mss.mss() as sct:
            self.update_monitor_info(sct)

    def update_monitor_info(self, sct_instance=None):
        should_close = False
        if sct_instance is None:
            sct_instance = mss.mss()
            should_close = True
            
        if self.monitor_index < len(sct_instance.monitors):
            self.monitor_rect = sct_instance.monitors[self.monitor_index]
        else:
            print(f"[視覺] ⚠️ 螢幕編號 {self.monitor_index} 超出範圍，重設為 1")
            self.monitor_index = 1
            self.monitor_rect = sct_instance.monitors[1]
            
        if should_close:
            sct_instance.close()

    def set_monitor(self, index):
        self.monitor_index = index
        with mss.mss() as sct:
            self.update_monitor_info(sct)
        print(f"[視覺] 👁️ 已切換至螢幕 {index}")

    def _get_reader(self):
        if self.reader is None:
            print("[視覺] 正在載入 EasyOCR 文字辨識模型...")
            self.reader = easyocr.Reader(['ch_tra', 'en'], gpu=True) 
        return self.reader

    def capture_screen(self, region=None):
        with mss.mss() as sct:
            monitor = self.monitor_rect
            if region:
                x, y, w, h = region
                monitor_region = {"top": y, "left": x, "width": w, "height": h}
                sct_img = sct.grab(monitor_region)
            else:
                sct_img = sct.grab(monitor)
                
            img = np.array(sct_img)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return img

    def read_image_safe(self, path):
        try:
            img_array = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            print(f"[視覺] 讀取圖片失敗: {e}")
            return None

    def find_image(self, template_path, confidence=0.8, region=None):
        if not os.path.exists(template_path): return None
        screen = self.capture_screen(region)
        template = self.read_image_safe(template_path)
        if template is None: return None

        try:
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= confidence:
                h, w = template.shape[:2]
                local_x = max_loc[0] + w // 2
                local_y = max_loc[1] + h // 2
                
                if region:
                    global_x = region[0] + local_x
                    global_y = region[1] + local_y
                else:
                    global_x = self.monitor_rect['left'] + local_x
                    global_y = self.monitor_rect['top'] + local_y
                    
                return (global_x, global_y)
            else:
                return None
        except Exception as e:
            print(f"[視覺] 比對發生錯誤: {e}")
            return None

    def preprocess_image(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        scale = 3
        enlarged = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    def ocr_screen(self, region=None):
        """
        ★ 修改：回傳詳細資料 (座標, 文字, 信心度)
        """
        raw_img = self.capture_screen(region)
        processed_img = self.preprocess_image(raw_img)
        reader = self._get_reader()
        # detail=1 會回傳 [[box], text, confidence]
        result = reader.readtext(processed_img, detail=1, paragraph=False)
        return result

    def find_color(self, target_rgb, tolerance=20, region=None):
        screen = self.capture_screen(region)
        target_bgr = (target_rgb[2], target_rgb[1], target_rgb[0])
        lower = np.array([max(0, c - tolerance) for c in target_bgr])
        upper = np.array([min(255, c + tolerance) for c in target_bgr])
        mask = cv2.inRange(screen, lower, upper)
        points = cv2.findNonZero(mask)
        if points is not None:
            local_x = points[0][0][0]
            local_y = points[0][0][1]
            if region:
                return (region[0] + local_x, region[1] + local_y)
            else:
                return (self.monitor_rect['left'] + local_x, self.monitor_rect['top'] + local_y)
        return None