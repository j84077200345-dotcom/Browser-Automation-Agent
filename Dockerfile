# 使用官方 Playwright Python image:已內建 Chromium 與所有系統相依套件。
# 標籤版本必須與 requirements.txt 的 playwright 版本一致,瀏覽器才找得到。
# (若 noble 標籤在部署平台不可用,可改用 v1.61.0-jammy。)
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# 先安裝相依套件,善用 Docker layer cache(程式碼變動時不需重裝套件)。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式原始碼。
COPY app ./app

# 預設環境變數;ANTHROPIC_API_KEY 由部署平台(Zeabur)以機密注入,不寫入 image。
ENV HEADLESS=true \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# 以 shell 形式啟動,讓 ${PORT} 能被部署平台注入的值取代。
CMD uvicorn app.web.server:app --host 0.0.0.0 --port ${PORT:-8000}
