"""Rasch-style ability updates on a shared 1–5 scale.

Item difficulty and learner ability use the same scale. The probability of a
correct answer is a one-parameter logistic of (ability - difficulty). Each
observed answer nudges ability toward the evidence with a fixed step size.
"""

from __future__ import annotations

MIN_ABILITY = 1.0
MAX_ABILITY = 5.0
DEFAULT_ABILITY = 3.0
STEP = 0.5
SCALE = 1.2


def clamp_ability(ability: float) -> float:
    return min(MAX_ABILITY, max(MIN_ABILITY, ability))


def expected_correct(ability: float, difficulty: float) -> float:
    return 1.0 / (1.0 + 10 ** ((difficulty - ability) / SCALE))


def update_ability(ability: float, difficulty: float, correct: bool) -> float:
    expected = expected_correct(ability, difficulty)
    actual = 1.0 if correct else 0.0
    return clamp_ability(ability + STEP * (actual - expected))


def mastery_percent(ability: float) -> int:
    raw = (clamp_ability(ability) - MIN_ABILITY) / (MAX_ABILITY - MIN_ABILITY) * 100
    return int(round(raw))
