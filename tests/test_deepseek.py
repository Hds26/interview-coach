"""DeepSeek provider tests. HTTP is mocked; no live key is required."""

import io
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from interview_coach.agent.coach import CoachAgent
from interview_coach.agent.llm import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLMConfigError,
    DeepSeekLLM,
    build_llm,
)
from interview_coach.agent.prompts import SYSTEM_PROMPT
from interview_coach.agent.tools import build_registry
from interview_coach.app import CoachApp
from interview_coach.cli import build_parser, main
from interview_coach.db import Database


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ready(tmp_path) -> CoachApp:
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend", daily_minutes=30)
    app.create_plan()
    return app


def _chat(message: dict) -> bytes:
    return json.dumps({"choices": [{"message": message}]}).encode()


def test_deepseek_requires_a_key_and_skips_http(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("HTTP should not be called without a key")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    llm = build_llm("deepseek")
    assert isinstance(llm, DeepSeekLLM)
    with pytest.raises(LLMConfigError, match="DEEPSEEK_API_KEY"):
        llm.complete([{"role": "user", "content": "hi"}])

    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    with pytest.raises(LLMConfigError, match="DEEPSEEK_API_KEY"):
        DeepSeekLLM().complete([{"role": "user", "content": "hi"}])


def test_deepseek_posts_chat_completions(monkeypatch):
    captured = {}

    def fake(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode())
        message = {"role": "assistant", "content": "Study hashing today."}
        return _Body(_chat(message))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    result = DeepSeekLLM(api_key="test-key").complete(
        [{"role": "user", "content": "today"}],
        tools=[{"type": "function", "function": {"name": "get_today"}}],
    )
    assert result.content == "Study hashing today."
    assert result.tool_calls == []
    assert captured["url"] == f"{DEEPSEEK_BASE_URL}/chat/completions"
    assert captured["timeout"] == 60.0
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == DEEPSEEK_MODEL
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["stream"] is False
    assert captured["body"]["tools"][0]["function"]["name"] == "get_today"
    assert "test-key" not in json.dumps(captured["body"])


def test_model_and_base_url_can_be_overridden(monkeypatch):
    captured = {}

    def fake(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _Body(_chat({"role": "assistant", "content": "ok"}))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    DeepSeekLLM(
        api_key="test-key",
        model="deepseek-v4-pro",
        base_url="https://example.com/v1/",
    ).complete([{"role": "user", "content": "hi"}])
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"]["model"] == "deepseek-v4-pro"

    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.com")
    DeepSeekLLM(api_key="test-key").complete([{"role": "user", "content": "hi"}])
    assert captured["url"] == "https://example.com/chat/completions"
    assert captured["body"]["model"] == "deepseek-v4-pro"


def test_base_url_must_be_https():
    with pytest.raises(LLMConfigError, match="https"):
        DeepSeekLLM(api_key="test-key", base_url="http://example.com")


def test_deepseek_ask_runs_local_tools_over_mocked_http(tmp_path, monkeypatch):
    calls = []

    def fake(request, timeout=None):
        payload = json.loads(request.data.decode())
        calls.append(payload)
        assert request.get_header("Authorization") == "Bearer test-key"
        assert b"test-key" not in request.data
        if len(calls) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_today", "arguments": "{}"},
                    }
                ],
            }
        else:
            message = {"role": "assistant", "content": "Review day 1 acceptance criteria."}
        return _Body(_chat(message))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    app = _ready(tmp_path)
    answer = CoachAgent(DeepSeekLLM(api_key="test-key"), build_registry(app)).ask(
        "What should I study today?"
    )
    assert answer == "Review day 1 acceptance criteria."
    assert calls[0]["messages"][0]["content"] == SYSTEM_PROMPT
    names = {spec["function"]["name"] for spec in calls[0]["tools"]}
    assert "get_today" in names
    assert "get_progress" in names
    tool_messages = [item for item in calls[1]["messages"] if item["role"] == "tool"]
    assert tool_messages[-1]["name"] == "get_today"
    assert "acceptance_criteria" in tool_messages[-1]["content"]


