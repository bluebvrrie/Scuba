"""
lesson_generator.py
---------------------
Orchestration layer that wraps TeachingAgent behind a standardized,
pipeline-friendly interface so it can be registered as a node/agent inside
a multi-agent framework such as NitroStack Studio.

Assumption (stated explicitly since NitroStack Studio's exact plugin API
wasn't provided): most agent-orchestration frameworks expect a component
that exposes a `name`, `description`, and a `run(payload: dict) -> dict`
method with predictable input/output contracts and structured error
handling. `NitroStackAgentInterface` below models that shape. If your
NitroStack Studio SDK provides its own base class/decorator, subclass or
wrap `LessonGenerator.run` with it directly — the internal logic doesn't
need to change.

Pipeline position:
    Research Agent  --(retrieved_context)-->  Teaching Agent  --(lesson JSON)-->  downstream agents / UI
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any, Dict, Optional

from teaching_agent import LessonRequest, LessonSchemaError, TeachingAgent, create_teaching_agent

logger = logging.getLogger("lesson_generator")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Generic agent interface (NitroStack Studio-compatible shape)
# ---------------------------------------------------------------------------

class NitroStackAgentInterface(ABC):
    """
    Minimal contract expected of any agent plugged into a NitroStack Studio
    style pipeline: a stable name, a description for the agent registry,
    and a single `run(payload)` method that always returns a structured
    result envelope (never raises past its own boundary).
    """

    name: str = "base_agent"
    description: str = "Base agent interface."

    @abstractmethod
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class InvalidPayloadError(ValueError):
    """Raised when the incoming pipeline payload is malformed."""


def _validate_payload(payload: Dict[str, Any]) -> LessonRequest:
    if not isinstance(payload, dict):
        raise InvalidPayloadError("Payload must be a dict.")

    topic = payload.get("topic")
    if not topic or not isinstance(topic, str):
        raise InvalidPayloadError("Payload must include a non-empty string 'topic'.")

    # Accept output from a Research Agent under either key, for flexibility
    retrieved_context = (
        payload.get("retrieved_context")
        or payload.get("research_context")
        or payload.get("context")
        or []
    )
    if not isinstance(retrieved_context, list):
        raise InvalidPayloadError("'retrieved_context' must be a list of context chunks.")

    difficulty = payload.get("difficulty", "intermediate")
    if not isinstance(difficulty, str):
        raise InvalidPayloadError("'difficulty' must be a string.")

    return LessonRequest(topic=topic, retrieved_context=retrieved_context, difficulty=difficulty)


# ---------------------------------------------------------------------------
# Lesson Generator (the pluggable agent node)
# ---------------------------------------------------------------------------

class LessonGenerator(NitroStackAgentInterface):
    """
    Pipeline-facing wrapper around TeachingAgent.

    Responsibilities beyond the raw TeachingAgent:
    - Validate/normalize input coming from upstream agents (Research Agent).
    - Enforce a stable, error-safe response envelope so a pipeline runner
      never crashes on this node's output.
    - Attach timing/telemetry metadata useful for orchestration/monitoring.
    """

    name = "teaching_agent.lesson_generator"
    description = (
        "Generates an adaptive lesson (explanation, examples, analogy, summary, "
        "practice questions, flashcards) from Research-Agent-retrieved context."
    )

    def __init__(self, agent: Optional[TeachingAgent] = None, **agent_factory_kwargs):
        """
        Pass an already-constructed TeachingAgent, or let this class build
        one for you via create_teaching_agent(**agent_factory_kwargs)
        (e.g. backend='anthropic', api_key=..., model=..., single_pass=False).
        """
        self.agent = agent or create_teaching_agent(**agent_factory_kwargs)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standard pipeline entrypoint.

        Input payload (flexible keys, see _validate_payload):
            {
              "topic": "Binary Search",
              "retrieved_context": [{"content": "...", "source": "..."}, ...],
              "difficulty": "beginner" | "intermediate" | "advanced"
            }

        Output envelope:
            {
              "status": "success" | "error",
              "agent": "teaching_agent.lesson_generator",
              "lesson": {...} | None,
              "error": None | "message",
              "latency_ms": int
            }
        """
        start = time.perf_counter()
        try:
            request = _validate_payload(payload)
        except InvalidPayloadError as e:
            logger.error("Invalid payload: %s", e)
            return self._envelope(status="error", lesson=None, error=str(e), start=start)

        try:
            lesson = self.agent.teach(request)
        except LessonSchemaError as e:
            logger.error("Lesson generation failed schema validation: %s", e)
            return self._envelope(status="error", lesson=None, error=str(e), start=start)
        except Exception as e:  # noqa: BLE001 - pipeline boundary must not crash the runner
            logger.exception("Unexpected error during lesson generation")
            return self._envelope(status="error", lesson=None, error=f"Unexpected error: {e}", start=start)

        return self._envelope(status="success", lesson=lesson, error=None, start=start, request=request)

    @staticmethod
    def _envelope(
        status: str,
        lesson: Optional[Dict[str, Any]],
        error: Optional[str],
        start: float,
        request: Optional[LessonRequest] = None,
    ) -> Dict[str, Any]:
        latency_ms = int((time.perf_counter() - start) * 1000)
        envelope = {
            "status": status,
            "agent": LessonGenerator.name,
            "lesson": lesson,
            "error": error,
            "latency_ms": latency_ms,
        }
        if request is not None:
            envelope["request_echo"] = asdict(request)
        return envelope


# ---------------------------------------------------------------------------
# Convenience module-level function (for simple / scripted pipeline calls)
# ---------------------------------------------------------------------------

_default_generator: Optional[LessonGenerator] = None


def generate_lesson(
    topic: str,
    retrieved_context: Optional[list] = None,
    difficulty: str = "intermediate",
    backend: str = "anthropic",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One-shot convenience function for callers that just want a lesson dict
    without instantiating classes themselves, e.g.:

        from lesson_generator import generate_lesson
        result = generate_lesson("Photosynthesis", research_agent_output, "beginner")
    """
    global _default_generator
    if _default_generator is None:
        _default_generator = LessonGenerator(backend=backend, api_key=api_key)

    payload = {
        "topic": topic,
        "retrieved_context": retrieved_context or [],
        "difficulty": difficulty,
    }
    return _default_generator.run(payload)


# ---------------------------------------------------------------------------
# Demo / manual smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Simulated output from a Research Agent
    mock_research_context = [
        {
            "content": (
                "Binary search is an algorithm for finding a target value in a sorted "
                "array by repeatedly halving the search interval. It compares the target "
                "to the middle element and discards the half that cannot contain the target."
            ),
            "source": "algorithms_textbook_ch4",
        },
        {
            "content": "Binary search runs in O(log n) time, compared to O(n) for linear search.",
            "source": "complexity_notes",
        },
    ]

    generator = LessonGenerator(backend="mock")  # swap to backend="anthropic" for real output
    result = generator.run({
        "topic": "Binary Search",
        "retrieved_context": mock_research_context,
        "difficulty": "beginner",
    })

    import json
    print(json.dumps(result, indent=2))
