import json
from types import SimpleNamespace

import pytest

from interview_coach.agent.coach import CoachAgent
from interview_coach.agent.llm import LLMConfigError, LLMResponse, OpenAILLM, ToolCall
from interview_coach.agent.prompts import SYSTEM_PROMPT
from interview_coach.agent.tools import build_registry
from interview_coach.app import CoachApp
from interview_coach.db import Database


class RecordingLLM:
    name = "recording"

    def complete(self, messages, tools=None):
        self.messages = messages
        self.tools = tools
        return LLMResponse(content="recorded")


def _ready(tmp_path) -> CoachApp:
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend", daily_minutes=30)
    app.create_plan()
    return app


def test_offline_ask_uses_the_plan_without_an_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = _ready(tmp_path)
    answer = app.agent("offline").ask("What should I study today?")
    assert "接下来" in answer
    assert "30" in answer
    assert "做到这几件就算完成" in answer


def test_agent_sends_the_system_prompt_and_tool_specs(tmp_path):
    app = _ready(tmp_path)
    llm = RecordingLLM()
    answer = CoachAgent(llm, build_registry(app)).ask("today")
    assert answer == "recorded"
    assert llm.messages[0]["content"] == SYSTEM_PROMPT
    names = {spec["function"]["name"] for spec in llm.tools}
    assert "get_today" in names
    assert "get_progress" in names


def test_offline_routes_progress_and_scores(tmp_path):
    app = _ready(tmp_path)
    progress = app.agent("offline").ask("show my progress")
    assert "计划 v1" in progress
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 2.0, answered = 2, correct = 0, credit = 0 WHERE topic = 'databases'"
    )
    app.db.conn.commit()
    scores = app.agent("offline").ask("what are my weak scores?")
    assert "目前较薄弱" in scores
    assert "数据库" in scores
    assert "ability" not in scores.lower()


def test_openai_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        OpenAILLM(api_key="").complete([{"role": "user", "content": "hi"}])


def test_openai_adapter_reads_tool_calls():
    function = SimpleNamespace(name="get_today", arguments=json.dumps({}))
    tool_call = SimpleNamespace(id="call-1", function=function)
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class Completions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return response

    completions = Completions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = OpenAILLM(api_key="sk-test", client=client).complete(
        [{"role": "user", "content": "today"}],
        tools=[{"type": "function"}],
    )
    assert result.tool_calls == [ToolCall(id="call-1", name="get_today", arguments={})]
    assert completions.kwargs["model"] == "gpt-4o-mini"
