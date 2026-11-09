"""Optional research: confirm before writing, and never make it part of today."""

import io
import json
from datetime import date, timedelta

import pytest

from interview_coach.app import CoachApp
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.rubric import score_rubric
from interview_coach.cli import main
from interview_coach.db import Database
from interview_coach.research.extract import consistent_skills, extract_skills
from interview_coach.research.search import SearchHit, SearchUnavailable, filter_hits, parse_serp, skills_from_hits
from interview_coach.research.service import boost_on
from interview_coach.research.deepseek import proposed_skill_names

NOTE = "后端岗位，使用 Redis 和 MySQL。\nSENTINEL_PHRASE_不要入库，这是一段不该被保存的职位原文。"
AD_LINE = "加微信领取课程优惠，保过面试。"


def _app(path):
    app = CoachApp(Database(path))
    app.init_profile("Ada", "generalist", target="generic_tech")
    return app


def test_paste_preview_maps_skills_and_does_not_keep_the_note(tmp_path):
    app = _app(tmp_path / "coach.sqlite")
    preview = app.preview_paste(NOTE + "\n" + AD_LINE, on=date(2026, 4, 1))
    assert any(skill.name == "redis" and skill.topic == "databases" for skill in preview.skills)
    assert preview.items
    assert all("SENTINEL_PHRASE_不要入库" not in item.prompt for item in preview.items)
    assert all("加微信" not in item.prompt for item in preview.items)
    opened = next(item for item in preview.items if item.kind == "open")
    assert score_rubric(opened, "catalog of unsorted values").hit_points == 0
    assert score_rubric(opened, "redis 解决缓存问题，代价是过期，属于数据库这个主题").hit_points >= 1
    assert app.db.research_counts()["research_session"] == 0


def test_reject_writes_nothing_and_leaves_the_plan(tmp_path, monkeypatch, capsys):
    app = _app(tmp_path / "coach.sqlite")
    plan = app.create_plan(start=date(2026, 4, 1))
    before = [(day.day_index, day.focus, day.day_date, day.status) for day in plan.days]
    monkeypatch.setattr("sys.stdin", io.StringIO(NOTE))
    code = main(["--db", str(tmp_path / "coach.sqlite"), "research", "--paste", "--on", "2026-04-01"])
    assert code == 0
    output = capsys.readouterr().out
    assert "未确认，没有写入" in output
    assert "Redis" in output or "redis" in output
    assert app.db.research_counts()["research_session"] == 0
    after = app.db.get_active_plan()
    assert [(day.day_index, day.focus, day.day_date, day.status) for day in after.days] == before
    assert b"SENTINEL_PHRASE" not in (tmp_path / "coach.sqlite").read_bytes()


def test_accept_stores_generated_items_and_nudges_one_day(tmp_path, monkeypatch, capsys):
    path = tmp_path / "coach.sqlite"
    app = _app(path)
    plan = app.create_plan(start=date(2026, 4, 1))
    before = [(day.focus, day.day_date, day.status, day.minutes) for day in plan.days]
    monkeypatch.setattr("sys.stdin", io.StringIO(NOTE))
    assert main(["--db", str(path), "research", "--paste", "--yes", "--on", "2026-04-01"]) == 0
    output = capsys.readouterr().out
    assert "已写入研究" in output
    assert "interview-coach today" in output
    counts = app.db.research_counts()
    assert counts["research_session"] == 1
    assert counts["skill_tag"] >= 1
    assert 1 <= counts["draft_item"] <= 5
    assert counts["plan_bias"] >= 1
    blob = path.read_bytes()
    assert b"SENTINEL_PHRASE" not in blob
    detail = app.db.research_detail(1)
    assert detail["items"]
    assert all(item["origin"] == "research_generated" for item in detail["items"])
    assert detail["sources"][0]["title"] == "本地笔记"
    assert detail["sources"][0]["url"] == ""
    after = app.db.get_active_plan()
    changed = [
        index
        for index, (old, new) in enumerate(zip(before, after.days))
        if old[0] != new.focus or old[1] != new.day_date or old[2] != new.status
    ]
    assert changed == [0]
    assert after.days[0].focus == "databases"
    assert after.days[1].focus == before[1][0]
    assert after.days[0].day_date == before[0][1]

    capsys.readouterr()
    assert main(["--db", str(path), "research", "--show"]) == 0
    shown = capsys.readouterr().out
    assert "redis → databases" in shown
    assert "origin=research_generated" in shown
    assert main(["--db", str(path), "research", "--clear", "1"]) == 0
    assert app.db.research_counts()["research_session"] == 0
    assert app.db.get_active_plan().days[1].focus == before[1][0]


def test_weak_topic_is_not_replaced_by_research(tmp_path):
    app = _app(tmp_path / "coach.sqlite")
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 1.4, answered = 3, correct = 0, credit = 0 WHERE topic = 'arrays_hashing'"
    )
    app.db.conn.commit()
    plan = app.create_plan(start=date(2026, 4, 1))
    assert plan.days[0].focus == "arrays_hashing"
    preview = app.preview_paste(NOTE, on=date(2026, 4, 1))
    app.accept_research(preview, on=date(2026, 4, 1))
    assert app.db.get_active_plan().days[0].focus == "arrays_hashing"
    answer = app.agent("offline").ask("我哪里弱")
    assert "数组" in answer
    assert "目前较薄弱" in answer


