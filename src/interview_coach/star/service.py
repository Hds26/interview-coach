"""Draw one STAR prompt, score it locally, and store the session."""

from __future__ import annotations

import random
from dataclasses import dataclass

from interview_coach.star.bank import StarItem, get_item, star_items
from interview_coach.star.parse import SECTIONS
from interview_coach.star.polish import polish_tips
from interview_coach.star.rubric import score_sections
from interview_coach.star.tips import example_lines, rewrite_tips


@dataclass(frozen=True)
class StarReport:
    session_id: int
    item_id: str
    tags: tuple[str, ...]
    prompt: str
    sections: dict[str, str]
    scores: dict[str, float]
    total: float
    weak: tuple[str, ...]
    tips: tuple[str, ...]
    example: tuple[str, ...]
    llm: str
    llm_error: str


def draw_item(items: tuple[StarItem, ...] | list[StarItem], seen: set[str], rng: random.Random) -> StarItem:
    """Pick an unseen prompt, or any prompt once the bank has all been used."""
    if not items:
        raise ValueError("STAR bank is empty")
    unseen = [item for item in items if item.id not in seen]
    pool = unseen or list(items)
    return rng.choice(pool)


def run_star_session(
    db,
    sections: dict[str, str],
    *,
    item_id: str | None = None,
    seed: int | None = None,
    llm: str = "offline",
    lang: str = "zh",
    opener=None,
) -> StarReport:
    """Score and store one story. Caller must already have a profile.

    This writes ``star_session`` only. Topic scores, plan days, and study logs
    stay as they were.
    """
    if llm not in {"", "offline", "deepseek"}:
        raise ValueError("star only uses --llm deepseek to polish tips; omit it for local templates")
    if not any(str(sections.get(name, "")).strip() for name in SECTIONS):
        raise ValueError("STAR answer was empty")
    if item_id:
        item = get_item(item_id)
    else:
        rng = random.Random(seed) if seed is not None else random.Random()
        item = draw_item(star_items(), set(db.star_item_ids()), rng)
    scored = score_sections(sections)
    language = "en" if lang == "en" else "zh"
    tips = rewrite_tips(scored, language)
    used = "offline"
    llm_error = ""
    if llm == "deepseek":
        tips, used, llm_error = polish_tips(
            tips,
            prompt=item.prompt,
            sections=sections,
            lang=language,
            opener=opener,
        )
        if llm_error:
            used = "offline"
    example = example_lines(item, language) if scored.weak else ()
    session_id = db.save_star_session(
        item.id,
        item.tags,
        item.prompt,
        {name: sections.get(name, "") for name in SECTIONS},
        scored.sections,
        scored.total,
        scored.weak,
        tips,
        used,
    )
    return StarReport(
        session_id=session_id,
        item_id=item.id,
        tags=item.tags,
        prompt=item.prompt,
        sections={name: sections.get(name, "") for name in SECTIONS},
        scores=dict(scored.sections),
        total=scored.total,
        weak=scored.weak,
        tips=tips,
        example=example,
        llm=used,
        llm_error=llm_error,
    )
