# Browser Automation Agent(瀏覽器自動化代理)

一個由 **LLM** 驅動的瀏覽器自動化代理:給它一個**自然語言目標**與**起始 URL**,
它會以 **Playwright(headless Chromium)** 一步一步操作真實瀏覽器,直到完成目標,
並產出**可驗證的產物**——結構化報告、擷取資料、每一步截圖,以及完整執行記錄。

> **供應商不寫死**:以 `LLM_PROVIDER` 環境變數在 **Anthropic(Claude)** 與
> **OpenAI(GPT)** 之間切換,你手上有哪家的 key 就用哪家(見 [`app/agent/llm.py`](app/agent/llm.py))。

> 範例目標:「在 Hacker News 找出排名第 1 的頭條,開啟其留言頁,並摘要討論氛圍。」

---

## 線上 Demo

- 公開網址:**https://browser-automation-agent.zeabur.app/**(部署於 Zeabur,供應商 OpenAI / gpt-4o)
- 健康檢查:[`/healthz`](https://browser-automation-agent.zeabur.app/healthz)
- 進入後首頁「歷史 run」即可看到內建的示範 run(可驗證的報告、資料與截圖);
  也可直接點選預設任務一鍵帶入,或輸入自訂目標觸發,執行過程與結果會即時顯示。
- 公開 URL 設有每日觸發上限(`DAILY_RUN_LIMIT`)以保護 API 額度。

---

## 它如何運作

```
自然語言目標 + 起始 URL
        │
        ▼
┌─────────────────────────────────────────────┐
│  agent 迴圈 (app/agent/agent.py)              │
│                                               │
│  1. 擷取頁面狀態(browser.py)                  │
│     → URL、標題、可見文字、「帶編號的互動元素」  │
│  2. 交給 LLM 決定下一步(tool / function call)  │
│     → navigate / click / type_text / scroll / │
│       read_page / go_back / finish            │
│  3. 執行動作 → 截圖 → 回傳新觀察給 LLM          │
│  4. 重複,直到 finish 或達步數上限              │
└─────────────────────────────────────────────┘
        │
        ▼
產物(app/runs/<run_id>/):run.json · log.jsonl · screenshots/ · report.md · data.json
```

**可靠性關鍵——以「元素編號」取代脆弱的 selector:**
每次擷取頁面時,會用一段 JavaScript 掃描所有*可見的*互動元素,在每個元素上標記
`data-agent-id`(從 0 開始編號)並回傳清單。LLM 只需說「點擊 [3]」而非提供 CSS
selector,因此對網站改版、動態 class 名稱具有韌性。這也讓模型看到的是精簡的
accessibility 視圖,而非整份 HTML,節省 token 並提升判斷品質。

### 專案結構

```
app/
├─ config.py          設定(從環境變數 / .env 載入)
├─ tasks.py           預設示範任務(免登入、可重現)
├─ runner.py          RunManager:背景執行、單一併發、每日上限、查詢歷史
├─ cli.py             命令列執行入口(本機驗證用)
├─ agent/
│  ├─ browser.py      Playwright 封裝 + 帶編號互動元素快照
│  ├─ agent.py        供應商無關的 agent 主迴圈
│  ├─ llm.py          LLM 供應商抽象層(Anthropic / OpenAI 可切換)
│  ├─ tools.py        工具定義(中立格式)與分派
│  ├─ prompts.py      系統提示
│  └─ logger.py       執行記錄與產物
└─ web/
   ├─ server.py       FastAPI:儀表板、觸發、API、靜態產物
   └─ templates/      base / index / run(run 詳情頁即時輪詢顯示進度)
Dockerfile            以官方 Playwright image 部署(Zeabur)
tests/                單元測試 + 離線瀏覽器整合測試
```

---

## 本機執行

需求:Python 3.11+、已建立的虛擬環境 `browser_auto_env`。

```powershell
# 1. 啟用虛擬環境(Windows PowerShell)
./browser_auto_env/Scripts/Activate.ps1

# 2. 安裝相依套件與瀏覽器
pip install -r requirements.txt
python -m playwright install chromium

# 3. 設定供應商與金鑰:複製 .env.example 為 .env
copy .env.example .env
#    然後編輯 .env:設定 LLM_PROVIDER=anthropic(或 openai),
#    並填入對應的 ANTHROPIC_API_KEY 或 OPENAI_API_KEY

# 4a. 啟動 Web 介面
uvicorn app.web.server:app --reload
#     瀏覽 http://localhost:8000

# 4b. 或用命令列直接跑一個預設任務
python -m app.cli --list
python -m app.cli --preset hn_top_story
```

---

## 如何驗證

> 本專案已內建一次**真實執行的示範 run**(`app/samples/`,以 OpenAI gpt-4o 擷取
> quotes.toscrape.com「humor」標籤的 12 則名言),啟動時會自動植入 `runs/`,因此
> 公開 URL 或本機一載入即可在「歷史 run」看到可驗證的報告、資料與截圖。

1. **執行一次 run**:在儀表板點選預設任務(如「Hacker News:頭條 + 留言摘要」)→
   觀看步驟即時更新、每步截圖,以及最終 Markdown 報告。
2. **檢視可驗證產物**(每次 run 一個資料夾 `app/runs/<run_id>/`,並透過 `/artifacts/...` 提供):
   - `report.md` — 交付報告
   - `data.json` — 結構化擷取資料(可程式化比對)
   - `screenshots/step-NN.png` — 每一步的截圖
   - `run.json` / `log.jsonl` — 完整執行記錄(思考 → 動作 → 觀察)
3. **跑測試**:
   ```powershell
   pip install -r requirements-dev.txt
   pytest -q
   ```
   含離線整合測試,驗證「帶編號互動元素快照」這個核心機制。

---

## 部署(Zeabur)

本專案以 `Dockerfile` 部署,base image 為官方
`mcr.microsoft.com/playwright/python`(已內建瀏覽器與系統相依)。

1. 將此 repo 連結到 Zeabur(或任何支援 Dockerfile 的平台)。
2. 在平台的環境變數設定中加入機密:`LLM_PROVIDER`(`anthropic` 或 `openai`)與對應的
   **`ANTHROPIC_API_KEY`** 或 **`OPENAI_API_KEY`**(切勿寫進程式碼)。
3. 平台會自動以 `$PORT` 注入埠號,容器啟動 `uvicorn app.web.server:app`。
4. 其他可調環境變數見 [`.env.example`](.env.example):`AGENT_MODEL`、
   `AGENT_MAX_STEPS`、`DAILY_RUN_LIMIT` 等。

---

## 關鍵假設與限制

- **僅操作免登入的公開頁面**:agent 被明確指示不得登入、付款或送出個資。
- **誠實回報**:系統提示要求 Claude 只根據實際觀察到的頁面內容作答,不得捏造數據。
- **單一併發 + 每日上限**:公開 URL 上一次只跑一個 run,並有每日次數上限以保護 API 額度。
- **產物為暫時性**:`app/runs/` 在部署平台上可能於重新部署時清空;此為 demo 用途的合理取捨。
- **示範任務以穩定的公開網站為主**(Hacker News、quotes.toscrape),確保可重現。

---

## 如何運用 AI / agent 工作流完成

- **全程以 Claude Code(Anthropic 官方 CLI)開發**:由 AI agent 規劃架構、撰寫程式、
  逐步以「實作 → 執行測試 → 修正」的迴圈推進,並維持有意義的 Git commit 歷史。
- **Skills**:本 repo 內含一個 Claude Code Skill(見 [`.claude/skills/browser-agent`](.claude/skills/browser-agent/SKILL.md)),
  將「執行一個瀏覽器自動化目標」的流程封裝為可重複呼叫的技能。
- **產品本身即 agent 工作流**:應用核心是一個 LLM 驅動的 agent 迴圈,Claude 透過
  tool-use 自主規劃並執行多步驟瀏覽器操作。

---

## 無機密資料

本專案僅使用公開網站與自建程式碼。API key(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`)
僅透過環境變數 / 平台機密注入,**絕不**寫入版控(`.gitignore` 已排除 `.env`)。
