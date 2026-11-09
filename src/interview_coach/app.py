"""Facade used by the CLI, demo, and agent tools."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from interview_coach.agent.coach import CoachAgent
from interview_coach.agent.llm import LLM, build_llm
from interview_coach.agent.tools import build_registry
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.scoring import is_weak_evidence, item_information, mastery_percent, update_ability
from interview_coach.assessment.targets import topic_weights
from interview_coach.coach_text import closing_lines, intro_lines, weak_labels
from interview_coach.db import Database
from interview_coach.models import AssessmentResult, AutoLog, PlanDay, Profile, Progress, StudyPlan, TopicScore
from interview_coach.planner.acceptance import applicable_criteria, evaluate, open_item_id
from interview_coach.planner.planner import (
    adjusted_minutes,
    build_week,
    choose_policy,
    explain_policy,
    focus_topics,
)
from interview_coach.profile.service import (
    DEFAULT_DAILY_MINUTES,
    DEFAULT_KINDS,
    DEFAULT_STREAK_GOAL,
    normalize_kinds,
    normalize_profile,
    prior_ability,
)
from interview_coach.tracker.export import export_ics, export_markdown
from interview_coach.tracker.importer import ImportBatch, load_progress
from interview_coach.tracker.schedule import item_next_due, next_review_on
from interview_coach.tracker.tracker import summarize, unfinished_focuses


class NothingDue(RuntimeError):
    """Drill found no due topics and did not change the schedule."""


@dataclass(frozen=True)
class ImportResult:
    practice_count: int
    log_count: int


@dataclass(frozen=True)
class TodaySetup:
    day: PlanDay
    topics: list[str]
    kinds: list[str]
    must_ask: tuple[str, ...]
    created_plan: bool
    replanned: bool
    lines: tuple[str, ...]


class CoachApp:
    def __init__(self, db: Database, bank: QuestionBank | None = None) -> None:
        self.db = db
        self.bank = bank or QuestionBank()

    def init_profile(
        self,
        name: str,
        target_role: str,
        level: str | None = None,
        daily_minutes: int | None = None,
        target: str | None = None,
        streak_goal: int | None = None,
        preferred_kinds: str | None = None,
        reset_scores: bool = False,
    ) -> Profile:
        """Create or update the learner.

        Omitted level, minutes, and target keep the saved values. On the first
        profile, an omitted target is inferred from the job title (``后端`` and
        ``Backend engineer`` both become ``backend_engineer``).
        """
        existing = self.db.get_profile()
        if level is None:
            level = existing.level if existing else "mid"
        if daily_minutes is None:
            daily_minutes = existing.daily_minutes if existing else DEFAULT_DAILY_MINUTES
        if target is None:
            target = existing.target_id if existing else "auto"
        if streak_goal is None:
            streak_goal = existing.streak_goal if existing else DEFAULT_STREAK_GOAL
        if preferred_kinds is None:
            preferred_kinds = existing.preferred_kinds if existing else DEFAULT_KINDS
        incoming = normalize_profile(
            name,
            target_role,
            level,
            daily_minutes,
            target,
            streak_goal=streak_goal,
            preferred_kinds=preferred_kinds,
        )
        return self.db.save_profile(
            incoming.name,
            incoming.target_role,
            incoming.level,
            incoming.daily_minutes,
            prior_ability(incoming.level),
            incoming.target_id,
            streak_goal=incoming.streak_goal,
            preferred_kinds=incoming.preferred_kinds,
            reset_scores=reset_scores,
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
        must_ask: list[str] | tuple[str, ...] | None = None,
    ) -> AssessmentResult:
        profile = self.require_profile()
        selected = list(topics) if topics else list(self.bank.topics())
        if question_count < 1:
            raise ValueError("question count must be at least 1")
        today = on or date.today()
        started = time.monotonic()
        engine = AdaptiveAssessment(
            self.bank,
            selected,
            prior=self.db.ability_map(),
            weights=topic_weights(profile.target_id),
            kinds=kinds,
            tags=tags,
            exposed=self.db.exposure_map(),
            today=today,
            must_ask=must_ask,
        )
        for index in range(question_count):
            question = engine.next_question(reserve=question_count - index - 1)
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
        exposures = [
            {
                "question_id": answer.question_id,
                "topic": answer.topic,
                "last_seen": today.isoformat(),
                "last_score": answer.score,
                "next_due": item_next_due(answer.score, answer.ability_after, today),
            }
            for answer in engine.answers
        ]
        assessment_id = self.db.save_assessment(payload, engine.ability, reviews, exposures)
        scores = tuple(self.db.list_scores())
        elapsed_minutes = int((time.monotonic() - started) // 60)
        autolog = self._autolog(tuple(engine.answers), kinds, elapsed_minutes)
        self._adapt_pending_plan()
        return AssessmentResult(assessment_id, tuple(engine.answers), scores, autolog)

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
        if not due:
            raise NothingDue("No topics are due. The schedule was left unchanged.")
        topics = due
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
        drafts = build_week(
            scores,
            profile.daily_minutes,
            policy="steady",
            weights=self._weights(),
            open_cursor=self._open_cursor(),
        )
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
            open_cursor=self._open_cursor(),
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

    def prepare_today(
        self,
        on: date | None = None,
        lang: str = "zh",
        kinds: list[str] | None = None,
    ) -> TodaySetup:
        """Make sure a week exists and describe the next pending day. Does not ask questions."""
        profile = self.require_profile()
        today = on or date.today()
        created = False
        replanned = False
        skipped = 0
        plan = self.db.get_active_plan()
        if plan is None:
            plan = self.create_plan(start=today)
            created = True
        else:
            skipped = self._skip_overdue(today)
            plan = self.db.get_active_plan()
        if plan is None or not any(day.status == "pending" for day in plan.days):
            plan, _reason = self.replan(start=today)
            replanned = True
        if plan is None:
            raise RuntimeError("the active plan has no pending day")
        day = next((item for item in plan.days if item.status == "pending"), None)
        if day is None:
            raise RuntimeError("the active plan has no pending day")
        topics = focus_topics(day.focus)
        session_kinds = _resolve_kinds(profile.preferred_kinds, kinds)
        question_id = open_item_id(day.acceptance_criteria)
        must_ask = (question_id,) if question_id and "open" in session_kinds else ()
        visible = tuple(applicable_criteria(day.acceptance_criteria, session_kinds))
        shown = replace(day, acceptance_criteria=visible or day.acceptance_criteria)
        lines = intro_lines(shown, lang, created_plan=created, replanned=replanned)
        if skipped:
            note = (
                f"有 {skipped} 天过了日期还没练，已记为错过。"
                if lang == "zh"
                else f"{skipped} scheduled day(s) passed without practice and were marked missed."
            )
            lines = [note, *lines]
        return TodaySetup(day, topics, session_kinds, must_ask, created, replanned, tuple(lines))

    def closing_lines(self, result: AssessmentResult, lang: str = "zh", on: date | None = None) -> list[str]:
        plan = self.db.get_active_plan()
        profile = self.db.get_profile()
        today = on or date.today()
        autolog = result.autolog
        logged = bool(autolog and autolog.logged)
        day_index = autolog.day_index if autolog else None
        focus = autolog.focus if autolog else ""
        missing = autolog.missing if autolog else ()
        next_day = None
        days_done = 0
        days_missed = 0
        if plan is not None:
            days_done = sum(1 for day in plan.days if day.status == "done")
            days_missed = sum(1 for day in plan.days if day.status == "missed")
            next_day = next((day for day in plan.days if day.status == "pending"), None)
        weak = weak_labels(self.db.list_scores(), lang)
        streak_goal = profile.streak_goal if profile else 5
        return closing_lines(
            lang=lang,
            logged=logged,
            day_index=day_index,
            focus=focus,
            missing=missing,
            next_day=next_day,
            days_done=days_done,
            streak_goal=streak_goal,
            weak=weak,
            streak=self.current_streak(today),
            days_missed=days_missed,
        )

    def current_streak(self, on: date | None = None) -> int:
        """Consecutive completed calendar days ending today, or yesterday if today is still open."""
        today = on or date.today()
        done = {date.fromisoformat(value) for value in self.db.completed_dates()}
        cursor = today if today in done else today - timedelta(days=1)
        if cursor not in done:
            return 0
        count = 0
        while cursor in done:
            count += 1
            cursor -= timedelta(days=1)
        return count

    def overdue_count(self, on: date | None = None) -> int:
        plan = self.db.get_active_plan()
        if plan is None:
            return 0
        today = on or date.today()
        return sum(
            1
            for day in plan.days
            if day.status == "pending" and date.fromisoformat(day.day_date) < today
        )

    def agent(self, llm_name: str = "offline", client: object | None = None, lang: str = "zh") -> CoachAgent:
        llm: LLM = build_llm(llm_name, client=client, lang=lang)
        return CoachAgent(llm, build_registry(self))

    def _autolog(
        self,
        answers: tuple,
        kinds: list[str] | None,
        minutes_spent: int,
    ) -> AutoLog | None:
        plan = self.db.get_active_plan()
        if plan is None or not answers:
            return None
        pending = [day for day in plan.days if day.status == "pending"]
        if not pending:
            return None
        day = pending[0]
        topics = set(focus_topics(day.focus))
        if topics.isdisjoint({answer.topic for answer in answers}):
            return None
        verdict = evaluate(day.acceptance_criteria, answers, topics, kinds=kinds)
        if not verdict.met:
            return AutoLog(False, day.day_index, day.focus, verdict.missing)
        relevant = [answer for answer in answers if answer.topic in topics]
        correct = sum(1 for answer in relevant if answer.correct)
        spent = max(0, int(minutes_spent))
        self.log_day(day.day_index, spent, True, correct, len(relevant), notes="auto")
        return AutoLog(True, day.day_index, day.focus, ())

    def _skip_overdue(self, today: date) -> int:
        plan = self.db.get_active_plan()
        if plan is None:
            return 0
        skipped = 0
        for day in plan.days:
            if day.status != "pending":
                continue
            if date.fromisoformat(day.day_date) >= today:
                continue
            self.log_day(day.day_index, 0, False, notes="skipped")
            skipped += 1
        return skipped

    def _adapt_pending_plan(self) -> None:
        """Point the remaining days at evidenced weak topics once answers exist."""
        plan = self.db.get_active_plan()
        if plan is None:
            return
        scores = self.db.list_scores()
        if not any(is_weak_evidence(item.answered, item.correct, item.credit) for item in scores):
            return
        pending = [day for day in plan.days if day.status == "pending"]
        if not pending:
            return
        policy = plan.policy if plan.policy in {"shrink", "stretch", "steady"} else "steady"
        drafts = build_week(
            scores,
            plan.daily_minutes,
            policy=policy,
            weights=self._weights(),
            open_cursor=self._open_cursor(),
        )
        focus_drafts = [item for item in drafts if not item.focus.startswith(("review:", "mock:"))]
        review = next(item for item in drafts if item.focus.startswith("review:"))
        mock = next(item for item in drafts if item.focus.startswith("mock:"))
        focus_index = 0
        for day in pending:
            if day.focus.startswith("review:"):
                draft = review
            elif day.focus.startswith("mock:"):
                draft = mock
            else:
                draft = focus_drafts[focus_index % len(focus_drafts)]
                focus_index += 1
            # Keep a day whose topic is already right so a retry still matches its open item.
            if day.focus == draft.focus:
                continue
            self.db.update_plan_day(
                day.id,
                draft.focus,
                day.minutes,
                draft.objective,
                draft.acceptance_criteria,
            )

    def _open_cursor(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for question_id in self.db.exposure_map():
            try:
                question = self.bank.get(question_id)
            except KeyError:
                continue
            if question.kind != "open":
                continue
            counts[question.topic] = counts.get(question.topic, 0) + 1
        return counts

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


def _resolve_kinds(preferred: str, override: list[str] | None) -> list[str]:
    """Honor an explicit mix. Do not add mcq or open the learner did not ask for."""
    if override:
        return normalize_kinds(",".join(override)).split(",")
    kinds = [part.strip() for part in preferred.split(",") if part.strip()]
    return kinds or ["mcq", "open"]


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
