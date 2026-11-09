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
from interview_coach.learner.model import (
    SOURCE_LABELS,
    parse_style,
    parse_weak,
    plan_carry,
    render_start,
    resolve_weak,
)
from interview_coach.models import AssessmentResult, AutoLog, PlanDay, Profile, Progress, StudyPlan, TopicScore
from interview_coach.planner.acceptance import applicable_criteria, evaluate, open_item_id
from interview_coach.planner.planner import (
    adjusted_minutes,
    build_week,
    choose_policy,
    explain_policy,
    focus_topics,
    single_focus_day,
)
from interview_coach.research.extract import draft_items
from interview_coach.star.service import StarReport, run_star_session
from interview_coach.research.service import (
    BOOST,
    EXPIRE_DAYS,
    FULL_DAYS,
    ResearchPreview,
    boost_on,
    prepare_paste,
    prepare_query,
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
class StartResult:
    profile: Profile
    plan: StudyPlan
    summary: str


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
            raise LookupError("No profile yet. Run: interview-coach start --name YourName --role 后端")
        return profile

    def start_onboarding(
        self,
        *,
        name: str | None = None,
        role: str | None = None,
        daily_minutes: int | None = None,
        kinds: str | None = None,
        weak: str | None = None,
        pastes: list[tuple[str, str]] | None = None,
        on: date | None = None,
        llm: str = "offline",
        opener=None,
    ) -> StartResult:
        """Save habits and pasted skill tags, then build or refresh the 7-day plan.

        Pasted text is mapped with the same local skill list as ``research --paste``.
        The note itself is not stored. Ability scores are left as they are.
        """
        if kinds is not None:
            parse_style(kinds)
        if weak is not None:
            parse_weak(weak)
        for kind, _text in pastes or []:
            if kind not in SOURCE_LABELS:
                raise ValueError("paste kind must be resume, jd, or notes")
        existing = self.db.get_profile()
        if existing is None and (not name or not name.strip() or not role or not role.strip()):
            raise ValueError("name and role are required")
        chosen_name = name.strip() if name and name.strip() else (existing.name if existing else "")
        chosen_role = role.strip() if role and role.strip() else (existing.target_role if existing else "")
        style = parse_style(kinds) if kinds is not None else None
        profile = self.init_profile(
            chosen_name,
            chosen_role,
            daily_minutes=daily_minutes,
            preferred_kinds=style,
        )
        previous = self.db.get_learner()
        self.db.save_learner_habits(
            profile.daily_minutes,
            profile.preferred_kinds,
            resolve_weak(weak, previous.self_weak if previous else None),
        )
        for kind, text in pastes or []:
            self._save_paste(kind, text, llm=llm, opener=opener)
        plan = self.refresh_plan_from_learner(on)
        model = self.db.get_learner()
        assert model is not None
        summary = render_start(
            minutes=profile.daily_minutes,
            style=profile.preferred_kinds,
            self_weak=model.self_weak,
            skills=model.skills,
            plan=plan,
            scores=self.db.list_scores(),
        )
        return StartResult(profile, plan, summary)

    def refresh_plan_from_learner(self, on: date | None = None) -> StudyPlan:
        """Create the week, or rewrite pending days from the learner model."""
        profile = self.require_profile()
        today = on or date.today()
        plan = self.db.get_active_plan()
        if plan is None:
            return self.create_plan(start=today)
        if not any(day.status == "pending" for day in plan.days):
            revised, _reason = self.replan(start=today)
            return revised
        pending = [day for day in plan.days if day.status == "pending"]
        policy = plan.policy if plan.policy in {"shrink", "stretch", "steady"} else "steady"
        drafts = build_week(
            self.db.list_scores(),
            profile.daily_minutes,
            policy=policy,
            carry=self._learner_carry(),
            weights=self._weights(today),
            open_cursor=self._open_cursor(),
        )
        self._apply_drafts(pending, drafts, profile.daily_minutes)
        if plan.daily_minutes != profile.daily_minutes:
            self.db.set_plan_minutes(plan.id, profile.daily_minutes)
        updated = self.db.get_active_plan()
        assert updated is not None
        return updated

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
            self.practice_bank(),
            selected,
            prior=self.db.ability_map(),
            weights=self._weights(today),
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
        today = start or date.today()
        drafts = build_week(
            scores,
            profile.daily_minutes,
            policy="steady",
            carry=self._learner_carry(),
            weights=self._weights(today),
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
        carry = _merge(
            self.db.due_topics(start_on.isoformat()),
            unfinished_focuses(current),
            self._learner_carry(),
        )
        drafts = build_week(
            self.db.list_scores(),
            minutes,
            policy=policy,
            carry=carry,
            weights=self._weights(start_on),
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

    def practice_star(
        self,
        sections: dict[str, str],
        *,
        item_id: str | None = None,
        seed: int | None = None,
        llm: str = "offline",
        lang: str = "zh",
        opener=None,
    ) -> StarReport:
        """Score one behavioral story. Does not change the knowledge plan."""
        self.require_profile()
        return run_star_session(
            self.db,
            sections,
            item_id=item_id,
            seed=seed,
            llm=llm,
            lang=lang,
            opener=opener,
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
            carry=self._learner_carry(),
            weights=self._weights(research=False),
            open_cursor=self._open_cursor(),
        )
        self._apply_drafts(pending, drafts, plan.daily_minutes)

    def _save_paste(self, kind: str, text: str, *, llm: str, opener) -> None:
        if kind not in SOURCE_LABELS:
            raise ValueError("paste kind must be resume, jd, or notes")
        skills: list[tuple[str, str]] = []
        if text.strip():
            preview = prepare_paste(
                text,
                label=SOURCE_LABELS[kind],
                max_skills=6,
                max_items=1,
                llm=llm,
                opener=opener,
            )
            skills = [(skill.name, skill.topic) for skill in preview.skills]
        self.db.replace_learner_source(kind, SOURCE_LABELS[kind], skills)

    def _learner_carry(self) -> list[str]:
        model = self.db.get_learner()
        if model is None:
            return []
        return plan_carry(self.db.list_scores(), model.self_weak, model.topics())

    def _apply_drafts(self, pending: list[PlanDay], drafts: list, minutes: int) -> None:
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
                if day.minutes != minutes:
                    self.db.update_plan_day(
                        day.id,
                        day.focus,
                        minutes,
                        day.objective,
                        day.acceptance_criteria,
                    )
                continue
            self.db.update_plan_day(
                day.id,
                draft.focus,
                minutes,
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

    def practice_bank(self) -> QuestionBank:
        """Local bank plus accepted research drafts. Empty research leaves the bank unchanged."""
        drafts = self.db.load_draft_questions()
        if not drafts:
            return self.bank
        by_id = {question.id: question for question in self.bank.questions}
        for question in drafts:
            by_id[question.id] = question
        return QuestionBank(tuple(by_id.values()))

    def preview_paste(
        self,
        text: str,
        *,
        label: str = "paste",
        max_skills: int = 6,
        max_items: int = 5,
        on: date | None = None,
        llm: str = "offline",
        opener=None,
    ) -> ResearchPreview:
        self.require_profile()
        return prepare_paste(
            text,
            label=label,
            max_skills=max_skills,
            max_items=max_items,
            today=on,
            llm=llm,
            opener=opener,
        )

    def preview_query(
        self,
        query: str,
        *,
        max_skills: int = 6,
        max_items: int = 5,
        on: date | None = None,
        opener=None,
        search=None,
    ) -> ResearchPreview:
        self.require_profile()
        return prepare_query(
            query,
            max_skills=max_skills,
            max_items=max_items,
            today=on,
            opener=opener,
            search=search,
        )

    def accept_research(self, preview: ResearchPreview, on: date | None = None) -> int:
        """Write an already confirmed preview. Rejected previews must not call this."""
        if not preview.skills or not preview.items:
            raise ValueError("nothing to save")
        today = on or date.today()
        session_id = self.db.save_research(
            preview.label,
            [(source.url, source.title) for source in preview.sources],
            [(skill.name, skill.topic) for skill in preview.skills],
            [],
            [
                {
                    "topic": topic,
                    "boost": BOOST,
                    "starts_on": today.isoformat(),
                    "full_until": (today + timedelta(days=FULL_DAYS)).isoformat(),
                    "expires_on": (today + timedelta(days=EXPIRE_DAYS)).isoformat(),
                }
                for topic in preview.topics
            ],
        )
        items = draft_items(list(preview.skills), limit=len(preview.items), session_key=str(session_id))
        self.db.save_research_items(session_id, items)
        self._nudge_next_focus(preview.topics[0], today)
        return session_id

    def _nudge_next_focus(self, topic: str, today: date) -> None:
        """Point the next pending focus day at the research topic. Leave the other days."""
        plan = self.db.get_active_plan()
        if plan is None:
            return
        weak = {
            score.topic
            for score in self.db.list_scores()
            if is_weak_evidence(score.answered, score.correct, score.credit)
        }
        pending = [
            day
            for day in plan.days
            if day.status == "pending" and not day.focus.startswith(("review:", "mock:"))
        ]
        if not pending:
            return
        day = pending[0]
        current = focus_topics(day.focus)[0]
        if current in weak or current == topic:
            return
        ability = next((score.ability for score in self.db.list_scores() if score.topic == topic), 3.0)
        draft = single_focus_day(topic, day.minutes, ability, self._open_cursor())
        self.db.update_plan_day(day.id, topic, day.minutes, draft.objective, draft.acceptance_criteria)

    def _weights(self, on: date | None = None, *, research: bool = True) -> dict[str, float]:
        table = topic_weights(self.require_profile().target_id)
        if not research:
            return table
        today = on or date.today()
        for row in self.db.bias_rows():
            extra = boost_on(
                today,
                date.fromisoformat(row["starts_on"]),
                date.fromisoformat(row["full_until"]),
                date.fromisoformat(row["expires_on"]),
                float(row["boost"]),
            )
            topic = row["topic"]
            if extra > 0 and topic in table:
                table[topic] = table[topic] + extra
        return table


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
