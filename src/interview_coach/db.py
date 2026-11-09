"""SQLite storage. The default file is data/coach.sqlite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from interview_coach.assessment.bank import TOPICS
from interview_coach.models import PlanDay, Profile, StudyLog, StudyPlan, TopicScore

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    target_role TEXT NOT NULL,
    level TEXT NOT NULL,
    daily_minutes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    target_id TEXT NOT NULL DEFAULT 'generic_tech',
    streak_goal INTEGER NOT NULL DEFAULT 5,
    preferred_kinds TEXT NOT NULL DEFAULT 'mcq,open'
);

CREATE TABLE IF NOT EXISTS topic_score (
    topic TEXT PRIMARY KEY,
    ability REAL NOT NULL,
    answered INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    information REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    next_review TEXT
);

CREATE TABLE IF NOT EXISTS assessment (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    question_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS response (
    id INTEGER PRIMARY KEY,
    assessment_id INTEGER NOT NULL REFERENCES assessment(id),
    question_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    choice_index INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    ability_after REAL NOT NULL,
    created_at TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 1,
    kind TEXT NOT NULL DEFAULT 'mcq',
    response_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS study_plan (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    daily_minutes INTEGER NOT NULL,
    policy TEXT NOT NULL,
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_day (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES study_plan(id),
    day_index INTEGER NOT NULL,
    day_date TEXT NOT NULL,
    focus TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (plan_id, day_index)
);

CREATE TABLE IF NOT EXISTS study_log (
    id INTEGER PRIMARY KEY,
    plan_day_id INTEGER NOT NULL REFERENCES plan_day(id),
    minutes_spent INTEGER NOT NULL,
    completed INTEGER NOT NULL,
    quiz_correct INTEGER,
    quiz_total INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_exposure (
    question_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    seen_count INTEGER NOT NULL,
    last_seen TEXT NOT NULL,
    last_score REAL NOT NULL,
    next_due TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add iteration-2 columns to a database created by the first release."""
    _add_column(conn, "profile", "target_id", "TEXT NOT NULL DEFAULT 'generic_tech'")
    _add_column(conn, "topic_score", "information", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "topic_score", "credit", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "topic_score", "next_review", "TEXT")
    _add_column(conn, "response", "score", "REAL NOT NULL DEFAULT 1")
    _add_column(conn, "response", "kind", "TEXT NOT NULL DEFAULT 'mcq'")
    _add_column(conn, "response", "response_text", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "profile", "streak_goal", "INTEGER NOT NULL DEFAULT 5")
    _add_column(conn, "profile", "preferred_kinds", "TEXT NOT NULL DEFAULT 'mcq,open'")


