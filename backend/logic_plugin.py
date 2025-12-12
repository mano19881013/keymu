# backend/logic_plugin.py

class LogicPluginBase:
    """
    邏輯判斷插件的基底類別
    所有邏輯插件都必須繼承它，並實作 check 方法
    """
    # 介面上顯示的名稱
    name = "未命名邏輯"
    
    def check(self, engine):
        """
        執行判斷邏輯
        :param engine: 包含 .hw (硬體) 和 .vision (視覺) 的橋接器
        :return: True (條件成立，執行跳轉) 或 False (條件不成立，繼續下一步)
        """
        return False