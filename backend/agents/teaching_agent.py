"""
teaching_agent.py
------------------
The Teaching Agent: receives retrieved context from the Research Agent and
produces an adaptive lesson (explanation, examples, analogy, summary,
practice questions, flashcards) as validated JSON.

Modularity notes:
- LLM access goes through the `LLMClient` interface, so this file has ZERO
  dependency on a specific SDK/vendor beyond the two thin adapter classes at
  the bottom. Swap `AnthropicLLMClient` for any other implementation without
  touching agent logic.
- All prompt text lives in prompt_templates.py (separation of concerns).
- Difficulty adaptation is data-driven (DIFFICULTY_PROFILES), not scattered
  if/else branches, so adding a new level is a one-line config change.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .prompt_templates import (
    DIFFICULTY_PROFILES,
    DifficultyLevel,
    SYSTEM_PROMPT,
    build_generation_prompt,
    build_planning_prompt,
    build_single_pass_prompt,
    format_research_context,
)

logger = logging.getLogger("teaching_agent")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# LLM client abstraction
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    """Minimal interface the Teaching Agent needs from any LLM backend."""

    @abstractmethod
    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        """Return raw text completion for a single-turn prompt."""
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    """
    Thin adapter over the Anthropic Messages API.
    Requires the `anthropic` package and an API key available in the
    environment (ANTHROPIC_API_KEY) or passed explicitly.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicLLMClient. "
                "Install it with: pip install anthropic"
            ) from e
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        return "\n".join(parts).strip()


class MockLLMClient(LLMClient):
    """
    Deterministic offline client for unit tests / local dev without API
    access. Returns a schema-valid stub so the rest of the pipeline
    (parsing, validation, orchestration) can be exercised end-to-end.
    """

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        if "planning step" in prompt:
            return (
                "1. Core idea: (mock) placeholder core idea derived from context.\n"
                "2. Key points: mock point A; mock point B; mock point C.\n"
                "3. Analogy candidate: mock everyday analogy.\n"
                "4. Worked example sketch: mock scenario.\n"
                "5. Gaps: none noted (mock)."
            )
        stub = {
            "explanation": {
                "simple": "This is a mock simple explanation of the topic.",
                "step_by_step": ["Mock step 1", "Mock step 2", "Mock step 3"],
                "key_points": ["Mock key point 1", "Mock key point 2", "Mock key point 3"],
            },
            "examples": {"worked_example": "Mock worked example walkthrough."},
            "analogy": "Mock real-life analogy.",
            "summary": "Mock two-sentence summary of the concept for testing purposes.",
            "practice_questions": [
                {"question": "Mock question 1?", "answer": "Mock answer 1", "difficulty": "beginner"},
                {"question": "Mock question 2?", "answer": "Mock answer 2", "difficulty": "beginner"},
            ],
            "flashcards": [
                {"front": "Mock term 1", "back": "Mock definition 1"},
                {"front": "Mock term 2", "back": "Mock definition 2"},
            ],
        }
        return "FINAL_JSON:\n" + json.dumps(stub)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL_KEYS = [
    "explanation", "examples", "analogy", "summary",
    "practice_questions", "flashcards",
]
REQUIRED_EXPLANATION_KEYS = ["simple", "step_by_step", "key_points"]
REQUIRED_EXAMPLE_KEYS = ["worked_example"]


@dataclass
class LessonRequest:
    topic: str
    retrieved_context: List[Dict[str, Any]] = field(default_factory=list)
    difficulty: str = "intermediate"


class LessonSchemaError(ValueError):
    """Raised when the LLM output cannot be coerced into the required schema."""


# ---------------------------------------------------------------------------
# Teaching Agent
# ---------------------------------------------------------------------------

