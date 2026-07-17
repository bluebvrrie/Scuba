"""
Core engine for the Learning Memory & Analytics Module.

`LearningMemoryModule` is the single public entry point applications
(e.g. NitroStack Studio) should instantiate. It composes:

  * `SQLiteStorage`  -- persistence
  * `utils.py`       -- scoring / streak / recommendation logic
  * `models.py`      -- validated request/response schemas

and exposes exactly the API surface requested:

    create_student()
    get_student()
    save_learning_session()
    save_quiz_result()
    update_progress()
    get_progress()
    generate_learning_report()
    recommend_next_topics()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import utils
from .exceptions import InvalidDataError, LearningMemoryError, StudentNotFoundError
from .models import (
    LearningSession,
    MasteryLevel,
    ProgressSummary,
    QuizResult,
    StudentProfile,
    UploadedDocument,
)
from .storage import SQLiteStorage

logger = logging.getLogger("learning_memory.core")
if not logger.handlers:
    # Sensible default so the module logs usefully even if the host
    # application hasn't configured logging itself.
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class LearningMemoryModule:
    """Facade providing the full Learning Memory & Analytics API."""

    def __init__(self, db_path: str = "learning_memory.db") -> None:
        self.storage = SQLiteStorage(db_path=db_path)
        logger.info("LearningMemoryModule ready (db=%s)", db_path)

    # ----------------------------------------------------------------
    # Student profile management
    # ----------------------------------------------------------------

    def create_student(
        self,
        name: str,
        email: Optional[str] = None,
        grade_level: Optional[str] = None,
        curriculum_topics: Optional[List[str]] = None,
    ) -> StudentProfile:
        """Create and persist a new student profile.

        Raises:
            InvalidDataError: if `name` is empty/blank.
            LearningMemoryError: on unexpected persistence failure.
        """
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
        except Exception as exc:  # defensive: never leak raw exceptions
            logger.exception("Failed to create student")
            raise LearningMemoryError(f"Could not create student: {exc}") from exc

    def get_student(self, student_id: str) -> StudentProfile:
        """Fetch a student profile by id.

        Raises:
            StudentNotFoundError: if no such student exists.
        """
        return self.storage.get_student(student_id)

    # ----------------------------------------------------------------
    # Learning history
    # ----------------------------------------------------------------

    def save_learning_session(
        self,
        student_id: str,
        topic: str,
        start_time,
        end_time,
        document_ids: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> LearningSession:
        """Record a study session for a student.

        Raises:
            StudentNotFoundError: if `student_id` doesn't exist.
            InvalidDataError: if end_time is before start_time or topic empty.
        """
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
        """Record metadata for a document a student uploaded to study from."""
        self._require_student(student_id)
        if not filename or not filename.strip():
            raise InvalidDataError("filename must not be empty.")
        doc = UploadedDocument(student_id=student_id, filename=filename.strip(), topic=topic)
        self.storage.insert_document(doc)
        logger.info("Saved uploaded document %s for student %s", doc.doc_id, student_id)
        return doc

    # ----------------------------------------------------------------
    # Quiz history
    # ----------------------------------------------------------------

    def save_quiz_result(
        self,
        student_id: str,
        topic: str,
        total_questions: int,
        correct_answers: int,
        difficulty: str = "medium",
    ) -> QuizResult:
        """Record a quiz attempt and immediately refresh the student's
        progress snapshot (per the 'update progress after every quiz'
        requirement).

        Raises:
            StudentNotFoundError: if `student_id` doesn't exist.
            InvalidDataError: on malformed question/answer counts.
        """
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

        # Requirement: "Update progress after every quiz".
        self.update_progress(student_id)
        return quiz

    # ----------------------------------------------------------------
    # Progress tracking
    # ----------------------------------------------------------------

    def update_progress(self, student_id: str) -> ProgressSummary:
        """Recompute and return the full progress snapshot for a student.

        This is the single source of truth for completed/weak/strong
        topics, streak, learning time, and per-topic progress %. It is
        idempotent and safe to call as often as needed (e.g. after every
        quiz, or on-demand from a dashboard).
        """
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)

        mastery_map = utils.compute_all_topic_mastery(
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

        recommended = utils.recommend_next_topics(
            mastery_map, student.curriculum_topics, limit=5
        )

        summary = ProgressSummary(
            student_id=student_id,
            completed_topics=completed,
            weak_topics=weak,
            strong_topics=strong,
            average_score=utils.compute_average_score(quizzes),
            learning_streak=utils.compute_learning_streak(sessions, quizzes),
            learning_time=utils.compute_total_learning_time(sessions),
            progress=progress_pct,
            recommended_topics=recommended,
        )
        logger.info(
            "Progress updated for %s: %d completed, %d weak, %d strong topics",
            student_id, len(completed), len(weak), len(strong),
        )
        return summary

    def get_progress(self, student_id: str) -> ProgressSummary:
        """Return the current progress snapshot (recomputed fresh from
        stored history, so it's always accurate without needing a
        separate cache-invalidation step)."""
        return self.update_progress(student_id)

    # ----------------------------------------------------------------
    # Recommendations
    # ----------------------------------------------------------------

    def recommend_next_topics(self, student_id: str, limit: int = 3) -> List[str]:
        """Return the top `limit` recommended next topics for a student."""
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)
        mastery_map = utils.compute_all_topic_mastery(
            quizzes, sessions, student.curriculum_topics
        )
        return utils.recommend_next_topics(mastery_map, student.curriculum_topics, limit=limit)

    # ----------------------------------------------------------------
    # Reporting / analytics
    # ----------------------------------------------------------------

    def generate_learning_report(self, student_id: str) -> Dict[str, Any]:
        """Generate the full learning report for a student, matching the
        module's canonical output schema:

            {
              student_profile, completed_topics, weak_topics, strong_topics,
              average_score, learning_streak, learning_time, progress,
              recommended_topics, analytics_report
            }

        `analytics_report` additionally bundles topic-wise mastery detail,
        learning trends, performance analytics, and a progress summary --
        i.e. everything requested under "Generate: ...".
        """
        student = self._require_student(student_id)
        sessions = self.storage.get_sessions(student_id)
        quizzes = self.storage.get_quiz_results(student_id)
        documents = self.storage.get_documents(student_id)

        mastery_map = utils.compute_all_topic_mastery(
            quizzes, sessions, student.curriculum_topics
        )
        progress = self.update_progress(student_id)

        topic_wise_mastery = {
            topic: tm.model_dump() for topic, tm in mastery_map.items()
        }
        learning_trends = utils.build_learning_trends(sessions, quizzes)

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
        # Serialize best_topic (a TopicMastery or None) safely.
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

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    def _require_student(self, student_id: str) -> StudentProfile:
        """Fetch a student or raise StudentNotFoundError -- used to
        fail fast/clearly before any write or computation."""
        try:
            return self.storage.get_student(student_id)
        except StudentNotFoundError:
            logger.warning("Operation attempted on unknown student_id=%s", student_id)
            raise
