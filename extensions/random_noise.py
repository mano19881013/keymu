# extensions/random_noise.py
import time
import random
from backend.plugin_base import PluginBase

class RandomNoise(PluginBase):
    name = "🤪 隨機廢操作 (干擾)"

    def run(self, engine):
        # 定義一些沒意義的動作庫
        actions = [
            'check_inventory', # 打開背包看一眼
            'mouse_circle',    # 滑鼠轉圈圈
            'check_status',    # 按 C 看素質
            'clear_screen',    # 點擊空白處取消選取
            'do_nothing'       # 純粹發呆
        ]
        
        # 只有 30% 的機率觸發，避免太頻繁反而像機器人
        if random.random() > 0.3:
            engine.log("[擬人] 這次不執行廢操作 (跳過)")
            return

        choice = random.choice(actions)
        engine.log(f"[擬人] 執行隨機動作: {choice}")

        if choice == 'check_inventory':
            # 假設 'I' 是背包鍵
            # 按下 I -> 等一下 -> 再按 I 關閉
            engine.hw.press(73) # I 鍵代碼 (需查 KeyMap)
            time.sleep(random.uniform(0.5, 1.5))
            engine.hw.press(73)
            
        elif choice == 'mouse_circle':
            # 讓滑鼠亂飄一下
            cx, cy = engine.hw.get_real_position()
            for _ in range(5):
                off_x = random.randint(-100, 100)
                off_y = random.randint(-100, 100)
                engine.hw.move(cx + off_x, cy + off_y)
                time.sleep(0.1)
                
        elif choice == 'clear_screen':
            # 點擊畫面邊緣空白處
            engine.hw.move(100, 300) # 假設這是空白處
            engine.hw.click()