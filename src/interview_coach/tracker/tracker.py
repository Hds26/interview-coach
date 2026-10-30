"""Progress math used by replan. Completion uses days the learner has reported."""

from __future__ import annotations

from interview_coach.models import PlanDay, Progress, StudyLog, StudyPlan


def reported_completion_rate(days: list[PlanDay] | tuple[PlanDay, ...]) -> float:
    reported = [day for day in days if day.status in {"done", "missed"}]
    if not reported:
        return 0.0
    done = sum(1 for day in reported if day.status == "done")
    return done / len(reported)


def mean_quiz_accuracy(logs: list[StudyLog] | tuple[StudyLog, ...]) -> float:
    ratios = [
        log.quiz_correct / log.quiz_total
        for log in logs
        if log.quiz_total and log.quiz_correct is not None
    ]
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)


def summarize(plan: StudyPlan, logs: list[StudyLog] | tuple[StudyLog, ...]) -> Progress:
    days_done = sum(1 for day in plan.days if day.status == "done")
    days_missed = sum(1 for day in plan.days if day.status == "missed")
    days_pending = sum(1 for day in plan.days if day.status == "pending")
    return Progress(
        plan_id=plan.id,
        version=plan.version,
        days_total=len(plan.days),
        days_done=days_done,
        days_missed=days_missed,
        days_pending=days_pending,
        reported_completion=reported_completion_rate(plan.days),
        quiz_accuracy=mean_quiz_accuracy(logs),
        minutes_spent=sum(log.minutes_spent for log in logs),
    )


def unfinished_focuses(plan: StudyPlan) -> list[str]:
    carried: list[str] = []
    for day in plan.days:
        if day.status == "done" or day.focus.startswith(("review:", "mock:")):
            continue
        if day.focus not in carried:
            carried.append(day.focus)
    return carried
