"""Iteration 2: open rubrics, tags, target weights, confidence, review, import/export."""

import json
import sqlite3
from datetime import date

import pytest

from interview_coach.app import CoachApp
from interview_coach.assessment.bank import TOPICS, QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.open_items import open_question_for
from interview_coach.assessment.rubric import score_rubric
from interview_coach.assessment.targets import infer_target, resolve_target, topic_weights
from interview_coach.cli import main
from interview_coach.db import Database
from interview_coach.models import TopicScore
from interview_coach.planner.planner import build_week
from interview_coach.tracker.schedule import review_interval_days


def test_every_target_weights_every_topic():
    from interview_coach.assessment.targets import TARGETS

    for target_id in TARGETS:
        weights = topic_weights(target_id)
        assert set(weights) == set(TOPICS)
        assert all(weight > 0 for weight in weights.values())


def test_job_title_stays_generic_until_a_target_is_chosen():
    assert resolve_target("Senior Backend Engineer", "generic_tech") == "generic_tech"
    assert resolve_target("Senior Backend Engineer", "auto") == "backend_engineer"
    assert resolve_target("React engineer", "auto") == "frontend_engineer"
    assert resolve_target("Data engineer, warehouse", "auto") == "data_engineer"
    assert resolve_target("Python exam retake", "auto") == "python_exam"
    assert resolve_target("System design loop", "auto") == "system_design_exam"
    assert resolve_target("Anyone", "python-exam") == "python_exam"
    assert infer_target("support") == "generic_tech"
    with pytest.raises(ValueError):
        resolve_target("Anyone", "staff-plus")


def test_open_rubric_scores_partial_and_full_credit():
    question = open_question_for("python")
    assert question is not None
    blank = score_rubric(question, "   ")
    assert blank.ratio == 0
    partial = score_rubric(question, "the default object is shared")
    assert partial.hit_points == 1
    assert 0 < partial.ratio < 1
    full = score_rubric(question, "created once, then shared, and the list is mutable")
    assert full.ratio == 1
    assert full.hit_points == 3


def test_open_answer_updates_ability_and_information():
    engine = AdaptiveAssessment(QuestionBank(), ["python"], kinds=["open"], prior={"python": 3.0})
    question = engine.next_question()
    assert question is not None and question.kind == "open"
    scored = engine.submit(question.id, "the default object is shared")
    assert scored.kind == "open"
    assert 0 < scored.score < 1
    assert scored.information > 0
    assert engine.information["python"] == scored.information
    assert engine.ability["python"] != 3.0


def test_tag_filter_keeps_only_matching_topics():
    engine = AdaptiveAssessment(QuestionBank(), list(TOPICS), tags=["gil"])
    assert engine.topics == ["python"]
    question = engine.next_question()
    assert question is not None
    assert "gil" in question.tags


def test_target_weights_schedule_the_heavier_topic_first():
    scores = [TopicScore(topic, 3.0, 2, 1) for topic in TOPICS]
    plain = build_week(scores, 30)
    weighted = build_week(scores, 30, weights=topic_weights("python_exam"))
    assert plain[0].focus == "arrays_hashing"
    assert weighted[0].focus == "python"
    assert any("py-open" in criterion for criterion in weighted[0].acceptance_criteria)


def test_python_exam_asks_python_more_often_than_a_low_weight_topic(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "Python engineer", target="python_exam")

    def choose(question):
        if question.kind == "open":
            return "skip"
        return question.answer

    result = app.assess(12, None, choose)
    counts: dict[str, int] = {}
    for answer in result.answers:
        counts[answer.topic] = counts.get(answer.topic, 0) + 1
    assert counts.get("python", 0) > counts.get("networking", 0)
    assert counts.get("python", 0) >= 3
    python = next(score for score in result.scores if score.topic == "python")
    assert python.information > 0
    assert python.next_review is not None
    assert python.credit > 0