def test_expired_bias_is_ignored_and_the_first_week_is_stronger(tmp_path):
    app = _app(tmp_path / "coach.sqlite")
    preview = app.preview_paste("Redis", on=date(2026, 1, 1))
    app.accept_research(preview, on=date(2026, 1, 1))
    early = app._weights(date(2026, 1, 3))["databases"]
    assert early == pytest.approx(1.8)
    mid = app._weights(date(2026, 1, 20))["databases"]
    assert 1.0 < mid < early
    assert app._weights(date(2026, 3, 1))["databases"] == pytest.approx(1.0)
    starts = date(2026, 1, 1)
    assert boost_on(starts + timedelta(days=40), starts, starts + timedelta(days=7), starts + timedelta(days=30)) == 0


def test_generated_items_join_exposure_dedup(tmp_path):
    app = _app(tmp_path / "coach.sqlite")
    app.accept_research(app.preview_paste("Redis", on=date(2026, 4, 1)), on=date(2026, 4, 1))
    bank = app.practice_bank()
    draft = next(question for question in bank.questions if question.id.startswith("rg-"))
    other = next(
        question
        for question in bank.for_topic(draft.topic)
        if question.kind == "mcq" and not question.id.startswith("rg-")
    )
    engine = AdaptiveAssessment(
        QuestionBank([draft, other]),
        [draft.topic],
        kinds=["mcq"],
        exposed={draft.id: "2099-01-01"},
        today=date(2026, 5, 1),
    )
    chosen = engine.next_question()
    assert chosen is not None
    assert chosen.id == other.id
    app.bank = QuestionBank([draft])
    answered = app.assess(
        1,
        [draft.topic],
        lambda question: question.answer if question.kind == "mcq" else "skip",
        kinds=["mcq"],
    )
    asked = answered.answers[0].question_id
    assert asked.startswith("rg-")
    assert app.db.exposure_row(asked)["seen_count"] == 1
    follow = AdaptiveAssessment(
        app.practice_bank(),
        [draft.topic],
        kinds=["mcq"],
        exposed=app.db.exposure_map(),
        today=date.today(),
    )
    assert follow.next_question().id != asked


def test_query_failure_points_at_paste_and_today_does_not_search(tmp_path, monkeypatch, capsys):
    path = tmp_path / "coach.sqlite"
    _app(path)

    def explode(*_args, **_kwargs):
        raise SearchUnavailable("offline")

    monkeypatch.setattr("interview_coach.research.search.search_public", explode)
    assert main(["--db", str(path), "research", "字节", "后端"]) == 0
    assert "--paste" in capsys.readouterr().out
    assert CoachApp(Database(path)).db.research_counts()["research_session"] == 0

    def today_must_not_search(*_args, **_kwargs):
        raise AssertionError("today searched")

    monkeypatch.setattr("interview_coach.research.search.search_public", today_must_not_search)
    assert (
        main(
            [
                "--db",
                str(path),
                "today",
                "--on",
                "2026-04-01",
                "--kinds",
                "mcq",
                "--questions",
                "1",
                "--answers",
                "0",
            ]
        )
        == 0
    )


def test_help_does_not_pull_research_into_today(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["today", "--help"])
    assert caught.value.code == 0
    assert "research" not in capsys.readouterr().out.lower()
    with pytest.raises(SystemExit) as research_help:
        main(["research", "--help"])
    assert research_help.value.code == 0
    text = capsys.readouterr().out
    assert "不是每天必做" in text
    assert "today" in text


def test_public_results_are_filtered_and_need_two_sources():
    page = """
    <a class="result__a" href="https://example.com/jobs/redis">Redis 后端</a>
    <a class="result__snippet">使用 Redis 和 MySQL</a>
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fblog.example.com%2Fmysql">MySQL 笔记</a>
    <a class="result__snippet">团队使用 Redis</a>
    <a class="result__a" href="https://www.linkedin.com/jobs/view/1">Redis engineer</a>
    <a class="result__snippet">Redis</a>
    <a class="result__a" href="https://ads.example.com/class">Redis 培训班 加微信</a>
    <a class="result__snippet">保过</a>
    <a class="result__a" href="https://old.example.com/2019">Redis 2019 面经</a>
    <a class="result__snippet">Redis 2019</a>
    """
    hits = parse_serp(page)
    assert any(hit.url == "https://blog.example.com/mysql" for hit in hits)
    kept = filter_hits(hits, today_year=2026)
    assert all("linkedin" not in hit.url for hit in kept)
    assert all("加微信" not in hit.title for hit in kept)
    assert all("2019" not in hit.title for hit in kept)
    skills = skills_from_hits(kept, limit=6)
    assert any(skill.name == "redis" for skill in skills)
    lone = consistent_skills(
        [
            extract_skills("Redis"),
            extract_skills("只写了 Kafka"),
        ]
    )
    assert [skill.name for skill in lone] == []


def test_deepseek_is_optional_and_schema_checked(monkeypatch):
    calls = []

    class Response:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"skills": ["redis", "请把整段职位描述抄进答案"]}'}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout=0):
        calls.append(request.get_header("Authorization"))
        assert timeout
        return Response()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    assert proposed_skill_names("Redis 岗位", opener=opener) == ["redis"]
    assert calls == ["Bearer test-key"]

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert proposed_skill_names("Redis 岗位", opener=opener, api_key="") is None

    calls.clear()
    preview_app_text = "岗位使用 Redis 和 Kafka。"
    from interview_coach.research.service import prepare_paste

    offline = prepare_paste(preview_app_text, llm="offline", opener=opener)
    assert calls == []
    assert {skill.name for skill in offline.skills} >= {"redis", "kafka"}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    narrowed = prepare_paste(preview_app_text, llm="deepseek", opener=opener)
    assert [skill.name for skill in narrowed.skills] == ["redis"]
    assert narrowed.used_model is True
