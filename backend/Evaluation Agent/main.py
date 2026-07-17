"""
main.py
=======
Orchestrator / integration entry point for the Evaluation & Planning Agent.

This is the piece a host application (e.g. NitroStack Studio) calls. It
wires together the four responsibility modules:

    quiz_generator   -> generate a quiz
    evaluation_agent -> grade an attempt, detect weak/strong topics, confidence
    progress_tracker -> persist history, compute longitudinal trends
    planner          -> turn all of the above into a study plan + recommendations

and returns exactly the JSON contract requested:

    {
      "score": ...,
      "weak_topics": [...],
      "strong_topics": [...],
      "progress": {...},
      "recommendations": [...],
      "study_plan": {...}
    }

Usage (see `if __name__ == "__main__"` at the bottom for a full demo):

    agent = EvaluationPlanningAgent(
        question_bank_path="sample_question_bank.json",
        student_id="student_123",
    )
    quiz = agent.generate_quiz(num_questions=8)
    # ... present quiz.to_student_view() to the student, collect answers ...
    result_json = agent.submit_answers(quiz, answers, learning_goals=["biology", "history"])
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any

from models import StudentAnswer, Quiz
from quiz_generator import QuizGenerator
from evaluation_agent import EvaluationAgent
from progress_tracker import ProgressTracker
from planner import StudyPlanner


class EvaluationPlanningAgent:
    """
    Top-level façade. This is the single object a host application needs
    to instantiate to use the whole system — it composes the four
    specialized modules and exposes a small, stable public API.
    """

    def __init__(
        self,
        question_bank_path: str,
        student_id: str,
        progress_dir: str = "./progress_data",
        weak_threshold: float = 0.5,
        strong_threshold: float = 0.8,
        minutes_per_day: int = 60,
    ):
        self.student_id = student_id
        self.quiz_generator = QuizGenerator.from_json_file(question_bank_path)
        self.evaluation_agent = EvaluationAgent(
            weak_threshold=weak_threshold, strong_threshold=strong_threshold
        )
        storage_path = str(Path(progress_dir) / f"{student_id}_history.json")
        self.progress_tracker = ProgressTracker(storage_path=storage_path)
        self.planner = StudyPlanner(default_minutes_per_day=minutes_per_day)

    # ------------------------------------------------------------------
    # Quiz generation
    # ------------------------------------------------------------------
    def generate_quiz(
        self,
        num_questions: int = 10,
        topics: Optional[List[str]] = None,
        adaptive: bool = True,
    ) -> Quiz:
        """
        Generate a new quiz. If `adaptive` is True and there is prior
        history, weak topics are over-sampled automatically.
        """
        weak_topics = None
        if adaptive:
            progress = self.progress_tracker.overall_progress()
            weak_topics = progress.get("topics_needing_work") or None
        return self.quiz_generator.generate_quiz(
            num_questions=num_questions, topics=topics, weak_topics=weak_topics
        )

    # ------------------------------------------------------------------
    # Evaluation + planning (the main contract method)
    # ------------------------------------------------------------------
    def submit_answers(
        self,
        quiz: Quiz,
        answers: List[StudentAnswer],
        learning_goals: Optional[List[str]] = None,
        minutes_per_day: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Grade a quiz attempt, update progress history, and build a fresh
        study plan + recommendations. Returns the exact JSON contract:

            {score, weak_topics, strong_topics, progress,
             recommendations, study_plan}
        """
        learning_goals = learning_goals or []

        # 1. Evaluate
        evaluation = self.evaluation_agent.evaluate(quiz, answers)

        # 2. Track progress
        self.progress_tracker.add_evaluation(evaluation)
        progress_summary = self.progress_tracker.overall_progress()

        # 3. Plan
        daily_plan = self.planner.generate_daily_plan(
            weak_topics=evaluation.weak_topics,
            strong_topics=evaluation.strong_topics,
            learning_goals=learning_goals,
            minutes_available=minutes_per_day,
        )
        weekly_plan = self.planner.generate_weekly_plan(
            weak_topics=evaluation.weak_topics,
            strong_topics=evaluation.strong_topics,
            learning_goals=learning_goals,
            minutes_per_day=minutes_per_day,
        )
        revision_schedule = self.planner.generate_revision_schedule(
            weak_topics=evaluation.weak_topics
        )
        recommendations = self.planner.generate_recommendations(
            evaluation=evaluation,
            progress_summary=progress_summary,
            learning_goals=learning_goals,
        )

        # 4. Assemble the required output contract
        return {
            "score": evaluation.score,
            "weak_topics": evaluation.weak_topics,
            "strong_topics": evaluation.strong_topics,
            "progress": progress_summary,
            "recommendations": recommendations,
            "study_plan": {
                "daily_plan": daily_plan,
                "weekly_plan": weekly_plan,
                "revision_schedule": revision_schedule,
            },
            # Extra diagnostic detail kept alongside the required contract
            # (harmless additive fields; host apps can ignore them).
            "_meta": {
                "confidence": evaluation.confidence,
                "confidence_label": evaluation.confidence_label,
                "quiz_id": evaluation.quiz_id,
                "timestamp": evaluation.timestamp,
            },
        }


# ==========================================================================
# Demo / manual test
# ==========================================================================
if __name__ == "__main__":
    BASE = Path(__file__).parent
    agent = EvaluationPlanningAgent(
        question_bank_path=str(BASE / "sample_question_bank.json"),
        student_id="demo_student",
        progress_dir=str(BASE / "progress_data"),
    )

    quiz = agent.generate_quiz(num_questions=8, adaptive=True)
    print(f"Generated quiz {quiz.quiz_id} with topics: {quiz.topic_distribution}\n")

    # Simulate a student attempt: get every algebra/history question wrong,
    # everything else right, to demonstrate weak-topic detection.
    simulated_answers = []
    for q in quiz.questions:
        if q.topic in ("algebra", "history"):
            wrong_options = [o for o in (q.options or []) if o != q.correct_answer]
            given = wrong_options[0] if wrong_options else "wrong"
        else:
            given = q.correct_answer
        simulated_answers.append(StudentAnswer(question_id=q.id, answer=given, time_taken_seconds=15))

    result = agent.submit_answers(
        quiz=quiz,
        answers=simulated_answers,
        learning_goals=["biology", "geometry", "statistics"],
        minutes_per_day=45,
    )

    print(json.dumps(result, indent=2))
