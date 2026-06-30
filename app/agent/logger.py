"""執行記錄(RunLogger)。

每一次 agent run 都對應一個獨立目錄,內容包含:
- run.json:該次 run 的標準狀態檔(Web UI 會輪詢此檔以顯示進度)。
- log.jsonl:逐步事件記錄,每行一筆,方便追蹤與除錯。
- screenshots/:每一步的截圖,作為可驗證的人類可讀產物。
- report.md / data.json:最終交付的報告與結構化資料(由 agent 的 finish 動作產生)。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    """回傳目前 UTC 時間的 ISO 8601 字串。"""
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    """產生一個可排序、且具唯一性的 run 識別碼(時間戳 + 短亂數)。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


class RunLogger:
    """負責單一次 run 的所有檔案產物與狀態維護。"""

    def __init__(self, runs_dir: Path, goal: str, start_url: str, model: str):
        self.run_id = new_run_id()
        self.dir = runs_dir / self.run_id
        self.screenshots_dir = self.dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = self.dir / "log.jsonl"
        self.state_path = self.dir / "run.json"

        # run.json 的標準內容,會在每一步後更新並寫回磁碟。
        self.state: dict[str, Any] = {
            "run_id": self.run_id,
            "goal": goal,
            "start_url": start_url,
            "model": model,
            "status": "running",          # running | succeeded | failed
            "started_at": _utc_now_iso(),
            "finished_at": None,
            "steps": [],                   # 每一步的摘要記錄
            "result": None,                # finish 動作產生的最終結果
            "error": None,
        }
        self._save_state()

    # --- 對外方法 ---

    def log_step(
        self,
        step_no: int,
        thought: str,
        action: str,
        action_input: dict[str, Any],
        observation: str,
        screenshot_file: str | None = None,
    ) -> None:
        """記錄 agent 的一個「思考 → 動作 → 觀察」步驟。"""
        record = {
            "step": step_no,
            "ts": _utc_now_iso(),
            "thought": thought,
            "action": action,
            "action_input": action_input,
            # 觀察內容可能很長,在 run.json 摘要中截斷,完整內容仍寫入 log.jsonl。
            "observation": observation,
            "screenshot": screenshot_file,
        }
        self._append_jsonl(record)

        summary = dict(record)
        summary["observation"] = _truncate(observation, 600)
        self.state["steps"].append(summary)
        self._save_state()

    def set_result(self, result: dict[str, Any]) -> None:
        """記錄 agent 透過 finish 動作回報的最終結果,並寫出 report.md / data.json。"""
        self.state["result"] = result

        report = result.get("report_markdown")
        if report:
            (self.dir / "report.md").write_text(report, encoding="utf-8")

        data = result.get("data")
        if data is not None:
            (self.dir / "data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        self._save_state()

    def finish(self, status: str, error: str | None = None) -> None:
        """標記 run 結束(succeeded / failed)。"""
        self.state["status"] = status
        self.state["error"] = error
        self.state["finished_at"] = _utc_now_iso()
        self._save_state()

    def screenshot_path(self, step_no: int) -> Path:
        """回傳某一步截圖應存放的路徑。"""
        return self.screenshots_dir / f"step-{step_no:02d}.png"

    # --- 內部工具 ---

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save_state(self) -> None:
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _truncate(text: str, limit: int) -> str:
    """將字串截斷至指定長度,超過時附上省略標記。"""
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + f"… [已截斷,共 {len(text)} 字]"
