# backend/plugin_base.py
class PluginBase:
    """
    所有擴充插件都必須繼承這個類別
    """
    # 介面上顯示的按鈕名稱
    name = "未命名插件"
    
    # 插件需要的參數 (例如: {'次數': 'int', '圖片': 'file'})
    # 目前先簡化，不設參數，直接執行邏輯
    
    def run(self, engine):
        """
        主程式會呼叫這個函數
        :param engine: 這是 HardwareController + VisionEye 的集合體
        """
        pass