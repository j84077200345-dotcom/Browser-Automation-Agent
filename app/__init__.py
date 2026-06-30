"""Browser Automation Agent(瀏覽器自動化代理)。

本套件提供一個由 LLM 驅動的 agent:接收自然語言目標與起始 URL 後,
透過 Claude 的 tool-use 機制逐步操控 headless 瀏覽器(Playwright),
並產出可驗證的產物:結構化報告、擷取的資料、每一步的截圖,以及完整執行記錄。
"""

__version__ = "0.1.0"
