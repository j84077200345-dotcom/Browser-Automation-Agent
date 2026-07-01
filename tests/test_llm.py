"""LLM 供應商抽象層的離線測試:中立回合 → 各供應商格式的轉換,以及設定解析。

不需網路:僅建立 client(以假 key,建構時不發送請求)並檢查訊息/工具格式轉換。
"""
from __future__ import annotations

import json

from app.agent.llm import (
    AnthropicClient,
    AssistantTurn,
    OpenAIClient,
    ToolCall,
    ToolResult,
    ToolResultsTurn,
    UserTurn,
)
from app.agent.tools import TOOL_DEFS
from app.config import get_settings

_TURNS = [
    UserTurn("目標與初始觀察"),
    AssistantTurn("我要點擊搜尋", [ToolCall("call_1", "click", {"index": 3})]),
    ToolResultsTurn([ToolResult("call_1", "已點擊元素 [3]")]),
]


def test_anthropic_message_and_tool_format():
    client = AnthropicClient(api_key="dummy", model="claude-sonnet-4-6")
    msgs = client._messages(_TURNS)

    assert msgs[0] == {"role": "user", "content": "目標與初始觀察"}
    # assistant 回合:含 text 與 tool_use 區塊
    assert msgs[1]["role"] == "assistant"
    blocks = msgs[1]["content"]
    assert any(b["type"] == "text" for b in blocks)
    tu = next(b for b in blocks if b["type"] == "tool_use")
    assert tu["name"] == "click" and tu["input"] == {"index": 3} and tu["id"] == "call_1"
    # 工具結果回合:轉為 user + tool_result
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"][0]["type"] == "tool_result"
    assert msgs[2]["content"][0]["tool_use_id"] == "call_1"

    tools = client._tools(TOOL_DEFS)
    assert tools[0]["name"] and "input_schema" in tools[0]


def test_openai_message_and_tool_format():
    client = OpenAIClient(api_key="dummy", model="gpt-4o")
    msgs = client._messages("系統提示", _TURNS)

    assert msgs[0] == {"role": "system", "content": "系統提示"}
    assert msgs[1] == {"role": "user", "content": "目標與初始觀察"}
    # assistant 回合:tool_calls 的 arguments 為 JSON 字串
    assert msgs[2]["role"] == "assistant"
    call = msgs[2]["tool_calls"][0]
    assert call["type"] == "function" and call["function"]["name"] == "click"
    assert json.loads(call["function"]["arguments"]) == {"index": 3}
    # 工具結果回合:轉為 role=tool 訊息
    assert msgs[3] == {"role": "tool", "tool_call_id": "call_1", "content": "已點擊元素 [3]"}

    tools = client._tools(TOOL_DEFS)
    assert tools[0]["type"] == "function" and "parameters" in tools[0]["function"]


def test_settings_provider_resolution(monkeypatch):
    # 預設 anthropic → claude 預設模型
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    s = get_settings()
    assert s.llm_provider == "anthropic"
    assert s.agent_model == "claude-sonnet-4-6"

    # 切換 openai → gpt 預設模型,且 active_api_key 取 openai 的 key
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    s = get_settings()
    assert s.llm_provider == "openai"
    assert s.agent_model == "gpt-4o"
    assert s.active_api_key == "sk-openai-test"
    assert s.has_api_key is True

    # AGENT_MODEL 明確覆寫預設
    monkeypatch.setenv("AGENT_MODEL", "gpt-4.1")
    assert get_settings().agent_model == "gpt-4.1"

    # 未知供應商 → 退回 anthropic
    monkeypatch.setenv("LLM_PROVIDER", "banana")
    assert get_settings().llm_provider == "anthropic"
