"""Short coach copy. Chinese is the default; English is ``--lang en``."""

from __future__ import annotations

import re

from interview_coach.assessment.bank import display_topic
from interview_coach.models import PlanDay, TopicScore
from interview_coach.planner.acceptance import OPEN_RE, QUIZ_RE
from interview_coach.planner.planner import focus_topics

ZH_TOPICS = {
    "arrays_hashing": "数组和哈希",
    "trees_graphs": "树和图",
    "complexity": "复杂度",
    "databases": "数据库",
    "networking": "网络",
    "python": "Python",
    "system_design": "系统设计",
    "concurrency": "并发",
}


def normalize_lang(lang: str | None, default: str = "zh") -> str:
    if not lang:
        return default
    lowered = lang.strip().lower()
    if lowered in {"zh", "cn", "chinese"}:
        return "zh"
    if lowered in {"en", "english"}:
        return "en"
    raise ValueError("lang must be zh or en")


def plain_topic(topic: str, lang: str) -> str:
    if lang != "zh":
        return display_topic(topic)
    labels = [ZH_TOPICS.get(part, part) for part in focus_topics(topic)]
    joined = "、".join(labels)
    if topic.startswith("review:"):
        return f"复习（{joined}）"
    if topic.startswith("mock:"):
        return f"模拟（{joined}）"
    return joined


def weak_labels(scores: list[TopicScore] | tuple[TopicScore, ...], lang: str, limit: int = 3) -> list[str]:
    ordered = sorted(scores, key=lambda item: (item.ability, item.topic))
    return [plain_topic(item.topic, lang) for item in ordered[:limit]]


def coach_bullets(criteria: tuple[str, ...] | list[str], lang: str, limit: int = 3) -> list[str]:
    ranked = sorted(criteria, key=lambda raw: (0 if _measurable(raw) else 1))
    bullets: list[str] = []
    for raw in ranked:
        bullets.append(_bullet(raw, lang))
        if len(bullets) == limit:
            break
    return bullets


def intro_lines(
    day: PlanDay,
    lang: str,
    *,
    created_plan: bool = False,
    replanned: bool = False,
) -> list[str]:
    label = plain_topic(day.focus, lang)
    bullets = coach_bullets(day.acceptance_criteria, lang)
    if lang == "zh":
        lines: list[str] = []
        if replanned:
            lines.append("上一周没有待完成的日子了，已按完成情况排好下一周。")
        elif created_plan:
            lines.append("已按当前水平排好 7 天，从最弱的一块开始。")
        lines.append(f"接下来 {day.minutes} 分钟：第 {day.day_index} 天，只练{label}。")
        lines.append("做到这几件就算完成：")
        lines.extend(f"- {bullet}" for bullet in bullets)
        return lines
    lines = []
    if replanned:
        lines.append("The week had nothing left, so the next week is ready.")
    elif created_plan:
        lines.append("A 7-day plan is ready, starting from the weakest topic.")
    lines.append(f"Next {day.minutes} minutes: day {day.day_index}, {label} only.")
    lines.append("Done when:")
    lines.extend(f"- {bullet}" for bullet in bullets)
    return lines


def format_missing(missing: tuple[str, ...] | list[str], lang: str) -> str:
    parts = [_one_missing(item, lang) for item in missing]
    if not parts:
        return ""
    if lang == "zh":
        return "还差：" + "；".join(parts) + "。"
    return "Still missing: " + "; ".join(parts) + "."


def no_profile_text(lang: str) -> str:
    if lang == "zh":
        return "还没有学习画像。\n下一步：interview-coach profile init --name 你的名字 --role 后端"
    return "No profile yet.\nNext: interview-coach profile init --name YourName --role backend"


