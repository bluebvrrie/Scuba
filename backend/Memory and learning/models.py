"""
Pydantic data models for the Learning Memory & Analytics Module.

Every entity that flows into or out of the module (student profiles,
learning sessions, quiz results, uploaded documents, and derived
analytics) is represented as a validated Pydantic model. This gives us:

  * Type-safe inputs/outputs (caught at construction time, not later).
  * Free serialization via `.model_dump()` / `.model_dump_json()`.
  * Self-documenting schemas for API consumers such as NitroStack Studio.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware 'now' helper, used as a default_factory everywhere."""
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    """Generate a short, prefixed unique id (e.g. 'stu_9c1f...')."""
    return f"{prefix}_{uuid4().hex[:12]}"


class MasteryLevel(str, Enum):
    """Qualitative classification of a student's grasp of a topic."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    UNRATED = "unrated"  # no data yet


# --------------------------------------------------------------------------
# Core input entities
# --------------------------------------------------------------------------


class StudentProfile(BaseModel):
    """A single student's identity and enrollment metadata."""

    student_id: str = Field(default_factory=lambda: _new_id("stu"))
    name: str
    email: Optional[str] = None
    grade_level: Optional[str] = None
    # Optional target curriculum. If provided, completion %/recommendations
    # are computed against this list; otherwise they are inferred from
    # whatever topics the student has actually engaged with.
    curriculum_topics: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class LearningSession(BaseModel):
    """A single study session (e.g. reading a document, watching a lesson)."""

    session_id: str = Field(default_factory=lambda: _new_id("sess"))
    student_id: str
    topic: str
    start_time: datetime
    end_time: datetime
    document_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        """Derived session length in minutes (never negative)."""
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
        """Percentage score 0-100 for this attempt."""
        if self.total_questions <= 0:
            return 0.0
        return round((self.correct_answers / self.total_questions) * 100, 2)


class UploadedDocument(BaseModel):
    """Metadata for a document a student has uploaded to study from."""

    doc_id: str = Field(default_factory=lambda: _new_id("doc"))
    student_id: str
    topic: Optional[str] = None
    filename: str
    uploaded_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------
# Derived / output entities
# --------------------------------------------------------------------------


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
    """The canonical progress snapshot for a student, returned by
    `get_progress()` / `update_progress()`."""

    student_id: str
    completed_topics: List[str] = Field(default_factory=list)
    weak_topics: List[str] = Field(default_factory=list)
    strong_topics: List[str] = Field(default_factory=list)
    average_score: float = 0.0
    learning_streak: int = 0
    learning_time: float = 0.0  # total minutes, all-time
    progress: Dict[str, float] = Field(default_factory=dict)  # topic -> % mastery
    recommended_topics: List[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utcnow)
