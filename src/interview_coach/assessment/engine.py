"""Adaptive multiple-choice session.

Topic choice prefers the least-attempted topic, then the lowest ability.
Item choice picks the unseen question whose difficulty is closest to the
current ability estimate. Ties break by question id so a session is
deterministic given the same answers.
"""

from __future__ import annotations

from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.scoring import DEFAULT_ABILITY, update_ability
from interview_coach.models import Question, ScoredAnswer


class AdaptiveAssessment:
    def __init__(
        self,
        bank: QuestionBank,
        topics: list[str],
        prior: dict[str, float] | None = None,
    ) -> None:
        if not topics:
            raise ValueError("at least one topic is required")
        unknown = [topic for topic in topics if not bank.for_topic(topic)]
        if unknown:
            raise ValueError(f"unknown or empty topics: {', '.join(unknown)}")
        self.bank = bank
        self.topics = list(topics)
        self.ability = {topic: (prior or {}).get(topic, DEFAULT_ABILITY) for topic in self.topics}
        self.asked: set[str] = set()
        self.counts = {topic: 0 for topic in self.topics}
        self.answers: list[ScoredAnswer] = []

    def next_question(self) -> Question | None:
        ranked = sorted(self.topics, key=lambda topic: (self.counts[topic], self.ability[topic], topic))
        for topic in ranked:
            question = self._closest(topic)
            if question is not None:
                return question
        return None

    def submit(self, question_id: str, choice_index: int) -> ScoredAnswer:
        question = self.bank.get(question_id)
        if question.topic not in self.ability:
            raise ValueError(f"{question.topic} is not part of this assessment")
        if question.id in self.asked:
            raise ValueError(f"{question.id} was already answered")
        if choice_index < 0 or choice_index >= len(question.choices):
            raise ValueError("choice index is out of range")
        correct = choice_index == question.answer
        ability = update_ability(self.ability[question.topic], question.difficulty, correct)
        self.ability[question.topic] = ability
        self.asked.add(question.id)
        self.counts[question.topic] += 1
        scored = ScoredAnswer(
            question_id=question.id,
            topic=question.topic,
            difficulty=question.difficulty,
            choice_index=choice_index,
            correct=correct,
            ability_after=ability,
        )
        self.answers.append(scored)
        return scored

    def _closest(self, topic: str) -> Question | None:
        candidates = [question for question in self.bank.for_topic(topic) if question.id not in self.asked]
        if not candidates:
            return None
        target = self.ability[topic]
        return min(candidates, key=lambda question: (abs(question.difficulty - target), question.id))
