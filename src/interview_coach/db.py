"""SQLite storage. The default file is data/coach.sqlite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from interview_coach.assessment.bank import TOPICS
from interview_coach.learner.model import SOURCE_KINDS, LearnerModel, LearnerSkill
from interview_coach.models import PlanDay, Profile, Question, RubricPoint, StudyLog, StudyPlan, TopicScore

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

CREATE TABLE IF NOT EXISTS research_session (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_source (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_session(id),
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skill_tag (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_session(id),
    name TEXT NOT NULL,
    topic TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_item (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_session(id),
    question_id TEXT NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    kind TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    choices TEXT NOT NULL,
    answer INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    rubric TEXT NOT NULL,
    tags TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'research_generated'
);

CREATE TABLE IF NOT EXISTS plan_bias (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES research_session(id),
    topic TEXT NOT NULL,
    boost REAL NOT NULL,
    starts_on TEXT NOT NULL,
    full_until TEXT NOT NULL,
    expires_on TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_model (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    minutes_per_day INTEGER NOT NULL,
    practice_style TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_baseline (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL UNIQUE,
    stance TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_source (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learner_skill (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES learner_source(id),
    name TEXT NOT NULL,
    topic TEXT NOT NULL
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

    def save_research(
        self,
        label: str,
        sources: list[tuple[str, str]],
        skills: list[tuple[str, str]],
        items: list[Question],
        biases: list[dict],
    ) -> int:
        """Persist an accepted research session. Callers must not pass the original note."""
        now = utc_now()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO research_session (label, created_at) VALUES (?, ?)",
                (label, now),
            )
            session_id = int(cursor.lastrowid)
            for url, title in sources:
                self.conn.execute(
                    "INSERT INTO research_source (session_id, url, title) VALUES (?, ?, ?)",
                    (session_id, url[:300], title[:160]),
                )
            for name, topic in skills:
                self.conn.execute(
                    "INSERT INTO skill_tag (session_id, name, topic) VALUES (?, ?, ?)",
                    (session_id, name[:40], topic),
                )
            for item in items:
                rubric = [
                    {"label": point.label, "keywords": list(point.keywords)}
                    for point in item.rubric
                ]
                self.conn.execute(
                    """
                    INSERT INTO draft_item (
                        session_id, question_id, topic, kind, difficulty, prompt, choices,
                        answer, explanation, rubric, tags, origin
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'research_generated')
                    """,
                    (
                        session_id,
                        item.id,
                        item.topic,
                        item.kind,
                        item.difficulty,
                        item.prompt,
                        json.dumps(list(item.choices), ensure_ascii=False),
                        item.answer,
                        item.explanation,
                        json.dumps(rubric, ensure_ascii=False),
                        json.dumps(list(item.tags), ensure_ascii=False),
                    ),
                )
            for bias in biases:
                self.conn.execute(
                    """
                    INSERT INTO plan_bias (
                        session_id, topic, boost, starts_on, full_until, expires_on
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        bias["topic"],
                        bias["boost"],
                        bias["starts_on"],
                        bias["full_until"],
                        bias["expires_on"],
                    ),
                )
        return session_id

    def save_research_items(self, session_id: int, items: list[Question]) -> None:
        with self.conn:
            for item in items:
                rubric = [
                    {"label": point.label, "keywords": list(point.keywords)}
                    for point in item.rubric
                ]
                self.conn.execute(
                    """
                    INSERT INTO draft_item (
                        session_id, question_id, topic, kind, difficulty, prompt, choices,
                        answer, explanation, rubric, tags, origin
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'research_generated')
                    """,
                    (
                        session_id,
                        item.id,
                        item.topic,
                        item.kind,
                        item.difficulty,
                        item.prompt,
                        json.dumps(list(item.choices), ensure_ascii=False),
                        item.answer,
                        item.explanation,
                        json.dumps(rubric, ensure_ascii=False),
                        json.dumps(list(item.tags), ensure_ascii=False),
                    ),
                )

    def research_sessions(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM research_session ORDER BY id").fetchall())

    def research_counts(self) -> dict[str, int]:
        counts = {}
        for table in ("research_session", "research_source", "skill_tag", "draft_item", "plan_bias"):
            row = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            counts[table] = int(row["n"])
        return counts

    def clear_research(self, session_id: int | None = None) -> int:
        with self.conn:
            if session_id is None:
                sessions = self.research_counts()["research_session"]
                for table in ("plan_bias", "draft_item", "skill_tag", "research_source", "research_session"):
                    self.conn.execute(f"DELETE FROM {table}")
                return sessions
            self.conn.execute("DELETE FROM plan_bias WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM draft_item WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM skill_tag WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM research_source WHERE session_id = ?", (session_id,))
            cursor = self.conn.execute("DELETE FROM research_session WHERE id = ?", (session_id,))
            return int(cursor.rowcount)

    def bias_rows(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM plan_bias ORDER BY id").fetchall())

    def load_draft_questions(self) -> list[Question]:
        rows = self.conn.execute("SELECT * FROM draft_item ORDER BY id").fetchall()
        questions: list[Question] = []
        for row in rows:
            raw_rubric = json.loads(row["rubric"])
            rubric = tuple(
                RubricPoint(str(point["label"]), tuple(point["keywords"]))
                for point in raw_rubric
            )
            questions.append(
                Question(
                    id=row["question_id"],
                    topic=row["topic"],
                    difficulty=int(row["difficulty"]),
                    prompt=row["prompt"],
                    choices=tuple(json.loads(row["choices"])),
                    answer=int(row["answer"]),
                    explanation=row["explanation"],
                    kind=row["kind"],
                    tags=tuple(json.loads(row["tags"])),
                    rubric=rubric,
                )
            )
        return questions

    def research_detail(self, session_id: int) -> dict | None:
        session = self.conn.execute(
            "SELECT * FROM research_session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return None
        return {
            "id": session["id"],
            "label": session["label"],
            "created_at": session["created_at"],
            "sources": [
                {"url": row["url"], "title": row["title"]}
                for row in self.conn.execute(
                    "SELECT url, title FROM research_source WHERE session_id = ? ORDER BY id",
                    (session_id,),
                )
            ],
            "skills": [
                {"name": row["name"], "topic": row["topic"]}
                for row in self.conn.execute(
                    "SELECT name, topic FROM skill_tag WHERE session_id = ? ORDER BY id",
                    (session_id,),
                )
            ],
            "items": [
                {"question_id": row["question_id"], "prompt": row["prompt"], "origin": row["origin"]}
                for row in self.conn.execute(
                    "SELECT question_id, prompt, origin FROM draft_item WHERE session_id = ? ORDER BY id",
                    (session_id,),
                )
            ],
        }

    def save_learner_habits(self, minutes: int, style: str, weak: list[str] | None) -> None:
        """Store minutes and practice style. ``weak is None`` leaves the baseline."""
        now = utc_now()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO learner_model (id, minutes_per_day, practice_style, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    minutes_per_day = excluded.minutes_per_day,
                    practice_style = excluded.practice_style,
                    updated_at = excluded.updated_at
                """,
                (minutes, style, now),
            )
            if weak is None:
                return
            self.conn.execute("DELETE FROM learner_baseline")
            for topic in weak:
                if topic not in TOPICS:
                    raise ValueError(f"unknown topic {topic}")
                self.conn.execute(
                    "INSERT INTO learner_baseline (topic, stance) VALUES (?, 'weak')",
                    (topic,),
                )

    def replace_learner_source(self, kind: str, label: str, skills: list[tuple[str, str]]) -> None:
        """Replace one paste kind. Skill names are lexicon hits, never the note."""
        if kind not in SOURCE_KINDS:
            raise ValueError("source kind must be resume, jd, or notes")
        now = utc_now()
        with self.conn:
            rows = self.conn.execute(
                "SELECT id FROM learner_source WHERE kind = ?",
                (kind,),
            ).fetchall()
            for row in rows:
                self.conn.execute("DELETE FROM learner_skill WHERE source_id = ?", (row["id"],))
            self.conn.execute("DELETE FROM learner_source WHERE kind = ?", (kind,))
            if not skills:
                return
            cursor = self.conn.execute(
                "INSERT INTO learner_source (kind, label, created_at) VALUES (?, ?, ?)",
                (kind, label[:40], now),
            )
            source_id = int(cursor.lastrowid)
            for name, topic in skills:
                if topic not in TOPICS:
                    raise ValueError(f"unknown topic {topic}")
                self.conn.execute(
                    "INSERT INTO learner_skill (source_id, name, topic) VALUES (?, ?, ?)",
                    (source_id, name[:40], topic),
                )

    def get_learner(self) -> LearnerModel | None:
        row = self.conn.execute("SELECT * FROM learner_model WHERE id = 1").fetchone()
        if row is None:
            return None
        weak_rows = self.conn.execute(
            "SELECT topic FROM learner_baseline ORDER BY id"
        ).fetchall()
        skill_rows = self.conn.execute(
            """
            SELECT learner_skill.id, learner_skill.source_id, learner_source.kind,
                   learner_skill.name, learner_skill.topic
            FROM learner_skill
            JOIN learner_source ON learner_source.id = learner_skill.source_id
            ORDER BY learner_skill.id
            """
        ).fetchall()
        return LearnerModel(
            minutes_per_day=int(row["minutes_per_day"]),
            practice_style=row["practice_style"],
            self_weak=tuple(item["topic"] for item in weak_rows),
            skills=tuple(
                LearnerSkill(
                    id=int(item["id"]),
                    source_id=int(item["source_id"]),
                    kind=item["kind"],
                    name=item["name"],
                    topic=item["topic"],
                )
                for item in skill_rows
            ),
        )

    def set_plan_minutes(self, plan_id: int, minutes: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE study_plan SET daily_minutes = ? WHERE id = ?",
                (minutes, plan_id),
            )

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
