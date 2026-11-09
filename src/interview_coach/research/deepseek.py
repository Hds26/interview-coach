"""Optional DeepSeek skill list. Missing key or a bad payload just returns nothing."""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.error import HTTPError, URLError

from interview_coach.research.extract import RULES

_KNOWN = {rule.name.casefold() for rule in RULES}


def proposed_skill_names(
    text: str,
    *,
    api_key: str | None = None,
    opener=None,
    model: str = "deepseek-flash",
    timeout: float = 20.0,
) -> list[str] | None:
    """Ask for a JSON skill list. Returns None when the call should be ignored."""
    key = (api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        return None
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return one JSON object and nothing else: "
                    '{"skills": ["redis"]}. Use short skill names only. '
                    "Do not copy the job description."
                ),
            },
            {"role": "user", "content": text[:4000]},
        ],
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(request, timeout=timeout) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    try:
        body = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return _names_from_content(content)


def _names_from_content(content: str) -> list[str] | None:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    skills = parsed.get("skills") if isinstance(parsed, dict) else None
    if not isinstance(skills, list):
        return None
    names: list[str] = []
    for item in skills:
        if not isinstance(item, str):
            continue
        token = item.strip().casefold()
        if token in _KNOWN and token not in names and len(token) <= 40:
            names.append(token)
    return names