class TeachingAgent:
    """
    Adaptive Teaching Agent.

    Pipeline (agent reasoning, two explicit steps):
      1. PLAN  -> the model reasons about core idea / key points / analogy /
                  example candidates given the retrieved context and the
                  difficulty profile.
      2. WRITE -> the model turns that plan into the final schema-conformant
                  JSON lesson.

    A `single_pass=True` mode is also available (one LLM call instead of
    two) for latency/cost-sensitive deployments; it uses a "reason, then
    FINAL_JSON:" prompting pattern instead.
    """

    def __init__(self, llm_client: LLMClient, single_pass: bool = False, max_retries: int = 2):
        self.llm_client = llm_client
        self.single_pass = single_pass
        self.max_retries = max_retries

    # -- Public API ---------------------------------------------------------

    def teach(self, request: LessonRequest) -> Dict[str, Any]:
        """
        Main entrypoint. Returns a validated lesson dict:
        {explanation, examples, analogy, summary, practice_questions, flashcards}
        """
        profile_key = DifficultyLevel.from_string(request.difficulty)
        profile = DIFFICULTY_PROFILES[profile_key]
        context_block = format_research_context(request.retrieved_context)

        logger.info(
            "TeachingAgent.teach() topic=%r difficulty=%s context_chunks=%d",
            request.topic, profile_key.value, len(request.retrieved_context),
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 2):  # first try + retries
            try:
                raw_output = self._run_reasoning_pipeline(request.topic, context_block, profile)
                lesson = self._extract_and_validate_json(raw_output, profile_key)
                lesson = self._post_process(lesson, profile_key)
                logger.info("Lesson generated successfully on attempt %d", attempt)
                return lesson
            except LessonSchemaError as e:
                last_error = e
                logger.warning("Attempt %d failed schema validation: %s", attempt, e)

        raise LessonSchemaError(
            f"Failed to produce a schema-valid lesson after {self.max_retries + 1} attempts: {last_error}"
        )

    # -- Reasoning pipeline ---------------------------------------------------

    def _run_reasoning_pipeline(self, topic: str, context_block: str, profile: Dict) -> str:
        if self.single_pass:
            prompt = build_single_pass_prompt(topic, context_block, profile)
            return self.llm_client.generate(SYSTEM_PROMPT, prompt, max_tokens=2000)

        # Step 1: planning (agent "thinks" before writing final content)
        planning_prompt = build_planning_prompt(topic, context_block, profile)
        plan_text = self.llm_client.generate(SYSTEM_PROMPT, planning_prompt, max_tokens=600)
        logger.debug("Plan:\n%s", plan_text)

        # Step 2: generation grounded in the plan
        generation_prompt = build_generation_prompt(topic, context_block, profile, plan_text)
        return self.llm_client.generate(SYSTEM_PROMPT, generation_prompt, max_tokens=2000)

    # -- Parsing & validation -------------------------------------------------

    def _extract_and_validate_json(self, raw_output: str, profile_key: DifficultyLevel) -> Dict[str, Any]:
        json_text = self._extract_json_block(raw_output)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise LessonSchemaError(f"Model output was not valid JSON: {e}")

        self._validate_schema(data)
        return data

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """
        Robustly pull a JSON object out of raw model text, handling:
        - a 'FINAL_JSON:' marker (single-pass mode)
        - accidental markdown code fences
        - leading/trailing commentary
        """
        marker = "FINAL_JSON:"
        if marker in text:
            text = text.split(marker, 1)[1]

        text = text.strip()
        text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

        # Fallback: grab the first {...} balanced-looking span
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                text = match.group(0)
        return text

    @staticmethod
    def _validate_schema(data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise LessonSchemaError("Top-level JSON is not an object.")

        missing = [k for k in REQUIRED_TOP_LEVEL_KEYS if k not in data]
        if missing:
            raise LessonSchemaError(f"Missing top-level keys: {missing}")

        explanation = data.get("explanation")
        if not isinstance(explanation, dict):
            raise LessonSchemaError("'explanation' must be an object.")
        missing_exp = [k for k in REQUIRED_EXPLANATION_KEYS if k not in explanation]
        if missing_exp:
            raise LessonSchemaError(f"Missing explanation sub-keys: {missing_exp}")
        if not isinstance(explanation["step_by_step"], list) or not explanation["step_by_step"]:
            raise LessonSchemaError("'explanation.step_by_step' must be a non-empty list.")
        if not isinstance(explanation["key_points"], list) or not explanation["key_points"]:
            raise LessonSchemaError("'explanation.key_points' must be a non-empty list.")

        examples = data.get("examples")
        if not isinstance(examples, dict):
            raise LessonSchemaError("'examples' must be an object.")
        missing_ex = [k for k in REQUIRED_EXAMPLE_KEYS if k not in examples]
        if missing_ex:
            raise LessonSchemaError(f"Missing examples sub-keys: {missing_ex}")

        if not isinstance(data.get("analogy"), str) or not data["analogy"].strip():
            raise LessonSchemaError("'analogy' must be a non-empty string.")

        if not isinstance(data.get("summary"), str) or not data["summary"].strip():
            raise LessonSchemaError("'summary' must be a non-empty string.")

        pq = data.get("practice_questions")
        if not isinstance(pq, list) or not pq:
            raise LessonSchemaError("'practice_questions' must be a non-empty list.")
        for i, q in enumerate(pq):
            if not isinstance(q, dict) or "question" not in q or "answer" not in q:
                raise LessonSchemaError(f"practice_questions[{i}] missing 'question'/'answer'.")

        fc = data.get("flashcards")
        if not isinstance(fc, list) or not fc:
            raise LessonSchemaError("'flashcards' must be a non-empty list.")
        for i, card in enumerate(fc):
            if not isinstance(card, dict) or "front" not in card or "back" not in card:
                raise LessonSchemaError(f"flashcards[{i}] missing 'front'/'back'.")

    # -- Post-processing -------------------------------------------------------

    @staticmethod
    def _post_process(lesson: Dict[str, Any], profile_key: DifficultyLevel) -> Dict[str, Any]:
        """Attach metadata useful to downstream agents/UI without breaking the schema contract."""
        lesson = dict(lesson)  # shallow copy
        for q in lesson.get("practice_questions", []):
            q.setdefault("difficulty", profile_key.value)
        lesson["_meta"] = {
            "difficulty": profile_key.value,
            "agent": "teaching_agent",
            "schema_version": "1.0",
        }
        return lesson


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_teaching_agent(
    backend: str = "anthropic",
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-6",
    single_pass: bool = False,
) -> TeachingAgent:
    """
    Factory so callers (e.g. lesson_generator.py or NitroStack Studio's
    agent registry) can construct a ready-to-use TeachingAgent from simple
    config values instead of wiring up LLMClient classes by hand.
    """
    if backend == "mock":
        client: LLMClient = MockLLMClient()
    elif backend == "anthropic":
        client = AnthropicLLMClient(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unknown backend '{backend}'. Use 'anthropic' or 'mock'.")

    return TeachingAgent(llm_client=client, single_pass=single_pass)
