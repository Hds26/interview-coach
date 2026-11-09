"""Iteration 3: daily command, preserved progress, exposure, and token rubrics."""

from datetime import date

import pytest

from interview_coach.app import CoachApp, NothingDue
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.open_items import open_question_for
from interview_coach.assessment.rubric import score_rubric
from interview_coach.cli import main
from interview_coach.db import Database


def _perfect(question):
    if question.kind == "open":
        return " ".join(point.keywords[0] for point in question.rubric if point.keywords)
    return question.answer


def test_profile_reinit_keeps_scores_and_plan(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    first = app.init_profile("Ada", "backend")
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 1.5, answered = 4, correct = 1 WHERE topic = 'python'"
    )
    app.db.conn.commit()
    plan = app.create_plan(start=date(2026, 4, 1))
    app.log_day(1, 30, True, 8, 10, "kept")
    renamed = app.init_profile("Grace", "frontend", level="senior", daily_minutes=45, target="frontend_engineer")
    assert renamed.name == "Grace"
    assert renamed.level == "senior"
    assert renamed.daily_minutes == 45
    assert renamed.target_id == "frontend_engineer"
    assert renamed.created_at == first.created_at
    score = next(item for item in app.db.list_scores() if item.topic == "python")
    assert score.ability == 1.5
    assert score.answered == 4
    assert score.correct == 1
    active = app.db.get_active_plan()
    assert active is not None
    assert active.id == plan.id
    assert active.days[0].status == "done"
    reset = app.init_profile("Grace", "frontend", reset_scores=True)
    assert reset.name == "Grace"
    cleared = next(item for item in app.db.list_scores() if item.topic == "python")
    assert cleared.answered == 0
    assert app.db.get_active_plan().id == plan.id


