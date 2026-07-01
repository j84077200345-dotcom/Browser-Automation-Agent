"""run 管理(RunManager)。

負責協調 agent 的執行,並提供 Web 層所需的查詢能力:
- 以非同步背景任務啟動一次 run,並立即回傳 run_id(Web 不需等待整段流程)。
- 一次只允許一個 run(瀏覽器自動化耗資源,避免在小型容器上同時跑多個而 OOM)。
- 每日觸發次數上限(保護公開 URL 上的 API 額度)。
- 讀取 runs 目錄下的 run.json,列出歷史 run 與單筆 run 詳情。
"""
from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent.agent import BrowserAgent
from .agent.logger import RunLogger
from .config import Settings


class RunManager:
    """全域單一 run 協調器。"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._settings.runs_dir.mkdir(parents=True, exist_ok=True)
        self._current_run_id: str | None = None
        self._daily_date: str | None = None
        self._daily_count: int = 0
        self._seed_samples()

    def _seed_samples(self) -> None:
        """把隨程式碼打包的示範 run 植入 runs_dir(尚未存在時才複製)。

        這樣即使在 Zeabur 這類重新部署會清空檔案系統的平台上,公開 URL 一載入就有
        可驗證的示範產物可看,不必先觸發 API 呼叫。
        """
        samples = self._settings.samples_dir
        if not samples.exists():
            return
        for sample in samples.iterdir():
            if not sample.is_dir():
                continue
            target = self._settings.runs_dir / sample.name
            if not target.exists():
                try:
                    shutil.copytree(sample, target)
                except OSError:
                    continue

    # --- 觸發 run ---

    def status(self) -> dict[str, Any]:
        """回傳目前忙碌狀態與額度資訊,供 Web 顯示與前端判斷。"""
        return {
            "busy": self._current_run_id is not None,
            "current_run_id": self._current_run_id,
            "has_api_key": self._settings.has_api_key,
            "provider": self._settings.llm_provider,
            "model": self._settings.agent_model,
            "daily_limit": self._settings.daily_run_limit,
            "daily_used": self._daily_count if self._is_today() else 0,
        }

    def can_start(self) -> tuple[bool, str]:
        """檢查目前是否可啟動新的 run,回傳 (是否可啟動, 原因)。"""
        if not self._settings.has_api_key:
            return False, "伺服器未設定 ANTHROPIC_API_KEY,無法執行 agent。"
        if self._current_run_id is not None:
            return False, "目前已有一個 run 正在執行,請稍候再試。"
        limit = self._settings.daily_run_limit
        if limit > 0 and self._is_today() and self._daily_count >= limit:
            return False, f"已達每日觸發上限({limit} 次),請明日再試。"
        return True, ""

    def start(self, goal: str, start_url: str) -> str:
        """建立 run 並以背景任務執行,立即回傳 run_id。"""
        logger = RunLogger(
            runs_dir=self._settings.runs_dir,
            goal=goal,
            start_url=start_url,
            model=self._settings.agent_model,
        )
        self._current_run_id = logger.run_id
        self._bump_daily()
        asyncio.create_task(self._execute(logger, goal, start_url))
        return logger.run_id

    async def _execute(self, logger: RunLogger, goal: str, start_url: str) -> None:
        """實際執行 agent;無論成功或失敗都釋放忙碌狀態。"""
        try:
            agent = BrowserAgent(self._settings, logger)
            await agent.run(goal, start_url)
        except Exception:
            # 錯誤已由 agent / logger 記錄到 run.json,此處僅確保不影響伺服器。
            pass
        finally:
            self._current_run_id = None

    # --- 查詢 ---

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """列出歷史 run(依時間新到舊),只取摘要欄位。"""
        runs = []
        for state in self._iter_run_states():
            runs.append(
                {
                    "run_id": state.get("run_id"),
                    "goal": state.get("goal"),
                    "status": state.get("status"),
                    "started_at": state.get("started_at"),
                    "steps": len(state.get("steps", [])),
                }
            )
        runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        return runs[:limit]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """取得單筆 run 的完整狀態(run.json),找不到時回傳 None。"""
        path = self._settings.runs_dir / run_id / "run.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def run_dir(self, run_id: str) -> Path:
        """回傳某次 run 的目錄路徑。"""
        return self._settings.runs_dir / run_id

    # --- 內部工具 ---

    def _iter_run_states(self):
        for child in self._settings.runs_dir.iterdir():
            state_file = child / "run.json"
            if state_file.exists():
                try:
                    yield json.loads(state_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _is_today(self) -> bool:
        return self._daily_date == self._today()

    def _bump_daily(self) -> None:
        today = self._today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        self._daily_count += 1
