"""LLM interface. Offline is the default. OpenAI is optional and never imported unless selected."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol

from interview_coach.agent.prompts import SYSTEM_PROMPT, render_tool_reply


class LLMConfigError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Return either a final answer or tool calls to run locally."""


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _tool_results(messages: list[dict]) -> list[dict]:
    return [message for message in messages if message.get("role") == "tool"]


class OfflineLLM:
    """Pick a local tool from the question, then draft the reply from its JSON result."""

    name = "offline"

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        del tools
        results = _tool_results(messages)
        if results:
            last = results[-1]
            payload = json.loads(last["content"])
            return LLMResponse(content=render_tool_reply(str(last["name"]), payload))
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id="local-1", name=_intent(messages), arguments={})],
        )


def _intent(messages: list[dict]) -> str:
    if not messages or messages[0].get("content") != SYSTEM_PROMPT:
        # Still route; the agent is responsible for sending the system prompt.
        pass
    text = _last_user_text(messages).lower()
    if any(token in text for token in ("progress", "进度", "completion", "完成率")):
        return "get_progress"
    if any(token in text for token in ("score", "weak", "assess", "掌握", "分数", "shortboard")):
        return "get_scores"
    if any(token in text for token in ("profile", "画像", "who am i")):
        return "get_profile"
    if any(token in text for token in ("plan", "计划", "week", "本周")) and "today" not in text and "今天" not in text:
        return "get_plan"
    return "get_today"


class OpenAILLM:
    """Thin adapter over the OpenAI chat API. Constructing it does not import the SDK."""

    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        client: object | None = None,
    ) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY") if api_key is None else api_key
        self.model = model
        self._client = client

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        client = self._client
        if client is None:
            if not self.api_key:
                raise LLMConfigError("OPENAI_API_KEY is required for --llm openai")
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            self._client = client
        kwargs: dict = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        calls: list[ToolCall] = []
        for index, tool_call in enumerate(getattr(message, "tool_calls", None) or []):
            function = tool_call.function
            raw_arguments = function.arguments or "{}"
            calls.append(
                ToolCall(
                    id=getattr(tool_call, "id", None) or f"call-{index}",
                    name=function.name,
                    arguments=json.loads(raw_arguments),
                )
            )
        return LLMResponse(content=message.content or "", tool_calls=calls)


def build_llm(name: str, client: object | None = None) -> LLM:
    if name in {"", "offline", "none"}:
        return OfflineLLM()
    if name == "openai":
        return OpenAILLM(client=client)
    raise ValueError("llm must be 'offline' or 'openai'")
