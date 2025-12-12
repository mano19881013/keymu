# extensions/human_idle.py
import time
import random
from backend.plugin_base import PluginBase

class HumanIdle(PluginBase):
    name = "🥱 擬人化發呆 (微顫)"

    def run(self, engine):
        # 設定發呆總時間 (例如 2~4 秒)
        total_time = random.uniform(2.0, 4.0)
        start_time = time.time()
        
        engine.log(f"[擬人] 開始發呆 {total_time:.1f} 秒...")
        
        while time.time() - start_time < total_time:
            # 1. 隨機決定要不要動
            if random.random() < 0.3: # 30% 機率會動一下
                # 2. 取得當前位置
                x, y = engine.hw.get_real_position()
                
                # 3. 極小幅度的抖動 (模擬呼吸或手抖)
                dx = random.randint(-3, 3)
                dy = random.randint(-3, 3)
                
                # 4. 移動
                engine.hw.move(x + dx, y + dy)
            
            # 每次抖動後的間隔
            time.sleep(random.uniform(0.1, 0.5))
            
            if engine.should_stop():
                break