def closing_lines(
    *,
    lang: str,
    logged: bool,
    day_index: int | None,
    focus: str,
    missing: tuple[str, ...],
    next_day: PlanDay | None,
    days_done: int,
    streak_goal: int,
    weak: list[str],
) -> list[str]:
    label = plain_topic(focus, lang) if focus else ""
    if lang == "zh":
        if logged and day_index is not None:
            lines = [f"今天已记入完成：第 {day_index} 天（{label}）。"]
            if next_day is not None:
                nxt = plain_topic(next_day.focus, lang)
                lines.append(
                    f"接下来：第 {next_day.day_index} 天练{nxt}，大约 {next_day.minutes} 分钟。"
                    f"本周已完成 {days_done} 天，连续目标 {streak_goal} 天。"
                )
            else:
                lines.append("这 7 天都有记录了。明天再运行 interview-coach today 会排下一周。")
            if weak:
                lines.append("目前较薄弱：" + "、".join(weak) + "。")
            return lines[:3]
        lines = ["今天先不记完成。"]
        detail = format_missing(missing, lang)
        if detail:
            lines.append(detail)
        lines.append("接下来：再运行 interview-coach today，把这一天补完。")
        return lines[:3]
    if logged and day_index is not None:
        lines = [f"Logged day {day_index} ({label}) as done."]
        if next_day is not None:
            nxt = plain_topic(next_day.focus, lang)
            lines.append(
                f"Next: day {next_day.day_index}, {nxt}, about {next_day.minutes} minutes. "
                f"{days_done} done this week, streak goal {streak_goal}."
            )
        else:
            lines.append("This week is fully logged. interview-coach today will plan the next one.")
        if weak:
            lines.append("Weaker right now: " + ", ".join(weak) + ".")
        return lines[:3]
    lines = ["Not logged yet."]
    detail = format_missing(missing, lang)
    if detail:
        lines.append(detail)
    lines.append("Next: run interview-coach today again and finish this day.")
    return lines[:3]


def render_today(payload: dict, lang: str) -> str:
    minutes = payload.get("minutes", 30)
    day_index = payload.get("day_index", 1)
    focus = str(payload.get("focus") or "")
    label = plain_topic(focus, lang) if focus else str(payload.get("label") or "")
    bullets = coach_bullets(payload.get("acceptance_criteria") or [], lang)
    weak = _payload_weak(payload, lang)
    if lang == "zh":
        lines = [f"接下来 {minutes} 分钟：第 {day_index} 天，只练{label}。", "做到这几件就算完成："]
        lines.extend(f"- {bullet}" for bullet in bullets)
        if weak:
            lines.append("目前较薄弱：" + "、".join(weak) + "。")
        return "\n".join(lines)
    lines = [f"Next {minutes} minutes: day {day_index}, {label} only.", "Done when:"]
    lines.extend(f"- {bullet}" for bullet in bullets)
    if weak:
        lines.append("Weaker right now: " + ", ".join(weak) + ".")
    return "\n".join(lines)


def render_scores(payload: dict, lang: str) -> str:
    minutes = payload.get("daily_minutes", 30)
    weak = _payload_weak(payload, lang)
    first = weak[0] if weak else ("最弱的一块" if lang == "zh" else "the weakest topic")
    if lang == "zh":
        lines = [f"接下来 {minutes} 分钟：先补{first}。"]
        if weak:
            lines.append("目前较薄弱：" + "、".join(weak) + "。")
        lines.append("先把这一块讲清楚，再看下一题。")
        return "\n".join(lines)
    lines = [f"Next {minutes} minutes: start with {first}."]
    if weak:
        lines.append("Weaker right now: " + ", ".join(weak) + ".")
    lines.append("Explain that topic once before the next question.")
    return "\n".join(lines)


def render_progress(payload: dict, lang: str) -> str:
    version = payload.get("version", 1)
    done = payload.get("days_done", 0)
    missed = payload.get("days_missed", 0)
    pending = payload.get("days_pending", 0)
    minutes = payload.get("minutes_spent", 0)
    if lang == "zh":
        return (
            f"计划 v{version}：完成 {done} 天，错过 {missed} 天，还剩 {pending} 天。\n"
            f"已记录 {minutes} 分钟。完成得多就保持，漏得多就缩小范围。"
        )
    return (
        f"Plan v{version}: {done} done, {missed} missed, {pending} still open.\n"
        f"{minutes} minutes logged. Keep going if most days are done; narrow the week if many were missed."
    )