def test_cli_profile_reinit_keeps_answered_topics(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    assert main([*db, "assess", "--questions", "1", "--topics", "python", "--kinds", "mcq", "--answers", "0"]) == 0
    assert main([*db, "plan", "--start", "2026-04-01"]) == 0
    capsys.readouterr()
    assert main([*db, "profile", "init", "--name", "Bea", "--role", "frontend"]) == 0
    assert main([*db, "profile", "show"]) == 0
    shown = capsys.readouterr().out
    assert "name: Bea" in shown
    assert "streak_goal: 5" in shown
    assert main([*db, "progress"]) == 0
    progress = capsys.readouterr().out
    assert "Python" in progress
    assert "(no answered topics)" not in progress


def test_demo_refuses_to_delete_without_confirmation(tmp_path, capsys):
    db = tmp_path / "demo.sqlite"
    db.write_text("sentinel", encoding="utf-8")
    code = main(["demo", "--db", str(db)])
    captured = capsys.readouterr()
    assert code == 1
    assert "already exists" in captured.err
    assert "--yes" in captured.err
    assert db.read_text(encoding="utf-8") == "sentinel"
    assert main(["demo", "--db", str(db), "--yes"]) == 0
    assert "Demo complete" in capsys.readouterr().out
    assert db.read_bytes().startswith(b"SQLite format 3")


def test_rubric_matches_tokens_not_substrings():
    complexity = open_question_for("complexity")
    missed = score_rubric(complexity, "a catalog of unsorted values")
    assert missed.hit_points == 0
    full = score_rubric(complexity, "sorted input, discard half each step, logarithmic")
    assert full.hit_points == 3

    design = open_question_for("system_design")
    scored = score_rubric(design, "retries must not duplicate the side effect")
    assert scored.hit_points == 3

    networking = open_question_for("networking")
    assert score_rubric(networking, "syntax").hit_points == 0
    handshake = score_rubric(networking, "SYN opens the connection and sends acknowledgements")
    assert handshake.hit_points == 3

    databases = open_question_for("databases")
    mvcc = score_rubric(databases, "readers don't block writers and keep a snapshot of each version")
    assert mvcc.hit_points == 3


def test_wrong_answer_prints_the_explanation(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    code = main(
        [*db, "assess", "--questions", "1", "--topics", "complexity", "--kinds", "mcq", "--answers", "0"]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "没对" in output
    assert "说明" in output
    assert "归并" in output


def test_sessions_do_not_repeat_items_until_the_pool_is_exhausted(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    first = app.assess(3, ["python"], _perfect, kinds=["mcq"], on=date(2026, 5, 1))
    second = app.assess(3, ["python"], _perfect, kinds=["mcq"], on=date(2026, 5, 1))
    seen = {answer.question_id for answer in first.answers}
    again = {answer.question_id for answer in second.answers}
    assert len(seen) == 3
    assert seen.isdisjoint(again)
    for question_id in seen:
        row = app.db.exposure_row(question_id)
        assert row is not None
        assert row["seen_count"] == 1
        assert row["next_due"] > "2026-05-01"
    third = app.assess(1, ["python"], _perfect, kinds=["mcq"], on=date(2026, 5, 1))
    # The bank has more than six multiple-choice items, so the next one is still unseen.
    assert third.answers[0].question_id not in seen | again


def test_due_item_returns_before_unseen_ones(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    first = app.assess(1, ["python"], lambda question: (question.answer + 1) % len(question.choices), kinds=["mcq"])
    question_id = first.answers[0].question_id
    app.db.conn.execute(
        "UPDATE item_exposure SET next_due = ? WHERE question_id = ?",
        (date.today().isoformat(), question_id),
    )
    app.db.conn.commit()
    second = app.assess(1, ["python"], _perfect, kinds=["mcq"])
    assert second.answers[0].question_id == question_id
    assert app.db.exposure_row(question_id)["seen_count"] == 2


def test_topic_cap_stops_a_long_quiz():
    engine = AdaptiveAssessment(QuestionBank(), ["python"], kinds=["mcq"], max_per_topic=4)
    asked = []
    for _ in range(10):
        question = engine.next_question()
        if question is None:
            break
        asked.append(question.id)
        engine.submit(question.id, 0)
    assert len(asked) == 4
    assert engine.next_question() is None


def test_empty_due_does_not_rewrite_the_schedule(tmp_path, capsys):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    app.db.conn.execute(
        "UPDATE topic_score SET ability = 3.2, answered = 1, correct = 1, next_review = '2099-06-01'"
    )
    app.db.conn.commit()
    before = [(item.topic, item.ability, item.answered, item.next_review) for item in app.db.list_scores()]
    with pytest.raises(NothingDue):
        app.drill(4, lambda question: 0, on=date(2026, 5, 1))
    after = [(item.topic, item.ability, item.answered, item.next_review) for item in app.db.list_scores()]
    assert after == before
    assert app.db.exposure_map() == {}

    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "drill", "--questions", "4", "--answers", "0,0,0,0"]) == 0
    assert "schedule was left unchanged" in capsys.readouterr().out
    still = [(item.topic, item.ability, item.answered, item.next_review) for item in app.db.list_scores()]
    assert still == before


def test_today_autologs_when_the_short_session_meets_the_day(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend", streak_goal=5)
    setup = app.prepare_today(on=date(2026, 4, 1), lang="zh")
    assert setup.created_plan is True
    assert any("接下来 30 分钟" in line for line in setup.lines)
    assert any(line.startswith("- ") for line in setup.lines)
    missed = app.assess(
        5,
        setup.topics,
        lambda question: "skip" if question.kind == "open" else (question.answer + 1) % len(question.choices),
        kinds=setup.kinds,
        on=date(2026, 4, 1),
        must_ask=setup.must_ask,
    )
    assert missed.autolog is not None and missed.autolog.logged is False
    assert app.db.get_active_plan().days[0].status == "pending"

    passed = app.assess(
        5,
        setup.topics,
        _perfect,
        kinds=setup.kinds,
        on=date(2026, 4, 1),
        must_ask=setup.must_ask,
    )
    assert passed.autolog is not None and passed.autolog.logged is True
    assert passed.autolog.day_index == 1
    assert passed.answers[-1].kind == "open"
    assert app.db.get_active_plan().days[0].status == "done"
    closing = app.closing_lines(passed, "zh")
    assert len(closing) <= 3
    assert "今天已记入完成" in closing[0]
    assert "接下来" in closing[1]
    text = "\n".join(closing)
    assert "%" not in text


def test_daily_commands_explain_the_day_in_chinese(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    code = main([*db])
    captured = capsys.readouterr()
    assert code == 1
    assert "接下来" in captured.out
    assert "做到这几件就算完成" in captured.out
    assert "--answers" in captured.err

    assert (
        main(
            [
                *db,
                "go",
                "--on",
                "2026-04-01",
                "--questions",
                "1",
                "--answers",
                "0",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "接下来 30 分钟" in output
    assert "今天先不记完成" in output
    assert "mastery" not in output.lower()


def test_today_english_flag(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend"]) == 0
    capsys.readouterr()
    assert main([*db, "today", "--lang", "en", "--on", "2026-04-01", "--questions", "1", "--answers", "0"]) == 0
    output = capsys.readouterr().out
    assert "Next 30 minutes" in output
    assert "Not logged yet." in output


def test_missing_profile_on_today_is_one_next_step(tmp_path, capsys):
    code = main(["--db", str(tmp_path / "missing.sqlite"), "today"])
    assert code == 1
    output = capsys.readouterr().out
    assert "学习画像" in output
    assert "interview-coach start" in output
