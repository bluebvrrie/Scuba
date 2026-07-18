"""
backend/database.py

Unified Database and Persistence Layer for Scuba.
Exposes the SQLite persistence, Pydantic models, exceptions, and analytics
business logic (mastery classification, learning streaks, trends, and recommendations).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterator, List, Optional, Sequence
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger("scuba.database")

# ==============================================================================
# Exceptions
# ==============================================================================

class LearningMemoryError(Exception):
    """Base class for all database/memory errors."""
    pass


class StudentNotFoundError(LearningMemoryError):
    """Raised when a student_id does not exist in storage."""
    def __init__(self, student_id: str):
        self.student_id = student_id
        super().__init__(f"Student '{student_id}' was not found.")


class InvalidDataError(LearningMemoryError):
    """Raised when input data fails validation before being persisted."""
    pass


class DatabaseError(LearningMemoryError):
    """Raised when a persistence-layer operation fails unexpectedly."""
    pass


# ==============================================================================
# Models
# ==============================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class MasteryLevel(str, Enum):
    """Qualitative classification of a student's grasp of a topic."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    UNRATED = "unrated"


class StudentProfile(BaseModel):
    """A student's identity and curriculum metadata."""
    student_id: str = Field(default_factory=lambda: _new_id("stu"))
    name: str
    email: Optional[str] = None
    grade_level: Optional[str] = None
    curriculum_topics: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class LearningSession(BaseModel):
    """A study session."""
    session_id: str = Field(default_factory=lambda: _new_id("sess"))
    student_id: str
    topic: str
    start_time: datetime
    end_time: datetime
    document_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        delta = (self.end_time - self.start_time).total_seconds() / 60.0
        return max(delta, 0.0)


class QuizResult(BaseModel):
    """The outcome of a single quiz attempt on a topic."""
    quiz_id: str = Field(default_factory=lambda: _new_id("quiz"))
    student_id: str
    topic: str
    total_questions: int
    correct_answers: int
    difficulty: str = "medium"
    timestamp: datetime = Field(default_factory=_utcnow)

    @property
    def score(self) -> float:
        if self.total_questions <= 0:
            return 0.0
        return round((self.correct_answers / self.total_questions) * 100, 2)


class UploadedDocument(BaseModel):
    """Metadata for a document a student has uploaded."""
    doc_id: str = Field(default_factory=lambda: _new_id("doc"))
    student_id: str
    topic: Optional[str] = None
    filename: str
    uploaded_at: datetime = Field(default_factory=_utcnow)


class TopicMastery(BaseModel):
    """Aggregated performance snapshot for one student on one topic."""
    topic: str
    attempts: int = 0
    average_score: float = 0.0
    best_score: float = 0.0
    last_practiced: Optional[datetime] = None
    total_minutes: float = 0.0
    mastery_level: MasteryLevel = MasteryLevel.UNRATED
    completed: bool = False


class ProgressSummary(BaseModel):
    """The progress snapshot for a student."""
    student_id: str
    completed_topics: List[str] = Field(default_factory=list)
    weak_topics: List[str] = Field(default_factory=list)
    strong_topics: List[str] = Field(default_factory=list)
    average_score: float = 0.0
    learning_streak: int = 0
    learning_time: float = 0.0  # total minutes
    progress: Dict[str, float] = Field(default_factory=dict)  # topic -> % mastery
    recommended_topics: List[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utcnow)


# ==============================================================================
# SQLite CRUD Storage
# ==============================================================================

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
    def __init__(self, db_path: str = "learning_memory.db") -> None:
        self.db_path = Path(db_path)
        self._init_schema()
        logger.info("SQLiteStorage initialized at %s", self.db_path.resolve())

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


# ==============================================================================
# Business Logic Helpers
# ==============================================================================

WEAK_THRESHOLD = 60.0
STRONG_THRESHOLD = 80.0
COMPLETION_THRESHOLD = 75.0
MIN_ATTEMPTS_FOR_COMPLETION = 1


