"""Profile validation. Daily study time defaults to 30 minutes."""

from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("junior", "mid", "senior")
DEFAULT_DAILY_MINUTES = 30
MIN_DAILY_MINUTES = 10
MAX_DAILY_MINUTES = 180
LEVEL_PRIOR = {"junior": 2.5, "mid": 3.0, "senior": 3.5}


@dataclass(frozen=True)
class ProfileInput:
    name: str
    target_role: str
    level: str
    daily_minutes: int


def normalize_profile(
    name: str,
    target_role: str,
    level: str = "mid",
    daily_minutes: int = DEFAULT_DAILY_MINUTES,
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
    return ProfileInput(clean_name, clean_role, level, daily_minutes)


def prior_ability(level: str) -> float:
    try:
        return LEVEL_PRIOR[level]
    except KeyError as exc:
        raise ValueError(f"unknown level {level}") from exc
