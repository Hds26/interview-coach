import pytest

from interview_coach.models import TopicScore
from interview_coach.planner.planner import (
    adjusted_minutes,
    build_week,
    choose_policy,
    explain_policy,
)


def _scores() -> list[TopicScore]:
    return [
        TopicScore("databases", 1.5, 4, 1),
        TopicScore("networking", 2.0, 4, 2),
        TopicScore("system_design", 2.4, 4, 2),
        TopicScore("arrays_hashing", 3.0, 4, 2),
        TopicScore("concurrency", 3.2, 4, 2),
        TopicScore("complexity", 3.4, 4, 3),
        TopicScore("trees_graphs", 4.0, 4, 3),
        TopicScore("python", 4.5, 4, 4),
    ]


def test_week_has_seven_measurable_days_at_the_daily_budget():
    days = build_week(_scores(), 30)
    assert [day.day_index for day in days] == [1, 2, 3, 4, 5, 6, 7]
    assert all(day.minutes == 30 for day in days)
    assert sum(day.minutes for day in days) == 210
    assert days[0].focus == "databases"
    assert days[5].focus.startswith("review:")
    assert days[6].focus.startswith("mock:")
    assert "Review: Review" not in days[5].objective
    assert "Mock: Mock" not in days[6].objective
    assert "Databases, Networking" in days[5].objective
    for day in days:
        assert day.acceptance_criteria
        for criterion in day.acceptance_criteria:
            assert any(char.isdigit() for char in criterion)


def test_stronger_topics_are_not_scheduled_before_weaker_ones():
    days = build_week(_scores(), 30)
    assert days[0].focus == "databases"
    assert "python" not in {day.focus for day in days[:5]}


def test_policy_thresholds():
    assert choose_policy(0.59, 0.95) == "shrink"
    assert choose_policy(0.60, 0.95) == "steady"
    assert choose_policy(0.84, 0.99) == "steady"
    assert choose_policy(0.85, 0.69) == "steady"
    assert choose_policy(0.85, 0.70) == "stretch"


def test_minutes_change_only_inside_the_allowed_band():
    assert adjusted_minutes(30, "shrink") == 25
    assert adjusted_minutes(10, "shrink") == 10
    assert adjusted_minutes(30, "stretch") == 35
    assert adjusted_minutes(120, "stretch") == 120
    assert adjusted_minutes(30, "steady") == 30


def test_shrink_week_repeats_the_three_weakest_topics():
    days = build_week(_scores(), 25, policy="shrink", carry=["python", "complexity"])
    core = {day.focus for day in days if day.day_index <= 5}
    assert days[0].focus == "databases"
    assert core == {"databases", "networking", "system_design"}
    assert "easy" in days[0].acceptance_criteria[1]


def test_steady_week_pulls_unfinished_topics_forward():
    days = build_week(_scores(), 30, policy="steady", carry=["python"])
    assert days[0].focus == "python"


def test_explain_policy_mentions_the_rate():
    text = explain_policy("shrink", 0.5, 0.75)
    assert "50%" in text
    assert "60%" in text


def test_empty_scores_are_rejected():
    with pytest.raises(ValueError):
        build_week([], 30)
