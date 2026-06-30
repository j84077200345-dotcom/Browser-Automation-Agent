"""FastAPI 應用:觸發 run 的儀表板與檢視執行結果的介面。

路由總覽:
- GET  /                  儀表板:輸入目標、選用預設任務、檢視歷史 run。
- POST /run               觸發一次新的 run,完成後導向該 run 的詳情頁。
- GET  /runs/{id}         單筆 run 詳情頁(前端會輪詢 API 顯示即時進度)。
- GET  /api/status        目前忙碌狀態與每日額度。
- GET  /api/runs          歷史 run 列表(JSON)。
- GET  /api/runs/{id}     單筆 run 完整狀態(JSON,即 run.json)。
- GET  /artifacts/...     靜態提供每次 run 的截圖、report.md、data.json。
- GET  /healthz           健康檢查。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..runner import RunManager
from ..tasks import PRESET_TASKS, get_preset

settings = get_settings()
manager = RunManager(settings)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(title="Browser Automation Agent")

# 將每次 run 的產物目錄以靜態檔案方式提供(截圖、report.md、data.json)。
settings.runs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(settings.runs_dir)), name="artifacts")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str | None = None):
    """儀表板首頁。"""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "presets": PRESET_TASKS,
            "runs": manager.list_runs(),
            "status": manager.status(),
            "error": error,
        },
    )


@app.post("/run")
async def trigger_run(
    request: Request,
    goal: str = Form(...),
    start_url: str = Form(...),
    preset: str = Form(""),
):
    """觸發一次新的 run。若選用了預設任務,則以預設內容覆寫表單。"""
    if preset:
        task = get_preset(preset)
        if task:
            goal, start_url = task.goal, task.start_url

    goal = goal.strip()
    start_url = start_url.strip()
    if not goal or not start_url:
        return await index(request, error="請填入目標與起始 URL。")

    ok, reason = manager.can_start()
    if not ok:
        return await index(request, error=reason)

    run_id = manager.start(goal, start_url)
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str):
    """單筆 run 詳情頁。"""
    state = manager.get_run(run_id)
    if state is None:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "presets": PRESET_TASKS,
                "runs": manager.list_runs(),
                "status": manager.status(),
                "error": f"找不到 run:{run_id}",
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request, "run.html", {"run_id": run_id, "state": state}
    )


@app.get("/api/status")
async def api_status():
    """目前忙碌狀態與每日額度。"""
    return JSONResponse(manager.status())


@app.get("/api/runs")
async def api_runs():
    """歷史 run 列表。"""
    return JSONResponse(manager.list_runs())


@app.get("/api/runs/{run_id}")
async def api_run(run_id: str):
    """單筆 run 完整狀態(即 run.json)。"""
    state = manager.get_run(run_id)
    if state is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(state)


@app.get("/healthz")
async def healthz():
    """健康檢查(部署平台用)。"""
    return {"status": "ok"}
