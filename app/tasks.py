"""預設示範任務。

提供幾個「免登入、可重現」的公開網站任務,讓使用者(或評分者)在 Web 介面上
一鍵觸發、驗證 agent 行為。每個任務包含自然語言目標與起始 URL。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetTask:
    """單一預設任務。"""

    key: str
    title: str
    goal: str
    start_url: str


PRESET_TASKS: list[PresetTask] = [
    PresetTask(
        key="hn_top_story",
        title="Hacker News:頭條 + 留言摘要",
        goal=(
            "在 Hacker News 首頁找出目前排名第 1 的頭條新聞,記下其標題、分數與來源網域,"
            "接著開啟該則新聞的留言頁,閱讀討論內容,並產出一份報告:包含新聞重點,"
            "以及留言區的主要觀點與討論氛圍摘要。"
        ),
        start_url="https://news.ycombinator.com",
    ),
    PresetTask(
        key="hn_frontpage",
        title="Hacker News:首頁前 10 則整理",
        goal=(
            "整理 Hacker News 首頁目前排名前 10 的新聞,對每一則列出排名、標題、分數、"
            "來源網域與留言數,最後產出一份條列式報告與對應的結構化資料。"
        ),
        start_url="https://news.ycombinator.com",
    ),
    PresetTask(
        key="quotes_humor",
        title="Quotes to Scrape:擷取 humor 標籤名言",
        goal=(
            "在這個練習用網站上,找出並擷取所有標記為 humor 標籤的名言,"
            "列出每則名言的內容與作者,並整理成報告與結構化資料。"
        ),
        start_url="https://quotes.toscrape.com/tag/humor/",
    ),
]


def get_preset(key: str) -> PresetTask | None:
    """依 key 取得預設任務,找不到時回傳 None。"""
    return next((t for t in PRESET_TASKS if t.key == key), None)
