"""NewQ analysis agent.

Orchestrates the MCQ pipeline as an agentic loop instead of a single
model call:

1. CLASSIFY  — deterministic rules (subject / topic / relevance).
2. GENERATE  — Gemini produces the draft set (the "generator tool").
3. VALIDATE  — NewQ rules: source evidence, option quality, dedupe.
4. REPAIR    — if questions were rejected and output is short of the
               requested count, feed each rejection reason back to the
               generator for one corrective pass, then re-validate.
5. ASSEMBLE  — merged, deduped final set plus an agent_trace so callers
               (and debugging) can see exactly what the agent did.

The generator/model behind step 2 is swappable: the loop only depends on
`generate_raw_questions(...)` returning a dict with a "questions" key and
`validate_questions(...)` enforcing NewQ rules. Gemini today; a local
model (e.g. Ollama) can implement the same contract tomorrow.
"""

import os
import time
from typing import Any, Dict, List

from ai_engine.gemini_engine import (
    classify_news,
    generate_raw_questions,
    validate_questions,
)

AGENT_ENABLED = os.getenv("NEWQ_AGENT", "1") != "0"
AGENT_MAX_REPAIRS = max(0, int(os.getenv("NEWQ_AGENT_MAX_REPAIRS", "1")))


def _repair_feedback(rejections: List[Dict[str, Any]]) -> str:
    """Render rejection reasons into concise feedback for the generator."""
    lines = []

    for rejection in rejections:
        question = str(rejection.get("question", "")).strip()
        reason = str(rejection.get("reason", "")).strip()

        if question:
            lines.append(f"- Question: \"{question}\" — rejected: {reason}")
        elif reason:
            lines.append(f"- Rejected: {reason}")

    return "\n".join(lines)


def _merge_attempts(
    gathered: List[Dict[str, Any]],
    question_count: int,
) -> List[Dict[str, Any]]:
    """Dedupe attempts across passes, keep order, cap at the request."""
    seen = set()
    merged = []

    for question in gathered:
        text_key = " ".join(
            str(question.get("question", "")).casefold().split()
        )

        if not text_key or text_key in seen:
            continue

        seen.add(text_key)
        merged.append(question)

        if len(merged) >= question_count:
            break

    for index, question in enumerate(merged, start=1):
        question["id"] = f"agent-{index}"

    return merged


def analyze_with_agent(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
) -> Dict[str, Any]:
    """Run the classify → generate → validate → repair pipeline."""
    started = time.perf_counter()
    trace: List[Dict[str, Any]] = []

    classification = classify_news(text, exam)
    trace.append({
        "step": "classify",
        "subject": classification["subject"],
        "topic": classification["topic"],
        "relevance": classification["relevance"],
    })

    valid: List[Dict[str, Any]] = []
    feedback = ""
    attempts = 0
    total_raw = 0
    total_rejected = 0
    last_generated: Dict[str, Any] = {}

    for attempt in range(AGENT_MAX_REPAIRS + 1):
        attempts += 1
        generated = generate_raw_questions(
            text,
            exam,
            question_count,
            repair_feedback=feedback,
        )
        last_generated = generated
        raw = generated.get("questions", [])
        raw_count = len(raw) if isinstance(raw, list) else 0
        total_raw += raw_count

        attempt_valid, rejections = validate_questions(
            raw,
            text,
            question_count,
            id_prefix=f"agent-a{attempt + 1}",
        )
        valid.extend(attempt_valid)
        total_rejected += len(rejections)

        trace.append({
            "step": "generate+validate",
            "attempt": attempt + 1,
            "generated": raw_count,
            "accepted": len(attempt_valid),
            "rejected": len(rejections),
            "reasons": [item["reason"] for item in rejections][:5],
        })

        if len(valid) >= question_count or not rejections:
            break

        # Only spend a repair pass while the request is still unmet.
        if attempt >= AGENT_MAX_REPAIRS:
            break

        feedback = _repair_feedback(rejections)
        trace.append({"step": "repair-feedback-sent", "issues": len(rejections)})

    merged = _merge_attempts(valid, question_count)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    trace.append({
        "step": "assemble",
        "final_questions": len(merged),
        "attempts": attempts,
        "elapsed_ms": elapsed_ms,
    })

    return {
        "app": "NewQ",
        "version": "0.3-agent",
        "exam": exam,
        "subject": last_generated.get("subject") or classification["subject"],
        "topic": last_generated.get("topic") or classification["topic"],
        "relevance": classification["relevance"],
        "relevance_score": classification["relevance_score"],
        "confidence_note": (
            "Agent pipeline: generated by AI, validated and repaired "
            "against NewQ source-evidence and option-quality rules."
        ),
        "keywords": last_generated.get("keywords", []),
        "summary": last_generated.get("summary", ""),
        "signals": classification["signals"],
        "subject_scores": classification["subject_scores"],
        "question_count": len(merged),
        "questions": merged,
        "agent_trace": trace,
        "agent_stats": {
            "generator_calls": attempts,
            "raw_generated": total_raw,
            "rejected": total_rejected,
        },
    }
