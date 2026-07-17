"""
evaluation_agent.py
====================
Responsibilities: QUIZ EVALUATION, SCORE CALCULATION, WEAK-TOPIC DETECTION,
CONFIDENCE ESTIMATION.

Given a Quiz (answer key) and the StudentAnswers submitted for it, this
module grades the attempt and produces an EvaluationResult:

    - overall score (0-100)
    - per-topic accuracy
    - weak topics   (accuracy below `weak_threshold`)
    - strong topics (accuracy at/above `strong_threshold`)
    - a confidence estimate (0-1) describing how reliable the topic
      classification is, based on sample size, score consistency and
      (if available) how quickly/consistently the student answered.
"""

import statistics
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from models import Quiz, StudentAnswer, QuestionResult, EvaluationResult, Difficulty


class EvaluationAgent:
    """Grades quiz attempts and detects strengths/weaknesses."""

    def __init__(self, weak_threshold: float = 0.5, strong_threshold: float = 0.8):
        """
        Args:
            weak_threshold: topic accuracy below this is flagged "weak".
            strong_threshold: topic accuracy at/above this is flagged "strong".
        """
        if not 0 <= weak_threshold < strong_threshold <= 1:
            raise ValueError("Require 0 <= weak_threshold < strong_threshold <= 1")
        self.weak_threshold = weak_threshold
        self.strong_threshold = strong_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, quiz: Quiz, answers: List[StudentAnswer]) -> EvaluationResult:
        """Grade a completed quiz attempt end to end."""
        answer_map: Dict[str, StudentAnswer] = {a.question_id: a for a in answers}

        results: List[QuestionResult] = []
        for question in quiz.questions:
            given = answer_map.get(question.id)
            student_answer = given.answer if given else None
            correct = self._is_correct(student_answer, question.correct_answer)
            results.append(
                QuestionResult(
                    question_id=question.id,
                    topic=question.topic,
                    difficulty=question.difficulty,
                    correct=correct,
                    student_answer=student_answer,
                    correct_answer=question.correct_answer,
                    time_taken_seconds=given.time_taken_seconds if given else None,
                )
            )

        score = self._calculate_score(results)
        topic_scores = self._topic_scores(results)
        weak_topics = [t for t, acc in topic_scores.items() if acc < self.weak_threshold]
        strong_topics = [t for t, acc in topic_scores.items() if acc >= self.strong_threshold]
        confidence, confidence_label = self._estimate_confidence(results, topic_scores)

        return EvaluationResult(
            quiz_id=quiz.quiz_id,
            timestamp=datetime.utcnow().isoformat(),
            total_questions=len(results),
            correct_count=sum(1 for r in results if r.correct),
            score=score,
            topic_scores=topic_scores,
            weak_topics=sorted(weak_topics),
            strong_topics=sorted(strong_topics),
            confidence=confidence,
            confidence_label=confidence_label,
            question_results=results,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_correct(student_answer: Optional[str], correct_answer: str) -> bool:
        if student_answer is None:
            return False  # unanswered counts as incorrect
        return str(student_answer).strip().lower() == str(correct_answer).strip().lower()

    @staticmethod
    def _calculate_score(results: List[QuestionResult]) -> float:
        if not results:
            return 0.0
        correct = sum(1 for r in results if r.correct)
        return round(100 * correct / len(results), 2)

    @staticmethod
    def _topic_scores(results: List[QuestionResult]) -> Dict[str, float]:
        by_topic: Dict[str, List[QuestionResult]] = {}
        for r in results:
            by_topic.setdefault(r.topic, []).append(r)
        return {
            topic: round(sum(1 for r in rs if r.correct) / len(rs), 3)
            for topic, rs in by_topic.items()
        }

    def _estimate_confidence(
        self, results: List[QuestionResult], topic_scores: Dict[str, float]
    ) -> Tuple[float, str]:
        """
        Confidence answers: "how much should we trust this weak/strong
        topic classification?" It blends three signals:

          1. Sample size   - more questions per topic => more trustworthy.
          2. Consistency   - low variance in per-topic accuracy suggests a
                              stable performance signal, not noise.
          3. Timing signal - if response times are available and roughly
                              consistent, that supports genuine (not
                              guessed/rushed) answers.

        Returns a (confidence 0-1, label) tuple.
        """
        if not results:
            return 0.0, "low"

        # 1) sample-size factor: saturate around ~5 questions/topic
        topics = set(r.topic for r in results)
        avg_per_topic = len(results) / max(len(topics), 1)
        sample_factor = min(avg_per_topic / 5.0, 1.0)

        # 2) consistency factor: low spread across topic accuracies = confident
        if len(topic_scores) > 1:
            spread = statistics.pstdev(list(topic_scores.values()))
            consistency_factor = max(0.0, 1.0 - spread)
        else:
            consistency_factor = 0.7  # single topic: neutral-ish confidence

        # 3) timing factor: only if timing data exists
        times = [r.time_taken_seconds for r in results if r.time_taken_seconds is not None]
        if len(times) >= 2:
            mean_t = statistics.mean(times)
            spread_t = statistics.pstdev(times)
            cv = (spread_t / mean_t) if mean_t > 0 else 1.0
            timing_factor = max(0.0, 1.0 - min(cv, 1.0))
        else:
            timing_factor = 0.6  # no data: neutral, doesn't penalize heavily

        confidence = round(
            0.5 * sample_factor + 0.3 * consistency_factor + 0.2 * timing_factor, 3
        )
        confidence = max(0.0, min(confidence, 1.0))

        if confidence >= 0.75:
            label = "high"
        elif confidence >= 0.45:
            label = "medium"
        else:
            label = "low"

        return confidence, label
