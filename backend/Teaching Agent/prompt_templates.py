"""
prompt_templates.py
--------------------
Prompt-engineering layer for the Teaching Agent.

This module owns *all* natural-language prompt construction. Keeping prompts
here (separate from orchestration logic in teaching_agent.py) makes the
system modular: prompts can be tuned, A/B tested, or localized without
touching agent control flow.

Design principles used:
1. Role/system separation      -> stable persona + hard output-format rules.
2. Difficulty conditioning     -> vocabulary, depth, and pacing change per level.
3. Structured output contract  -> the model is told the EXACT JSON schema to
   return, with a "reasoning then answer" pattern so the model can think
   step-by-step (agent reasoning) before committing to final structured output,
   without polluting the final JSON with that reasoning.
4. Few-shot micro-example      -> a tiny illustrative snippet reduces schema
   drift (missing keys, wrong types) far more reliably than instructions alone.
"""

from enum import Enum
from typing import Dict, List


# ---------------------------------------------------------------------------
# Difficulty levels
# ---------------------------------------------------------------------------

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

    @classmethod
    def from_string(cls, value: str) -> "DifficultyLevel":
        """Fuzzy-match a free-text difficulty string onto a known level."""
        if not value:
            return cls.INTERMEDIATE
        value = value.strip().lower()
        for level in cls:
            if level.value == value:
                return level
        # Loose aliases a user/UI might send
        aliases = {
            "easy": cls.BEGINNER,
            "novice": cls.BEGINNER,
            "medium": cls.INTERMEDIATE,
            "intermediate level": cls.INTERMEDIATE,
            "hard": cls.ADVANCED,
            "expert": cls.ADVANCED,
        }
        return aliases.get(value, cls.INTERMEDIATE)


# ---------------------------------------------------------------------------
# Difficulty -> generation profile
# ---------------------------------------------------------------------------
# These knobs are injected into the prompt so the SAME prompt template
# produces meaningfully different output per level, rather than just saying
# "explain this for a beginner" (which models tend to under-adapt to).

DIFFICULTY_PROFILES: Dict[DifficultyLevel, Dict] = {
    DifficultyLevel.BEGINNER: {
        "label": "Beginner",
        "vocabulary": "everyday, non-technical words; define any unavoidable jargon immediately",
        "sentence_style": "short sentences, one idea per sentence",
        "depth": "focus on WHAT and WHY only, avoid edge cases and internals",
        "analogy_style": "a very familiar, concrete, everyday-life analogy (kitchen, sports, school, commuting)",
        "example_complexity": "one small, fully-worked, low-step example",
        "num_step_by_step": (3, 5),
        "num_key_points": (3, 4),
        "num_practice_questions": 3,
        "num_flashcards": 5,
        "question_style": "recall and basic understanding (What is / Which of the following)",
    },
    DifficultyLevel.INTERMEDIATE: {
        "label": "Intermediate",
        "vocabulary": "standard technical vocabulary, defined briefly on first use",
        "sentence_style": "clear sentences, may combine 2 related ideas",
        "depth": "cover WHAT, WHY, and HOW; mention common pitfalls",
        "analogy_style": "an analogy that maps closely to the mechanism, not just the surface idea",
        "example_complexity": "one realistic, multi-step worked example",
        "num_step_by_step": (4, 7),
        "num_key_points": (4, 6),
        "num_practice_questions": 4,
        "num_flashcards": 7,
        "question_style": "application and short problem-solving",
    },
    DifficultyLevel.ADVANCED: {
        "label": "Advanced",
        "vocabulary": "precise technical/academic vocabulary, minimal hand-holding",
        "sentence_style": "dense, information-rich sentences are acceptable",
        "depth": "cover WHAT, WHY, HOW, internal mechanics, trade-offs, and edge cases",
        "analogy_style": "a precise analogy that also exposes where the analogy breaks down",
        "example_complexity": "one non-trivial worked example with an edge case or optimization noted",
        "num_step_by_step": (5, 9),
        "num_key_points": (5, 8),
        "num_practice_questions": 5,
        "num_flashcards": 8,
        "question_style": "analysis, comparison, and 'explain why' reasoning questions",
    },
}


# ---------------------------------------------------------------------------
# System persona
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Teaching Agent inside a multi-agent AI learning assistant.

Your job: take verified context retrieved by a separate Research Agent and turn it
into an adaptive, pedagogically sound lesson for a specific learner difficulty level.

Rules you must always follow:
- Ground every explanation strictly in the provided context. Do not invent facts
  that contradict or go beyond it. If the context is insufficient for something,
  say so briefly rather than fabricating.
- Adapt vocabulary, depth, and pacing to the requested difficulty profile exactly.
- Be pedagogically deliberate: simple explanation before step-by-step breakdown,
  concrete analogy before abstract summary, and practice questions that actually
  test the key points you just taught (no surprise content).
- Think through your plan first, then output the final answer.
- The FINAL answer must be valid JSON only, matching the schema given, with no
  markdown code fences, no commentary, and no trailing text after it.
