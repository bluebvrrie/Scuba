"""
Custom exception hierarchy for the Learning Memory & Analytics Module.

Keeping a dedicated exception hierarchy lets calling applications
(e.g. NitroStack Studio) catch module-specific errors without
accidentally swallowing unrelated system exceptions.
"""


class LearningMemoryError(Exception):
    """Base class for all errors raised by this module."""


class StudentNotFoundError(LearningMemoryError):
    """Raised when a student_id does not exist in storage."""

    def __init__(self, student_id: str):
        self.student_id = student_id
        super().__init__(f"Student '{student_id}' was not found.")


class InvalidDataError(LearningMemoryError):
    """Raised when input data fails validation before being persisted."""


class DatabaseError(LearningMemoryError):
    """Raised when a persistence-layer operation fails unexpectedly."""