def test_http_error_redacts_the_key(monkeypatch):
    secret = "super-secret-deepseek-key"

    def fake(request, timeout=None):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            None,
            io.BytesIO(f"invalid key {secret}".encode()),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake)
    with pytest.raises(LLMConfigError, match="401") as exc_info:
        DeepSeekLLM(api_key=secret).complete([{"role": "user", "content": "hi"}])
    text = str(exc_info.value)
    assert secret not in text
    assert "[redacted]" in text


def test_url_error_and_invalid_json(monkeypatch):
    def refuse(request, timeout=None):
        raise URLError("name resolution failed")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(LLMConfigError, match="request failed"):
        DeepSeekLLM(api_key="test-key").complete([{"role": "user", "content": "hi"}])

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Body(b"not-json"))
    with pytest.raises(LLMConfigError, match="invalid JSON"):
        DeepSeekLLM(api_key="test-key").complete([{"role": "user", "content": "hi"}])

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Body(b"\xff"))
    with pytest.raises(LLMConfigError, match="invalid JSON"):
        DeepSeekLLM(api_key="test-key").complete([{"role": "user", "content": "hi"}])

    secret = "test-key"
    error = json.dumps({"error": {"message": f"rejected {secret}"}}).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=None: _Body(error))
    with pytest.raises(LLMConfigError, match="DeepSeek API error") as exc_info:
        DeepSeekLLM(api_key=secret).complete([{"role": "user", "content": "hi"}])
    assert secret not in str(exc_info.value)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _Body(_chat({"content": "", "tool_calls": [
            {"id": "c", "function": {"name": "get_today", "arguments": "not-json"}}
        ]})),
    )
    with pytest.raises(LLMConfigError, match="not valid JSON"):
        DeepSeekLLM(api_key="test-key").complete([{"role": "user", "content": "hi"}])


def test_offline_ask_ignores_a_deepseek_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "should-not-be-sent")

    def boom(*args, **kwargs):
        raise AssertionError("offline must not call HTTP")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    answer = _ready(tmp_path).agent("offline").ask("What should I study today?")
    assert "Acceptance criteria" in answer


def test_cli_deepseek_missing_key_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("HTTP should not be called without a key")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    db = ["--db", str(tmp_path / "coach.sqlite")]
    code = main([*db, "ask", "what should I study today", "--llm", "deepseek"])
    assert code == 1
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err

    code = main(["--llm", "deepseek", *db, "ask", "hello"])
    assert code == 1
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err


def test_cli_ask_deepseek_prints_the_mocked_answer(tmp_path, monkeypatch, capsys):
    db = tmp_path / "coach.sqlite"
    prefix = ["--db", str(db)]
    assert main([*prefix, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    assert main([*prefix, "plan"]) == 0
    capsys.readouterr()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "cli-test-key")
    calls = []

    def fake(request, timeout=None):
        payload = json.loads(request.data.decode())
        calls.append(payload)
        assert request.get_header("Authorization") == "Bearer cli-test-key"
        assert b"cli-test-key" not in request.data
        if len(calls) == 1:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-7",
                        "type": "function",
                        "function": {"name": "get_today", "arguments": "{}"},
                    }
                ],
            }
        else:
            message = {"role": "assistant", "content": "Do day 1, then check the acceptance criteria."}
        return _Body(_chat(message))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    code = main([*prefix, "ask", "what should I study today", "--llm", "deepseek"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "Do day 1, then check the acceptance criteria."
    assert len(calls) == 2
    assert calls[0]["model"] == "deepseek-flash"


def test_parser_accepts_deepseek_before_or_after_the_command():
    parser = build_parser()
    after = parser.parse_args(["ask", "hello", "--llm", "deepseek"])
    before = parser.parse_args(["--llm", "deepseek", "ask", "hello"])
    assert after.llm == "deepseek"
    assert before.llm == "deepseek"
    offline = parser.parse_args(["ask", "hello"])
    assert not hasattr(offline, "llm")


def test_env_example_is_empty_and_dotenv_is_ignored():
    root = Path(__file__).resolve().parents[1]
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in example
    value = ""
    for line in example.splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            value = line.split("=", 1)[1]
    assert value == ""
    assert "sk-" not in example.lower()
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=root, check=False)
    assert ignored.returncode == 0
    tracked = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=root, check=False)
    assert tracked.returncode == 1


def test_unknown_llm_name_is_rejected():
    with pytest.raises(ValueError, match="deepseek"):
        build_llm("other")