"""


# ---------------------------------------------------------------------------
# Output schema (kept as a string block so it can be embedded verbatim
# into the prompt AND used for documentation/validation reference)
# ---------------------------------------------------------------------------

JSON_SCHEMA_DESCRIPTION = """{
  "explanation": {
    "simple": "<one short, jargon-adapted paragraph explaining the concept>",
    "step_by_step": ["<step 1>", "<step 2>", "..."],
    "key_points": ["<key point 1>", "<key point 2>", "..."]
  },
  "examples": {
    "worked_example": "<one fully worked example matching the difficulty level>"
  },
  "analogy": "<one real-life analogy appropriate to the difficulty level>",
  "summary": "<a concise 2-4 sentence summary of the whole concept>",
  "practice_questions": [
    {"question": "<question text>", "answer": "<model answer>", "difficulty": "<beginner|intermediate|advanced>"}
  ],
  "flashcards": [
    {"front": "<term or question>", "back": "<concise answer/definition>"}
  ]
}"""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def format_research_context(retrieved_context: List[Dict]) -> str:
    """
    Turn the Research Agent's retrieved chunks into a numbered, source-tagged
    context block the model can cite against. Expected input shape (flexible):
        [{"content": "...", "source": "...", "score": 0.87}, ...]
    """
    if not retrieved_context:
        return "(No retrieved context was provided. Rely on general, widely-agreed-upon knowledge and state that explicitly.)"

    lines = []
    for i, chunk in enumerate(retrieved_context, start=1):
        content = chunk.get("content") or chunk.get("text") or ""
        source = chunk.get("source") or chunk.get("title") or f"source_{i}"
        lines.append(f"[{i}] (source: {source})\n{content.strip()}")
    return "\n\n".join(lines)


def build_planning_prompt(topic: str, context_block: str, profile: Dict) -> str:
    """
    Step 1 of agent reasoning: a lightweight planning pass where the model
    identifies what to teach and how, BEFORE writing final content. This
    reduces schema drift and improves coherence between explanation,
    examples, and questions (they all trace back to the same plan).
    """
    return f"""TOPIC: {topic}

DIFFICULTY PROFILE: {profile['label']}
- Vocabulary: {profile['vocabulary']}
- Depth: {profile['depth']}
- Analogy style: {profile['analogy_style']}
- Example complexity: {profile['example_complexity']}

RETRIEVED CONTEXT FROM RESEARCH AGENT:
{context_block}

TASK (planning step, think out loud, this will NOT be shown to the learner):
1. In 1-2 sentences, identify the core idea of "{topic}" as supported by the context.
2. List the {profile['num_key_points'][0]}-{profile['num_key_points'][1]} most important
   sub-points a learner at this level must understand.
3. Sketch a real-life analogy candidate ({profile['analogy_style']}).
4. Sketch one worked example scenario ({profile['example_complexity']}).
5. Note anything in the context that is missing or insufficient for a complete lesson.

Respond with your plan in plain text (not JSON yet)."""


def build_generation_prompt(topic: str, context_block: str, profile: Dict, plan_text: str) -> str:
    """
    Step 2 of agent reasoning: convert the plan into the final structured
    lesson JSON, strictly following the schema and difficulty profile.
    """
    return f"""TOPIC: {topic}

DIFFICULTY PROFILE: {profile['label']}
- Vocabulary: {profile['vocabulary']}
- Sentence style: {profile['sentence_style']}
- Depth: {profile['depth']}
- Analogy style: {profile['analogy_style']}
- Example complexity: {profile['example_complexity']}
- step_by_step should have between {profile['num_step_by_step'][0]} and {profile['num_step_by_step'][1]} steps.
- key_points should have between {profile['num_key_points'][0]} and {profile['num_key_points'][1]} items.
- practice_questions must contain exactly {profile['num_practice_questions']} items, style: {profile['question_style']}.
- flashcards must contain exactly {profile['num_flashcards']} items.

RETRIEVED CONTEXT FROM RESEARCH AGENT:
{context_block}

YOUR PRIOR PLAN (use it, don't repeat it verbatim, refine it into final content):
{plan_text}

TASK:
Produce the final lesson content now.

Return ONLY a single JSON object matching exactly this schema (no extra keys,
no missing keys, no markdown fences, no text before or after it):

{JSON_SCHEMA_DESCRIPTION}

Remember: ground content in the retrieved context, match the difficulty profile
exactly, and make practice_questions test the key_points you wrote above."""


def build_single_pass_prompt(topic: str, context_block: str, profile: Dict) -> str:
    """
    Optional single-call variant (plan + generate combined) for lower latency
    / lower token-cost use cases where two separate LLM calls aren't wanted.
    The model is still asked to reason first, then emit a clearly delimited
    final JSON block, which teaching_agent.py extracts by marker.
    """
    return f"""TOPIC: {topic}

DIFFICULTY PROFILE: {profile['label']}
- Vocabulary: {profile['vocabulary']}
- Sentence style: {profile['sentence_style']}
- Depth: {profile['depth']}
- Analogy style: {profile['analogy_style']}
- Example complexity: {profile['example_complexity']}
- step_by_step should have between {profile['num_step_by_step'][0]} and {profile['num_step_by_step'][1]} steps.
- key_points should have between {profile['num_key_points'][0]} and {profile['num_key_points'][1]} items.
- practice_questions must contain exactly {profile['num_practice_questions']} items, style: {profile['question_style']}.
- flashcards must contain exactly {profile['num_flashcards']} items.

RETRIEVED CONTEXT FROM RESEARCH AGENT:
{context_block}

TASK:
First, briefly reason step-by-step (a few lines) about the core idea, the key
points, a fitting analogy, and a worked example, grounded in the context above.

Then write the line:
FINAL_JSON:

Followed immediately by ONE valid JSON object (no markdown fences) matching
exactly this schema:

{JSON_SCHEMA_DESCRIPTION}
"""
