"""Build a research preview in memory. Nothing here writes to the database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from interview_coach.assessment.bank import chinese_subject
from interview_coach.models import Question
from interview_coach.research.deepseek import proposed_skill_names
from interview_coach.research.extract import (
    SkillHit,
    draft_items,
    echoes_source,
    extract_skills,
    looks_stale,
)
from interview_coach.research.search import search_public, skills_from_hits

PASTE_HINT = "网络不可用，或没有可用的公开结果。下一步：interview-coach research --paste"
FULL_DAYS = 7
EXPIRE_DAYS = 30
BOOST = 0.8


@dataclass(frozen=True)
class SourceCite:
    url: str
    title: str


@dataclass(frozen=True)
class ResearchPreview:
    label: str
    sources: tuple[SourceCite, ...]
    skills: tuple[SkillHit, ...]
    items: tuple[Question, ...]
    stale_note: str = ""
    used_model: bool = False

    @property
    def topics(self) -> tuple[str, ...]:
        ordered: list[str] = []
        for skill in self.skills:
            if skill.topic not in ordered:
                ordered.append(skill.topic)
        return tuple(ordered)


def prepare_paste(
    text: str,
    *,
    label: str = "paste",
    max_skills: int = 6,
    max_items: int = 5,
    today: date | None = None,
    llm: str = "offline",
    opener=None,
) -> ResearchPreview:
    day = today or date.today()
    note = "笔记里的年份看起来比较旧，仍然只按技能出题。" if looks_stale(text, day.year) else ""
    skills, used_model = _skills_for_text(text, max_skills=max_skills, llm=llm, opener=opener)
    items = _safe_items(text, skills, max_items=max_items)
    return ResearchPreview(
        label=_short_label(label),
        sources=(SourceCite("", "本地笔记"),),
        skills=tuple(skills),
        items=tuple(items),
        stale_note=note,
        used_model=used_model,
    )


def prepare_query(
    query: str,
    *,
    max_skills: int = 6,
    max_items: int = 5,
    today: date | None = None,
    opener=None,
    search=None,
) -> ResearchPreview:
    """Search once. Raises SearchUnavailable so the caller can print the paste hint."""
    if search is None:
        hits = search_public(query, opener=opener)
    else:
        hits = search(query)
    # The default search_public takes opener as keyword. A test double may take only the query.
    skills = skills_from_hits(hits, limit=max_skills)
    combined = "\n".join(f"{hit.title}\n{hit.snippet}" for hit in hits)
    items = _safe_items(combined, skills, max_items=max_items)
    cites = tuple(SourceCite(hit.url, hit.title) for hit in hits[:5])
    return ResearchPreview(
        label=_short_label(query),
        sources=cites,
        skills=tuple(skills),
        items=tuple(items),
    )


def render_preview(preview: ResearchPreview) -> str:
    lines = ["可选研究。这不是每天的命令，也不会把这些主题说成薄弱项。", "来源（只保留标题和链接）："]
    if not preview.sources:
        lines.append("- （没有来源）")
    for source in preview.sources:
        if source.url:
            lines.append(f"- {source.title}  {source.url}")
        else:
            lines.append(f"- {source.title}（原文不保存）")
    if preview.stale_note:
        lines.append(preview.stale_note)
    lines.append("技能 → 主题：")
    if not preview.skills:
        lines.append("- 没有映射到本地主题的技能，所以不会写入。")
        return "\n".join(lines)
    for skill in preview.skills:
        lines.append(f"- {skill.name} → {chinese_subject(skill.topic)}")
    lines.append("生成的草稿（不是原文）：")
    for index, item in enumerate(preview.items, start=1):
        lines.append(f"{index}. [{item.kind}] {item.prompt}")
    topics = "、".join(chinese_subject(topic) for topic in preview.topics)
    lines.append(
        f"确认后：接下来 {FULL_DAYS} 天提高这些主题的权重（{EXPIRE_DAYS} 天后失效）：{topics}。"
        "只改接下来要练的那一天，不重写整周。"
    )
    lines.append("写入吗？[y/N]")
    return "\n".join(lines)


def boost_on(today: date, starts: date, full_until: date, expires: date, boost: float = BOOST) -> float:
    """Full boost for the first week, then a linear decay until the expiry day."""
    if today < starts or today >= expires:
        return 0.0
    if today < full_until:
        return boost
    span = (expires - full_until).days
    if span <= 0:
        return 0.0
    remaining = (expires - today).days
    if remaining <= 0:
        return 0.0
    return boost * remaining / span


def _skills_for_text(text: str, *, max_skills: int, llm: str, opener) -> tuple[list[SkillHit], bool]:
    local = extract_skills(text, limit=max_skills)
    if llm != "deepseek":
        return local, False
    proposed = proposed_skill_names(text, opener=opener)
    if not proposed:
        return local, False
    by_name = {hit.name.casefold(): hit for hit in local}
    chosen = [by_name[name] for name in proposed if name in by_name]
    if not chosen:
        return local, False
    return chosen[:max_skills], True


def _safe_items(source: str, skills: list[SkillHit], *, max_items: int) -> list[Question]:
    items = draft_items(skills, limit=max_items)
    return [item for item in items if not echoes_source(item.prompt, source)]


def _short_label(label: str) -> str:
    compact = " ".join(label.split())
    return compact[:80] or "paste"
