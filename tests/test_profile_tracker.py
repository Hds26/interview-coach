from datetime import date

import pytest

from interview_coach.app import CoachApp
from interview_coach.db import Database
from interview_coach.models import PlanDay, StudyLog, StudyPlan
from interview_coach.profile.service import normalize_profile
from interview_coach.tracker.tracker import mean_quiz_accuracy, reported_completion_rate, summarize


def test_profile_defaults_to_thirty_minutes(tmp_path):
    app = CoachApp(Database(tmp_path / "data" / "coach.sqlite"))
    profile = app.init_profile("Ada", "backend")
    assert profile.daily_minutes == 30
    assert profile.level == "mid"
    assert app.db.path.exists()
    assert len(app.db.list_scores()) == 8


def test_profile_validation():
    with pytest.raises(ValueError):
        normalize_profile(" ", "backend")
    with pytest.raises(ValueError):
        normalize_profile("Ada", "backend", daily_minutes=5)
    with pytest.raises(ValueError):
        normalize_profile("Ada", "backend", level="staff")


def test_completion_uses_reported_days_only():
    days = [
        _day(1, "done"),
        _day(2, "done"),
        _day(3, "missed"),
        _day(4, "pending"),
    ]
    assert reported_completion_rate(days) == pytest.approx(2 / 3)


def test_quiz_accuracy_ignores_logs_without_a_score():
    logs = [
        StudyLog(1, 1, 1, 30, True, 8, 10, ""),
        StudyLog(2, 2, 2, 0, False, None, None, ""),
        StudyLog(3, 3, 3, 30, True, 6, 10, ""),
    ]
    assert mean_quiz_accuracy(logs) == pytest.approx(0.7)


def test_log_and_replan_round_trip(tmp_path):
    app = CoachApp(Database(tmp_path / "coach.sqlite"))
    app.init_profile("Ada", "backend", daily_minutes=30)
    app.db.conn.execute("UPDATE topic_score SET ability = 1.2, answered = 4, correct = 1 WHERE topic = 'databases'")
    app.db.conn.commit()
    plan = app.create_plan(start=date(2026, 1, 5))
    assert plan.version == 1
    assert plan.days[0].focus == "databases"
    app.log_day(1, 30, True, 8, 10)
    app.log_day(2, 10, False)
    progress = app.progress()
    assert progress.days_done == 1
    assert progress.days_missed == 1
    assert progress.reported_completion == pytest.approx(0.5)
    revised, reason = app.replan(start=date(2026, 1, 12))
    assert revised.version == 2
    assert revised.policy == "shrink"
    assert revised.daily_minutes == 25
    assert "below 60%" in reason
    assert summarize(revised, []).days_pending == 7


def _day(index: int, status: str) -> PlanDay:
    return PlanDay(index, index, "2026-01-05", "databases", 30, "obj", ("Score at least 6/10.",), status)


def test_summarize_counts_statuses():
    plan = StudyPlan(1, 1, 30, "initial", "2026-01-05", (_day(1, "done"), _day(2, "missed"), _day(3, "pending")))
    progress = summarize(plan, [StudyLog(1, 1, 1, 30, True, 8, 10, "")])
    assert progress.days_done == 1
    assert progress.days_missed == 1
    assert progress.minutes_spent == 30
