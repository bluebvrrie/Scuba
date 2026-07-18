"""
progress_tracker.py
====================
Responsibility: PROGRESS TRACKING.

Stores a student's history of graded quiz attempts (EvaluationResults)
and derives longitudinal insights from it:

  - overall score trend (improving / declining / stable)
  - per-topic mastery trend over time
  - which topics are now mastered vs. still need work
  - simple JSON-file persistence, so history survives across sessions
    (swap `JsonFileStore` for a DB-backed store in production without
    touching the rest of the class).
"""

import json
import statistics
from pathlib import Path
from typing import List, Dict, Optional, Any

from models import EvaluationResult


class ProgressTracker:
    """Keeps a running history of quiz results for one student and
    summarizes progress over time."""

    def __init__(self, storage_path: Optional[str] = None, mastery_threshold: float = 0.8):
        """
        Args:
            storage_path: path to a JSON file used to persist history.
                If it exists, history is loaded from it. If None, the
                tracker is in-memory only (useful for tests).
            mastery_threshold: topic accuracy at/above this (on the most
                recent attempt touching that topic) counts as "mastered".
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.mastery_threshold = mastery_threshold
        self.history: List[Dict[str, Any]] = []
        if self.storage_path and self.storage_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        with open(self.storage_path, "r", encoding="utf-8") as f:
            self.history = json.load(f)

    def _save(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_evaluation(self, result: EvaluationResult) -> None:
        """Record a new graded quiz attempt and persist it."""
        self.history.append(result.to_dict())
        self._save()

    def get_history(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return raw history, optionally filtered to attempts touching a topic."""
        if topic is None:
            return list(self.history)
        return [h for h in self.history if topic in h.get("topic_scores", {})]

    def topic_mastery_trend(self, topic: str) -> List[Dict[str, Any]]:
        """Chronological list of (timestamp, accuracy) for a single topic."""
        trend = []
        for h in self.history:
            if topic in h.get("topic_scores", {}):
                trend.append({"timestamp": h["timestamp"], "accuracy": h["topic_scores"][topic]})
        return trend

    def overall_progress(self) -> Dict[str, Any]:
        """
        Summarize progress across all recorded attempts.

        Returns a dict with:
            total_quizzes, average_score, latest_score, score_trend,
            mastered_topics, topics_needing_work, topic_latest_scores
        """
        if not self.history:
            return {
                "total_quizzes": 0,
                "average_score": None,
                "latest_score": None,
                "score_trend": "no_data",
                "mastered_topics": [],
                "topics_needing_work": [],
                "topic_latest_scores": {},
            }

        scores = [h["score"] for h in self.history]
        average_score = round(statistics.mean(scores), 2)
        latest_score = scores[-1]
        score_trend = self._score_trend(scores)

        # Most recent accuracy seen per topic, across all attempts.
        topic_latest_scores: Dict[str, float] = {}
        for h in self.history:  # chronological, so later entries overwrite earlier
            for topic, acc in h.get("topic_scores", {}).items():
                topic_latest_scores[topic] = acc

        mastered = sorted(
            t for t, acc in topic_latest_scores.items() if acc >= self.mastery_threshold
        )
        needing_work = sorted(
            t for t, acc in topic_latest_scores.items() if acc < self.mastery_threshold
        )

        return {
            "total_quizzes": len(self.history),
            "average_score": average_score,
            "latest_score": latest_score,
            "score_trend": score_trend,
            "mastered_topics": mastered,
            "topics_needing_work": needing_work,
            "topic_latest_scores": topic_latest_scores,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _score_trend(scores: List[float], window: int = 3) -> str:
        """
        Compare the average of the last `window` attempts to the average
        of the attempts before that. Requires at least 2 attempts to say
        anything more specific than 'stable'.
        """
        if len(scores) < 2:
            return "stable"

        recent = scores[-window:]
        prior = scores[:-window] if len(scores) > window else scores[: len(scores) // 2] or scores[:1]

        recent_avg = statistics.mean(recent)
        prior_avg = statistics.mean(prior)
        delta = recent_avg - prior_avg

        if delta > 3:
            return "improving"
        if delta < -3:
            return "declining"
        return "stable"
