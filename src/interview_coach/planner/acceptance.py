"""Check a practice session against one plan day's acceptance criteria.

Minutes and reflection lines are satisfied by finishing the session.
Score lines and open-item rubric lines are checked against the answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interview_coach.models import ScoredAnswer

OPEN_RE = re.compile(r"Open item ([A-Za-z0-9_-]+)", re.IGNORECASE)
QUIZ_RE = re.compile(r"at least (\d+)/(\d+)", re.IGNORECASE)
SHORT_SET = 4


@dataclass(frozen=True)
class Verdict:
    met: bool
    missing: tuple[str, ...] = ()


def open_item_id(criteria: tuple[str, ...] | list[str]) -> str | None:
    for raw in criteria:
        match = OPEN_RE.search(raw)
        if match:
            return match.group(1)
    return None


def evaluate(
    criteria: tuple[str, ...] | list[str],
    answers: tuple[ScoredAnswer, ...] | list[ScoredAnswer],
    topics: set[str],
) -> Verdict:
    relevant = [answer for answer in answers if answer.topic in topics]
    missing: list[str] = []
    checks = 0
    for raw in criteria:
        opened = OPEN_RE.search(raw)
        quiz = QUIZ_RE.search(raw)
        if opened and quiz:
            checks += 1
            need = int(quiz.group(1))
            total = int(quiz.group(2))
            question_id = opened.group(1)
            hits = 0
            for answer in relevant:
                if answer.question_id == question_id:
                    hits = max(hits, len(answer.rubric_hits))
            if hits < need:
                missing.append(f"rubric:{question_id}:{hits}:{need}:{total}")
            continue
        if quiz:
            checks += 1
            need = int(quiz.group(1))
            out_of = int(quiz.group(2))
            minimum = min(SHORT_SET, out_of)
            if len(relevant) < minimum:
                missing.append(f"items:{len(relevant)}:{minimum}")
                continue
            earned = sum(answer.score for answer in relevant)
            if earned / len(relevant) + 1e-9 < need / out_of:
                missing.append(f"quiz:{_ratio(earned, len(relevant))}:{need}/{out_of}")
    if checks == 0:
        return Verdict(False, ("checks:0",))
    return Verdict(not missing, tuple(missing))


def _ratio(earned: float, count: int) -> str:
    if abs(earned - round(earned)) < 1e-6:
        return f"{int(round(earned))}/{count}"
    return f"{earned:.1f}/{count}"
