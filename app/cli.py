"""命令列執行入口,供本機測試與驗證使用。

範例:
    python -m app.cli --preset hn_top_story
    python -m app.cli --goal "在 Hacker News 找出頭條並摘要留言" --url https://news.ycombinator.com
    python -m app.cli --list
"""
from __future__ import annotations

import argparse
import asyncio

from .agent.agent import BrowserAgent
from .agent.logger import RunLogger
from .config import get_settings
from .tasks import PRESET_TASKS, get_preset


async def _run(goal: str, url: str) -> None:
    settings = get_settings()
    if not settings.has_api_key:
        key_name = "OPENAI_API_KEY" if settings.llm_provider == "openai" else "ANTHROPIC_API_KEY"
        print(f"錯誤:未設定 {key_name}(請於 .env 或環境變數提供)。")
        return
    print(f"供應商:{settings.llm_provider} / 模型:{settings.agent_model}")

    logger = RunLogger(settings.runs_dir, goal, url, settings.agent_model)
    print(f"▶ 開始 run {logger.run_id}\n  目標:{goal}\n  起點:{url}")
    agent = BrowserAgent(settings, logger)
    state = await agent.run(goal, url)

    print(f"\n狀態:{state['status']}  步數:{len(state['steps'])}")
    if state.get("error"):
        print(f"錯誤:{state['error']}")
    if state.get("result"):
        print(f"摘要:{state['result'].get('summary', '')}")
    print(f"產物目錄:{logger.dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="瀏覽器自動化代理 — 命令列執行")
    parser.add_argument("--goal", help="自然語言目標")
    parser.add_argument("--url", help="起始 URL")
    parser.add_argument("--preset", help="預設任務 key(見 --list)")
    parser.add_argument("--list", action="store_true", help="列出所有預設任務")
    args = parser.parse_args()

    if args.list:
        print("可用的預設任務:")
        for t in PRESET_TASKS:
            print(f"  {t.key:16s} {t.title}\n      起點:{t.start_url}")
        return

    goal, url = args.goal, args.url
    if args.preset:
        task = get_preset(args.preset)
        if not task:
            print(f"找不到預設任務:{args.preset}(用 --list 查看)")
            return
        goal, url = task.goal, task.start_url

    if not goal or not url:
        parser.error("請提供 --goal 與 --url,或使用 --preset。")

    asyncio.run(_run(goal, url))


if __name__ == "__main__":
    main()
