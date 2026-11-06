"""Offline rubric scoring for open answers. No model and no network.

Keywords match tokens, not raw substrings. ``log`` does not hit inside
``catalog``, and ``sorted`` does not hit inside ``unsorted``. A short stem
still accepts ``retries`` for ``retry`` and ``acknowledgements`` for
``acknowledg``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interview_coach.models import Question

_TOKEN = re.compile(r"[a-z0-9]+")
_CONTRACTIONS = (
    ("don't", "do not"),
    ("doesn't", "does not"),
    ("won't", "will not"),
    ("can't", "cannot"),
    ("isn't", "is not"),
)


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
    haystack = _tokens(text)
    hits: list[str] = []
    earned = 0.0
    total = 0.0
    for point in question.rubric:
        if point.weight <= 0:
            raise ValueError(f"{question.id} has a non-positive rubric weight")
        total += point.weight
        if haystack and any(_keyword_in(keyword, haystack) for keyword in point.keywords):
            earned += point.weight
            hits.append(point.label)
    ratio = 0.0 if total == 0 else earned / total
    return RubricScore(ratio, tuple(hits), len(question.rubric), len(hits))


def _tokens(text: str) -> list[str]:
    lowered = text.lower().replace("’", "'")
    for source, target in _CONTRACTIONS:
        lowered = lowered.replace(source, target)
    lowered = lowered.replace("-", " ")
    return _TOKEN.findall(lowered)


def _keyword_in(keyword: str, haystack: list[str]) -> bool:
    parts = _tokens(keyword)
    if not parts:
        return False
    if len(parts) == 1:
        return any(_token_hit(parts[0], token) for token in haystack)
    width = len(parts)
    if len(haystack) < width:
        return False
    for start in range(len(haystack) - width + 1):
        if all(_token_hit(parts[offset], haystack[start + offset]) for offset in range(width)):
            return True
    return False


def _token_hit(keyword: str, token: str) -> bool:
    if token == keyword or _stem(token) == _stem(keyword):
        return True
    if len(keyword) >= 5 and token.startswith(keyword) and len(token) - len(keyword) <= 8:
        return True
    if len(token) >= 5 and keyword.startswith(token) and len(keyword) - len(token) <= 8:
        return True
    return False


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word
