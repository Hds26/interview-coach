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
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
# A keyword must not match only as the tail of a negation: 未排序 does not hit 排序.
_CJK_NEGATION = frozenset("不未非无")
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
        if any(_keyword_in(keyword, haystack, text) for keyword in point.keywords):
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


def _keyword_in(keyword: str, haystack: list[str], raw: str = "") -> bool:
    """Match an English token sequence or a Chinese phrase.

    Chinese is not space-separated, so CJK keywords match as phrases. A pure
    Latin keyword still uses the token rules, which keep ``sorted`` from
    hitting inside ``unsorted``.
    """
    cjk_runs = _CJK_RUN.findall(keyword)
    latin = _tokens(keyword)
    if cjk_runs and not latin:
        return all(_cjk_in(run, raw) for run in cjk_runs)
    if cjk_runs and latin:
        return all(_cjk_in(run, raw) for run in cjk_runs) and _latin_in(keyword, haystack)
    return _latin_in(keyword, haystack)


def _cjk_in(keyword: str, raw: str) -> bool:
    if not keyword or not raw:
        return False
    folded = re.sub(r"\s+", "", raw)
    start = 0
    while True:
        index = folded.find(keyword, start)
        if index < 0:
            return False
        if index == 0 or folded[index - 1] not in _CJK_NEGATION:
            return True
        start = index + len(keyword)


def _latin_in(keyword: str, haystack: list[str]) -> bool:
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
