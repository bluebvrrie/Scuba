"""
planner.py
==========
Responsibility: STUDY PLAN GENERATION.

Turns an EvaluationResult + progress summary + learning goals into a
concrete plan of action:

  - generate_daily_plan()      -> what to study today
  - generate_weekly_plan()     -> a 7-day rolling plan
  - generate_revision_schedule() -> spaced-repetition dates for weak topics
  - generate_recommendations() -> short adaptive coaching tips

Design notes
------------
Time allocation is weak-topic-first: weak topics get the largest slice
of study time, strong topics get light maintenance review, and any
topics tied to the student's stated learning goals that haven't shown
up yet get an "explore" slot. Revision uses a simplified spaced-repetition
curve (1, 3, 7, 14 days) similar in spirit to SM-2, without the full
per-card ease-factor bookkeeping.
"""

from datetime import date, timedelta
from typing import List, Dict, Optional, Any

from models import EvaluationResult

# Simplified spaced-repetition intervals (days after first review).
DEFAULT_REVISION_INTERVALS = [1, 3, 7, 14]


class StudyPlanner:
    """Generates daily/weekly study plans, revision schedules and
    adaptive recommendations from evaluation + progress data."""

    def __init__(self, default_minutes_per_day: int = 60):
        self.default_minutes_per_day = default_minutes_per_day

    # ------------------------------------------------------------------
    # Daily plan
    # ------------------------------------------------------------------
    def generate_daily_plan(
        self,
        weak_topics: List[str],
        strong_topics: List[str],
        learning_goals: Optional[List[str]] = None,
        minutes_available: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build a single day's plan. Time budget split:
            60% weak topics (capped so no block is absurdly long)
            20% strong topics (maintenance/spaced review)
            20% new/goal topics not yet attempted
        """
        minutes = minutes_available or self.default_minutes_per_day
        learning_goals = learning_goals or []
        goal_topics = [g for g in learning_goals if g not in weak_topics and g not in strong_topics]

        blocks: List[Dict[str, Any]] = []

        weak_minutes = round(minutes * 0.6)
        strong_minutes = round(minutes * 0.2)
        goal_minutes = minutes - weak_minutes - strong_minutes

        blocks.extend(self._time_blocks(weak_topics, weak_minutes, "focused_practice"))
        blocks.extend(self._time_blocks(strong_topics, strong_minutes, "maintenance_review"))
        blocks.extend(self._time_blocks(goal_topics, goal_minutes, "exploration"))

        return {
            "date": date.today().isoformat(),
            "total_minutes": minutes,
            "blocks": blocks,
        }

    # ------------------------------------------------------------------
    # Weekly plan
    # ------------------------------------------------------------------
    def generate_weekly_plan(
        self,
        weak_topics: List[str],
        strong_topics: List[str],
        learning_goals: Optional[List[str]] = None,
        minutes_per_day: Optional[int] = None,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Build a rolling 7-day plan:
          - Weak topics are rotated across the week so each gets repeated
            exposure (better for retention than cramming one topic once).
          - Every 3rd day is a lighter "review & quiz" day mixing strong
            + previously-covered weak topics.
          - One day per week is reserved for a full-length mock quiz.
        """
        minutes_per_day = minutes_per_day or self.default_minutes_per_day
        learning_goals = learning_goals or []
        goal_topics = [g for g in learning_goals if g not in weak_topics and g not in strong_topics]

        week: List[Dict[str, Any]] = []
        start = date.today()

        for i in range(days):
            day_date = start + timedelta(days=i)
            weekday_label = day_date.strftime("%A")

            if i == days - 1:
                # Last day of the week: mock quiz / full assessment.
                week.append(
                    {
                        "date": day_date.isoformat(),
                        "day": weekday_label,
                        "focus": "mock_quiz",
                        "blocks": [
                            {
                                "topic": "mixed_review",
                                "activity": "full_length_mock_quiz",
                                "minutes": minutes_per_day,
                            }
                        ],
                    }
                )
                continue

            if weak_topics and (i + 1) % 3 == 0:
                # Light review day.
                topics_today = (weak_topics + strong_topics)[:2] or ["general_review"]
                activity = "review_and_quiz"
            elif weak_topics:
                # Rotate through weak topics, one/two per day.
                topics_today = self._rotate(weak_topics, i, count=2)
                activity = "focused_practice"
            else:
                topics_today = self._rotate(goal_topics or strong_topics, i, count=2)
                activity = "exploration"

            blocks = self._time_blocks(topics_today, minutes_per_day, activity)
            week.append(
                {
                    "date": day_date.isoformat(),
                    "day": weekday_label,
                    "focus": activity,
                    "blocks": blocks,
                }
            )

        return week

    # ------------------------------------------------------------------
    # Revision schedule (spaced repetition)
    # ------------------------------------------------------------------
    def generate_revision_schedule(
        self,
        weak_topics: List[str],
        start_date: Optional[date] = None,
        intervals: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        For each weak topic, schedule spaced-repetition review dates
        (default: +1, +3, +7, +14 days from today). This spreads out
        recall practice for maximum long-term retention.
        """
        start_date = start_date or date.today()
        intervals = intervals or DEFAULT_REVISION_INTERVALS

        schedule = []
        for topic in weak_topics:
            reviews = [
                {"date": (start_date + timedelta(days=offset)).isoformat(), "interval_day": offset}
                for offset in intervals
            ]
            schedule.append({"topic": topic, "reviews": reviews})
        return schedule

    # ------------------------------------------------------------------
    # Adaptive recommendations
    # ------------------------------------------------------------------
    def generate_recommendations(
        self,
        evaluation: EvaluationResult,
        progress_summary: Dict[str, Any],
        learning_goals: Optional[List[str]] = None,
    ) -> List[str]:
        """Short, human-readable coaching tips derived from the latest
        evaluation, longer-term progress, and stated goals."""
        recs: List[str] = []
        learning_goals = learning_goals or []

        if evaluation.weak_topics:
            recs.append(
                "Prioritize focused practice on: " + ", ".join(evaluation.weak_topics) + "."
            )
        if evaluation.strong_topics:
            recs.append(
                "Maintain strength in " + ", ".join(evaluation.strong_topics)
                + " with brief periodic review rather than heavy new study time."
            )

        if evaluation.confidence_label == "low":
            recs.append(
                "Confidence in this topic breakdown is low (small sample size or "
                "inconsistent performance) — take another quiz to sharpen the diagnosis."
            )

        trend = progress_summary.get("score_trend")
        if trend == "declining":
            recs.append(
                "Recent scores are trending down — consider shorter, more frequent "
                "sessions and revisiting fundamentals before adding new material."
            )
        elif trend == "improving":
            recs.append("Scores are trending upward — good pace, keep the current routine.")
        elif trend == "stable" and progress_summary.get("total_quizzes", 0) > 3:
            recs.append(
                "Scores have plateaued — try increasing difficulty or mixing in new "
                "topics to break through the plateau."
            )

        uncovered_goals = [
            g for g in learning_goals
            if g not in evaluation.topic_scores and g not in progress_summary.get("topic_latest_scores", {})
        ]
        if uncovered_goals:
            recs.append(
                "These learning goals haven't been assessed yet: "
                + ", ".join(uncovered_goals)
                + ". Include them in an upcoming quiz."
            )

        if not recs:
            recs.append("Performance is solid across the board — keep up regular practice.")

        return recs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _time_blocks(topics: List[str], total_minutes: int, activity: str) -> List[Dict[str, Any]]:
        """Split `total_minutes` evenly across `topics` into study blocks."""
        topics = [t for t in topics if t]
        if not topics or total_minutes <= 0:
            return []
        per_topic = max(5, round(total_minutes / len(topics)))  # min 5-minute blocks
        return [{"topic": t, "activity": activity, "minutes": per_topic} for t in topics]

    @staticmethod
    def _rotate(items: List[str], day_index: int, count: int = 2) -> List[str]:
        """Pick `count` items from `items`, rotating the starting point each day
        so topics get even, staggered coverage across the week."""
        if not items:
            return []
        n = len(items)
        start = (day_index * count) % n
        return [items[(start + i) % n] for i in range(min(count, n))]
