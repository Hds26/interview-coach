"""Scripted end-to-end session. No prompts and no network."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from interview_coach.app import CoachApp, overall_mastery
from interview_coach.assessment.bank import display_topic
from interview_coach.assessment.scoring import confidence_percent, mastery_percent
from interview_coach.db import Database
from interview_coach.models import Question

MISS_TOPICS = {"databases", "system_design", "networking"}


def scripted_choice(question: Question) -> int | str:
    if question.kind == "open":
        if question.topic in MISS_TOPICS:
            return "unsure"
        return " ".join(point.keywords[0] for point in question.rubric if point.keywords)
    if question.topic in MISS_TOPICS:
        return (question.answer + 1) % len(question.choices)
    return question.answer


def run_demo(db_path: Path, start: date | None = None) -> int:
    if db_path.exists():
        db_path.unlink()
    app = CoachApp(Database(db_path))
    profile = app.init_profile("demo-learner", "backend", "mid", 30)
    result = app.assess(12, None, scripted_choice)
    plan_start = start or date(2026, 1, 5)
    plan = app.create_plan(start=plan_start)
    app.log_day(1, 30, True, 8, 10, "demo day 1")
    app.log_day(2, 28, True, 7, 10, "demo day 2")
    app.log_day(3, 0, False, notes="missed")
    app.log_day(4, 0, False, notes="missed")
    progress = app.progress()
    revised, reason = app.replan(start=plan_start + timedelta(days=7))
    advice = app.agent("offline").ask("What should I study today?")

    print("Interview Study Coach demo")
    print(f"Database: {db_path}")
    print("LLM: offline (no API key)")
    print()
    print("Profile")
    print(f"  name: {profile.name}")
    print(f"  role: {profile.target_role}")
    print(f"  target: {profile.target_id}")
    print(f"  level: {profile.level}")
    print(f"  daily_minutes: {profile.daily_minutes}")
    print()
    print("Assessment")
    print(f"  questions: {len(result.answers)}")
    print(f"  correct: {result.correct_count}")
    print(f"  overall_mastery: {overall_mastery(result.scores)}%")
    for score in sorted(result.scores, key=lambda item: (item.ability, item.topic)):
        if score.answered == 0:
            continue
        print(
            f"  {score.topic:16} ability={score.ability:.2f}  "
            f"mastery={mastery_percent(score.ability):3d}%  "
            f"confidence={confidence_percent(score.information):3d}%  "
            f"correct={score.correct}/{score.answered}"
        )
    print()
    _print_plan(plan)
    print()
    print("Progress before replan")
    print(f"  reported_completion: {round(progress.reported_completion * 100)}%")
    print(f"  quiz_accuracy: {round(progress.quiz_accuracy * 100)}%")
    print(
        f"  done={progress.days_done} missed={progress.days_missed} pending={progress.days_pending}"
    )
    print()
    print("Replan")
    print(f"  policy: {revised.policy}")
    print(f"  daily_minutes: {revised.daily_minutes}")
    print(f"  plan: v{revised.version}")
    print(f"  reason: {reason}")
    print()
    _print_plan(revised)
    print()
    print("Coach")
    print(advice)
    print()
    print("Demo complete")
    app.db.close()
    return 0


def _print_plan(plan) -> None:
    print(
        f"7-day plan v{plan.version}  policy={plan.policy}  "
        f"{plan.daily_minutes} min/day  start={plan.start_date}"
    )
    for day in plan.days:
        print(
            f"  Day {day.day_index}  {day.day_date}  {display_topic(day.focus)}  "
            f"{day.minutes} min  [{day.status}]"
        )
        print(f"    objective: {day.objective}")
        for criterion in day.acceptance_criteria:
            print(f"    acceptance: {criterion}")
