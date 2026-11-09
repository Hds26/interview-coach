"""Onboarding writes a learner model and a 7-day plan. It does not invent scores."""

import io
import sys
from datetime import date

from interview_coach import __version__
from interview_coach.app import CoachApp
from interview_coach.cli import main
from interview_coach.db import Database
from interview_coach.learner.model import plan_carry
from interview_coach.models import TopicScore


SECRET = "紫薇星机密项目XYZ不会入库"


def _scores() -> list[TopicScore]:
    return [
        TopicScore("python", 3.0, 1, 0, 0.0, 0.0),
        TopicScore("databases", 3.0, 2, 2, 0.0, 2.0),
        TopicScore("networking", 3.0, 0, 0),
        TopicScore("system_design", 3.0, 0, 0),
        TopicScore("concurrency", 3.0, 0, 0),
    ]


def test_plan_carry_puts_evidence_ahead_of_self_rating_and_jd():
    carry = plan_carry(_scores(), ["databases", "networking"], ["databases", "system_design"])
    assert carry == ["python", "networking", "system_design"]


def test_version_is_the_personalization_slice():
    assert __version__ == "0.6.0"


def test_start_builds_a_plan_without_storing_the_note_or_scores(tmp_path, monkeypatch, capsys):
    note = f"后端岗位，使用 Redis 和 MySQL。{SECRET}\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(note))
    db_path = tmp_path / "coach.sqlite"
    db = ["--db", str(db_path)]
    assert (
        main(
            [
                *db,
                "start",
                "--name",
                "Ada",
                "--role",
                "后端",
                "--daily-minutes",
                "25",
                "--kinds",
                "开放题",
                "--weak",
                "网络",
                "--paste-jd",
                "--on",
                "2026-04-01",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "第 1 天练网络" in output
    assert "职位说明：数据库" in output
    assert "自评薄弱：网络" in output
    assert "这不是做题分数" in output
    assert "这一天的验收" in output
    assert "练习至少对" in output
    assert "下一步：interview-coach today" in output
    assert "mastery" not in output.lower()
    assert SECRET not in output
    blob = db_path.read_bytes()
    assert SECRET.encode() not in blob
    assert "使用 Redis 和 MySQL".encode() not in blob

    app = CoachApp(Database(db_path))
    assert app.db.research_counts()["research_session"] == 0
    assert all(score.answered == 0 for score in app.db.list_scores())
    model = app.db.get_learner()
    assert model is not None
    assert model.minutes_per_day == 25
    assert model.practice_style == "open"
    assert model.self_weak == ("networking",)
    assert model.topics("jd") == ("databases",)
    plan = app.db.get_active_plan()
    assert plan is not None
    assert plan.days[0].focus == "networking"
    assert plan.days[0].minutes == 25
    assert plan.days[0].acceptance_criteria
    profile = app.require_profile()
    assert profile.preferred_kinds == "open"
    assert profile.daily_minutes == 25
    assert profile.target_id == "backend_engineer"

    capsys.readouterr()
    assert main([*db, "profile", "show"]) == 0
    shown = capsys.readouterr().out
    assert "self_weak: networking" in shown
    assert "source_topics: jd=databases" in shown

    assert main([*db, "today", "--on", "2026-04-01", "--questions", "1", "--kinds", "mcq", "--answers", "0"]) == 0
    today = capsys.readouterr().out
    assert "接下来 25 分钟" in today
    assert "网络" in today


def test_answer_evidence_beats_a_conflicting_self_rating_and_jd(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "start", "--name", "Ada", "--role", "后端", "--weak", "python", "--on", "2026-04-01"]) == 0
    assert "第 1 天练Python" in capsys.readouterr().out
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 4.0, answered = 2, correct = 2, credit = 2 WHERE topic = 'python'"
    )
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 2.0, answered = 1, correct = 0, credit = 0 WHERE topic = 'databases'"
    )
    app.db.conn.commit()
    note_path = tmp_path / "jd.txt"
    note_path.write_text(f"熟悉 Redis。{SECRET}", encoding="utf-8")
    assert main([*db, "start", "--weak", "python", "--jd-file", str(note_path), "--on", "2026-04-01"]) == 0
    output = capsys.readouterr().out
    assert "第 1 天练数据库" in output
    assert "做题记录排在自评和职位说明前面" in output
    assert SECRET.encode() not in (tmp_path / "coach.sqlite").read_bytes()
    python = next(score for score in app.db.list_scores() if score.topic == "python")
    assert python.answered == 2
    assert python.correct == 2
    plan = app.db.get_active_plan()
    assert plan is not None
    assert plan.days[0].focus == "databases"


