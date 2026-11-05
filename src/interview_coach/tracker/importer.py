"""Load completed practice from a local JSON or CSV file. No network."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from interview_coach.assessment.bank import TOPICS
from interview_coach.assessment.scoring import default_discrimination


@dataclass(frozen=True)
class PracticeRecord:
    topic: str
    difficulty: int
    score: float
    discrimination: float


@dataclass(frozen=True)
class LogRecord:
    day: int
    minutes: int
    completed: bool
    quiz_correct: int | None
    quiz_total: int | None
    notes: str


@dataclass(frozen=True)
class ImportBatch:
    practice: tuple[PracticeRecord, ...]
    logs: tuple[LogRecord, ...]


def load_progress(path: Path) -> ImportBatch:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"import file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return _from_json(file_path)
    if suffix == ".csv":
        return _from_csv(file_path)
    raise ValueError("import file must be .json or .csv")


def _from_json(path: Path) -> ImportBatch:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"import JSON is not valid: {exc}") from exc
    if isinstance(payload, list):
        if not payload:
            raise ValueError("import file has no practice rows or logs")
        return ImportBatch(tuple(_practice_row(item, index) for index, item in enumerate(payload, start=1)), ())
    if isinstance(payload, dict):
        practice_rows = payload.get("practice", [])
        log_rows = payload.get("logs", [])
        if not isinstance(practice_rows, list) or not isinstance(log_rows, list):
            raise ValueError("import JSON practice and logs must be lists")
        practice = tuple(_practice_row(item, index) for index, item in enumerate(practice_rows, start=1))
        logs = tuple(_log_row(item, index) for index, item in enumerate(log_rows, start=1))
        if not practice and not logs:
            raise ValueError("import file has no practice rows or logs")
        return ImportBatch(practice, logs)
    raise ValueError("import JSON must be a list or an object with practice and logs")


def _from_csv(path: Path) -> ImportBatch:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("import CSV needs a header row")
        fields = {(name or "").strip().lower() for name in reader.fieldnames}
        practice: list[PracticeRecord] = []
        logs: list[LogRecord] = []
        for index, row in enumerate(reader, start=1):
            normalized = {(key or "").strip().lower(): (value or "").strip() for key, value in row.items()}
            if not any(normalized.values()):
                continue
            if normalized.get("topic"):
                practice.append(_practice_row(normalized, index))
            elif normalized.get("day"):
                logs.append(_log_row(normalized, index))
            else:
                raise ValueError(f"row {index} needs a topic or a day")
    if "topic" not in fields and "day" not in fields:
        raise ValueError("import CSV needs a topic column, a day column, or both")
    if not practice and not logs:
        raise ValueError("import file has no practice rows or logs")
    return ImportBatch(tuple(practice), tuple(logs))


def _practice_row(raw: object, index: int) -> PracticeRecord:
    if not isinstance(raw, dict):
        raise ValueError(f"practice row {index} must be an object")
    topic = str(raw.get("topic", "")).strip()
    if topic not in TOPICS:
        raise ValueError(f"practice row {index} has unknown topic {topic or '(missing)'}")
    difficulty = _int_field(raw.get("difficulty", 3), f"practice row {index} difficulty")
    if difficulty not in range(1, 6):
        raise ValueError(f"practice row {index} difficulty must be from 1 to 5")
    score = _score_field(raw, index)
    if "discrimination" in raw and str(raw.get("discrimination", "")).strip() != "":
        discrimination = float(raw["discrimination"])
        if discrimination <= 0:
            raise ValueError(f"practice row {index} discrimination must be positive")
    else:
        discrimination = default_discrimination(difficulty)
    return PracticeRecord(topic, difficulty, score, discrimination)


def _score_field(raw: dict, index: int) -> float:
    if "score" in raw and str(raw.get("score", "")).strip() != "":
        score = float(raw["score"])
    elif "correct" in raw and str(raw.get("correct", "")).strip() != "":
        score = _correct_value(raw["correct"])
    else:
        raise ValueError(f"practice row {index} needs correct or score")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"practice row {index} score must be between 0 and 1")
    return score


def _correct_value(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "correct"}:
        return 1.0
    if text in {"0", "false", "no", "n", "incorrect"}:
        return 0.0
    return float(text)


def _log_row(raw: object, index: int) -> LogRecord:
    if not isinstance(raw, dict):
        raise ValueError(f"log row {index} must be an object")
    day = _int_field(raw.get("day"), f"log row {index} day")
    minutes = _int_field(raw.get("minutes", 0), f"log row {index} minutes")
    if minutes < 0:
        raise ValueError(f"log row {index} minutes cannot be negative")
    completed = _completed_value(raw.get("completed", True))
    quiz_correct, quiz_total = _quiz_field(raw, index)
    notes = str(raw.get("notes", "") or "")
    return LogRecord(day, minutes, completed, quiz_correct, quiz_total, notes)


def _quiz_field(raw: dict, index: int) -> tuple[int | None, int | None]:
    quiz = str(raw.get("quiz", "") or "").strip()
    if quiz:
        if "/" not in quiz:
            raise ValueError(f"log row {index} quiz must look like 6/10")
        left, right = quiz.split("/", 1)
        return int(left), int(right)
    correct = raw.get("quiz_correct")
    total = raw.get("quiz_total")
    if (correct in (None, "")) and (total in (None, "")):
        return None, None
    return _int_field(correct, f"log row {index} quiz_correct"), _int_field(total, f"log row {index} quiz_total")


def _completed_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "done", "complete", "completed"}:
        return True
    if text in {"0", "false", "no", "n", "missed", "miss"}:
        return False
    raise ValueError(f"cannot read completed value {value!r}")


def _int_field(value: object, label: str) -> int:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            raise ValueError
        number = float(value)
        if not number.is_integer():
            raise ValueError
        return int(number)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
