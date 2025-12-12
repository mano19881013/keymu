# extensions/demo_afk.py
import time
import random
import math
from backend.plugin_base import PluginBase

class AFKPlugin(PluginBase):
    # 這行字會顯示在按鈕上
    name = "💤 防發呆 (畫圈圈)"

    def run(self, engine):
        # engine 包含了 .hw (硬體) 和 .eye (視覺)
        # 我們來畫一個圓圈
        print("[插件] 執行防發呆邏輯...")
        
        center_x, center_y = 960, 540
        radius = 100
        
        for i in range(0, 360, 20):
            angle = math.radians(i)
            x = int(center_x + radius * math.cos(angle))
            y = int(center_y + radius * math.sin(angle))
            
            # 呼叫主程式的移動指令
            engine.hw.move(x, y)
            time.sleep(0.05)
            
        print("[插件] 防發呆結束")