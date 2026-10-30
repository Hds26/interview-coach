"""Export the active week as Markdown or an iCalendar file. No network."""

from __future__ import annotations

from datetime import date, timedelta

from interview_coach.assessment.bank import display_topic
from interview_coach.models import StudyPlan


def export_markdown(plan: StudyPlan) -> str:
    lines = [
        f"# Interview study week v{plan.version}",
        "",
        f"- Policy: {plan.policy}",
        f"- Daily minutes: {plan.daily_minutes}",
        f"- Start: {plan.start_date}",
        "",
    ]
    for day in plan.days:
        lines.append(f"## Day {day.day_index} — {day.day_date} — {display_topic(day.focus)}")
        lines.append("")
        lines.append(f"- Status: {day.status}")
        lines.append(f"- Minutes: {day.minutes}")
        lines.append(f"- Objective: {day.objective}")
        lines.append("- Acceptance:")
        for criterion in day.acceptance_criteria:
            lines.append(f"  - {criterion}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_ics(plan: StudyPlan) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//interview-coach//EN",
        "CALSCALE:GREGORIAN",
    ]
    for day in plan.days:
        start = date.fromisoformat(day.day_date)
        end = start + timedelta(days=1)
        summary = f"Day {day.day_index}: {display_topic(day.focus)} ({day.minutes} min)"
        description = "\n".join([day.objective, *day.acceptance_criteria])
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:interview-coach-plan{plan.id}-day{day.day_index}@local",
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
                f"SUMMARY:{_ics_escape(summary)}",
                f"DESCRIPTION:{_ics_escape(description)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )
