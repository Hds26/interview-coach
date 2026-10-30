"""Local tools the coach can call. They read SQLite state and never touch the network."""

from __future__ import annotations

import json
from typing import Callable

from interview_coach.assessment.bank import display_topic
from interview_coach.assessment.scoring import mastery_percent

ToolHandler = Callable[[dict], dict]


def tool_specs() -> list[dict]:
    def spec(name: str, description: str) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }

    return [
        spec("get_profile", "Read the learner profile, including daily minutes."),
        spec("get_scores", "Read topic ability scores, weakest first."),
        spec("get_plan", "Read the active 7-day plan and acceptance criteria."),
        spec("get_progress", "Read completion rate, quiz accuracy, and logged minutes."),
        spec("get_today", "Read the next pending study block and its acceptance criteria."),
    ]


class ToolRegistry:
    def __init__(self, handlers: dict[str, ToolHandler]) -> None:
        self.handlers = handlers

    def dispatch(self, name: str, arguments: dict | str | None) -> str:
        args = _coerce(arguments)
        handler = self.handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool {name}"})
        return json.dumps(handler(args), ensure_ascii=False)


def _coerce(arguments: dict | str | None) -> dict:
    if arguments is None or arguments == "":
        return {}
    if isinstance(arguments, str):
        return json.loads(arguments or "{}")
    return dict(arguments)


def build_registry(app: object) -> ToolRegistry:
    def require_profile() -> dict | None:
        profile = app.db.get_profile()  # type: ignore[attr-defined]
        if profile is None:
            return {"error": "No profile yet."}
        return None

    def get_profile(_: dict) -> dict:
        missing = require_profile()
        if missing:
            return missing
        profile = app.db.get_profile()  # type: ignore[attr-defined]
        return {
            "name": profile.name,
            "target_role": profile.target_role,
            "level": profile.level,
            "daily_minutes": profile.daily_minutes,
        }

    def get_scores(_: dict) -> dict:
        missing = require_profile()
        if missing:
            return missing
        scores = sorted(app.db.list_scores(), key=lambda item: (item.ability, item.topic))  # type: ignore[attr-defined]
        rendered = [
            {
                "topic": score.topic,
                "label": display_topic(score.topic),
                "ability": round(score.ability, 2),
                "mastery": f"{mastery_percent(score.ability)}%",
                "answered": score.answered,
                "correct": score.correct,
            }
            for score in scores
        ]
        weakest = [item["label"] for item in rendered[:3]]
        return {"scores": rendered, "weakest": weakest}

    def get_plan(_: dict) -> dict:
        plan = app.db.get_active_plan()  # type: ignore[attr-defined]
        if plan is None:
            return {"error": "No active plan yet. Run interview-coach plan."}
        return _plan_payload(plan)

    def get_progress(_: dict) -> dict:
        plan = app.db.get_active_plan()  # type: ignore[attr-defined]
        if plan is None:
            return {"error": "No active plan yet. Run interview-coach plan."}
        progress = app.progress()  # type: ignore[attr-defined]
        return {
            "version": progress.version,
            "days_done": progress.days_done,
            "days_missed": progress.days_missed,
            "days_pending": progress.days_pending,
            "reported_completion": f"{round(progress.reported_completion * 100)}%",
            "quiz_accuracy": f"{round(progress.quiz_accuracy * 100)}%",
            "minutes_spent": progress.minutes_spent,
        }

    def get_today(_: dict) -> dict:
        plan = app.db.get_active_plan()  # type: ignore[attr-defined]
        if plan is None:
            return {"error": "No active plan yet. Run interview-coach plan."}
        pending = [day for day in plan.days if day.status == "pending"]
        day = pending[0] if pending else plan.days[0]
        return {
            "day_index": day.day_index,
            "date": day.day_date,
            "focus": day.focus,
            "label": display_topic(day.focus),
            "minutes": day.minutes,
            "objective": day.objective,
            "acceptance_criteria": list(day.acceptance_criteria),
            "status": day.status,
        }

    return ToolRegistry(
        {
            "get_profile": get_profile,
            "get_scores": get_scores,
            "get_plan": get_plan,
            "get_progress": get_progress,
            "get_today": get_today,
        }
    )


def _plan_payload(plan: object) -> dict:
    return {
        "version": plan.version,  # type: ignore[attr-defined]
        "policy": plan.policy,  # type: ignore[attr-defined]
        "daily_minutes": plan.daily_minutes,  # type: ignore[attr-defined]
        "start_date": plan.start_date,  # type: ignore[attr-defined]
        "days": [
            {
                "day_index": day.day_index,
                "date": day.day_date,
                "focus": day.focus,
                "label": display_topic(day.focus),
                "minutes": day.minutes,
                "status": day.status,
                "objective": day.objective,
                "acceptance_criteria": list(day.acceptance_criteria),
            }
            for day in plan.days  # type: ignore[attr-defined]
        ],
    }
