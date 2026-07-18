"""
backend/orchestrator.py

Agent Orchestrator for the Scuba Multi-Agent Learning Assistant.
Coordinates:
- Ingestion: Chunking text files/PDFs, embedding them, and saving to disk (Persistent Vector Store).
- Research + Teaching: ResearchAgent retrieves context, TeachingAgent synthesizes a lesson.
- Evaluation + Planning: QuizGenerator builds adaptive quizzes, EvaluationAgent grades them,
  and StudyPlanner produces study plans, persisted to the database.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

# Local imports
from mcp_servers.vector_store import VectorStore, Document
from agents.research_agent import ResearchAgent
from agents.teaching_agent import TeachingAgent, LessonRequest, create_teaching_agent
from agents.quiz_generator import QuizGenerator
from agents.evaluation_agent import EvaluationAgent
from agents.planner import StudyPlanner
from agents.models import StudentAnswer, Quiz, Question
from database import LearningMemoryModule

logger = logging.getLogger("scuba.orchestrator")
logger.setLevel(logging.INFO)


class AgentOrchestrator:
    def __init__(self, db_path: str = "learning_memory.db", question_bank_path: Optional[str] = None):
        self.db = LearningMemoryModule(db_path=db_path)
        self.vector_store = VectorStore()
        
        # Initialize Teaching Agent (falls back to mock if Anthropic key is missing)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        backend = "anthropic" if anthropic_key else "mock"
        self.teaching_agent = create_teaching_agent(backend=backend, api_key=anthropic_key)
        
        # Set up default question bank path
        if question_bank_path is None:
            # Fallback to agents/sample_question_bank.json relative to backend
            question_bank_path = str(Path(__file__).resolve().parent / "agents" / "sample_question_bank.json")
        self.question_bank_path = question_bank_path
        
        logger.info("AgentOrchestrator initialized (db=%s, question_bank=%s)", db_path, question_bank_path)

    # --------------------------------------------------------------------------
    # Document Ingestion Pipeline
    # --------------------------------------------------------------------------
    async def ingest_document(self, student_id: str, filename: str, content: str, topic: Optional[str] = None) -> Dict[str, Any]:
        """
        Ingest, chunk, embed, and index a document into the vector store.
        Also registers the upload in the SQLite database.
        """
        logger.info("Ingesting document: %s for student: %s", filename, student_id)
        
        # 1. Register in SQLite database
        db_doc = self.db.save_uploaded_document(student_id=student_id, filename=filename, topic=topic)
        
        # 2. Chunking logic (simple sentence/paragraph chunks)
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks = []
        for p in paragraphs:
            # If paragraph is very long, split into smaller blocks of ~800 chars
            if len(p) > 1000:
                words = p.split()
                current_chunk = []
                current_len = 0
                for w in words:
                    current_chunk.append(w)
                    current_len += len(w) + 1
                    if current_len >= 800:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = []
                        current_len = 0
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
            else:
                chunks.append(p)
                
        # 3. Create Document objects for indexing
        collection = "pdf" if filename.lower().endswith(".pdf") else "notes"
        documents = []
        for i, chunk_text in enumerate(chunks):
            doc = Document(
                doc_id=f"doc_{db_doc.doc_id}_{i}",
                text=chunk_text,
                source=filename,
                metadata={"student_id": student_id, "topic": topic or "general"}
            )
            documents.append(doc)
            
        # 4. Add to persistent vector store
        if documents:
            await self.vector_store.add_documents(collection=collection, documents=documents)
            
        logger.info("Successfully indexed %d chunks for document %s in collection '%s'", len(documents), filename, collection)
        return {
            "doc_id": db_doc.doc_id,
            "filename": filename,
            "topic": topic,
            "chunks_indexed": len(documents)
        }

    # --------------------------------------------------------------------------
    # RAG + Lesson Generation Flow
    # --------------------------------------------------------------------------
    async def generate_lesson(self, student_id: str, topic: str, difficulty: str = "intermediate") -> Dict[str, Any]:
        """
        Run the complete RAG + Lesson generation pipeline:
        1. Research Agent retrieves context using MCP servers
        2. Teaching Agent constructs adaptive structured lesson
        3. Save study session metadata in database
        """
        logger.info("Generating lesson on %r for student %s (%s)", topic, student_id, difficulty)
        start_time = datetime.now(timezone.utc)
        
        # 1. Run Research Agent
        async with ResearchAgent(top_k=5) as research_agent:
            research_response = await research_agent.answer_question(topic)
            
        # Format the retrieved chunks for the Teaching Agent
        # Teaching Agent expects a list of dictionaries with keys "text", "source", "collection", "score"
        retrieved_context_list = []
        if research_response.retrieved_context:
            # We reconstruct list chunks from the formatted string or we parse it
            # To be simple and direct, let's check research_response for sources
            # Let's inspect the actual chunks returned.
            # In research_agent.py, answer_question returns ResearchResponse(retrieved_context, sources, confidence_score)
            # The teaching agent expects List[Dict[str, Any]]. Let's adapt it:
            # Split by double newline which separates sources
            parts = research_response.retrieved_context.split("\n\n")
            for part in parts:
                if part.startswith("[Source:"):
                    lines = part.split("\n", 1)
                    if len(lines) == 2:
                        src_line, text = lines
                        source = src_line.replace("[Source: ", "").replace("]", "")
                        retrieved_context_list.append({
                            "text": text,
                            "source": source,
                            "collection": "web" if "http" in source else "pdf/notes",
                            "score": 0.8  # dummy score
                        })
                        
        # 2. Call Teaching Agent
        lesson_request = LessonRequest(
            topic=topic,
            retrieved_context=retrieved_context_list,
            difficulty=difficulty
        )
        lesson_data = self.teaching_agent.teach(lesson_request)
        
        # 3. Record Learning Session in Database
        end_time = datetime.now(timezone.utc)
        self.db.save_learning_session(
            student_id=student_id,
            topic=topic,
            start_time=start_time,
            end_time=end_time,
            notes=f"Generated adaptive lesson. Confidence: {research_response.confidence_score}"
        )
        
        # 4. Assemble final response
        return {
            "topic": topic,
            "difficulty": difficulty,
            "lesson": lesson_data,
            "research": {
                "sources": research_response.sources,
                "confidence_score": research_response.confidence_score,
                "retrieved_context": research_response.retrieved_context
            }
        }

    # --------------------------------------------------------------------------
    # Quiz Generation Flow
    # --------------------------------------------------------------------------
    def generate_quiz(self, student_id: str, num_questions: int = 5, topics: Optional[List[str]] = None, adaptive: bool = True) -> Dict[str, Any]:
        """
        Generate a quiz. If adaptive is True, over-sample weak topics from student progress.
        """
        logger.info("Generating quiz for student %s (adaptive=%s)", student_id, adaptive)
        
        # Get weak topics
        weak_topics = None
        if adaptive:
            progress = self.db.get_progress(student_id)
            weak_topics = progress.weak_topics
            logger.info("Adaptive mode: student's weak topics are %s", weak_topics)
            
        # Initialize QuizGenerator
        if not os.path.exists(self.question_bank_path):
            # If the sample bank doesn't exist, create a tiny default fallback to avoid crashes
            logger.warning("Question bank path %s does not exist! Creating default.", self.question_bank_path)
            self._create_default_question_bank()
            
        generator = QuizGenerator.from_json_file(self.question_bank_path)
        quiz = generator.generate_quiz(
            num_questions=num_questions,
            topics=topics,
            weak_topics=weak_topics
        )
        
        return quiz.to_student_view()

    # --------------------------------------------------------------------------
    # Quiz Evaluation & Study Planning Flow
    # --------------------------------------------------------------------------
    def evaluate_quiz(self, student_id: str, quiz_data: Dict[str, Any], submitted_answers: List[Dict[str, Any]], learning_goals: Optional[List[str]] = None, minutes_per_day: Optional[int] = 60) -> Dict[str, Any]:
        """
        Grade the student's quiz answers, record performance per topic in the database,
        recompute progress, and generate personalized daily/weekly study plans.
        """
        logger.info("Evaluating quiz for student %s", student_id)
        
        # 1. Reconstruct Quiz object from quiz_data
        # Note: quiz_data from frontend contains student view. We need answers too.
        # We load full questions from the bank by ID to grade them securely.
        generator = QuizGenerator.from_json_file(self.question_bank_path)
        question_map = {q.id: q for q in generator.questions}
        
        graded_questions = []
        for q_data in quiz_data.get("questions", []):
            q_id = q_data["id"]
            if q_id in question_map:
                graded_questions.append(question_map[q_id])
                
        quiz = Quiz(
            quiz_id=quiz_data["quiz_id"],
            questions=graded_questions,
            topic_distribution=quiz_data.get("topic_distribution", {})
        )
        
        # 2. Reconstruct StudentAnswer objects
        answers = []
        for ans_data in submitted_answers:
            answers.append(StudentAnswer(
                question_id=ans_data["question_id"],
                answer=ans_data["answer"],
                time_taken_seconds=ans_data.get("time_taken_seconds")
            ))
            
        # 3. Grade using EvaluationAgent
        evaluation_agent = EvaluationAgent(weak_threshold=0.6, strong_threshold=0.8)
        evaluation = evaluation_agent.evaluate(quiz, answers)
        
        # 4. Save QuizResult in SQLite database
        # Quiz may span multiple topics, but we record score per topic to update student topic progress.
        # For each topic represented in the quiz, extract correct/total and save a DB entry.
        topic_counts = {}
        topic_correct = {}
        for r in evaluation.question_results:
            topic_counts[r.topic] = topic_counts.get(r.topic, 0) + 1
            if r.correct:
                topic_correct[r.topic] = topic_correct.get(r.topic, 0) + 1
                
        for topic, total in topic_counts.items():
            correct = topic_correct.get(topic, 0)
            # Find difficulty of questions for this topic (dominant difficulty)
            diff_list = [r.difficulty.value for r in evaluation.question_results if r.topic == topic]
            difficulty = max(set(diff_list), key=diff_list.count) if diff_list else "medium"
            
            self.db.save_quiz_result(
                student_id=student_id,
                topic=topic,
                total_questions=total,
                correct_answers=correct,
                difficulty=difficulty
            )
            
        # 5. Fetch updated Progress Summary from database
        progress_summary = self.db.update_progress(student_id)
        
        # 6. Generate Study Plans & Recommendations
        planner = StudyPlanner(default_minutes_per_day=minutes_per_day or 60)
        daily_plan = planner.generate_daily_plan(
            weak_topics=evaluation.weak_topics,
            strong_topics=evaluation.strong_topics,
            learning_goals=learning_goals or [],
            minutes_available=minutes_per_day
        )
        weekly_plan = planner.generate_weekly_plan(
            weak_topics=evaluation.weak_topics,
            strong_topics=evaluation.strong_topics,
            learning_goals=learning_goals or [],
            minutes_per_day=minutes_per_day
        )
        revision_schedule = planner.generate_revision_schedule(
            weak_topics=evaluation.weak_topics
        )
        recommendations = planner.generate_recommendations(
            evaluation=evaluation,
            progress_summary=progress_summary.model_dump(),
            learning_goals=learning_goals or []
        )
        
        # 7. Format result mapping the hackathon contract
        return {
            "quiz_id": quiz.quiz_id,
            "score": evaluation.score,
            "correct_count": evaluation.correct_count,
            "total_questions": evaluation.total_questions,
            "weak_topics": evaluation.weak_topics,
            "strong_topics": evaluation.strong_topics,
            "progress": progress_summary.model_dump(),
            "recommendations": recommendations,
            "study_plan": {
                "daily_plan": daily_plan,
                "weekly_plan": weekly_plan,
                "revision_schedule": revision_schedule
            },
            "graded_results": [
                {
                    "question_id": r.question_id,
                    "topic": r.topic,
                    "correct": r.correct,
                    "student_answer": r.student_answer,
                    "correct_answer": r.correct_answer,
                    "explanation": question_map[r.question_id].explanation if r.question_id in question_map else None
                }
                for r in evaluation.question_results
            ]
        }

    # --------------------------------------------------------------------------
    # Fallback default question bank creation
    # --------------------------------------------------------------------------
    def _create_default_question_bank(self):
        Path(self.question_bank_path).parent.mkdir(parents=True, exist_ok=True)
        default_bank = [
            {
                "id": "q1",
                "topic": "physics",
                "difficulty": "easy",
                "text": "What is the unit of electrical resistance?",
                "correct_answer": "Ohm",
                "options": ["Ampere", "Volt", "Ohm", "Watt"],
                "explanation": "Resistance is measured in Ohms, named after Georg Ohm."
            },
            {
                "id": "q2",
                "topic": "physics",
                "difficulty": "medium",
                "text": "What is the speed of light in a vacuum?",
                "correct_answer": "299,792 km/s",
                "options": ["150,000 km/s", "299,792 km/s", "300,000 km/s", "450,000 km/s"],
                "explanation": "The speed of light in vacuum is exactly 299,792,458 meters per second."
            },
            {
                "id": "q3",
                "topic": "algebra",
                "difficulty": "easy",
                "text": "Solve for x: 2x + 5 = 15.",
                "correct_answer": "5",
                "options": ["2", "5", "10", "15"],
                "explanation": "Subtract 5: 2x = 10, then divide by 2: x = 5."
            },
            {
                "id": "q4",
                "topic": "algebra",
                "difficulty": "medium",
                "text": "What is the vertex of the parabola y = (x - 3)^2 + 4?",
                "correct_answer": "(3, 4)",
                "options": ["(-3, 4)", "(3, 4)", "(3, -4)", "(-3, -4)"],
                "explanation": "The vertex form of a quadratic is y = a(x - h)^2 + k, vertex is (h, k)."
            },
            {
                "id": "q5",
                "topic": "chemistry",
                "difficulty": "easy",
                "text": "What is the chemical symbol for Gold?",
                "correct_answer": "Au",
                "options": ["Ag", "Au", "Fe", "Gd"],
                "explanation": "Au comes from the Latin word for gold, 'aurum'."
            },
            {
                "id": "q6",
                "topic": "chemistry",
                "difficulty": "medium",
                "text": "What type of bond forms between sodium and chlorine in NaCl?",
                "correct_answer": "Ionic",
                "options": ["Covalent", "Ionic", "Metallic", "Hydrogen"],
                "explanation": "Sodium transfers an electron to chlorine, forming positive and negative ions that attract."
            }
        ]
        import json
        with open(self.question_bank_path, "w", encoding="utf-8") as f:
            json.dump(default_bank, f, indent=2)
        logger.info("Created default question bank at %s", self.question_bank_path)
