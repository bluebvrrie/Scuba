"""
Learning Memory & Analytics Module
===================================

A self-contained learning-progress engine for adaptive learning platforms.

Public entry point: `LearningMemoryModule` (see core.py).

Compatible with NitroStack Studio -- instantiate `LearningMemoryModule`
and call its public API methods (create_student, save_learning_session,
save_quiz_result, update_progress, generate_learning_report, ...).
"""

from .core import LearningMemoryModule
from .models import (
    StudentProfile,
    LearningSession,
    QuizResult,
    UploadedDocument,
    TopicMastery,
    ProgressSummary,
)
from .exceptions import (
    LearningMemoryError,
    StudentNotFoundError,
    InvalidDataError,
    DatabaseError,
)

__all__ = [
    "LearningMemoryModule",
    "StudentProfile",
    "LearningSession",
    "QuizResult",
    "UploadedDocument",
    "TopicMastery",
    "ProgressSummary",
    "LearningMemoryError",
    "StudentNotFoundError",
    "InvalidDataError",
    "DatabaseError",
]

__version__ = "1.0.0"
