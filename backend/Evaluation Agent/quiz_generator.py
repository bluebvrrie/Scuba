"""
quiz_generator.py
==================
Responsibility: QUIZ GENERATION.

Builds quizzes from a question bank. Supports:
  - random quizzes over any subset of topics
  - difficulty filtering
  - ADAPTIVE generation that over-samples a student's weak topics so
    practice time is spent where it matters most.

The question bank can be supplied as a list of dicts (e.g. loaded from
a JSON file or a database) or as a list of `models.Question` objects.
"""

import json
import random
import uuid
from collections import defaultdict
from typing import List, Dict, Optional, Iterable

from models import Question, Quiz, Difficulty


class QuestionBankError(Exception):
    """Raised when the question bank cannot satisfy a quiz request."""


class QuizGenerator:
    """Generates quizzes from an in-memory question bank."""

    def __init__(self, questions: Iterable[Question]):
        self.questions: List[Question] = list(questions)
        if not self.questions:
            raise QuestionBankError("Question bank is empty.")
        self._by_topic: Dict[str, List[Question]] = defaultdict(list)
        for q in self.questions:
            self._by_topic[q.topic].append(q)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_json_file(cls, path: str) -> "QuizGenerator":
        """Load a question bank from a JSON file (list of question dicts)."""
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(Question.from_dict(q) for q in raw)

    @classmethod
    def from_dicts(cls, raw_questions: List[Dict]) -> "QuizGenerator":
        return cls(Question.from_dict(q) for q in raw_questions)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def available_topics(self) -> List[str]:
        return sorted(self._by_topic.keys())

    def generate_quiz(
        self,
        num_questions: int = 10,
        topics: Optional[List[str]] = None,
        difficulty: Optional[Difficulty] = None,
        weak_topics: Optional[List[str]] = None,
        weak_topic_weight: float = 0.6,
        seed: Optional[int] = None,
    ) -> Quiz:
        """
        Build a quiz.

        Args:
            num_questions: total number of questions requested.
            topics: restrict the pool to these topics (None = all topics).
            difficulty: restrict the pool to a single difficulty (None = any).
            weak_topics: topics the student is struggling with. When given,
                `weak_topic_weight` fraction of the quiz is drawn preferentially
                from these topics (adaptive practice), the remainder is drawn
                from the general pool.
            weak_topic_weight: fraction (0-1) of the quiz reserved for weak
                topics. Ignored if weak_topics is empty/None.
            seed: optional RNG seed for reproducible quizzes (useful for tests).

        Returns:
            A Quiz object. Raises QuestionBankError if there simply aren't
            enough questions to satisfy the request.
        """
        rng = random.Random(seed)
        pool = self._filter_pool(topics, difficulty)
        if not pool:
            raise QuestionBankError(
                f"No questions match topics={topics} difficulty={difficulty}."
            )

        selected: List[Question] = []

        if weak_topics:
            weak_pool = [q for q in pool if q.topic in weak_topics]
            n_weak = min(len(weak_pool), round(num_questions * weak_topic_weight))
            if weak_pool and n_weak > 0:
                selected.extend(rng.sample(weak_pool, n_weak))

        remaining_needed = num_questions - len(selected)
        if remaining_needed > 0:
            already_ids = {q.id for q in selected}
            rest_pool = [q for q in pool if q.id not in already_ids]
            n_rest = min(len(rest_pool), remaining_needed)
            if n_rest > 0:
                selected.extend(rng.sample(rest_pool, n_rest))

        if not selected:
            raise QuestionBankError("Could not assemble any questions for this quiz.")

        rng.shuffle(selected)

        distribution: Dict[str, int] = defaultdict(int)
        for q in selected:
            distribution[q.topic] += 1

        return Quiz(
            quiz_id=str(uuid.uuid4())[:8],
            questions=selected,
            topic_distribution=dict(distribution),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _filter_pool(
        self, topics: Optional[List[str]], difficulty: Optional[Difficulty]
    ) -> List[Question]:
        pool = self.questions
        if topics:
            pool = [q for q in pool if q.topic in topics]
        if difficulty:
            pool = [q for q in pool if q.difficulty == difficulty]
        return pool

    @staticmethod
    def to_student_view(quiz: Quiz) -> Dict:
        """Convenience passthrough: quiz with answers stripped out."""
        return quiz.to_student_view()
