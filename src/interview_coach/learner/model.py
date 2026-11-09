"""One learner model for onboarding. It orders the week; it does not invent scores.

Answer evidence comes first. A topic answered at full credit is not pulled
forward by a self-rating or a pasted resume / JD tag. Self-rated topics come
next, then topics mapped from a paste. The original note is never stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from interview_coach.assessment.bank import TOPICS, ZH_TOPICS, chinese_subject
from interview_coach.assessment.scoring import is_weak_evidence
from interview_coach.coach_text import coach_bullets
from interview_coach.models import StudyPlan, TopicScore
from interview_coach.planner.planner import focus_topics
from interview_coach.profile.service import normalize_kinds
from interview_coach.research.extract import RULES

SOURCE_KINDS = ("resume", "jd", "notes")
SOURCE_LABELS = {"resume": "简历", "jd": "职位说明", "notes": "笔记"}
STYLE_LABELS = {"mcq": "选择题", "open": "开放题", "mcq,open": "选择题和开放题"}
MAX_WEAK = 5


@dataclass(frozen=True)
class LearnerSkill:
    id: int
    source_id: int
    kind: str
    name: str
    topic: str


@dataclass(frozen=True)
class LearnerModel:
    minutes_per_day: int
    practice_style: str
    self_weak: tuple[str, ...]
    skills: tuple[LearnerSkill, ...]

    def topics(self, kind: str | None = None) -> tuple[str, ...]:
        order = {name: index for index, name in enumerate(SOURCE_KINDS)}
        chosen = [skill for skill in self.skills if kind is None or skill.kind == kind]
        chosen.sort(key=lambda skill: (order.get(skill.kind, 9), skill.source_id, skill.id))
        topics: list[str] = []
        for skill in chosen:
            if skill.topic not in topics:
                topics.append(skill.topic)
        return tuple(topics)


_STYLE = {
    "1": "mcq",
    "mcq": "mcq",
    "选择题": "mcq",
    "选择": "mcq",
    "2": "open",
    "open": "open",
    "开放题": "open",
    "开放": "open",
    "简答": "open",
    "3": "mcq,open",
    "both": "mcq,open",
    "都要": "mcq,open",
    "都练": "mcq,open",
    "mcq,open": "mcq,open",
    "open,mcq": "mcq,open",
}


def parse_style(raw: str) -> str:
    key = raw.strip().casefold().replace(" ", "")
    if key in _STYLE:
        return _STYLE[key]
    return normalize_kinds(raw)


def parse_weak(raw: str) -> list[str]:
    """Map a short self-rating onto local topic ids. Empty means none."""
    topics: list[str] = []
    for piece in re.split(r"[,，、]", raw):
        token = piece.strip()
        if not token:
            continue
        topic = topic_from_token(token)
        if topic not in topics:
            topics.append(topic)
    if len(topics) > MAX_WEAK:
        raise ValueError(f"list at most {MAX_WEAK} weak topics")
    return topics


def resolve_weak(raw: str | None, existing: tuple[str, ...] | None) -> list[str] | None:
    """None keeps a saved baseline. A first run with no flag stores an empty list."""
    if raw is None:
        if existing is None:
            return []
        return None
    return parse_weak(raw)


def topic_from_token(token: str) -> str:
    raw = token.strip()
    if not raw:
        raise ValueError("weak topic is empty")
    folded = raw.casefold()
    if folded in TOPICS:
        return folded
    for topic, label in ZH_TOPICS.items():
        if raw == label:
            return topic
    for topic, label in TOPICS.items():
        if folded == label.casefold():
            return topic
    for rule in RULES:
        names = {rule.name.casefold(), *(needle.casefold() for needle in rule.needles)}
        if folded in names or raw in rule.needles:
            return rule.topic
    known = "、".join(ZH_TOPICS.values())
    raise ValueError(f"unknown topic {token}; choose one of: {known}")


def plan_carry(
    scores: list[TopicScore] | tuple[TopicScore, ...],
    self_weak: list[str] | tuple[str, ...],
    source_topics: list[str] | tuple[str, ...],
) -> list[str]:
    """Evidence, then self-rating, then pasted tags. Full-credit topics stay out."""
    known = {score.topic for score in scores}
    evidenced = [score for score in scores if is_weak_evidence(score.answered, score.correct, score.credit)]
    evidenced.sort(key=lambda item: (item.ability, item.topic))
    strong = {
        score.topic
        for score in scores
        if score.answered > 0 and not is_weak_evidence(score.answered, score.correct, score.credit)
    }
    ordered = [score.topic for score in evidenced]
    for topic in list(self_weak) + list(source_topics):
        if topic not in known or topic in strong or topic in ordered:
            continue
        ordered.append(topic)
    return ordered


def evidence_leads(
    focus: str,
    scores: list[TopicScore] | tuple[TopicScore, ...],
    self_weak: tuple[str, ...],
    source_topics: tuple[str, ...],
) -> bool:
    primary = focus_topics(focus)[0]
    score = next((item for item in scores if item.topic == primary), None)
    if score is None or not is_weak_evidence(score.answered, score.correct, score.credit):
        return False
    return any(topic != primary for topic in (*self_weak, *source_topics))


def render_start(
    *,
    minutes: int,
    style: str,
    self_weak: tuple[str, ...],
    skills: tuple[LearnerSkill, ...],
    plan: StudyPlan,
    scores: list[TopicScore] | tuple[TopicScore, ...],
) -> str:
    style_label = STYLE_LABELS.get(style, style)
    lines = [
        "已记下学习画像。简历和职位说明的原文不会保存。",
        f"每天 {minutes} 分钟，练习方式：{style_label}。",
    ]
    if self_weak:
        names = "、".join(chinese_subject(topic) for topic in self_weak)
        lines.append(f"自评薄弱：{names}。这不是做题分数。")
    else:
        lines.append("没有填写自评薄弱。")
    for kind in SOURCE_KINDS:
        topics: list[str] = []
        for skill in skills:
            if skill.kind == kind and skill.topic not in topics:
                topics.append(skill.topic)
        if not topics:
            continue
        label = SOURCE_LABELS[kind]
        names = "、".join(chinese_subject(topic) for topic in topics)
        lines.append(f"{label}：{names}。")
    shown = next((day for day in plan.days if day.status == "pending"), plan.days[0])
    source_topics = _source_topics(skills)
    if evidence_leads(shown.focus, scores, self_weak, source_topics):
        lines.append("做题记录排在自评和职位说明前面。")
    lines.append(f"7 天计划已排好。第 {shown.day_index} 天练{chinese_subject(shown.focus)}。")
    lines.append("这一天的验收：")
    for bullet in coach_bullets(shown.acceptance_criteria, "zh"):
        lines.append(f"- {bullet}")
    lines.append("下一步：interview-coach today")
    return "\n".join(lines)


def _source_topics(skills: tuple[LearnerSkill, ...]) -> tuple[str, ...]:
    order = {kind: index for index, kind in enumerate(SOURCE_KINDS)}
    chosen = sorted(skills, key=lambda skill: (order.get(skill.kind, 9), skill.source_id, skill.id))
    topics: list[str] = []
    for skill in chosen:
        if skill.topic not in topics:
            topics.append(skill.topic)
    return tuple(topics)