def render_plan(payload: dict, lang: str) -> str:
    version = payload.get("version", 1)
    minutes = payload.get("daily_minutes", 30)
    days = payload.get("days") or []
    if lang == "zh":
        lines = [f"计划 v{version}，每天大约 {minutes} 分钟。"]
        for day in days[:3]:
            label = plain_topic(str(day.get("focus") or ""), lang)
            lines.append(f"第 {day.get('day_index')} 天：{label}。")
        if len(days) > 3:
            lines.append("其余几天用 interview-coach progress 看。")
        return "\n".join(lines)
    lines = [f"Plan v{version}, about {minutes} minutes a day."]
    for day in days[:3]:
        label = plain_topic(str(day.get("focus") or ""), lang)
        lines.append(f"Day {day.get('day_index')}: {label}.")
    if len(days) > 3:
        lines.append("See the rest with interview-coach progress.")
    return "\n".join(lines)


def render_profile(payload: dict, lang: str) -> str:
    name = payload.get("name", "")
    minutes = payload.get("daily_minutes", 30)
    streak = payload.get("streak_goal", 5)
    if lang == "zh":
        return f"{name}，每天大约 {minutes} 分钟，连续目标 {streak} 天。直接运行 interview-coach today。"
    return f"{name}, about {minutes} minutes a day, streak goal {streak}. Run interview-coach today."


def render_error(message: str, lang: str) -> str:
    text = message.lower()
    if "profile" in text or "画像" in message:
        return no_profile_text(lang)
    if lang == "zh":
        return "还没有今天的计划。\n下一步：interview-coach today"
    return "No plan for today yet.\nNext: interview-coach today"


def _payload_weak(payload: dict, lang: str) -> list[str]:
    weak = payload.get("weakest") or []
    labels: list[str] = []
    for item in weak:
        if isinstance(item, dict):
            topic = str(item.get("topic") or "")
            labels.append(plain_topic(topic, lang) if topic else str(item.get("label") or ""))
        else:
            labels.append(str(item))
    return [label for label in labels if label]


def _measurable(raw: str) -> bool:
    return OPEN_RE.search(raw) is not None or QUIZ_RE.search(raw) is not None or "minute" in raw.lower()


def _bullet(raw: str, lang: str) -> str:
    opened = OPEN_RE.search(raw)
    quiz = QUIZ_RE.search(raw)
    if opened and quiz:
        question_id, need, total = opened.group(1), quiz.group(1), quiz.group(2)
        if lang == "zh":
            return f"开放题 {question_id}：用自己的话回答，至少命中 {need}/{total} 个要点。"
        return f"Open item {question_id}: hit at least {need}/{total} rubric points in your own words."
    if quiz:
        need, total = quiz.group(1), quiz.group(2)
        if lang == "zh":
            return f"练习至少对 {need}/{total}。"
        return f"Score at least {need}/{total}."
    minutes = _minutes(raw)
    if minutes is not None:
        if lang == "zh":
            return f"一次专心学 {minutes} 分钟。"
        return f"Spend {minutes} minutes in one sitting."
    if lang == "zh":
        return "用一两句话记下这次的缺口。"
    return "Write down the gap from this session."


def _minutes(raw: str) -> str | None:
    match = re.search(r"(\d+)[- ]minute|\b(\d+) (?:focused )?minutes\b", raw, re.IGNORECASE)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _one_missing(code: str, lang: str) -> str:
    parts = code.split(":")
    kind = parts[0]
    if kind == "items" and len(parts) == 3:
        got, need = parts[1], parts[2]
        if lang == "zh":
            return f"这次只有 {got} 题，至少做 {need} 题"
        return f"only {got} items, need at least {need}"
    if kind == "quiz" and len(parts) == 3:
        got, need = parts[1], parts[2]
        if lang == "zh":
            return f"这次 {got}，需要至少 {need}"
        return f"this session was {got}, need at least {need}"
    if kind == "rubric" and len(parts) == 5:
        question_id, hits, need, total = parts[1], parts[2], parts[3], parts[4]
        if lang == "zh":
            return f"开放题 {question_id} 命中 {hits}/{total}，需要 {need}/{total}"
        return f"open item {question_id} hit {hits}/{total}, need {need}/{total}"
    if lang == "zh":
        return "这一天没有可自动核对的标准"
    return "this day has no scored check"
