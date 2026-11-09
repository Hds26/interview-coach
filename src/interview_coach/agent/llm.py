"""LLM interface. Offline is the default. OpenAI and DeepSeek are selected explicitly."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError

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

    def __init__(self, lang: str = "zh") -> None:
        self.lang = lang if lang in {"zh", "en"} else "zh"

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        del tools
        results = _tool_results(messages)
        if results:
            last = results[-1]
            payload = json.loads(last["content"])
            return LLMResponse(content=render_tool_reply(str(last["name"]), payload, self.lang))
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id="local-1", name=_intent(messages), arguments={})],
        )


def _intent(messages: list[dict]) -> str:
    if not messages or messages[0].get("content") != SYSTEM_PROMPT:
        # Still route; the agent is responsible for sending the system prompt.
        pass
    text = _last_user_text(messages).lower()
    if re.search(r"\bstar\b", text) or any(token in text for token in ("behavioral", "行为面试", "行为题")):
        return "get_progress"
    if any(token in text for token in ("progress", "进度", "completion", "完成率")):
        return "get_progress"
    if any(
        token in text
        for token in (
            "score",
            "weak",
            "assess",
            "掌握",
            "分数",
            "shortboard",
            "confidence",
            "信心",
            "弱",
            "薄弱",
            "短板",
            "不熟",
            "错题",
        )
    ):
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


# https://api-docs.deepseek.com/ — current ids are deepseek-flash and deepseek-v4-pro.
# deepseek-chat was retired, so the default is deepseek-flash. Thinking stays off so
# tool calls stay on the same local loop as the other providers.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"


class DeepSeekLLM:
    """OpenAI-compatible DeepSeek chat client. The HTTP call uses the standard library."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        urlopen: Callable[..., object] | None = None,
        timeout: float = 60.0,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.api_key = (api_key or "").strip()
        if model is None:
            model = os.environ.get("DEEPSEEK_MODEL")
        self.model = (model or "").strip() or DEEPSEEK_MODEL
        if base_url is None:
            base_url = os.environ.get("DEEPSEEK_BASE_URL")
        self.base_url = _normalize_base_url((base_url or "").strip() or DEEPSEEK_BASE_URL)
        self._urlopen = urlopen
        self.timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        if not self.api_key:
            raise LLMConfigError("DEEPSEEK_API_KEY is required for --llm deepseek")
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        body = self._post(payload)
        return _response_from_chat(body)

    def _post(self, payload: dict) -> dict:
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=raw_body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        opener = self._urlopen or urllib.request.urlopen
        try:
            with opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = _read_error_body(exc)
            message = f"DeepSeek API returned HTTP {exc.code}: {detail}"
            raise LLMConfigError(_redact(message, self.api_key)) from exc
        except URLError as exc:
            reason = _redact(str(exc.reason), self.api_key)
            raise LLMConfigError(f"DeepSeek API request failed: {reason}") from exc
        except TimeoutError as exc:
            raise LLMConfigError("DeepSeek API request timed out") from exc
        return _decode_json(raw, self.api_key)


def _normalize_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LLMConfigError("DEEPSEEK_BASE_URL must be an https URL")
    return base


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def _read_error_body(exc: HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:
        return str(exc.msg or "")
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    text = " ".join(text.split())
    if len(text) > 300:
        return text[:300] + "..."
    return text


def _decode_json(raw: bytes | str, secret: str) -> dict:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LLMConfigError("DeepSeek API returned invalid JSON") from exc
    else:
        text = raw
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMConfigError("DeepSeek API returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMConfigError("DeepSeek API returned an unexpected payload")
    if "error" in parsed and "choices" not in parsed:
        message = parsed["error"]
        if isinstance(message, dict):
            message = message.get("message") or message
        raise LLMConfigError(_redact(f"DeepSeek API error: {message}", secret))
    return parsed


def _response_from_chat(payload: dict) -> LLMResponse:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMConfigError("DeepSeek API returned no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LLMConfigError("DeepSeek API returned no message")
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = ""
    return LLMResponse(content=content, tool_calls=_tool_calls_from_message(message))


def _tool_calls_from_message(message: dict) -> list[ToolCall]:
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        raise LLMConfigError("DeepSeek API returned malformed tool calls")
    calls: list[ToolCall] = []
    for index, tool_call in enumerate(raw_calls):
        if not isinstance(tool_call, dict):
            raise LLMConfigError("DeepSeek API returned malformed tool calls")
        function = tool_call.get("function") or {}
        if not isinstance(function, dict):
            raise LLMConfigError("DeepSeek API returned malformed tool calls")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise LLMConfigError("DeepSeek API returned a tool call without a name")
        supplied = function.get("arguments")
        raw_arguments = supplied if supplied not in (None, "") else "{}"
        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            try:
                arguments = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                raise LLMConfigError(f"DeepSeek tool arguments were not valid JSON for {name}") from exc
        if not isinstance(arguments, dict):
            raise LLMConfigError(f"DeepSeek tool arguments for {name} must be a JSON object")
        call_id = tool_call.get("id") or f"call-{index}"
        calls.append(ToolCall(id=str(call_id), name=name, arguments=arguments))
    return calls


def build_llm(name: str, client: object | None = None, lang: str = "zh") -> LLM:
    if name in {"", "offline", "none"}:
        return OfflineLLM(lang=lang)
    if name == "openai":
        return OpenAILLM(client=client)
    if name == "deepseek":
        return DeepSeekLLM()
    raise ValueError("llm must be 'offline', 'openai', or 'deepseek'")
