# backend/cognitive.py
import time
import random

class CognitiveSystem:
    def __init__(self):
        self.start_time = time.time()
        self.last_break_time = time.time()
        
    def get_fatigue_level(self):
        """
        計算疲勞度 (0.0 ~ 1.0)
        假設連續玩 4 小時 (14400秒) 會達到疲勞頂峰
        """
        run_time = time.time() - self.start_time
        
        # 疲勞曲線：前 1 小時增加很慢，之後變快
        # 這裡用簡單的線性模擬：每小時增加 0.2
        fatigue = min(run_time / 14400, 1.0) 
        return fatigue

    def get_reaction_multiplier(self):
        """
        根據疲勞度，回傳反應時間的倍率
        剛開始: 1.0x (正常)
        很累時: 1.5x ~ 2.0x (動作變慢)
        """
        fatigue = self.get_fatigue_level()
        
        # 基礎倍率 1.0 + 疲勞加成 (0~0.8) + 隨機波動 (-0.1~0.1)
        # 這樣就算在同一分鐘內，反應速度也會忽快忽慢，更像人
        multiplier = 1.0 + (fatigue * 0.8) + random.uniform(-0.1, 0.1)
        
        return max(0.9, multiplier) # 最快不能低於 0.9 倍

    def get_human_wait(self, base_time):
        """
        將固定的等待時間轉換為擬人化的時間 (高斯分佈)
        """
        if base_time <= 0: return 0

        fatigue = self.get_reaction_multiplier()
        
        # 平均值 (mu) 會隨著疲勞稍微變長
        mu = base_time * fatigue
        
        # 標準差 (sigma) 設定為時間的 15%~25%
        sigma = base_time * random.uniform(0.15, 0.25)
        
        # 使用高斯隨機生成
        final_wait = random.gauss(mu, sigma)
        
        # 確保不會變成負數，且至少保留原本時間的 50%
        return max(base_time * 0.5, final_wait)

    def check_garbage_time(self):
        """
        檢查是否該觸發「垃圾時間」(發呆)
        建議在每次循環結束後呼叫
        """
        # 疲勞度越高，發呆機率越高
        fatigue = self.get_fatigue_level()
        chance = 0.01 + (fatigue * 0.05) # 1% ~ 6% 機率
        
        if random.random() < chance:
            duration = random.uniform(2.0, 10.0)
            print(f"[認知] 😴 玩家累了，發呆 {duration:.1f} 秒...")
            time.sleep(duration)
            return True
        return False