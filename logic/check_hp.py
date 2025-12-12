# logic/check_hp.py
from backend.logic_plugin import LogicPluginBase

class CheckHPLow(LogicPluginBase):
    name = "🩸 檢查血量 (範例)"
    
    def check(self, engine):
        print("[邏輯] 正在檢查血量...")
        
        # 設定血條的座標 (您可以改成讀取設定檔或寫死)
        # 例如血條 80% 的位置在 (100, 30)
        x, y = 100, 30
        
        # 紅色的 RGB 值
        target_red = (255, 0, 0)
        
        # 使用引擎的視覺模組檢查顏色
        # check_pixel_color(x, y, rgb, tolerance)
        is_red = engine.vision.check_pixel_color(x, y, target_red, tolerance=30)
        
        if not is_red:
            print("[邏輯] ⚠️ 血量低於 80% (該點不是紅色) -> 觸發回補！")
            return True # 條件成立 (沒血了)
        else:
            print("[邏輯] ✅ 血量健康")
            return False # 條件不成立