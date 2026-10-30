"""Rasch-style ability updates on a shared 1–5 scale.

Item difficulty and learner ability use the same scale. The probability of a
correct answer is a one-parameter logistic of (ability - difficulty). Each
observed answer nudges ability by a step scaled by item discrimination.
Partial credit (0–1) is allowed for rubric-scored open answers.

Confidence is not a fitted model. It is the share of accumulated Fisher-style
information, ``I / (I + 1)``, where each answer contributes
``discrimination^2 * p * (1 - p)`` and ``p`` is the expected score.
"""

from __future__ import annotations

import math

MIN_ABILITY = 1.0
MAX_ABILITY = 5.0
DEFAULT_ABILITY = 3.0
STEP = 0.5
SCALE = 1.2
# Harder items separate learners a bit more. This is a fixed prior, not a fit.
DISCRIMINATION_BY_DIFFICULTY = {1: 0.8, 2: 0.9, 3: 1.0, 4: 1.15, 5: 1.3}


def clamp_ability(ability: float) -> float:
    return min(MAX_ABILITY, max(MIN_ABILITY, ability))


def default_discrimination(difficulty: int) -> float:
    return DISCRIMINATION_BY_DIFFICULTY.get(int(difficulty), 1.0)


def expected_correct(ability: float, difficulty: float) -> float:
    return 1.0 / (1.0 + 10 ** ((difficulty - ability) / SCALE))


def update_ability(
    ability: float,
    difficulty: float,
    correct: bool | float,
    discrimination: float = 1.0,
) -> float:
    expected = expected_correct(ability, difficulty)
    if isinstance(correct, bool):
        actual = 1.0 if correct else 0.0
    else:
        actual = float(correct)
    if not 0.0 <= actual <= 1.0:
        raise ValueError("score must be between 0 and 1")
    disc = discrimination if discrimination > 0 else 1.0
    return clamp_ability(ability + STEP * disc * (actual - expected))


def item_information(ability: float, difficulty: float, discrimination: float = 1.0) -> float:
    """Information proxy. Highest when the item sits near the current ability."""
    probability = expected_correct(ability, difficulty)
    disc = discrimination if discrimination > 0 else 1.0
    return (disc ** 2) * probability * (1.0 - probability)


def confidence_ratio(information: float) -> float:
    if information <= 0:
        return 0.0
    return information / (information + 1.0)


def confidence_percent(information: float) -> int:
    return int(round(100 * confidence_ratio(information)))


def ability_standard_error(information: float) -> float | None:
    if information <= 0:
        return None
    return 1.0 / math.sqrt(information)


def mastery_percent(ability: float) -> int:
    raw = (clamp_ability(ability) - MIN_ABILITY) / (MAX_ABILITY - MIN_ABILITY) * 100
    return int(round(raw))