def classify_mastery(average_score: float) -> MasteryLevel:
    if average_score >= STRONG_THRESHOLD:
        return MasteryLevel.STRONG
    if average_score < WEAK_THRESHOLD:
        return MasteryLevel.WEAK
    return MasteryLevel.MODERATE


def build_topic_mastery(
    topic: str,
    quiz_results: Sequence[QuizResult],
    sessions: Sequence[LearningSession],
) -> TopicMastery:
    topic_quizzes = [q for q in quiz_results if q.topic == topic]
    topic_sessions = [s for s in sessions if s.topic == topic]

    scores = [q.score for q in topic_quizzes]
    avg_score = round(mean(scores), 2) if scores else 0.0
    best_score = round(max(scores), 2) if scores else 0.0
    total_minutes = round(sum(s.duration_minutes for s in topic_sessions), 2)
    last_practiced: Optional[datetime] = None
    timestamps = [q.timestamp for q in topic_quizzes] + [s.end_time for s in topic_sessions]
    if timestamps:
        last_practiced = max(timestamps)

    mastery_level = classify_mastery(avg_score) if scores else MasteryLevel.UNRATED
    completed = (
        len(topic_quizzes) >= MIN_ATTEMPTS_FOR_COMPLETION
        and avg_score >= COMPLETION_THRESHOLD
    )

    return TopicMastery(
        topic=topic,
        attempts=len(topic_quizzes),
        average_score=avg_score,
        best_score=best_score,
        last_practiced=last_practiced,
        total_minutes=total_minutes,
        mastery_level=mastery_level,
        completed=completed,
    )


def compute_all_topic_mastery(
    quiz_results: Sequence[QuizResult],
    sessions: Sequence[LearningSession],
    curriculum_topics: Optional[Sequence[str]] = None,
) -> Dict[str, TopicMastery]:
    topics = set(q.topic for q in quiz_results) | set(s.topic for s in sessions)
    if curriculum_topics:
        topics |= set(curriculum_topics)
    return {t: build_topic_mastery(t, quiz_results, sessions) for t in sorted(topics)}


def compute_learning_streak(
    sessions: Sequence[LearningSession],
    quiz_results: Sequence[QuizResult],
    reference_date: Optional[datetime] = None,
) -> int:
    reference_date = reference_date or datetime.now(timezone.utc)
    activity_dates = set()
    for s in sessions:
        activity_dates.add(s.end_time.date())
    for q in quiz_results:
        activity_dates.add(q.timestamp.date())

    if not activity_dates:
        return 0

    today = reference_date.date()
    cursor = today
    if cursor not in activity_dates:
        cursor -= timedelta(days=1)
        if cursor not in activity_dates:
            return 0

    streak = 0
    while cursor in activity_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def compute_total_learning_time(sessions: Sequence[LearningSession]) -> float:
    return round(sum(s.duration_minutes for s in sessions), 2)


def compute_average_score(quiz_results: Sequence[QuizResult]) -> float:
    if not quiz_results:
        return 0.0
    return round(mean(q.score for q in quiz_results), 2)


def recommend_next_topics(
    topic_mastery: Dict[str, TopicMastery],
    curriculum_topics: Optional[Sequence[str]] = None,
    limit: int = 3,
) -> List[str]:
    weak = [
        tm for tm in topic_mastery.values() if tm.mastery_level == MasteryLevel.WEAK
    ]
    weak_sorted = sorted(weak, key=lambda tm: tm.average_score)
    recommendations: List[str] = [tm.topic for tm in weak_sorted]

    if curriculum_topics:
        attempted = {t for t, tm in topic_mastery.items() if tm.attempts > 0}
        unattempted = [t for t in curriculum_topics if t not in attempted]
        recommendations.extend(t for t in unattempted if t not in recommendations)
    else:
        unrated = [
            tm.topic
            for tm in topic_mastery.values()
            if tm.mastery_level == MasteryLevel.UNRATED and tm.topic not in recommendations
        ]
        recommendations.extend(unrated)

    return recommendations[:limit]


