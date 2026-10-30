"""Facade used by the CLI, demo, and agent tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from interview_coach.agent.coach import CoachAgent
from interview_coach.agent.llm import LLM, build_llm
from interview_coach.agent.tools import build_registry
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.scoring import item_information, mastery_percent, update_ability
from interview_coach.assessment.targets import topic_weights
from interview_coach.db import Database
from interview_coach.models import AssessmentResult, Profile, Progress, StudyPlan, TopicScore
from interview_coach.planner.planner import adjusted_minutes, build_week, choose_policy, explain_policy, rank_topics
from interview_coach.profile.service import normalize_profile, prior_ability
from interview_coach.tracker.export import export_ics, export_markdown
from interview_coach.tracker.importer import ImportBatch, load_progress
from interview_coach.tracker.schedule import next_review_on
from interview_coach.tracker.tracker import summarize, unfinished_focuses


@dataclass(frozen=True)
class ImportResult:
    practice_count: int
    log_count: int


class CoachApp:
    def __init__(self, db: Database, bank: QuestionBank | None = None) -> None:
        self.db = db
        self.bank = bank or QuestionBank()

    def init_profile(
        self,
        name: str,
        target_role: str,
        level: str = "mid",
        daily_minutes: int = 30,
        target: str = "generic_tech",
    ) -> Profile:
        incoming = normalize_profile(name, target_role, level, daily_minutes, target)
        return self.db.save_profile(
            incoming.name,
            incoming.target_role,
            incoming.level,
            incoming.daily_minutes,
            prior_ability(incoming.level),
            incoming.target_id,
        )

    def require_profile(self) -> Profile:
        profile = self.db.get_profile()
        if profile is None:
            raise LookupError("No profile yet. Run: interview-coach profile init --name YourName --role backend")
        return profile

    def assess(
        self,
        question_count: int,
        topics: list[str] | None,
        choose: Callable,
        kinds: list[str] | None = None,
        tags: list[str] | None = None,
        on: date | None = None,
        on_scored: Callable | None = None,
    ) -> AssessmentResult:
        profile = self.require_profile()
        selected = list(topics) if topics else list(self.bank.topics())
        if question_count < 1:
            raise ValueError("question count must be at least 1")
        engine = AdaptiveAssessment(
            self.bank,
            selected,
            prior=self.db.ability_map(),
            weights=topic_weights(profile.target_id),
            kinds=kinds,
            tags=tags,
        )
        for _ in range(question_count):
            question = engine.next_question()
            if question is None:
                break
            choice = choose(question)
            scored = engine.submit(question.id, choice)
            if on_scored is not None:
                on_scored(question, scored)
        if not engine.answers:
            raise RuntimeError("the question bank produced no items")
        today = on or date.today()
        payload = [
            {
                "question_id": answer.question_id,
                "topic": answer.topic,
                "difficulty": answer.difficulty,
                "choice_index": answer.choice_index,
                "correct": answer.correct,
                "ability_after": answer.ability_after,
                "score": answer.score,
                "kind": answer.kind,
                "information": answer.information,
                "response_text": answer.response_text,
            }
            for answer in engine.answers
        ]
        reviews = {
            topic: next_review_on(ability, today)
            for topic, ability in engine.ability.items()
            if any(answer.topic == topic for answer in engine.answers)
        }
        assessment_id = self.db.save_assessment(payload, engine.ability, reviews)
        scores = tuple(self.db.list_scores())
        return AssessmentResult(assessment_id, tuple(engine.answers), scores)

    def drill(
        self,
        question_count: int,
        choose: Callable,
        kinds: list[str] | None = None,
        tags: list[str] | None = None,
        on: date | None = None,
        on_scored: Callable | None = None,
        reviewed_on: date | None = None,
    ) -> AssessmentResult:
        """Practice due topics without replacing the active week.

        ``on`` only chooses which topics count as due. The next review date is
        scheduled from ``reviewed_on`` (today, unless a test pins it).
        """
        self.require_profile()
        due_on = on or date.today()
        due = self.db.due_topics(due_on.isoformat())
        if due:
            topics = due
        else:
            topics = rank_topics(self.db.list_scores(), self._weights())[:3]
        return self.assess(
            question_count,
            topics,
            choose,
            kinds=kinds,
            tags=tags,
            on=reviewed_on,
            on_scored=on_scored,
        )

    def create_plan(self, start: date | None = None, force: bool = False) -> StudyPlan:
        profile = self.require_profile()
        if self.db.get_active_plan() is not None and not force:
            raise RuntimeError("an active plan already exists; use replan or plan --force")
        scores = self.db.list_scores()
        drafts = build_week(scores, profile.daily_minutes, policy="steady", weights=self._weights())
        return self._store_plan(profile.daily_minutes, "initial", start or date.today(), drafts)

    def replan(self, start: date | None = None) -> tuple[StudyPlan, str]:
        profile = self.require_profile()
        current = self.db.get_active_plan()
        if current is None:
            raise LookupError("No plan yet. Run: interview-coach plan")
        progress = self.progress()
        policy = choose_policy(progress.reported_completion, progress.quiz_accuracy)
        minutes = adjusted_minutes(profile.daily_minutes, policy)
        start_on = start or date.today()
        carry = _merge(self.db.due_topics(start_on.isoformat()), unfinished_focuses(current))
        drafts = build_week(
            self.db.list_scores(),
            minutes,
            policy=policy,
            carry=carry,
            weights=self._weights(),
        )
        plan = self._store_plan(minutes, policy, start_on, drafts)
        return plan, explain_policy(policy, progress.reported_completion, progress.quiz_accuracy)

    def log_day(
        self,
        day_index: int,
        minutes_spent: int,
        completed: bool,
        quiz_correct: int | None = None,
        quiz_total: int | None = None,
        notes: str = "",
    ) -> None:
        plan = self.db.get_active_plan()
        if plan is None:
            raise LookupError("No plan yet. Run: interview-coach plan")
        day = next((item for item in plan.days if item.day_index == day_index), None)
        if day is None:
            raise ValueError(f"day {day_index} is not in the active plan")
        if minutes_spent < 0:
            raise ValueError("minutes spent cannot be negative")
        if (quiz_correct is None) ^ (quiz_total is None):
            raise ValueError("pass both quiz correct and quiz total")
        if quiz_total is not None and (quiz_total <= 0 or quiz_correct is None or not 0 <= quiz_correct <= quiz_total):
            raise ValueError("quiz score is out of range")
        self.db.add_log(day.id, minutes_spent, completed, quiz_correct, quiz_total, notes)
        self.db.set_day_status(day.id, "done" if completed else "missed")

    def progress(self) -> Progress:
        plan = self.db.get_active_plan()
        if plan is None:
            raise LookupError("No plan yet. Run: interview-coach plan")
        return summarize(plan, self.db.list_logs(plan.id))

    def due_topics(self, on: date | None = None) -> list[TopicScore]:
        self.require_profile()
        today = on or date.today()
        due = set(self.db.due_topics(today.isoformat()))
        return [score for score in self.db.list_scores() if score.topic in due]

    def export_plan(self, export_format: str) -> str:
        plan = self.db.get_active_plan()
        if plan is None:
            raise LookupError("No plan yet. Run: interview-coach plan")
        if export_format == "md":
            return export_markdown(plan)
        if export_format == "ics":
            return export_ics(plan)
        raise ValueError("format must be md or ics")

    def import_progress(self, path: Path, on: date | None = None) -> ImportResult:
        batch = load_progress(path)
        return self.import_batch(batch, on=on)

    def import_batch(self, batch: ImportBatch, on: date | None = None) -> ImportResult:
        self.require_profile()
        today = on or date.today()
        if batch.logs and self.db.get_active_plan() is None:
            raise LookupError("import includes day logs but there is no active plan")
        ability = self.db.ability_map()
        for record in batch.practice:
            if record.topic not in ability:
                raise ValueError(f"unknown topic {record.topic}")
        for record in batch.practice:
            prior = ability[record.topic]
            information = item_information(prior, record.difficulty, record.discrimination)
            updated = update_ability(prior, record.difficulty, record.score, record.discrimination)
            ability[record.topic] = updated
            self.db.apply_practice(
                record.topic,
                updated,
                record.score,
                information,
                next_review_on(updated, today),
            )
        for record in batch.logs:
            self.log_day(
                record.day,
                record.minutes,
                record.completed,
                quiz_correct=record.quiz_correct,
                quiz_total=record.quiz_total,
                notes=record.notes,
            )
        return ImportResult(len(batch.practice), len(batch.logs))

    def agent(self, llm_name: str = "offline", client: object | None = None) -> CoachAgent:
        llm: LLM = build_llm(llm_name, client=client)
        return CoachAgent(llm, build_registry(self))

    def _store_plan(self, minutes: int, policy: str, start: date, drafts: list) -> StudyPlan:
        days = []
        for draft in drafts:
            days.append(
                {
                    "day_index": draft.day_index,
                    "day_date": (start + timedelta(days=draft.day_index - 1)).isoformat(),
                    "focus": draft.focus,
                    "minutes": draft.minutes,
                    "objective": draft.objective,
                    "acceptance_criteria": draft.acceptance_criteria,
                }
            )
        return self.db.create_plan(minutes, policy, start.isoformat(), days)

    def _weights(self) -> dict[str, float]:
        return topic_weights(self.require_profile().target_id)


def _merge(*groups: list[str]) -> list[str]:
    ordered: list[str] = []
    for group in groups:
        for topic in group:
            if topic not in ordered:
                ordered.append(topic)
    return ordered


def overall_mastery(scores: tuple[TopicScore, ...] | list[TopicScore], answered_only: bool = True) -> int:
    chosen = [score for score in scores if score.answered > 0] if answered_only else list(scores)
    if not chosen:
        chosen = list(scores)
    if not chosen:
        return 0
    return int(round(sum(mastery_percent(score.ability) for score in chosen) / len(chosen)))
