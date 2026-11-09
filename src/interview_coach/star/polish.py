"""Optional DeepSeek polish for STAR tips. Scoring stays local."""

from __future__ import annotations

import json
import os

from interview_coach.agent.llm import DeepSeekLLM, LLMConfigError
from interview_coach.star.parse import SECTIONS

_SYSTEM = (
    "You polish interview coaching tips. Return one JSON object and nothing else: "
    '{"tips": ["...", "..."]}. Give 2 or 3 short tips in the requested language. '
    "Do not invent numbers, systems, or events the learner did not write. "
    "Do not score the answer."
)


def polish_tips(
    tips: tuple[str, ...],
    *,
    prompt: str,
    sections: dict[str, str],
    lang: str,
    opener=None,
) -> tuple[tuple[str, ...], str, str]:
    """Return tips, the source, and an error string.

    No ``DEEPSEEK_API_KEY`` keeps the local templates, records the same error
    ``ask --llm deepseek`` uses, and does not call the network.
    """
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        return tips, "offline", "DEEPSEEK_API_KEY is required for --llm deepseek"
    language = "English" if lang == "en" else "Chinese"
    payload = {
        "language": language,
        "prompt": prompt,
        "answer": {name: sections.get(name, "") for name in SECTIONS},
        "local_tips": list(tips),
    }
    try:
        response = DeepSeekLLM(api_key=key, urlopen=opener).complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
        parsed = _tips_from_content(response.content)
    except LLMConfigError as exc:
        return tips, "offline", str(exc)
    if parsed is None:
        return tips, "offline", "DeepSeek API returned no rewrite tips"
    return parsed, "deepseek", ""


def _tips_from_content(content: str) -> tuple[str, ...] | None:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    raw = parsed.get("tips") if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        return None
    tips: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split())
        if text:
            tips.append(text[:200])
    if len(tips) < 2:
        return None
    return tuple(tips[:3])
