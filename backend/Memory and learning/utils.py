"""
Business-logic helpers: mastery classification, streak calculation,
topic-wise analytics, and next-topic recommendation.

Kept separate from `core.py` so the scoring/streak/recommendation
rules can be unit-tested and tuned in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Dict, List, Optional, Sequence

from .models import LearningSession, MasteryLevel, QuizResult, TopicMastery

# Tunable thresholds -- adjust to change grading strictness.
WEAK_THRESHOLD = 60.0       # average_score below this => weak topic
STRONG_THRESHOLD = 80.0     # average_score at/above this => strong topic
COMPLETION_THRESHOLD = 75.0  # average_score at/above this (with min attempts) => completed
MIN_ATTEMPTS_FOR_COMPLETION = 1


def classify_mastery(average_score: float) -> MasteryLevel:
    """Map a numeric average score to a qualitative mastery bucket."""
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
    """Aggregate all quiz attempts and study sessions for one topic into
    a single TopicMastery snapshot."""
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
    """Compute per-topic mastery for every topic the student has touched,
    plus any curriculum topics not yet attempted (so they show up as
    'unrated' / recommendable)."""
    topics = set(q.topic for q in quiz_results) | set(s.topic for s in sessions)
    if curriculum_topics:
        topics |= set(curriculum_topics)
    return {t: build_topic_mastery(t, quiz_results, sessions) for t in sorted(topics)}


def compute_learning_streak(
    sessions: Sequence[LearningSession],
    quiz_results: Sequence[QuizResult],
    reference_date: Optional[datetime] = None,
) -> int:
    """Count consecutive days (ending today or yesterday) with at least
    one learning session or quiz attempt.

    If there was no activity today, the streak still counts as long as
    yesterday had activity (so a student doesn't lose their streak the
    moment midnight passes, only after a full missed day).
    """
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
    # If nothing happened today, start counting from yesterday instead --
    # a streak isn't broken until a full day passes with no activity.
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
    """Total learning time across all sessions, in minutes."""
    return round(sum(s.duration_minutes for s in sessions), 2)


def compute_average_score(quiz_results: Sequence[QuizResult]) -> float:
    """Overall average quiz score (0-100) across all topics/attempts."""
    if not quiz_results:
        return 0.0
    return round(mean(q.score for q in quiz_results), 2)


def recommend_next_topics(
    topic_mastery: Dict[str, TopicMastery],
    curriculum_topics: Optional[Sequence[str]] = None,
    limit: int = 3,
) -> List[str]:
    """Recommend the next topics a student should study.

    Priority order:
      1. Weak topics already attempted (need reinforcement) -- lowest
         average score first.
      2. Curriculum topics never attempted (new material) -- in
         curriculum order.
      3. If no curriculum is defined, fall back to any 'unrated' topics
         already on record.

    This mirrors a common spaced-repetition-adjacent heuristic: shore up
    weak spots before piling on new material, but don't starve progress
    if everything so far is strong.
    """
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
    """Daily time-series of study minutes and average quiz score for the
    last `days` days -- useful for plotting learning trends over time."""
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
