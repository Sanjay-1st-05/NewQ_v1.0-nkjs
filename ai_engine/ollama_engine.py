"""Stage 7c: offline question generation via a local Ollama model.

Runs when the cloud path (agent/Gemini) is unavailable — no internet,
missing API key, provider outage — generating MCQs on-device with the
same validation rules as the Gemini engine, so a llama3.2 response that
cannot quote the news verbatim is rejected rather than trusted.

Reuses the shared pieces (classification, prompt builder, validator)
from gemini_engine to keep one source of truth for quality rules.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict

from dotenv import load_dotenv

from ai_engine.engine import clean_text
from ai_engine.gemini_engine import (
    _build_prompt,
    classify_news,
    validate_questions,
)

load_dotenv()

# Local defaults: stock Ollama install on the same PC as the backend.
OLLAMA_HOST = os.getenv("NEWQ_OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("NEWQ_OLLAMA_MODEL", "llama3.2:3b")
# Availability probes are cached so /health and repeated requests stay cheap.
AVAILABILITY_TTL_SECONDS = 30.0
# CPU-only inference (no discrete GPU) runs llama3.2:3b at ~7 tok/s; a
# full 5-question JSON answer needs several minutes including load time.
GENERATE_TIMEOUT_SECONDS = 420.0

_availability_cache: Dict[str, Any] = {"checked_at": 0.0, "available": False}


def _get_json(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def is_ollama_available() -> bool:
    """Whether the local Ollama server is up and has the model loaded."""
    now = time.monotonic()
    if now - _availability_cache["checked_at"] < AVAILABILITY_TTL_SECONDS:
        return _availability_cache["available"]

    available = False
    try:
        tags = _get_json(f"{OLLAMA_HOST}/api/tags")
        names = {model.get("name", "") for model in tags.get("models", [])}
        available = any(
            name == OLLAMA_MODEL or name.split(":")[0] == OLLAMA_MODEL.split(":")[0]
            for name in names
        )
    except (urllib.error.URLError, OSError, ValueError):
        available = False

    _availability_cache["checked_at"] = now
    _availability_cache["available"] = available
    return available


def _extract_json(raw: str) -> Dict[str, Any]:
    """Parse the model's JSON payload, tolerating code fences."""
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        generated = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON.") from exc
    if not isinstance(generated, dict):
        raise RuntimeError("Ollama returned an invalid JSON structure.")
    return generated


def generate_raw_questions_ollama(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
    repair_feedback: str = "",
) -> Dict[str, Any]:
    """Run the local Ollama JSON call and return the raw generated payload.

    Raises ValueError for client-side problems and RuntimeError for
    provider problems, matching the Gemini engine's contract.
    """
    text = clean_text(text)

    if len(text) < 80:
        raise ValueError("Please provide at least 80 characters of news content.")

    if not is_ollama_available():
        raise RuntimeError(
            f"Ollama is not running or model '{OLLAMA_MODEL}' is not pulled."
        )

    prompt = build_prompt_simple(text, exam, question_count)

    response = _post_json(
        f"{OLLAMA_HOST}/api/generate",
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1400,
            },
        },
        timeout=GENERATE_TIMEOUT_SECONDS,
    )

    raw = response.get("response", "")
    if not raw:
        raise RuntimeError("Ollama returned an empty response.")

    return _extract_json(raw)


def build_prompt_simple(text: str, exam: str, question_count: int) -> str:
    """Wrap the shared Gemini prompt builder with the detected context."""
    from ai_engine.engine import detect_subject, detect_topic

    subject, _ = detect_subject(text)
    topic = detect_topic(text, subject)
    return _build_prompt(text, exam, question_count, subject, topic)


def analyze_news_ollama(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
) -> Dict[str, Any]:
    """Generate exam-focused news analysis using local Ollama."""
    text = clean_text(text)

    if len(text) < 80:
        raise ValueError("Please provide at least 80 characters of news content.")

    classification = classify_news(text, exam)
    generated = generate_raw_questions_ollama(text, exam, question_count)
    valid_questions, _ = validate_questions(
        generated.get("questions"),
        text,
        question_count,
        id_prefix="ollama",
    )

    return {
        "app": "NewQ",
        "version": "0.3-ollama",
        "exam": exam,
        "subject": generated.get("subject") or classification["subject"],
        "topic": generated.get("topic") or classification["topic"],
        "relevance": classification["relevance"],
        "relevance_score": classification["relevance_score"],
        "confidence_note": (
            "Offline analysis generated by the local Ollama model. "
            "Questions are checked against NewQ validation rules and "
            "source evidence."
        ),
        "keywords": generated.get("keywords", []),
        "summary": generated.get("summary", ""),
        "signals": classification["signals"],
        "subject_scores": classification["subject_scores"],
        "question_count": len(valid_questions),
        "questions": valid_questions,
    }
