---
name: browser-agent
description: 執行一個瀏覽器自動化目標——以本專案中由 Claude 驅動的 Playwright agent,操作免登入的公開網站來擷取資料或產出報告。當使用者想「自動瀏覽某網站並整理/摘要/擷取內容」時使用。
---

# Browser Automation Agent(技能)

把一個自然語言目標交給本專案的 agent,讓它以 headless 瀏覽器逐步完成,並產出
報告、結構化資料與截圖。

## 何時使用

- 使用者想自動操作某個**公開、免登入**的網站(如 Hacker News、文件站、列表頁),
  以擷取資料或產生摘要報告。
- 使用者想驗證或重現一個瀏覽器自動化流程。

## 如何執行

先確認已啟用虛擬環境 `browser_auto_env`,並依 `LLM_PROVIDER` 設定對應的 API key
(`ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`)。

**用預設任務(最快驗證):**
```bash
python -m app.cli --list                 # 列出預設任務
python -m app.cli --preset hn_top_story  # 執行
```

**自訂目標:**
```bash
python -m app.cli --goal "在 Hacker News 找出頭條並摘要其留言討論" \
                  --url  https://news.ycombinator.com
```

**或啟動 Web 介面**(可即時觀看步驟與截圖):
```bash
uvicorn app.web.server:app --reload   # 開啟 http://localhost:8000
```

## 產物位置

每次執行會在 `app/runs/<run_id>/` 產生:
- `report.md` — 交付報告
- `data.json` — 結構化擷取資料
- `screenshots/step-NN.png` — 每一步截圖
- `run.json` / `log.jsonl` — 完整執行記錄

## 注意事項

- 僅操作免登入公開頁面;不得登入、付款或送出個資。
- 只根據實際觀察到的頁面內容作答,不得捏造資料。
- 可用環境變數調整行為:`AGENT_MODEL`、`AGENT_MAX_STEPS`、`HEADLESS`。
