"""LLM 供應商抽象層。

agent 迴圈以一組「中立」的對話回合(turn)與工具呼叫來運作,不直接依賴任何一家
供應商的 API 格式。各家 adapter 負責把中立回合翻譯成自家格式、發送請求,並把回應
翻回中立的 AssistantTurn。目前支援 Anthropic(tool-use)與 OpenAI(function calling),
以 LLM_PROVIDER 環境變數切換。

中立對話模型:
- UserTurn(text):使用者/系統餵入的文字(含頁面觀察)。
- AssistantTurn(text, tool_calls):模型的思考文字與其決定的工具呼叫。
- ToolResultsTurn(results):對應每個工具呼叫的執行結果。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings


# --- 中立對話資料結構 ---

@dataclass
class ToolCall:
    """一次工具呼叫:id 用於回填結果,name/input 為工具與參數。"""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class UserTurn:
    text: str


@dataclass
class AssistantTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResult:
    id: str
    content: str


@dataclass
class ToolResultsTurn:
    results: list[ToolResult]


Turn = UserTurn | AssistantTurn | ToolResultsTurn


# --- 供應商 adapter ---

class LLMClient:
    """供應商 adapter 的共同介面。"""

    async def complete(
        self, system: str, turns: list[Turn], tools: list[dict[str, Any]], max_tokens: int
    ) -> AssistantTurn:
        raise NotImplementedError


class AnthropicClient(LLMClient):
    """Anthropic Claude 的 tool-use adapter。"""

    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Anthropic 格式:{name, description, input_schema}
        return [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]

    def _messages(self, turns: list[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in turns:
            if isinstance(turn, UserTurn):
                messages.append({"role": "user", "content": turn.text})
            elif isinstance(turn, AssistantTurn):
                content: list[dict[str, Any]] = []
                if turn.text:
                    content.append({"type": "text", "text": turn.text})
                for tc in turn.tool_calls:
                    content.append(
                        {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                    )
                messages.append({"role": "assistant", "content": content})
            elif isinstance(turn, ToolResultsTurn):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": r.id, "content": r.content}
                            for r in turn.results
                        ],
                    }
                )
        return messages

    async def complete(self, system, turns, tools, max_tokens) -> AssistantTurn:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=self._tools(tools),
            messages=self._messages(turns),
        )
        text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=dict(b.input))
            for b in resp.content
            if b.type == "tool_use"
        ]
        return AssistantTurn(text=text, tool_calls=tool_calls)


class OpenAIClient(LLMClient):
    """OpenAI 的 function calling adapter。"""

    def __init__(self, api_key: str, model: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # OpenAI 格式:{type:function, function:{name, description, parameters}}
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def _messages(self, system: str, turns: list[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for turn in turns:
            if isinstance(turn, UserTurn):
                messages.append({"role": "user", "content": turn.text})
            elif isinstance(turn, AssistantTurn):
                msg: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
                if turn.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.input, ensure_ascii=False),
                            },
                        }
                        for tc in turn.tool_calls
                    ]
                messages.append(msg)
            elif isinstance(turn, ToolResultsTurn):
                for r in turn.results:
                    messages.append(
                        {"role": "tool", "tool_call_id": r.id, "content": r.content}
                    )
        return messages

    async def complete(self, system, turns, tools, max_tokens) -> AssistantTurn:
        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            tools=self._tools(tools),
            tool_choice="auto",
            messages=self._messages(system, turns),
        )
        message = resp.choices[0].message
        tool_calls = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
        return AssistantTurn(text=(message.content or "").strip(), tool_calls=tool_calls)


def get_llm_client(settings: Settings) -> LLMClient:
    """依設定建立對應供應商的 LLMClient。"""
    if settings.llm_provider == "openai":
        return OpenAIClient(settings.openai_api_key, settings.agent_model)
    return AnthropicClient(settings.anthropic_api_key, settings.agent_model)
