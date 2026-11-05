"""Adaptive session for multiple-choice and open items.

Topic choice prefers the topic that is furthest behind its target weight,
then the lowest ability. With equal weights this is the same as fewest
attempts, then lowest ability.

Item choice picks the unseen question whose difficulty is closest to the
current ability estimate. Ties break by question id so a session is
deterministic given the same answers.
"""

from __future__ import annotations

from datetime import date

from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.rubric import score_rubric
from interview_coach.assessment.scoring import DEFAULT_ABILITY, item_information, update_ability
from interview_coach.models import Question, ScoredAnswer

FULL_CREDIT = 0.999
SHORT_TOPIC_CAP = 6


class AdaptiveAssessment:
    def __init__(
        self,
        bank: QuestionBank,
        topics: list[str],
        prior: dict[str, float] | None = None,
        weights: dict[str, float] | None = None,
        kinds: list[str] | tuple[str, ...] | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        exposed: dict[str, str] | None = None,
        today: date | None = None,
        max_per_topic: int = SHORT_TOPIC_CAP,
        must_ask: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        if not topics:
            raise ValueError("at least one topic is required")
        unknown = [topic for topic in topics if not bank.for_topic(topic)]
        if unknown:
            raise ValueError(f"unknown or empty topics: {', '.join(unknown)}")
        self.bank = bank
        self.kinds = _normalize_kinds(kinds)
        self.tags = {tag.strip().lower() for tag in tags or () if tag.strip()} or None
        self.weights = {topic: _positive(weight) for topic, weight in (weights or {}).items()}
        available = [topic for topic in topics if self._candidates(topic)]
        if not available:
            detail = ", ".join(sorted(self.tags)) if self.tags else ", ".join(sorted(self.kinds))
            raise ValueError(f"no questions matched the requested filter ({detail})")
        self.topics = available
        self.ability = {topic: (prior or {}).get(topic, DEFAULT_ABILITY) for topic in self.topics}
        self.asked: set[str] = set()
        self.counts = {topic: 0 for topic in self.topics}
        self.information = {topic: 0.0 for topic in self.topics}
        self.answers: list[ScoredAnswer] = []
        self.exposed = dict(exposed or {})
        self.today = (today or date.today()).isoformat()
        self.max_per_topic = max_per_topic
        self.must_ask = [item for item in (must_ask or ()) if item]

    def next_question(self, reserve: int = 0) -> Question | None:
        """Next item. ``reserve`` is how many questions the caller still has after this one.

        Required open items wait until a reserved slot so a short session still
        ends on the rubric instead of opening with it.
        """
        pending = self._must_ask()
        if pending is not None and reserve < self._pending_must_ask_count():
            return pending
        natural = self._natural_next()
        if natural is not None:
            return natural
        return pending

    def _natural_next(self) -> Question | None:
        ranked = sorted(self.topics, key=self._topic_key)
        for topic in ranked:
            question = self._closest(topic)
            if question is not None:
                return question
        return None

    def submit(self, question_id: str, response: int | str) -> ScoredAnswer:
        question = self.bank.get(question_id)
        if question.topic not in self.ability:
            raise ValueError(f"{question.topic} is not part of this assessment")
        if question.id in self.asked:
            raise ValueError(f"{question.id} was already answered")
        if question.kind == "open":
            text = response if isinstance(response, str) else str(response)
            rubric = score_rubric(question, text)
            score = rubric.ratio
            hits = rubric.hits
            choice_index = -1
        else:
            if isinstance(response, str):
                raise ValueError("multiple-choice answers must be an index")
            choice_index = int(response)
            if choice_index < 0 or choice_index >= len(question.choices):
                raise ValueError("choice index is out of range")
            score = 1.0 if choice_index == question.answer else 0.0
            hits = ()
            text = ""
        prior = self.ability[question.topic]
        information = item_information(prior, question.difficulty, question.discrimination)
        ability = update_ability(prior, question.difficulty, score, question.discrimination)
        self.ability[question.topic] = ability
        self.information[question.topic] += information
        self.asked.add(question.id)
        self.counts[question.topic] += 1
        scored = ScoredAnswer(
            question_id=question.id,
            topic=question.topic,
            difficulty=question.difficulty,
            choice_index=choice_index,
            correct=score >= FULL_CREDIT,
            ability_after=ability,
            score=score,
            kind=question.kind,
            information=information,
            response_text=text,
            rubric_hits=hits,
        )
        self.answers.append(scored)
        return scored

    def _topic_key(self, topic: str) -> tuple[float, float, str]:
        weight = self.weights.get(topic, 1.0)
        return ((self.counts[topic] + 1) / weight, self.ability[topic], topic)

    def _pending_ids(self) -> set[str]:
        return {question_id for question_id in self.must_ask if question_id not in self.asked}

    def _pending_must_ask_count(self) -> int:
        return len(self._pending_ids())

    def _must_ask(self) -> Question | None:
        """The day's open item is part of the assignment, so exposure does not hide it."""
        for question_id in self.must_ask:
            if question_id in self.asked:
                continue
            try:
                question = self.bank.get(question_id)
            except KeyError:
                continue
            if question.topic not in self.ability or question.kind not in self.kinds:
                continue
            return question
        return None

    def _closest(self, topic: str) -> Question | None:
        if self.counts[topic] >= self.max_per_topic:
            return None
        reserved = self._pending_ids()
        candidates = [
            question
            for question in self._candidates(topic)
            if question.id not in self.asked and question.id not in reserved
        ]
        if not candidates:
            return None
        due = [
            question
            for question in candidates
            if question.id in self.exposed and self.exposed[question.id] <= self.today
        ]
        unseen = [question for question in candidates if question.id not in self.exposed]
        if due:
            pool = due
        elif unseen:
            pool = unseen
        else:
            pool = candidates
        target = self.ability[topic]
        return min(pool, key=lambda question: (abs(question.difficulty - target), question.id))

    def _candidates(self, topic: str) -> list[Question]:
        matched: list[Question] = []
        for question in self.bank.for_topic(topic):
            if question.kind not in self.kinds:
                continue
            if self.tags is not None and not self.tags.intersection(tag.lower() for tag in question.tags):
                continue
            matched.append(question)
        return matched


def _positive(weight: float) -> float:
    if weight <= 0:
        raise ValueError("topic weights must be positive")
    return float(weight)


def _normalize_kinds(kinds: list[str] | tuple[str, ...] | None) -> set[str]:
    if not kinds:
        return {"mcq", "open"}
    normalized = {kind.strip().lower() for kind in kinds if kind.strip()}
    unknown = normalized - {"mcq", "open"}
    if unknown:
        raise ValueError(f"unknown question kinds: {', '.join(sorted(unknown))}")
    if not normalized:
        raise ValueError("at least one question kind is required")
    return normalized
