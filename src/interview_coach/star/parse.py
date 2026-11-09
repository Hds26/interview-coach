"""Split a STAR answer into Situation, Task, Action, and Result."""

from __future__ import annotations

import re

SECTIONS: tuple[str, ...] = ("situation", "task", "action", "result")

_NAMES = {
    "situation": "situation",
    "s": "situation",
    "情境": "situation",
    "情况": "situation",
    "背景": "situation",
    "task": "task",
    "t": "task",
    "任务": "task",
    "目标": "task",
    "action": "action",
    "a": "action",
    "行动": "action",
    "做法": "action",
    "result": "result",
    "r": "result",
    "结果": "result",
    "反思": "result",
}

_LABELS = {
    "zh": {"situation": "情境", "task": "任务", "action": "行动", "result": "结果"},
    "en": {"situation": "Situation", "task": "Task", "action": "Action", "result": "Result"},
}


def section_label(name: str, lang: str) -> str:
    table = _LABELS["en"] if lang == "en" else _LABELS["zh"]
    return table.get(name, name)


def empty_sections() -> dict[str, str]:
    return {name: "" for name in SECTIONS}


def split_answer_blob(raw: str) -> dict[str, str]:
    """Accept ``||`` segments or one paste with headings or blank lines."""
    text = raw.replace("\r\n", "\n").strip()
    if "||" in text:
        parts = [part.strip() for part in text.split("||")]
        while len(parts) < 4:
            parts.append("")
        return {name: parts[index] for index, name in enumerate(SECTIONS)}
    return parse_sections(text)


def parse_sections(text: str) -> dict[str, str]:
    """Map a paste onto the four sections.

    Headings win. A heading is a line such as ``情境：``、``Situation:`` or
    ``S:``. Without headings, blank lines split the paste in STAR order.
    """
    normalized = text.replace("\r\n", "\n").strip()
    headed = _parse_headings(normalized)
    if headed is not None:
        return headed
    sections = empty_sections()
    blocks = [block.strip() for block in re.split(r"\n[ \t]*\n", normalized) if block.strip()]
    if len(blocks) > 4:
        blocks = [*blocks[:3], "\n\n".join(blocks[3:])]
    for name, block in zip(SECTIONS, blocks, strict=False):
        sections[name] = block
    return sections


def read_sections(lang: str, read) -> dict[str, str]:
    """Read four prompts, or one paste when the first entry already has sections."""
    first = read(_first_prompt(lang)).strip()
    parsed = parse_sections(first)
    filled = [name for name in SECTIONS if parsed[name].strip()]
    if len(filled) >= 2:
        return parsed
    sections = empty_sections()
    sections["situation"] = first
    for name in SECTIONS[1:]:
        label = section_label(name, lang)
        sep = ": " if lang == "en" else "："
        sections[name] = read(f"{label}{sep}").strip()
    return sections


def _first_prompt(lang: str) -> str:
    if lang == "en":
        return (
            "Situation (or paste all four, with headings or blank lines): "
        )
    return "情境（或一次贴上四段，用情境/任务/行动/结果或空行分开）："


def _parse_headings(text: str) -> dict[str, str] | None:
    sections: dict[str, list[str]] = {name: [] for name in SECTIONS}
    current: str | None = None
    found = False
    for line in text.split("\n"):
        heading = _heading(line)
        if heading is not None:
            found = True
            current, rest = heading
            if rest:
                sections[current].append(rest)
            continue
        if current is not None:
            sections[current].append(line)
    if not found:
        return None
    return {name: "\n".join(parts).strip() for name, parts in sections.items()}


def _heading(line: str) -> tuple[str, str] | None:
    stripped = re.sub(r"^#{1,3}\s*", "", line.strip())
    if not stripped:
        return None
    matched = re.match(r"^(?P<name>.+?)\s*[:：]\s*(?P<rest>.*)$", stripped)
    if matched:
        key = _lookup(matched.group("name").strip())
        if key:
            return key, matched.group("rest").strip()
    key = _lookup(stripped)
    if key and stripped.casefold() not in {"s", "t", "a", "r"}:
        return key, ""
    return None


def _lookup(name: str) -> str | None:
    return _NAMES.get(name.casefold()) or _NAMES.get(name)
