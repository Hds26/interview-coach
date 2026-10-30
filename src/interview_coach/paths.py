"""Default locations. Study data lives under data/."""

from __future__ import annotations

import os
from pathlib import Path


def default_db_path() -> Path:
    override = os.environ.get("INTERVIEW_COACH_DB")
    if override:
        return Path(override)
    return Path.cwd() / "data" / "coach.sqlite"
