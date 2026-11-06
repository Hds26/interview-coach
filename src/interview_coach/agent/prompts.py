"""Coach prompts. Offline mode fills these templates from local tool results."""

from __future__ import annotations

from interview_coach.coach_text import (
    render_error,
    render_plan,
    render_profile,
    render_progress,
    render_scores,
    render_today,
)

SYSTEM_PROMPT = """You are an interview study coach.
Use the local tools before you answer. They are the only source of profile, scores, plan, and progress.
Reply in short sentences. Lead with what to do in the next session, about 30 minutes.
Then give 2 or 3 acceptance checks. Name weak areas in plain language.
Do not open with raw ability, mastery, or confidence numbers. If you mention a number, it must be one the tools returned, and it comes after the action.
Never invent scores, dates, minutes, or criteria.
When a tool returns an error, tell the learner the next command to run.
Reply in Chinese unless the user explicitly asks for English.
Open answers are scored locally. Do not grade them yourself.
"""


def render_tool_reply(tool_name: str, payload: dict, lang: str = "zh") -> str:
    if payload.get("error"):
        return render_error(str(payload["error"]), lang)
    if tool_name == "get_today":
        return render_today(payload, lang)
    if tool_name == "get_progress":
        return render_progress(payload, lang)
    if tool_name == "get_plan":
        return render_plan(payload, lang)
    if tool_name == "get_scores":
        return render_scores(payload, lang)
    if tool_name == "get_profile":
        return render_profile(payload, lang)
    if lang == "zh":
        return "没有本地结果。下一步：interview-coach today"
    return "No local result. Next: interview-coach today"
