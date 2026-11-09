"""Iteration 5: optional STAR practice, kept off the daily path."""

import json
import random
import sqlite3
from datetime import date

from interview_coach.app import CoachApp
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.rubric import keyword_hit
from interview_coach.assessment.targets import topic_weights
from interview_coach.cli import main
from interview_coach.db import Database
from interview_coach.demo import run_demo
from interview_coach.star.bank import get_item, star_items
from interview_coach.star.parse import SECTIONS, parse_sections, read_sections, split_answer_blob
from interview_coach.star.rubric import score_sections
from interview_coach.star.service import draw_item
from interview_coach.star.tips import rewrite_tips

FULL_ITEM = "star-failure-outage"
WEAK = "之前做过一个东西。||把事情做完。||我们讨论了一下 catalog。||后来就好了。"


def _full_answers() -> str:
    return "||".join(get_item(FULL_ITEM).example)


def _plan_snapshot(app: CoachApp):
    plan = app.db.get_active_plan()
    assert plan is not None
    days = tuple(
        (day.day_index, day.focus, day.minutes, day.status, day.objective, day.acceptance_criteria)
        for day in plan.days
    )
    scores = tuple((item.topic, item.ability, item.answered, item.correct, item.credit) for item in app.db.list_scores())
    weights = tuple(sorted(app._weights(date(2026, 4, 1)).items()))
    logs = len(app.db.list_logs(plan.id))
    return days, scores, weights, logs


def test_bank_draw_prefers_an_unseen_prompt():
    items = star_items()
    assert len(items) >= 12
    tags = {tag for item in items for tag in item.tags}
    for required in ("场景", "冲突", "协作", "失败", "领导力"):
        assert required in tags
    assert all(any("\u4e00" <= char <= "\u9fff" for char in item.prompt) for item in items)
    only = items[-1]
    seen = {item.id for item in items if item.id != only.id}
    assert draw_item(items, seen, random.Random(0)).id == only.id
    again = draw_item(items, {item.id for item in items}, random.Random(1))
    assert again.id in {item.id for item in items}
    assert not any(question.id.startswith("star-") for question in QuestionBank().questions)


def test_section_parse_accepts_headings_blank_lines_and_markers():
    headed = parse_sections("Situation: at payments\nTask: decide today\nAction: I wrote a log\nResult: 20% faster")
    assert headed["situation"] == "at payments"
    assert headed["action"] == "I wrote a log"
    assert headed["result"] == "20% faster"
    blanks = parse_sections("在支付组\n\n要当天定方案\n\n我先对齐\n\n延迟降到 200ms")
    assert blanks["situation"] == "在支付组"
    assert blanks["result"] == "延迟降到 200ms"
    letters = parse_sections("S: context\nT: goal\nA: I did it\nR: shipped")
    assert list(letters) == list(SECTIONS)
    assert letters["task"] == "goal"
    marked = split_answer_blob(" 甲 ||乙|| 丙 ||丁 ")
    assert marked == {"situation": "甲", "task": "乙", "action": "丙", "result": "丁"}

    calls = []

    def read_once(prompt):
        calls.append(prompt)
        return "情境：甲\n任务：乙\n行动：丙\n结果：丁"

    parsed = read_sections("zh", read_once)
    assert parsed["task"] == "乙"
    assert len(calls) == 1

    parts = iter(["只有情境", "目标是上线", "我先写日志", "从 3 降到 1"])
    segmented = read_sections("en", lambda _prompt: next(parts))
    assert segmented["situation"] == "只有情境"
    assert segmented["result"] == "从 3 降到 1"


