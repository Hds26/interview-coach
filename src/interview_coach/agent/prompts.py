"""Coach prompts. Offline mode fills these templates from local tool results."""

from __future__ import annotations

SYSTEM_PROMPT = """You are an interview study coach.
Use the local tools to read the learner profile, topic scores, active 7-day plan, and progress.
Recommend the next block using the plan's minutes and acceptance criteria.
Do not invent scores, dates, or criteria that the tools did not return.
When a tool returns an error, tell the learner the next command to run.
Stay concrete: one focus, the minute budget, and the measurable check.
"""


def render_tool_reply(tool_name: str, payload: dict) -> str:
    if payload.get("error"):
        return f"{payload['error']} Next: interview-coach profile init --name YourName --role backend"
    if tool_name == "get_today":
        criteria = "\n".join(f"- {item}" for item in payload.get("acceptance_criteria", []))
        return (
            f"Today is day {payload['day_index']} ({payload['date']}): {payload['label']}.\n"
            f"Budget: {payload['minutes']} minutes.\n"
            f"Objective: {payload['objective']}\n"
            f"Acceptance criteria:\n{criteria}"
        )
    if tool_name == "get_progress":
        return (
            f"Plan v{payload['version']}: {payload['days_done']} done, "
            f"{payload['days_missed']} missed, {payload['days_pending']} pending.\n"
            f"Reported completion: {payload['reported_completion']}. "
            f"Quiz accuracy: {payload['quiz_accuracy']}.\n"
            f"Minutes logged: {payload['minutes_spent']}."
        )
    if tool_name == "get_plan":
        lines = [
            f"Plan v{payload['version']} ({payload['policy']}), {payload['daily_minutes']} min/day, "
            f"starts {payload['start_date']}."
        ]
        for day in payload["days"]:
            lines.append(
                f"Day {day['day_index']} [{day['status']}] {day['label']} — {day['minutes']} min. "
                f"Check: {day['acceptance_criteria'][0]}"
            )
        return "\n".join(lines)
    if tool_name == "get_scores":
        lines = ["Topic scores (weakest first):"]
        for score in payload["scores"]:
            lines.append(
                f"- {score['label']}: ability {score['ability']}, "
                f"mastery {score['mastery']}, {score['correct']}/{score['answered']}"
            )
        if payload.get("weakest"):
            lines.append("Spend the next block on " + ", ".join(payload["weakest"]) + ".")
        return "\n".join(lines)
    if tool_name == "get_profile":
        return (
            f"Profile {payload['name']}, role {payload['target_role']}, level {payload['level']}, "
            f"{payload['daily_minutes']} minutes/day."
        )
    return "No local tool result to render."
