"""不需網路或 API key 的單元測試:設定解析、執行記錄、預設任務、工具分派。"""
from __future__ import annotations

import json

import dataclasses

from app.agent.logger import RunLogger, new_run_id
from app.agent.tools import dispatch
from app.config import _as_bool, _as_int, get_settings
from app.runner import RunManager
from app.tasks import PRESET_TASKS, get_preset


def test_as_bool():
    assert _as_bool("true", False) is True
    assert _as_bool("0", True) is False
    assert _as_bool(None, True) is True
    assert _as_bool("YES", False) is True


def test_as_int():
    assert _as_int("25", 10) == 25
    assert _as_int(None, 10) == 10
    assert _as_int("not-a-number", 7) == 7


def test_new_run_id_unique():
    assert new_run_id() != new_run_id()


def test_run_logger_lifecycle(tmp_path):
    """RunLogger 應建立目錄、寫出 run.json,並在 set_result 時輸出 report.md / data.json。"""
    logger = RunLogger(tmp_path, goal="測試目標", start_url="https://example.com", model="claude-x")
    assert logger.dir.exists()

    logger.log_step(1, "想法", "navigate", {"url": "https://example.com"}, "觀察內容", "step-01.png")
    state = json.loads(logger.state_path.read_text(encoding="utf-8"))
    assert state["status"] == "running"
    assert len(state["steps"]) == 1
    assert state["steps"][0]["action"] == "navigate"

    logger.set_result({"summary": "完成", "report_markdown": "# 報告\n內容", "data": {"k": 1}})
    logger.finish("succeeded")

    assert (logger.dir / "report.md").read_text(encoding="utf-8").startswith("# 報告")
    assert json.loads((logger.dir / "data.json").read_text(encoding="utf-8")) == {"k": 1}

    final = json.loads(logger.state_path.read_text(encoding="utf-8"))
    assert final["status"] == "succeeded"
    assert final["finished_at"] is not None

    # log.jsonl 每行為一筆 JSON。
    lines = (logger.dir / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["step"] == 1


def test_presets_well_formed():
    assert len(PRESET_TASKS) >= 1
    for t in PRESET_TASKS:
        assert t.goal and t.start_url.startswith("http")
    assert get_preset(PRESET_TASKS[0].key) is not None
    assert get_preset("does-not-exist") is None


async def test_dispatch_finish_does_not_touch_browser():
    """finish 動作不應呼叫 browser;應回傳 is_finish=True 與結構化結果。"""
    obs, is_finish, result = await dispatch(
        browser=None,  # finish 不會用到 browser
        name="finish",
        tool_input={"summary": "做完了", "report_markdown": "# r", "data": {"a": 1}},
    )
    assert is_finish is True
    assert result["summary"] == "做完了"
    assert result["data"] == {"a": 1}
    assert obs == "做完了"


async def test_dispatch_unknown_tool():
    obs, is_finish, result = await dispatch(browser=None, name="frobnicate", tool_input={})
    assert is_finish is False
    assert result is None
    assert "未知的工具" in obs


def test_runmanager_seeds_samples(tmp_path):
    """RunManager 初始化時應把 samples_dir 內的示範 run 複製進(空的)runs_dir。"""
    empty_runs = tmp_path / "runs"
    settings = dataclasses.replace(get_settings(), runs_dir=empty_runs)
    # 使用專案內真實的 samples_dir(含已提交的示範 run)。
    assert settings.samples_dir.exists()

    manager = RunManager(settings)
    seeded = manager.list_runs()
    assert len(seeded) >= 1
    # 植入後應可查得該筆 run 且產物存在。
    run_id = seeded[0]["run_id"]
    assert (empty_runs / run_id / "run.json").exists()
