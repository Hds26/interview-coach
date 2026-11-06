"""Spaced-repetition intervals from the current ability estimate.

Low ability comes back in a day or two. High ability waits one or two weeks.
This is a fixed schedule, not a fitted memory model.
"""

from __future__ import annotations

from datetime import date, timedelta


def review_interval_days(ability: float) -> int:
    if ability < 2.0:
        return 1
    if ability < 3.0:
        return 2
    if ability < 4.0:
        return 4
    if ability < 4.5:
        return 7
    return 14


def next_review_on(ability: float, today: date) -> str:
    return (today + timedelta(days=review_interval_days(ability))).isoformat()


def item_review_days(score: float, ability: float) -> int:
    """When a seen item may return. Misses come back sooner than clean answers."""
    if score < 0.5:
        return 1
    if score < 0.999:
        return 2
    return review_interval_days(ability)


def item_next_due(score: float, ability: float, today: date) -> str:
    return (today + timedelta(days=item_review_days(score, ability))).isoformat()
