"""Profile validation. Daily study time defaults to 30 minutes."""

from __future__ import annotations

from dataclasses import dataclass

from interview_coach.assessment.targets import resolve_target

LEVELS = ("junior", "mid", "senior")
DEFAULT_DAILY_MINUTES = 30
MIN_DAILY_MINUTES = 10
MAX_DAILY_MINUTES = 180
LEVEL_PRIOR = {"junior": 2.5, "mid": 3.0, "senior": 3.5}


DEFAULT_STREAK_GOAL = 5
DEFAULT_KINDS = "mcq,open"


@dataclass(frozen=True)
class ProfileInput:
    name: str
    target_role: str
    level: str
    daily_minutes: int
    target_id: str = "generic_tech"
    streak_goal: int = DEFAULT_STREAK_GOAL
    preferred_kinds: str = DEFAULT_KINDS


def normalize_kinds(preferred_kinds: str) -> str:
    parts = [part.strip().lower() for part in preferred_kinds.split(",") if part.strip()]
    if not parts:
        return DEFAULT_KINDS
    unknown = [part for part in parts if part not in {"mcq", "open"}]
    if unknown:
        raise ValueError("preferred kinds must be mcq, open, or both")
    return ",".join(kind for kind in ("mcq", "open") if kind in parts)


def normalize_profile(
    name: str,
    target_role: str,
    level: str = "mid",
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
    target: str = "generic_tech",
    streak_goal: int = DEFAULT_STREAK_GOAL,
    preferred_kinds: str = DEFAULT_KINDS,
) -> ProfileInput:
    clean_name = name.strip()
    clean_role = target_role.strip()
    if not clean_name:
        raise ValueError("name is required")
    if not clean_role:
        raise ValueError("target role is required")
    if level not in LEVELS:
        raise ValueError(f"level must be one of: {', '.join(LEVELS)}")
    if not isinstance(daily_minutes, int) or isinstance(daily_minutes, bool):
        raise ValueError("daily minutes must be an integer")
    if not MIN_DAILY_MINUTES <= daily_minutes <= MAX_DAILY_MINUTES:
        raise ValueError(
            f"daily minutes must be between {MIN_DAILY_MINUTES} and {MAX_DAILY_MINUTES}"
        )
    if isinstance(streak_goal, bool) or not isinstance(streak_goal, int):
        raise ValueError("streak goal must be an integer")
    if not 0 <= streak_goal <= 30:
        raise ValueError("streak goal must be between 0 and 30")
    kinds = normalize_kinds(preferred_kinds)
    target_id = resolve_target(clean_role, target)
    return ProfileInput(clean_name, clean_role, level, daily_minutes, target_id, streak_goal, kinds)


def prior_ability(level: str) -> float:
    try:
        return LEVEL_PRIOR[level]
    except KeyError as exc:
        raise ValueError(f"unknown level {level}") from exc