def build_learning_trends(
    sessions: Sequence[LearningSession],
    quiz_results: Sequence[QuizResult],
    days: int = 14,
) -> Dict[str, Dict[str, float]]:
    trend: Dict[str, Dict[str, float]] = {}
    today = datetime.now(timezone.utc).date()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        day_minutes = round(
            sum(s.duration_minutes for s in sessions if s.end_time.date() == day), 2
        )
        day_scores = [q.score for q in quiz_results if q.timestamp.date() == day]
        day_avg = round(mean(day_scores), 2) if day_scores else 0.0
        trend[key] = {"minutes_studied": day_minutes, "average_quiz_score": day_avg}
    return trend


# ==============================================================================
# Public Facade: LearningMemoryModule
# ==============================================================================

class LearningMemoryModule:
    def __init__(self, db_path: str = "learning_memory.db") -> None:
        self.storage = SQLiteStorage(db_path=db_path)
        logger.info("LearningMemoryModule ready (db=%s)", db_path)

    def create_student(
        self,
        name: str,
        email: Optional[str] = None,
        grade_level: Optional[str] = None,
        curriculum_topics: Optional[List[str]] = None,
    ) -> StudentProfile:
        if not name or not name.strip():
            raise InvalidDataError("Student name must not be empty.")
        try:
            student = StudentProfile(
                name=name.strip(),
                email=email,
                grade_level=grade_level,
                curriculum_topics=curriculum_topics or [],
            )
            self.storage.insert_student(student)
            logger.info("Created student '%s' (%s)", student.name, student.student_id)
            return student
        except LearningMemoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create student")
            raise LearningMemoryError(f"Could not create student: {exc}") from exc

    def get_student(self, student_id: str) -> StudentProfile:
        return self.storage.get_student(student_id)

    def save_learning_session(
        self,
        student_id: str,
        topic: str,
        start_time: datetime,
        end_time: datetime,
        document_ids: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> LearningSession:
        self._require_student(student_id)
        if not topic or not topic.strip():
            raise InvalidDataError("Session topic must not be empty.")
        if end_time < start_time:
            raise InvalidDataError("Session end_time cannot precede start_time.")

        session = LearningSession(
            student_id=student_id,
            topic=topic.strip(),
            start_time=start_time,
            end_time=end_time,
            document_ids=document_ids or [],
            notes=notes,
        )
        self.storage.insert_session(session)
        logger.info(
            "Saved learning session %s for student %s (topic=%s, %.1f min)",
            session.session_id, student_id, topic, session.duration_minutes,
        )
        return session

    def save_uploaded_document(
        self, student_id: str, filename: str, topic: Optional[str] = None
    ) -> UploadedDocument:
        self._require_student(student_id)
        if not filename or not filename.strip():
            raise InvalidDataError("filename must not be empty.")
        doc = UploadedDocument(student_id=student_id, filename=filename.strip(), topic=topic)
        self.storage.insert_document(doc)
        logger.info("Saved uploaded document %s for student %s", doc.doc_id, student_id)
        return doc

    def save_quiz_result(
        self,
        student_id: str,
        topic: str,
        total_questions: int,
        correct_answers: int,
        difficulty: str = "medium",
    ) -> QuizResult:
        self._require_student(student_id)
        if not topic or not topic.strip():
            raise InvalidDataError("Quiz topic must not be empty.")
        if total_questions <= 0:
            raise InvalidDataError("total_questions must be positive.")
        if not (0 <= correct_answers <= total_questions):
            raise InvalidDataError("correct_answers must be between 0 and total_questions.")

        quiz = QuizResult(
            student_id=student_id,
            topic=topic.strip(),
            total_questions=total_questions,
            correct_answers=correct_answers,
            difficulty=difficulty,
        )
        self.storage.insert_quiz_result(quiz)
        logger.info(
            "Saved quiz result %s for student %s (topic=%s, score=%.1f%%)",
            quiz.quiz_id, student_id, topic, quiz.score,
        )
        self.update_progress(student_id)
        return quiz

    def update_progress(self, student_id: str) -> ProgressSummary:
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)

        mastery_map = compute_all_topic_mastery(
            quizzes, sessions, student.curriculum_topics
        )

        completed = sorted(t for t, tm in mastery_map.items() if tm.completed)
        weak = sorted(
            t for t, tm in mastery_map.items() if tm.mastery_level == MasteryLevel.WEAK
        )
        strong = sorted(
            t for t, tm in mastery_map.items() if tm.mastery_level == MasteryLevel.STRONG
        )
        progress_pct = {t: tm.average_score for t, tm in mastery_map.items()}

        recommended = recommend_next_topics(
            mastery_map, student.curriculum_topics, limit=5
        )

        summary = ProgressSummary(
            student_id=student_id,
            completed_topics=completed,
            weak_topics=weak,
            strong_topics=strong,
            average_score=compute_average_score(quizzes),
            learning_streak=compute_learning_streak(sessions, quizzes),
            learning_time=compute_total_learning_time(sessions),
            progress=progress_pct,
            recommended_topics=recommended,
        )
        logger.info(
            "Progress updated for %s: %d completed, %d weak, %d strong topics",
            student_id, len(completed), len(weak), len(strong),
        )
        return summary

    def get_progress(self, student_id: str) -> ProgressSummary:
        return self.update_progress(student_id)

    def recommend_next_topics(self, student_id: str, limit: int = 3) -> List[str]:
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)
        mastery_map = compute_all_topic_mastery(
            quizzes, sessions, student.curriculum_topics
        )
        return recommend_next_topics(mastery_map, student.curriculum_topics, limit=limit)

    def generate_learning_report(self, student_id: str) -> Dict[str, Any]:
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)
        documents = self.storage.get_documents(student_id)

        mastery_map = compute_all_topic_mastery(
            quizzes, sessions, student.curriculum_topics
        )
        progress = self.update_progress(student_id)

        topic_wise_mastery = {
            topic: tm.model_dump() for topic, tm in mastery_map.items()
        }
        learning_trends = build_learning_trends(sessions, quizzes)

        performance_analytics = {
            "total_quizzes_taken": len(quizzes),
            "total_sessions": len(sessions),
            "total_documents_uploaded": len(documents),
            "overall_average_score": progress.average_score,
            "best_topic": max(
                mastery_map.values(), key=lambda tm: tm.average_score, default=None
            ),
            "topics_attempted": len([tm for tm in mastery_map.values() if tm.attempts > 0]),
            "topics_in_curriculum": len(student.curriculum_topics),
        }
        best = performance_analytics["best_topic"]
        performance_analytics["best_topic"] = best.model_dump() if best else None

        analytics_report = {
            "topic_wise_mastery": topic_wise_mastery,
            "learning_trends": learning_trends,
            "performance_analytics": performance_analytics,
            "progress_summary": progress.model_dump(),
        }

        report = {
            "student_profile": student.model_dump(),
            "completed_topics": progress.completed_topics,
            "weak_topics": progress.weak_topics,
            "strong_topics": progress.strong_topics,
            "average_score": progress.average_score,
            "learning_streak": progress.learning_streak,
            "learning_time": progress.learning_time,
            "progress": progress.progress,
            "recommended_topics": progress.recommended_topics,
            "analytics_report": analytics_report,
        }
        logger.info("Generated learning report for student %s", student_id)
        return report

    def _require_student(self, student_id: str) -> StudentProfile:
        try:
            return self.storage.get_student(student_id)
        except StudentNotFoundError:
            logger.warning("Operation attempted on unknown student_id=%s", student_id)
            raise