def test_a_mastered_jd_topic_does_not_stay_ahead_of_a_miss(tmp_path, capsys):
    db_path = tmp_path / "coach.sqlite"
    db = ["--db", str(db_path)]
    jd = tmp_path / "jd.txt"
    jd.write_text("岗位要求 Redis 和 MySQL。", encoding="utf-8")
    assert main([*db, "start", "--name", "Ada", "--role", "generalist", "--jd-file", str(jd), "--on", "2026-04-01"]) == 0
    assert "第 1 天练数据库" in capsys.readouterr().out
    app = CoachApp(Database(db_path))
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 4.2, answered = 2, correct = 2, credit = 2 WHERE topic = 'databases'"
    )
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 2.0, answered = 1, correct = 0, credit = 0 WHERE topic = 'python'"
    )
    app.db.conn.commit()
    assert main([*db, "start", "--jd-file", str(jd), "--on", "2026-04-01"]) == 0
    output = capsys.readouterr().out
    assert "第 1 天练Python" in output
    plan = CoachApp(Database(db_path)).db.get_active_plan()
    assert plan is not None
    assert plan.days[0].focus == "python"
    assert "databases" not in plan_carry(
        CoachApp(Database(db_path)).db.list_scores(),
        [],
        ["databases"],
    )


def test_resume_stays_when_a_later_start_replaces_only_the_jd(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    resume = tmp_path / "resume.txt"
    resume.write_text("熟悉 Python 和 FastAPI。", encoding="utf-8")
    first_jd = tmp_path / "jd.txt"
    first_jd.write_text("熟悉 Redis。", encoding="utf-8")
    assert (
        main(
            [
                *db,
                "start",
                "--name",
                "Ada",
                "--role",
                "后端",
                "--resume-file",
                str(resume),
                "--jd-file",
                str(first_jd),
                "--weak",
                "网络",
                "--on",
                "2026-04-01",
            ]
        )
        == 0
    )
    capsys.readouterr()
    second_jd = tmp_path / "jd2.txt"
    second_jd.write_text("熟悉并发和死锁。", encoding="utf-8")
    assert main([*db, "start", "--jd-file", str(second_jd), "--on", "2026-04-01"]) == 0
    output = capsys.readouterr().out
    assert "简历：Python" in output
    assert "职位说明：并发" in output
    assert "自评薄弱：网络" in output
    model = CoachApp(Database(tmp_path / "coach.sqlite")).db.get_learner()
    assert model is not None
    assert model.topics("resume") == ("python",)
    assert model.topics("jd") == ("concurrency",)
    assert "databases" not in model.topics()


def test_logged_day_stays_when_the_plan_is_refreshed(tmp_path):
    db_path = tmp_path / "coach.sqlite"
    app = CoachApp(Database(db_path))
    result = app.start_onboarding(name="Ada", role="后端", weak="网络", on=date(2026, 4, 1))
    assert result.plan.days[0].focus == "networking"
    app.log_day(1, 25, True, 8, 10)
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 2.0, answered = 1, correct = 0, credit = 0 WHERE topic = 'python'"
    )
    app.db.conn.commit()
    refreshed = app.start_onboarding(weak="网络", on=date(2026, 4, 1))
    done = next(day for day in refreshed.plan.days if day.day_index == 1)
    pending = next(day for day in refreshed.plan.days if day.status == "pending" and day.day_index <= 5)
    assert done.status == "done"
    assert done.focus == "networking"
    assert pending.focus == "python"


def test_start_without_a_name_tells_you_the_one_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    code = main(["--db", str(tmp_path / "missing.sqlite"), "start"])
    assert code == 1
    output = capsys.readouterr().out
    assert "interview-coach start --name 你的名字 --role 后端" in output
    assert not (tmp_path / "missing.sqlite").exists() or CoachApp(Database(tmp_path / "missing.sqlite")).db.get_profile() is None


def test_unknown_weak_topic_does_not_save_a_profile(tmp_path, capsys):
    code = main(
        ["--db", str(tmp_path / "coach.sqlite"), "start", "--name", "Ada", "--role", "后端", "--weak", "烹饪"]
    )
    assert code == 1
    assert "unknown topic" in capsys.readouterr().err
    assert CoachApp(Database(tmp_path / "coach.sqlite")).db.get_profile() is None


def test_interactive_start_uses_five_answers(tmp_path, monkeypatch, capsys):
    answers = iter(["Ada", "后端", "", "1", "网络"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["--db", str(tmp_path / "coach.sqlite"), "start", "--on", "2026-04-01"]) == 0
    output = capsys.readouterr().out
    assert "第 1 天练网络" in output
    assert "练习方式：选择题" in output
    profile = CoachApp(Database(tmp_path / "coach.sqlite")).require_profile()
    assert profile.name == "Ada"
    assert profile.daily_minutes == 30
    assert profile.preferred_kinds == "mcq"
    assert profile.target_id == "backend_engineer"


def test_deepseek_without_a_key_stays_local(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def opener(*_args, **_kwargs):
        raise AssertionError("should not call the network")

    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    result = app.start_onboarding(
        name="Ada",
        role="后端",
        pastes=[("jd", "熟悉 Redis 和缓存")],
        llm="deepseek",
        opener=opener,
        on=date(2026, 4, 1),
    )
    assert "数据库" in result.summary
    model = app.db.get_learner()
    assert model is not None
    assert "databases" in model.topics("jd")
    assert "system_design" in model.topics("jd")
