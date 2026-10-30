"""Shared domain records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    topic: str
    difficulty: int
    prompt: str
    choices: tuple[str, ...]
    answer: int
    explanation: str


@dataclass(frozen=True)
class Profile:
    name: str
    target_role: str
    level: str
    daily_minutes: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TopicScore:
    topic: str
    ability: float
    answered: int
    correct: int


@dataclass(frozen=True)
class ScoredAnswer:
    question_id: str
    topic: str
    difficulty: int
    choice_index: int
    correct: bool
    ability_after: float


@dataclass(frozen=True)
class AssessmentResult:
    assessment_id: int
    answers: tuple[ScoredAnswer, ...]
    scores: tuple[TopicScore, ...]

    @property
    def correct_count(self) -> int:
        return sum(1 for answer in self.answers if answer.correct)


@dataclass(frozen=True)
class DayDraft:
    day_index: int
    focus: str
    minutes: int
    objective: str
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True)
class PlanDay:
    id: int
    day_index: int
    day_date: str
    focus: str
    minutes: int
    objective: str
    acceptance_criteria: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class StudyPlan:
    id: int
    version: int
    daily_minutes: int
    policy: str
    start_date: str
    days: tuple[PlanDay, ...]


@dataclass(frozen=True)
class StudyLog:
    id: int
    plan_day_id: int
    day_index: int
    minutes_spent: int
    completed: bool
    quiz_correct: int | None
    quiz_total: int | None
    notes: str


@dataclass(frozen=True)
class Progress:
    plan_id: int
    version: int
    days_total: int
    days_done: int
    days_missed: int
    days_pending: int
    reported_completion: float
    quiz_accuracy: float
    minutes_spent: int