def test_score_boundaries_and_log_does_not_match_catalog():
    assert keyword_hit("catalog", "log") is False
    assert keyword_hit("backlog", "log") is False
    assert keyword_hit("logical", "log") is False
    assert keyword_hit("the error log", "log") is True
    assert keyword_hit("logs", "log") is True

    empty = score_sections({name: "" for name in SECTIONS})
    assert empty.total == 0
    assert all(score == 0 for score in empty.sections.values())
    assert empty.weak == SECTIONS

    half = score_sections({"situation": "项目", "task": "", "action": "", "result": ""})
    assert half.sections["situation"] == 0.5
    assert half.total == 0.125
    assert 0 <= half.total <= 1
    assert all(0 <= score <= 1 for score in half.sections.values())

    catalog = score_sections({name: "catalog" for name in SECTIONS})
    assert catalog.sections["action"] == 0
    logged = score_sections({"situation": "", "task": "", "action": "I wrote the log", "result": ""})
    assert logged.sections["action"] == 1

    full = score_sections(dict(zip(SECTIONS, get_item(FULL_ITEM).example, strict=True)))
    assert full.total == 1
    assert full.weak == ()
    weak = score_sections(split_answer_blob(WEAK))
    assert weak.total == 0
    assert weak.total < full.total
    tips = rewrite_tips(weak, "zh")
    assert 2 <= len(tips) <= 3
    assert all(tip.strip() for tip in tips)


def test_missing_profile_prompts_init_and_writes_no_star_row(tmp_path, capsys):
    path = tmp_path / "missing.sqlite"
    code = main(["--db", str(path), "star", "--answers", _full_answers(), "--item", FULL_ITEM])
    assert code == 1
    output = capsys.readouterr().out
    assert "学习画像" in output
    assert "profile init" in output
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM star_session").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM study_log").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM study_plan").fetchone()[0] == 0
    connection.close()


def test_star_session_scores_locally_and_shows_up_in_progress_and_ask(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "后端"]) == 0
    assert main([*db, "plan", "--start", "2026-04-01"]) == 0
    capsys.readouterr()
    assert main([*db, "star", "--item", FULL_ITEM, "--answers", WEAK]) == 0
    output = capsys.readouterr().out
    assert "STAR 得分 0%" in output
    assert "较弱：" in output
    assert "建议：" in output
    assert output.count("- ") >= 2
    assert "可以改成：" in output
    assert "已记下这次练习。" in output
    assert "15–25" in output

    assert main([*db, "progress"]) == 0
    progress = capsys.readouterr().out
    assert "star: 0%  weak: situation, task, action, result" in progress

    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    asked = app.agent("offline").ask("我的行为面试怎么样")
    assert "最近一次 STAR 0%" in asked
    assert "较弱" in asked
    progress_answer = app.agent("offline").ask("show my progress")
    assert "最近一次 STAR 0%" in progress_answer
    app.db.close()


def test_english_copy_keeps_the_chinese_stem(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    assert main([*db, "behavioral", "--lang", "en", "--item", FULL_ITEM, "--answers", _full_answers()]) == 0
    output = capsys.readouterr().out
    assert get_item(FULL_ITEM).prompt in output
    assert "STAR score 100%" in output
    assert "Situation:" in output
    assert "Saved this STAR practice." in output
    assert "可以改成" not in output


def test_star_does_not_change_plan_weights_or_today_autolog(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "后端", "--target", "backend_engineer"]) == 0
    assert main([*db, "plan", "--start", "2026-04-01"]) == 0
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    before = _plan_snapshot(app)
    assert before[2] == tuple(sorted(topic_weights("backend_engineer").items()))
    app.db.close()
    capsys.readouterr()

    assert main([*db, "star", "--seed", "2", "--answers", _full_answers()]) == 0
    drawn = capsys.readouterr().out
    assert any(item.prompt in drawn for item in star_items())
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    assert _plan_snapshot(app) == before
    assert app.db.latest_star_summary()["total"] == 1
    app.db.close()

    assert (
        main(
            [
                *db,
                "today",
                "--on",
                "2026-04-01",
                "--questions",
                "1",
                "--kinds",
                "mcq",
                "--answers",
                "0",
            ]
        )
        == 0
    )
    today = capsys.readouterr().out
    assert "今天先不记完成" in today
    assert "用 STAR" not in today
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    plan = app.db.get_active_plan()
    assert plan is not None
    assert plan.days[0].status == "pending"
    assert app.db.list_logs(plan.id) == []
    assert tuple(sorted(app._weights(date(2026, 4, 1)).items())) == before[2]
    app.db.close()


