"""Offline rubric scoring for open answers. No model and no network."""

from __future__ import annotations

from dataclasses import dataclass

from interview_coach.models import Question


@dataclass(frozen=True)
class RubricScore:
    ratio: float
    hits: tuple[str, ...]
    total_points: int
    hit_points: int


def score_rubric(question: Question, text: str) -> RubricScore:
    if question.kind != "open":
        raise ValueError("rubric scoring is for open questions")
    if not question.rubric:
        raise ValueError(f"{question.id} has no rubric")
    haystack = " ".join(text.lower().split())
    hits: list[str] = []
    earned = 0.0
    total = 0.0
    for point in question.rubric:
        if point.weight <= 0:
            raise ValueError(f"{question.id} has a non-positive rubric weight")
        total += point.weight
        if haystack and any(keyword.lower() in haystack for keyword in point.keywords):
            earned += point.weight
            hits.append(point.label)
    ratio = 0.0 if total == 0 else earned / total
    return RubricScore(ratio, tuple(hits), len(question.rubric), len(hits))