def _add_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if not existing or column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    conn.commit()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        _migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    def get_profile(self) -> Profile | None:
        row = self.conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        if row is None:
            return None
        return Profile(
            name=row["name"],
            target_role=row["target_role"],
            level=row["level"],
            daily_minutes=row["daily_minutes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            target_id=row["target_id"],
            streak_goal=row["streak_goal"],
            preferred_kinds=row["preferred_kinds"],
        )

    def save_profile(
        self,
        name: str,
        target_role: str,
        level: str,
        daily_minutes: int,
        prior: float,
        target_id: str = "generic_tech",
        streak_goal: int = 5,
        preferred_kinds: str = "mcq,open",
        reset_scores: bool = False,
    ) -> Profile:
        """Update the learner. Existing ability rows and plans stay unless ``reset_scores``."""
        now = utc_now()
        existing = self.get_profile()
        created = existing.created_at if existing else now
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO profile (
                    id, name, target_role, level, daily_minutes, created_at, updated_at,
                    target_id, streak_goal, preferred_kinds
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    target_role = excluded.target_role,
                    level = excluded.level,
                    daily_minutes = excluded.daily_minutes,
                    updated_at = excluded.updated_at,
                    target_id = excluded.target_id,
                    streak_goal = excluded.streak_goal,
                    preferred_kinds = excluded.preferred_kinds
                """,
                (name, target_role, level, daily_minutes, created, now, target_id, streak_goal, preferred_kinds),
            )
            if reset_scores:
                self.conn.execute("DELETE FROM topic_score")
                self.conn.execute("DELETE FROM item_exposure")
            self._ensure_score_rows(prior, now)
        profile = self.get_profile()
        assert profile is not None
        return profile

    def _ensure_score_rows(self, prior: float, now: str) -> None:
        have = {row["topic"] for row in self.conn.execute("SELECT topic FROM topic_score")}
        for topic in TOPICS:
            if topic in have:
                continue
            self.conn.execute(
                """
                INSERT INTO topic_score (topic, ability, answered, correct, updated_at)
                VALUES (?, ?, 0, 0, ?)
                """,
                (topic, prior, now),
            )

    def list_scores(self) -> list[TopicScore]:
        rows = self.conn.execute(
            """
            SELECT topic, ability, answered, correct, information, credit, next_review
            FROM topic_score
            ORDER BY topic
            """
        ).fetchall()
        return [
            TopicScore(
                topic=row["topic"],
                ability=row["ability"],
                answered=row["answered"],
                correct=row["correct"],
                information=row["information"],
                credit=row["credit"],
                next_review=row["next_review"],
            )
            for row in rows
        ]

    def ability_map(self) -> dict[str, float]:
        return {score.topic: score.ability for score in self.list_scores()}

    def save_assessment(
        self,
        answers: list[dict],
        final_ability: dict[str, float],
        next_review: dict[str, str] | None = None,
        exposures: list[dict] | None = None,
    ) -> int:
        now = utc_now()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO assessment (started_at, finished_at, question_count) VALUES (?, ?, ?)",
                (now, now, len(answers)),
            )
            assessment_id = int(cursor.lastrowid)
            per_topic: dict[str, list[dict]] = {}
            for answer in answers:
                self.conn.execute(
                    """
                    INSERT INTO response (
                        assessment_id, question_id, topic, difficulty, choice_index,
                        correct, ability_after, created_at, score, kind, response_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assessment_id,
                        answer["question_id"],
                        answer["topic"],
                        answer["difficulty"],
                        answer["choice_index"],
                        int(answer["correct"]),
                        answer["ability_after"],
                        now,
                        answer.get("score", 1.0 if answer["correct"] else 0.0),
                        answer.get("kind", "mcq"),
                        answer.get("response_text", ""),
                    ),
                )
                per_topic.setdefault(answer["topic"], []).append(answer)
            for topic, ability in final_ability.items():
                batch = per_topic.get(topic, [])
                if not batch:
                    continue
                correct = sum(1 for item in batch if item.get("score", 1.0 if item["correct"] else 0.0) >= 0.999)
                credit = sum(float(item.get("score", 1.0 if item["correct"] else 0.0)) for item in batch)
                information = sum(float(item.get("information", 0.0)) for item in batch)
                review = (next_review or {}).get(topic)
                self.conn.execute(
                    """
                    UPDATE topic_score
                    SET ability = ?,
                        answered = answered + ?,
                        correct = correct + ?,
                        credit = credit + ?,
                        information = information + ?,
                        next_review = COALESCE(?, next_review),
                        updated_at = ?
                    WHERE topic = ?
                    """,
                    (ability, len(batch), correct, credit, information, review, now, topic),
                )
            for item in exposures or []:
                self._upsert_exposure(item)
        return assessment_id

    def _upsert_exposure(self, item: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO item_exposure (question_id, topic, seen_count, last_seen, last_score, next_due)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                topic = excluded.topic,
                seen_count = item_exposure.seen_count + 1,
                last_seen = excluded.last_seen,
                last_score = excluded.last_score,
                next_due = excluded.next_due
            """,
            (
                item["question_id"],
                item["topic"],
                item["last_seen"],
                item["last_score"],
                item["next_due"],
            ),
        )

    def exposure_map(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT question_id, next_due FROM item_exposure").fetchall()
        return {row["question_id"]: row["next_due"] for row in rows}

    def exposure_row(self, question_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM item_exposure WHERE question_id = ?",
            (question_id,),
        ).fetchone()

    def apply_practice(
        self,
        topic: str,
        ability: float,
        score: float,
        information: float,
        next_review: str,
    ) -> None:
        now = utc_now()
        full = 1 if score >= 0.999 else 0
        with self.conn:
            updated = self.conn.execute(
                """
                UPDATE topic_score
                SET ability = ?,
                    answered = answered + 1,
                    correct = correct + ?,
                    credit = credit + ?,
                    information = information + ?,
                    next_review = ?,
                    updated_at = ?
                WHERE topic = ?
                """,
                (ability, full, score, information, next_review, now, topic),
            )
            if updated.rowcount != 1:
                raise ValueError(f"unknown topic {topic}")

    def due_topics(self, on: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT topic FROM topic_score
            WHERE next_review IS NOT NULL AND next_review <= ? AND answered > 0
            ORDER BY next_review, ability, topic
            """,
            (on,),
        ).fetchall()
        return [row["topic"] for row in rows]

    def next_plan_version(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM study_plan").fetchone()
        return int(row["version"]) + 1

    def create_plan(
        self,
        daily_minutes: int,
        policy: str,
        start_date: str,
        days: list[dict],
    ) -> StudyPlan:
        now = utc_now()
        version = self.next_plan_version()
        with self.conn:
            self.conn.execute("UPDATE study_plan SET active = 0 WHERE active = 1")
            cursor = self.conn.execute(
                """
                INSERT INTO study_plan (version, daily_minutes, policy, start_date, created_at, active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (version, daily_minutes, policy, start_date, now),
            )
            plan_id = int(cursor.lastrowid)
            for day in days:
                self.conn.execute(
                    """
                    INSERT INTO plan_day (
                        plan_id, day_index, day_date, focus, minutes, objective,
                        acceptance_criteria, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        plan_id,
                        day["day_index"],
                        day["day_date"],
                        day["focus"],
                        day["minutes"],
                        day["objective"],
                        json.dumps(list(day["acceptance_criteria"])),
                    ),
                )
        plan = self.get_active_plan()
        assert plan is not None
        return plan

    def get_active_plan(self) -> StudyPlan | None:
        row = self.conn.execute("SELECT * FROM study_plan WHERE active = 1").fetchone()
        if row is None:
            return None
        return self._plan_from_row(row)

    def set_day_status(self, plan_day_id: int, status: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE plan_day SET status = ? WHERE id = ?", (status, plan_day_id))

    def update_plan_day(
        self,
        plan_day_id: int,
        focus: str,
        minutes: int,
        objective: str,
        acceptance_criteria: tuple[str, ...] | list[str],
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE plan_day
                SET focus = ?, minutes = ?, objective = ?, acceptance_criteria = ?
                WHERE id = ?
                """,
                (focus, minutes, objective, json.dumps(list(acceptance_criteria)), plan_day_id),
            )

    def completed_dates(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT day_date FROM plan_day WHERE status = 'done' ORDER BY day_date"
        ).fetchall()
        return [row["day_date"] for row in rows]

    def add_log(
        self,
        plan_day_id: int,
        minutes_spent: int,
        completed: bool,
        quiz_correct: int | None,
        quiz_total: int | None,
        notes: str,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO study_log (
                    plan_day_id, minutes_spent, completed, quiz_correct, quiz_total, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (plan_day_id, minutes_spent, int(completed), quiz_correct, quiz_total, notes, utc_now()),
            )

    def list_logs(self, plan_id: int) -> list[StudyLog]:
        rows = self.conn.execute(
            """
            SELECT study_log.*, plan_day.day_index
            FROM study_log
            JOIN plan_day ON plan_day.id = study_log.plan_day_id
            WHERE plan_day.plan_id = ?
            ORDER BY study_log.id
            """,
            (plan_id,),
        ).fetchall()
        return [
            StudyLog(
                id=row["id"],
                plan_day_id=row["plan_day_id"],
                day_index=row["day_index"],
                minutes_spent=row["minutes_spent"],
                completed=bool(row["completed"]),
                quiz_correct=row["quiz_correct"],
                quiz_total=row["quiz_total"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def _plan_from_row(self, row: sqlite3.Row) -> StudyPlan:
        day_rows = self.conn.execute(
            "SELECT * FROM plan_day WHERE plan_id = ? ORDER BY day_index",
            (row["id"],),
        ).fetchall()
        days = tuple(
            PlanDay(
                id=day["id"],
                day_index=day["day_index"],
                day_date=day["day_date"],
                focus=day["focus"],
                minutes=day["minutes"],
                objective=day["objective"],
                acceptance_criteria=tuple(json.loads(day["acceptance_criteria"])),
                status=day["status"],
            )
            for day in day_rows
        )
        return StudyPlan(
            id=row["id"],
            version=row["version"],
            daily_minutes=row["daily_minutes"],
            policy=row["policy"],
            start_date=row["start_date"],
            days=days,
        )