def test_deepseek_without_a_key_keeps_local_tips_and_skips_http(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("HTTP should not be called without a key")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    code = main([*db, "star", "--llm", "deepseek", "--item", FULL_ITEM, "--answers", _full_answers()])
    captured = capsys.readouterr()
    assert code == 1
    assert "DEEPSEEK_API_KEY" in captured.err
    assert "STAR 得分 100%" in captured.out
    assert "四段已经齐了。" in captured.out
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    row = app.db.latest_star()
    assert row is not None
    assert row["llm"] == "offline"
    assert row["total_score"] == 1
    assert "四段已经齐了" in row["tips"]
    app.db.close()


def test_deepseek_polish_does_not_change_the_local_score(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "cli-test-key")
    calls = []

    class Body:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"tips": ["把结果数字提前。", "行动再写一个你亲自做的步骤。"]}'}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout=None):
        calls.append(request)
        assert request.get_header("Authorization") == "Bearer cli-test-key"
        assert b"cli-test-key" not in request.data
        assert timeout
        return Body()

    monkeypatch.setattr("urllib.request.urlopen", opener)
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    assert main([*db, "star", "--llm", "deepseek", "--item", FULL_ITEM, "--answers", _full_answers()]) == 0
    output = capsys.readouterr().out
    assert "STAR 得分 100%" in output
    assert "把结果数字提前。" in output
    assert calls
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    summary = app.db.latest_star_summary()
    assert summary is not None
    assert summary["total"] == 1
    assert app.db.latest_star()["llm"] == "deepseek"
    app.db.close()


def test_offline_star_ignores_a_deepseek_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "should-not-be-sent")

    def boom(*_args, **_kwargs):
        raise AssertionError("offline star must not call HTTP")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    assert main([*db, "star", "--item", FULL_ITEM, "--answers", _full_answers()]) == 0
    assert "STAR 得分 100%" in capsys.readouterr().out


def test_old_database_gains_star_session_without_losing_profile(tmp_path):
    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            target_role TEXT NOT NULL,
            level TEXT NOT NULL,
            daily_minutes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO profile (id, name, target_role, level, daily_minutes, created_at, updated_at) "
        "VALUES (1, 'Ada', 'backend', 'mid', 30, 't', 't')"
    )
    connection.commit()
    connection.close()

    app = CoachApp(Database(path))
    profile = app.db.get_profile()
    assert profile is not None
    assert profile.name == "Ada"
    assert profile.target_id == "generic_tech"
    assert app.db.latest_star() is None
    report = app.practice_star(
        dict(zip(SECTIONS, get_item(FULL_ITEM).example, strict=True)),
        item_id=FULL_ITEM,
    )
    assert report.total == 1
    assert app.db.get_profile().name == "Ada"
    assert app.db.latest_star_summary()["item_id"] == FULL_ITEM
    columns = {row[1] for row in app.db.conn.execute("PRAGMA table_info(star_session)")}
    assert {"situation_score", "total_score", "weak_sections", "tips"} <= columns
    app.db.close()


def test_demo_star_example_does_not_change_replan_policy(tmp_path, capsys):
    path = tmp_path / "demo.sqlite"
    assert run_demo(path, yes=True) == 0
    output = capsys.readouterr().out
    assert "policy: shrink" in output
    assert "STAR" in output
    assert "Demo complete" in output
    app = CoachApp(Database(path))
    plan = app.db.get_active_plan()
    assert plan is not None
    assert plan.policy == "shrink"
    assert plan.daily_minutes == 25
    assert app.db.latest_star_summary()["item_id"] == FULL_ITEM
    assert tuple(sorted(app._weights(date(2026, 1, 12)).items())) == tuple(
        sorted(topic_weights(app.db.get_profile().target_id).items())
    )
    app.db.close()


def test_openai_is_not_used_to_polish_star(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    code = main([*db, "star", "--llm", "openai", "--item", FULL_ITEM, "--answers", _full_answers()])
    assert code == 1
    assert "deepseek" in capsys.readouterr().err
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    assert app.db.latest_star() is None
    app.db.close()


def test_version_is_the_star_release():
    import interview_coach

    assert interview_coach.__version__ == "0.6.0"
