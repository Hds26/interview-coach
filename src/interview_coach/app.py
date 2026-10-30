"""Facade used by the CLI, demo, and agent tools."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from interview_coach.agent.coach import CoachAgent
from interview_coach.agent.llm import LLM, build_llm
from interview_coach.agent.tools import build_registry
from interview_coach.assessment.bank import QuestionBank
from interview_coach.assessment.engine import AdaptiveAssessment
from interview_coach.assessment.scoring import mastery_percent
from interview_coach.db import Database
from interview_coach.models import AssessmentResult, Profile, Progress, StudyPlan, TopicScore
from interview_coach.planner.planner import adjusted_minutes, build_week, choose_policy, explain_policy
from interview_coach.profile.service import normalize_profile, prior_ability
from interview_coach.tracker.tracker import summarize, unfinished_focuses


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
    ) -> Profile:
        incoming = normalize_profile(name, target_role, level, daily_minutes)
        return self.db.save_profile(
            incoming.name,
            incoming.target_role,
            incoming.level,
            incoming.daily_minutes,
            prior_ability(incoming.level),
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
    ) -> AssessmentResult:
        self.require_profile()
        selected = list(topics) if topics else list(self.bank.topics())
        if question_count < 1:
            raise ValueError("question count must be at least 1")
        engine = AdaptiveAssessment(self.bank, selected, prior=self.db.ability_map())
        for _ in range(question_count):
            question = engine.next_question()
            if question is None:
                break
            choice = choose(question)
            engine.submit(question.id, int(choice))
        if not engine.answers:
            raise RuntimeError("the question bank produced no items")
        payload = [
            {
                "question_id": answer.question_id,
                "topic": answer.topic,
                "difficulty": answer.difficulty,
                "choice_index": answer.choice_index,
                "correct": answer.correct,
                "ability_after": answer.ability_after,
            }
            for answer in engine.answers
        ]
        assessment_id = self.db.save_assessment(payload, engine.ability)
        scores = tuple(self.db.list_scores())
        return AssessmentResult(assessment_id, tuple(engine.answers), scores)

    def create_plan(self, start: date | None = None, force: bool = False) -> StudyPlan:
        profile = self.require_profile()
        if self.db.get_active_plan() is not None and not force:
            raise RuntimeError("an active plan already exists; use replan or plan --force")
        scores = self.db.list_scores()
        drafts = build_week(scores, profile.daily_minutes, policy="steady")
        return self._store_plan(profile.daily_minutes, "initial", start or date.today(), drafts)

    def replan(self, start: date | None = None) -> tuple[StudyPlan, str]:
        profile = self.require_profile()
        current = self.db.get_active_plan()
        if current is None:
            raise LookupError("No plan yet. Run: interview-coach plan")
        progress = self.progress()
        policy = choose_policy(progress.reported_completion, progress.quiz_accuracy)
        minutes = adjusted_minutes(profile.daily_minutes, policy)
        drafts = build_week(
            self.db.list_scores(),
            minutes,
            policy=policy,
            carry=unfinished_focuses(current),
        )
        plan = self._store_plan(minutes, policy, start or date.today(), drafts)
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


def overall_mastery(scores: tuple[TopicScore, ...] | list[TopicScore], answered_only: bool = True) -> int:
    chosen = [score for score in scores if score.answered > 0] if answered_only else list(scores)
    if not chosen:
        chosen = list(scores)
    if not chosen:
        return 0
    return int(round(sum(mastery_percent(score.ability) for score in chosen) / len(chosen)))