def test_review_intervals_get_longer_as_ability_rises():
    assert review_interval_days(1.2) == 1
    assert review_interval_days(2.4) == 2
    assert review_interval_days(3.4) == 4
    assert review_interval_days(4.2) == 7
    assert review_interval_days(4.8) == 14


def test_replan_puts_a_due_topic_ahead_of_a_weaker_one(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    app.db.conn.execute("UPDATE topic_score SET ability = 4.2, answered = 2, correct = 2")
    app.db.conn.execute("UPDATE topic_score SET ability = 1.5 WHERE topic = 'python'")
    app.db.conn.execute("UPDATE topic_score SET ability = 4.0 WHERE topic = 'databases'")
    app.db.conn.commit()
    plan = app.create_plan(start=date(2026, 1, 5))
    assert plan.days[0].focus == "python"
    assert plan.days[1].focus == "databases"
    app.log_day(1, 30, True, 8, 10)
    app.log_day(2, 30, True, 8, 10)
    app.log_day(3, 0, False)
    app.db.conn.execute("UPDATE topic_score SET next_review = '2026-01-12' WHERE topic = 'databases'")
    app.db.conn.execute("UPDATE topic_score SET next_review = '2026-03-01' WHERE topic != 'databases'")
    app.db.conn.commit()
    revised, _reason = app.replan(start=date(2026, 1, 12))
    assert revised.policy == "steady"
    assert revised.daily_minutes == 30
    assert revised.days[0].focus == "databases"


def test_import_json_and_csv_updates_ability_and_logs(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    before = app.db.ability_map()["python"]
    practice = tmp_path / "practice.json"
    practice.write_text(
        json.dumps([{"topic": "python", "difficulty": 5, "correct": True}]),
        encoding="utf-8",
    )
    imported = app.import_progress(practice, on=date(2026, 4, 1))
    assert imported.practice_count == 1
    after = next(score for score in app.db.list_scores() if score.topic == "python")
    assert after.ability > before
    assert after.next_review == "2026-04-05"
    assert after.information > 0

    app.create_plan(start=date(2026, 4, 1))
    logs = tmp_path / "week.csv"
    logs.write_text(
        "day,minutes,completed,quiz,notes\n1,30,true,8/10,imported\n2,0,missed,,skip\n",
        encoding="utf-8",
    )
    imported_logs = app.import_progress(logs, on=date(2026, 4, 1))
    assert imported_logs.log_count == 2
    progress = app.progress()
    assert progress.days_done == 1
    assert progress.days_missed == 1

    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps(
            {
                "practice": [{"topic": "databases", "difficulty": 2, "score": 0.5}],
                "logs": [{"day": 3, "minutes": 20, "completed": True, "quiz": "7/10"}],
            }
        ),
        encoding="utf-8",
    )
    both = app.import_progress(mixed, on=date(2026, 4, 1))
    assert both.practice_count == 1
    assert both.log_count == 1
    databases = next(score for score in app.db.list_scores() if score.topic == "databases")
    assert databases.credit == pytest.approx(0.5)
    assert app.progress().days_done == 2


def test_export_markdown_and_ics(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    app.create_plan(start=date(2026, 3, 2))
    markdown = app.export_plan("md")
    calendar = app.export_plan("ics")
    assert "# Interview study week v1" in markdown
    assert "2026-03-02" in markdown
    assert "Open item" in markdown
    assert "BEGIN:VCALENDAR" in calendar
    assert "DTSTART;VALUE=DATE:20260302" in calendar
    assert "END:VCALENDAR" in calendar


def test_v1_database_gains_iteration2_columns(tmp_path):
    path = tmp_path / "v1.sqlite"
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
        CREATE TABLE topic_score (
            topic TEXT PRIMARY KEY,
            ability REAL NOT NULL,
            answered INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE response (
            id INTEGER PRIMARY KEY,
            assessment_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            difficulty INTEGER NOT NULL,
            choice_index INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            ability_after REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO profile (id, name, target_role, level, daily_minutes, created_at, updated_at) "
        "VALUES (1, 'Ada', 'backend', 'mid', 30, 't', 't')"
    )
    connection.execute(
        "INSERT INTO topic_score (topic, ability, answered, correct, updated_at) VALUES ('python', 3, 1, 1, 't')"
    )
    connection.commit()
    connection.close()

    database = Database(path)
    profile = database.get_profile()
    assert profile is not None
    assert profile.target_id == "generic_tech"
    score = next(item for item in database.list_scores() if item.topic == "python")
    assert score.information == 0
    assert score.credit == 0
    assert score.next_review is None
    columns = {row[1] for row in database.conn.execute("PRAGMA table_info(response)")}
    assert {"score", "kind", "response_text"} <= columns


def test_drill_due_date_does_not_become_the_review_date(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend")
    app.db.conn.execute(
        """
        UPDATE topic_score
        SET ability = 2.0, answered = 1, correct = 0, next_review = '2026-01-01'
        WHERE topic = 'python'
        """
    )
    app.db.conn.commit()

    def choose(question):
        return 0 if question.kind == "mcq" else "skip"

    app.drill(1, choose, kinds=["mcq"], on=date(2099, 1, 1), reviewed_on=date(2026, 5, 1))
    score = next(item for item in app.db.list_scores() if item.topic == "python")
    assert score.answered == 2
    assert score.next_review is not None
    assert score.next_review.startswith("2026-05-")
    assert not score.next_review.startswith("2099")


def test_cli_open_answer_export_import_and_drill(tmp_path, capsys):
    db = ["--db", str(tmp_path / "coach.sqlite")]
    assert (
        main(
            [
                *db,
                "profile",
                "init",
                "--name",
                "Ada",
                "--role",
                "Staff Backend Engineer",
                "--target",
                "python_exam",
            ]
        )
        == 0
    )
    assert main([*db, "profile", "show"]) == 0
    shown = capsys.readouterr().out
    assert "target: python_exam" in shown
    assert "python=" in shown
    assert main([*db, "topics"]) == 0
    assert "gil" in capsys.readouterr().out
    assert (
        main(
            [
                *db,
                "assess",
                "--questions",
                "1",
                "--topics",
                "python",
                "--kinds",
                "open",
                "--answers",
                "|created once and then shared because the list is mutable|",
            ]
        )
        == 0
    )
    assessed = capsys.readouterr().out
    assert "Rubric score: 100%" in assessed
    assert "confidence" in assessed
    assert main([*db, "plan", "--start", "2026-03-02"]) == 0
    assert "Open item py-open" in capsys.readouterr().out
    stem = tmp_path / "week"
    assert main([*db, "export", "--format", "both", "--out", str(stem)]) == 0
    assert (tmp_path / "week.md").read_text(encoding="utf-8").startswith("# Interview study week")
    assert "BEGIN:VCALENDAR" in (tmp_path / "week.ics").read_text(encoding="utf-8")
    capsys.readouterr()
    practice = tmp_path / "practice.csv"
    practice.write_text("topic,difficulty,score\ndatabases,2,0.5\n", encoding="utf-8")
    assert main([*db, "import", str(practice)]) == 0
    assert "Imported 1 practice rows" in capsys.readouterr().out
    assert main([*db, "due", "--on", "2099-01-01"]) == 0
    assert "python" in capsys.readouterr().out
    assert (
        main(
            [
                *db,
                "drill",
                "--questions",
                "1",
                "--kinds",
                "mcq",
                "--answers",
                "0",
                "--on",
                "2099-01-01",
            ]
        )
        == 0
    )
    assert "Finished 1 questions" in capsys.readouterr().out
    assert main([*db, "profile", "init", "--name", "Ada", "--role", "backend", "--target", "nope"]) == 1
