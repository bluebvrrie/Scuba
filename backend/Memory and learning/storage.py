"""
Persistence layer for the Learning Memory & Analytics Module.

Uses SQLite (via the stdlib `sqlite3` module) so the module has zero
external dependencies for storage and works as a single portable
`.db` file -- convenient for NitroStack Studio deployments and for
local development alike.

All complex/nested fields (lists, dicts) are stored as JSON text
columns. Timestamps are stored as ISO-8601 strings.

This module deliberately knows nothing about business logic (mastery
classification, streaks, recommendations, ...) -- it is a thin,
well-tested CRUD layer that `core.py` builds on.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Optional

from .exceptions import DatabaseError, StudentNotFoundError
from .models import LearningSession, QuizResult, StudentProfile, UploadedDocument

logger = logging.getLogger("learning_memory.storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT,
    grade_level     TEXT,
    curriculum_topics TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_sessions (
    session_id      TEXT PRIMARY KEY,
    student_id      TEXT NOT NULL,
    topic           TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    document_ids    TEXT NOT NULL DEFAULT '[]',
    notes           TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS quiz_results (
    quiz_id         TEXT PRIMARY KEY,
    student_id      TEXT NOT NULL,
    topic           TEXT NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_answers INTEGER NOT NULL,
    difficulty      TEXT NOT NULL DEFAULT 'medium',
    timestamp       TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS uploaded_documents (
    doc_id          TEXT PRIMARY KEY,
    student_id      TEXT NOT NULL,
    topic           TEXT,
    filename        TEXT NOT NULL,
    uploaded_at     TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_student ON learning_sessions(student_id);
CREATE INDEX IF NOT EXISTS idx_quiz_student ON quiz_results(student_id);
CREATE INDEX IF NOT EXISTS idx_docs_student ON uploaded_documents(student_id);
"""


class SQLiteStorage:
    """Thin CRUD wrapper around a SQLite database file."""

    def __init__(self, db_path: str = "learning_memory.db") -> None:
        self.db_path = Path(db_path)
        self._init_schema()
        logger.info("SQLiteStorage initialized at %s", self.db_path.resolve())

    # -- connection management -------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            logger.exception("Database operation failed")
            raise DatabaseError(str(exc)) from exc
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # -- students ----------------------------------------------------------

    def insert_student(self, student: StudentProfile) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO students
                   (student_id, name, email, grade_level, curriculum_topics, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    student.student_id,
                    student.name,
                    student.email,
                    student.grade_level,
                    json.dumps(student.curriculum_topics),
                    student.created_at.isoformat(),
                ),
            )

    def get_student(self, student_id: str) -> StudentProfile:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        if row is None:
            raise StudentNotFoundError(student_id)
        return StudentProfile(
            student_id=row["student_id"],
            name=row["name"],
            email=row["email"],
            grade_level=row["grade_level"],
            curriculum_topics=json.loads(row["curriculum_topics"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def student_exists(self, student_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        return row is not None

    # -- learning sessions ---------------------------------------------------

    def insert_session(self, session: LearningSession) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO learning_sessions
                   (session_id, student_id, topic, start_time, end_time, document_ids, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.session_id,
                    session.student_id,
                    session.topic,
                    session.start_time.isoformat(),
                    session.end_time.isoformat(),
                    json.dumps(session.document_ids),
                    session.notes,
                ),
            )

    def get_sessions(self, student_id: str) -> List[LearningSession]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM learning_sessions WHERE student_id = ? ORDER BY start_time",
                (student_id,),
            ).fetchall()
        return [
            LearningSession(
                session_id=r["session_id"],
                student_id=r["student_id"],
                topic=r["topic"],
                start_time=datetime.fromisoformat(r["start_time"]),
                end_time=datetime.fromisoformat(r["end_time"]),
                document_ids=json.loads(r["document_ids"]),
                notes=r["notes"],
            )
            for r in rows
        ]

    # -- quiz results --------------------------------------------------------

    def insert_quiz_result(self, quiz: QuizResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO quiz_results
                   (quiz_id, student_id, topic, total_questions, correct_answers, difficulty, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    quiz.quiz_id,
                    quiz.student_id,
                    quiz.topic,
                    quiz.total_questions,
                    quiz.correct_answers,
                    quiz.difficulty,
                    quiz.timestamp.isoformat(),
                ),
            )

    def get_quiz_results(self, student_id: str) -> List[QuizResult]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM quiz_results WHERE student_id = ? ORDER BY timestamp",
                (student_id,),
            ).fetchall()
        return [
            QuizResult(
                quiz_id=r["quiz_id"],
                student_id=r["student_id"],
                topic=r["topic"],
                total_questions=r["total_questions"],
                correct_answers=r["correct_answers"],
                difficulty=r["difficulty"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    # -- uploaded documents ----------------------------------------------------

    def insert_document(self, doc: UploadedDocument) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO uploaded_documents
                   (doc_id, student_id, topic, filename, uploaded_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    doc.doc_id,
                    doc.student_id,
                    doc.topic,
                    doc.filename,
                    doc.uploaded_at.isoformat(),
                ),
            )

    def get_documents(self, student_id: str) -> List[UploadedDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM uploaded_documents WHERE student_id = ? ORDER BY uploaded_at",
                (student_id,),
            ).fetchall()
        return [
            UploadedDocument(
                doc_id=r["doc_id"],
                student_id=r["student_id"],
                topic=r["topic"],
                filename=r["filename"],
                uploaded_at=datetime.fromisoformat(r["uploaded_at"]),
            )
            for r in rows
        ]
