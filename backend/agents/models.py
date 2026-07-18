"""
models.py
=========
Shared data structures used by every module in the Evaluation & Planning
Agent (quiz_generator, evaluation_agent, progress_tracker, planner).

Keeping these in one place gives the whole system a single, consistent
vocabulary and avoids circular imports between the four agent modules.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any


class Difficulty(str, Enum):
    """Question difficulty levels used for adaptive quiz generation."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class Question:
    """A single question living in the question bank."""
    id: str
    topic: str
    difficulty: Difficulty
    text: str
    correct_answer: str
    options: Optional[List[str]] = None          # None => open/short-answer question
    explanation: Optional[str] = None             # shown during review, not during the quiz

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Question":
        return Question(
            id=d["id"],
            topic=d["topic"],
            difficulty=Difficulty(d.get("difficulty", "medium")),
            text=d["text"],
            correct_answer=d["correct_answer"],
            options=d.get("options"),
            explanation=d.get("explanation"),
        )

    def to_student_view(self) -> Dict[str, Any]:
        """Serialize WITHOUT the answer key, safe to hand to a student."""
        return {
            "id": self.id,
            "topic": self.topic,
            "difficulty": self.difficulty.value,
            "text": self.text,
            "options": self.options,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["difficulty"] = self.difficulty.value
        return d


@dataclass
class Quiz:
    """A generated quiz: an ordered set of questions plus metadata."""
    quiz_id: str
    questions: List[Question]
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    topic_distribution: Dict[str, int] = field(default_factory=dict)

    def to_student_view(self) -> Dict[str, Any]:
        return {
            "quiz_id": self.quiz_id,
            "created_at": self.created_at,
            "topic_distribution": self.topic_distribution,
            "questions": [q.to_student_view() for q in self.questions],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quiz_id": self.quiz_id,
            "created_at": self.created_at,
            "topic_distribution": self.topic_distribution,
            "questions": [q.to_dict() for q in self.questions],
        }


@dataclass
class StudentAnswer:
    """One answer submitted by the student for a given question."""
    question_id: str
    answer: str
    time_taken_seconds: Optional[float] = None


@dataclass
class QuestionResult:
    """The graded outcome for a single question."""
    question_id: str
    topic: str
    difficulty: Difficulty
    correct: bool
    student_answer: Optional[str]
    correct_answer: str
    time_taken_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["difficulty"] = self.difficulty.value
        return d


@dataclass
class EvaluationResult:
    """Full outcome of grading one quiz attempt."""
    quiz_id: str
    timestamp: str
    total_questions: int
    correct_count: int
    score: float                              # 0-100
    topic_scores: Dict[str, float]            # topic -> accuracy 0-1
    weak_topics: List[str]
    strong_topics: List[str]
    confidence: float                         # 0-1
    confidence_label: str                     # low / medium / high
    question_results: List[QuestionResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quiz_id": self.quiz_id,
            "timestamp": self.timestamp,
            "total_questions": self.total_questions,
            "correct_count": self.correct_count,
            "score": self.score,
            "topic_scores": self.topic_scores,
            "weak_topics": self.weak_topics,
            "strong_topics": self.strong_topics,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "question_results": [qr.to_dict() for qr in self.question_results],
        }
