"""agent 主迴圈:以 Claude tool-use 驅動瀏覽器。

流程概述:
1. 啟動瀏覽器並開啟起始頁,建立初始觀察。
2. 反覆向 Claude 請求下一步動作(tool-use),執行該動作,並把「動作結果 + 新頁面觀察」
   當成 tool_result 回傳給 Claude,直到 Claude 呼叫 finish 或達到最大步數。
3. 全程透過 RunLogger 記錄每一步、截圖,以及最終報告與結構化資料。
"""
from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from ..config import Settings
from .browser import BrowserController
from .logger import RunLogger
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, dispatch

# 每次向 Claude 請求時的輸出上限。非 finish 步驟只會產生簡短工具呼叫,
# 但 finish 的報告可能較長,故給予較寬裕的額度(未用到的部分不計費)。
_MAX_TOKENS = 8000


class BrowserAgent:
    """封裝一次完整的 agent run。"""

    def __init__(self, settings: Settings, logger: RunLogger):
        self._settings = settings
        self._logger = logger
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def run(self, goal: str, start_url: str) -> dict[str, Any]:
        """執行一次 run,回傳最終的 run 狀態(即 run.json 內容)。"""
        if not self._settings.has_api_key:
            self._logger.finish("failed", error="未設定 ANTHROPIC_API_KEY")
            return self._logger.state

        max_steps = self._settings.agent_max_steps
        browser = BrowserController(headless=self._settings.headless)
        await browser.start()
        try:
            # 開啟起始頁並建立初始觀察(以 step 0 的截圖記錄起點)。
            nav_result = await browser.navigate(start_url)
            await browser.screenshot(self._logger.screenshot_path(0))
            initial_obs = await browser.observation(0, max_steps)
            self._logger.log_step(
                0, "開啟起始頁", "navigate", {"url": start_url},
                f"{nav_result}\n\n{initial_obs}", screenshot_file="step-00.png",
            )

            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": (
                        f"GOAL: {goal}\n\n"
                        f"以下是起始頁面的觀察,請開始達成目標:\n\n{initial_obs}"
                    ),
                }
            ]

            for step in range(1, max_steps + 1):
                resp = await self._client.messages.create(
                    model=self._settings.agent_model,
                    max_tokens=_MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
                # 把 Claude 本回合的回覆(含 thought 與 tool_use)加入對話歷史。
                messages.append({"role": "assistant", "content": resp.content})

                thought = " ".join(
                    b.text for b in resp.content if b.type == "text"
                ).strip()
                tool_uses = [b for b in resp.content if b.type == "tool_use"]

                # Claude 未呼叫任何工具:提醒它使用工具或呼叫 finish,再續下一步。
                if not tool_uses:
                    messages.append(
                        {
                            "role": "user",
                            "content": "請使用提供的工具進行下一步操作,或在目標完成時呼叫 finish。",
                        }
                    )
                    self._logger.log_step(
                        step, thought, "noop", {}, "Claude 未呼叫工具,已提示其繼續。"
                    )
                    continue

                # 依序執行本回合的工具呼叫(通常為一個)。
                tool_results = []
                finished = False
                for tu in tool_uses:
                    obs, is_finish, result = await dispatch(browser, tu.name, tu.input)

                    if is_finish:
                        self._logger.set_result(result)
                        # finish 的 report_markdown 已另存 report.md,記錄時不重複存全文。
                        slim_input = {"summary": result.get("summary", "")}
                        self._logger.log_step(
                            step, thought, "finish", slim_input,
                            result.get("summary", "已完成"),
                        )
                        tool_results.append(
                            {"type": "tool_result", "tool_use_id": tu.id,
                             "content": "已記錄最終結果,run 結束。"}
                        )
                        finished = True
                        break

                    # 一般動作:截圖 → 建立新觀察 → 回傳給 Claude,並記錄此步驟。
                    shot = self._logger.screenshot_path(step)
                    await browser.screenshot(shot)
                    new_obs = await browser.observation(step, max_steps)
                    self._logger.log_step(
                        step, thought, tu.name, dict(tu.input),
                        obs, screenshot_file=shot.name,
                    )
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tu.id,
                         "content": f"{obs}\n\n{new_obs}"}
                    )

                if finished:
                    self._logger.finish("succeeded")
                    return self._logger.state

                messages.append({"role": "user", "content": tool_results})

            # 迴圈跑完仍未呼叫 finish:視為未在步數內完成。
            self._logger.finish("failed", error=f"達到最大步數({max_steps})仍未完成目標")
            return self._logger.state

        except Exception as exc:  # noqa: BLE001 - 記錄錯誤後重新拋出
            self._logger.finish("failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            await browser.close()
