"""Claude tool-use 的工具定義與分派。

此模組做兩件事:
1. TOOL_SCHEMAS:提供給 Anthropic API 的工具規格(名稱、說明、參數 schema)。
2. dispatch():把 Claude 選用的工具與參數,轉成對 BrowserController 的實際呼叫,
   並回傳「執行結果觀察字串、是否為結束動作、最終結果(若 finish)」。
"""
from __future__ import annotations

from typing import Any

from .browser import BrowserController

# 提供給 Claude 的工具清單。input_schema 採用 JSON Schema。
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "navigate",
        "description": "前往指定的 URL。",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要開啟的完整網址。"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": "點擊觀察清單中指定編號的互動元素。",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "互動元素的編號。"}
            },
            "required": ["index"],
        },
    },
    {
        "name": "type_text",
        "description": "在指定編號的輸入框中填入文字;submit 為 true 時填入後按下 Enter。",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "輸入框元素的編號。"},
                "text": {"type": "string", "description": "要輸入的文字。"},
                "submit": {
                    "type": "boolean",
                    "description": "是否在輸入後按 Enter 送出。",
                    "default": False,
                },
            },
            "required": ["index", "text"],
        },
    },
    {
        "name": "scroll",
        "description": "向上或向下捲動一個視窗高度,以顯示更多內容。",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "捲動方向。",
                    "default": "down",
                }
            },
        },
    },
    {
        "name": "read_page",
        "description": "讀取目前頁面較完整的可見文字(供擷取較長內容時使用)。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "go_back",
        "description": "回到瀏覽器的上一頁。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "finish",
        "description": "目標完成時呼叫,回報最終結果與交付產物。",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "用一兩句話說明完成了什麼。",
                },
                "report_markdown": {
                    "type": "string",
                    "description": "以 Markdown 撰寫的最終報告(交付產物)。",
                },
                "data": {
                    "type": "object",
                    "description": "結構化的關鍵擷取資料,讓結果可被機器驗證。",
                },
            },
            "required": ["summary", "report_markdown"],
        },
    },
]


async def dispatch(
    browser: BrowserController, name: str, tool_input: dict[str, Any]
) -> tuple[str, bool, dict[str, Any] | None]:
    """執行單一工具呼叫。

    回傳 (observation, is_finish, result):
    - observation:此動作的執行結果字串(navigate/click 等的回饋)。
    - is_finish:是否為 finish 動作。
    - result:若為 finish,帶出 summary / report_markdown / data。
    """
    if name == "navigate":
        return await browser.navigate(tool_input["url"]), False, None
    if name == "click":
        return await browser.click(int(tool_input["index"])), False, None
    if name == "type_text":
        return (
            await browser.type_text(
                int(tool_input["index"]),
                tool_input["text"],
                bool(tool_input.get("submit", False)),
            ),
            False,
            None,
        )
    if name == "scroll":
        return await browser.scroll(tool_input.get("direction", "down")), False, None
    if name == "read_page":
        return await browser.read_page(), False, None
    if name == "go_back":
        return await browser.go_back(), False, None
    if name == "finish":
        result = {
            "summary": tool_input.get("summary", ""),
            "report_markdown": tool_input.get("report_markdown", ""),
            "data": tool_input.get("data"),
        }
        return result["summary"], True, result

    return f"未知的工具:{name}", False, None
