# extensions/bio_scheduler.py
import time
import random
import datetime
from backend.plugin_base import PluginBase

class BioScheduler(PluginBase):
    name = "📅 生理時鐘行程表"

    def run(self, engine):
        now = datetime.datetime.now()
        hour = now.hour
        minute = now.minute
        
        # 1. 用餐時間判斷 (午餐 11:30~13:30, 晚餐 17:30~19:30)
        is_lunch = 11 <= hour <= 13
        is_dinner = 17 <= hour <= 19
        
        # 2. 深夜防護 (凌晨 2:00 ~ 6:00)
        is_sleeping = 2 <= hour <= 6

        # --- 邏輯 A: 長休息 (吃飯/睡覺) ---
        # 只有 1% 的極低機率觸發，避免每次經過都停
        if (is_lunch or is_dinner) and random.random() < 0.01:
            duration = random.uniform(15 * 60, 40 * 60) # 休息 15~40 分鐘
            engine.log(f"[生理] 🍱 到了吃飯時間，休息 {duration/60:.1f} 分鐘...")
            
            # 模擬掛網：先隨便點一下地板，避免被踢下線
            self._anti_afk_click(engine)
            time.sleep(duration)
            engine.log("[生理] 吃飽了，繼續工作！")
            return

        # --- 邏輯 B: 短休息 (上廁所/倒水) ---
        # 任何時間都有 0.5% 機率發生
        if random.random() < 0.005:
            duration = random.uniform(60, 180) # 休息 1~3 分鐘
            engine.log(f"[生理] 🚽 去個廁所/倒杯水，暫離 {duration:.0f} 秒...")
            time.sleep(duration)
            return

        # --- 邏輯 C: 深夜降速 (愛睏) ---
        if is_sleeping:
            engine.log("[生理] 🌙 深夜精神不濟，動作變慢...")
            # 強制讓休息時間變長
            time.sleep(random.uniform(2.0, 5.0))

    def _anti_afk_click(self, engine):
        # 簡單防止長時間不動被踢
        x, y = engine.hw.get_real_position()
        engine.hw.move(x + random.randint(-5, 5), y + random.randint(-5, 5))
        # 不點擊，只是動一下滑鼠喚醒螢幕保護程式的感覺