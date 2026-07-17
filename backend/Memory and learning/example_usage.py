"""
Example usage of the Learning Memory & Analytics Module.

Run with:  python3 example_usage.py
(Requires `pydantic` to be installed: pip install pydantic)
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from learning_memory import LearningMemoryModule

# Optional: turn on INFO-level logs to see the module narrate its actions.
logging.basicConfig(level=logging.INFO)


def main() -> None:
    # 1. Initialize the module (creates/opens learning_memory.db)
    module = LearningMemoryModule(db_path="learning_memory.db")

    # 2. Create a student profile
    student = module.create_student(
        name="Asha Menon",
        email="asha@example.com",
        grade_level="Grade 8",
        curriculum_topics=["Algebra", "Geometry", "Fractions", "Statistics"],
    )
    print(f"\nCreated student: {student.name} ({student.student_id})")

    # 3. Log a learning session (e.g. after the student studies a topic)
    now = datetime.now(timezone.utc)
    module.save_learning_session(
        student_id=student.student_id,
        topic="Algebra",
        start_time=now - timedelta(minutes=45),
        end_time=now - timedelta(minutes=5),
        document_ids=[],
        notes="Reviewed linear equations",
    )

    # 4. Record uploaded study documents
    module.save_uploaded_document(
        student_id=student.student_id, filename="algebra_notes.pdf", topic="Algebra"
    )

    # 5. Save quiz results (progress auto-updates after each one)
    module.save_quiz_result(student.student_id, "Algebra", total_questions=10, correct_answers=9)
    module.save_quiz_result(student.student_id, "Fractions", total_questions=10, correct_answers=4)

    # 6. Pull the current progress snapshot
    progress = module.get_progress(student.student_id)
    print("\nProgress snapshot:")
    print(json.dumps(progress.model_dump(), indent=2, default=str))

    # 7. Get topic recommendations
    next_topics = module.recommend_next_topics(student.student_id, limit=3)
    print("\nRecommended next topics:", next_topics)

    # 8. Generate the full learning report (canonical output schema)
    report = module.generate_learning_report(student.student_id)
    print("\nFull learning report:")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
