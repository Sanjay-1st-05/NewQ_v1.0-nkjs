
import os
import json
import re
from typing import Any, Dict

from dotenv import load_dotenv
from google import genai

from ai_engine.engine import (
    clean_text,
    detect_subject,
    detect_topic,
    relevance,
    validate_question,
)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

client = genai.Client(api_key=API_KEY) if API_KEY else None

# Option patterns that can never be source-validated and make distractor
# quality checks meaningless. Compared after whitespace/punctuation folding.
BANNED_OPTION_TEXTS = {
    "all of the above",
    "all the above",
    "none of the above",
    "none of these",
    "all of these",
    "both a and b",
    "both 1 and 2",
    "both a and b only",
}


def normalize_option_text(value) -> str:
    """Fold whitespace, punctuation, and case for option comparisons."""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return re.sub(r"[.!?,;:]+$", "", text)

# One-line style guidance per supported exam, mirroring the orientation of
# the rule-based engine's EXAM_WEIGHTS (which subjects matter most).
EXAM_STYLE = {
    "UPSC": (
        "Analytical civil-services current affairs; expect questions on the "
        "significance, institutions, and policy implications of the news."
    ),
    "TNPSC": (
        "State civil-service current affairs with emphasis on Indian "
        "government actions, statutory bodies, and factual specifics."
    ),
    "SSC": (
        "Direct fact-recall style questions: names, programmes, dates, and "
        "official launches mentioned in the news."
    ),
    "Banking": (
        "Banking, monetary policy, and financial-regulation focus: RBI, "
        "liquidity, interest rates, and financial stability framing."
    ),
    "Defence": (
        "Defence, security, and strategic current affairs: services, "
        "exercises, systems, and border-security developments."
    ),
}


def classify_news(text: str, exam: str = "UPSC") -> Dict[str, Any]:
    """Detected subject, topic, and relevance for a news text.

    Shared by the direct Gemini engine and the agent orchestrator so both
    produce identical classification fields.
    """
    subject, subject_scores = detect_subject(text)
    topic = detect_topic(text, subject)
    level, score, signals = relevance(text, exam, subject, topic)

    return {
        "subject": subject,
        "subject_scores": subject_scores,
        "topic": topic,
        "relevance": level,
        "relevance_score": score,
        "signals": signals,
    }


def _build_prompt(
    text: str,
    exam: str,
    question_count: int,
    subject: str,
    topic: str,
    repair_feedback: str = "",
) -> str:
    exam_style = EXAM_STYLE.get(
        exam,
        "General competitive-exam current-affairs style.",
    )

    if repair_feedback:
        repair_section = f"""
IMPORTANT — REPAIR pass. In your previous attempt the following questions
were rejected by the NewQ validator and must be fixed or reproduced
correctly. Each entry shows the question and its rejection reason:

{repair_feedback}

Fix every listed issue strictly. Every fixed question must still be
answerable only from the supplied news, and its "source" field must quote
the news text verbatim. In addition to the repaired questions, regenerate
the full set so the total covers {question_count} valid questions.
"""
    else:
        repair_section = ""

    return f"""
You are NewQ, an exam-preparation news analysis assistant.

Target exam: {exam}
Exam style focus: {exam_style}
Detected subject: {subject}
Detected topic: {topic}
Requested MCQs: {question_count}

Analyze ONLY the supplied news. Do not invent facts, dates, statistics,
institutions, or claims. Every question must be answerable from the news.

Generate exactly {question_count} useful MCQs whenever the source supports
that many distinct, valid questions. Do not invent facts or repeat questions.
If the source does not support that many questions, return only the valid ones.
{repair_section}
Each question must contain:
- type
- question
- options: exactly four distinct strings
- answer: exactly one of the options
- explanation
- source: an exact supporting excerpt from the supplied news
- difficulty: Easy, Medium, or Hard
- topic

Question wording rules:
- Phrase clear, direct, self-contained questions.
- Do not use unsupported fill-in-the-blank questions.
- The question must be answerable from the news alone.

Option quality rules:
- All four options must be plausible, comparable in length and abstraction.
- Distractors must be factually wrong or unsupported by the news, never
  self-evidently absurd.
- Never use "All of the above", "None of the above", or numbered
  combination options.
- Exactly one option may be defensibly correct using the supplied news.

Difficulty rubric:
- Easy: a directly stated fact.
- Medium: reworded content or details that require locating in the source.
- Hard: inference or comparison, still strictly grounded in the source.

Return JSON only with these fields:
subject, topic, summary, keywords, questions.

NEWS CONTENT:
{text}
"""


def generate_raw_questions(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
    repair_feedback: str = "",
) -> Dict[str, Any]:
    """Run the Gemini JSON call and return the raw generated payload.

    Raises the same error types as before (ValueError for client-side
    problems, RuntimeError for provider problems) so the fallback logic in
    the API layer stays accurate.
    """
    text = clean_text(text)

    if len(text) < 80:
        raise ValueError("Please provide at least 80 characters of news content.")

    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    subject, _ = detect_subject(text)
    topic = detect_topic(text, subject)

    prompt = _build_prompt(text, exam, question_count, subject, topic, repair_feedback)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": {
                "type": "OBJECT",
                "properties": {
                    "subject": {"type": "STRING"},
                    "topic": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "keywords": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "questions": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "type": {"type": "STRING"},
                                "question": {"type": "STRING"},
                                "options": {
                                    "type": "ARRAY",
                                    "items": {"type": "STRING"},
                                },
                                "answer": {"type": "STRING"},
                                "explanation": {"type": "STRING"},
                                "source": {"type": "STRING"},
                                "difficulty": {"type": "STRING"},
                                "topic": {"type": "STRING"},
                            },
                            "required": [
                                "type",
                                "question",
                                "options",
                                "answer",
                                "explanation",
                                "source",
                                "difficulty",
                                "topic",
                            ],
                        },
                    },
                },
                "required": [
                    "subject",
                    "topic",
                    "summary",
                    "keywords",
                    "questions",
                ],
            },
        },
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        generated = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned invalid JSON.") from exc

    if not isinstance(generated, dict):
        raise RuntimeError("Gemini returned an invalid JSON structure.")

    return generated


def validate_questions(
    raw_questions: Any,
    text: str,
    question_count: int = 5,
    id_prefix: str = "gemini",
) -> tuple:
    """Apply the NewQ validation rules to generated questions.

    Returns (valid_questions, rejections) — rejections carry the question
    text and reason so the agent can budget a repair pass and the API can
    keep its debug output.
    """
    valid_questions = []
    rejections = []
    seen_questions = set()

    raw_list = raw_questions if isinstance(raw_questions, list) else []

    print(f"\n[DEBUG] Gemini returned {len(raw_list)} questions")

    for index, raw_question in enumerate(raw_list, start=1):
        if not isinstance(raw_question, dict):
            rejections.append({"index": index, "question": "", "reason": "not a dictionary"})
            print(f"[DEBUG] Question {index}: rejected — not a dictionary")
            continue

        # Work on a copy so the original response is not modified.
        question = raw_question.copy()

        # Reject lazy option patterns such as "All of the above" that make
        # options unusable and cannot be validated against the source.
        normalized_options = [
            normalize_option_text(option)
            if isinstance(option, str)
            else ""
            for option in question.get("options", [])
        ]
        if any(option in BANNED_OPTION_TEXTS for option in normalized_options):
            rejections.append({
                "index": index,
                "question": str(question.get("question", ""))[:120],
                "reason": "banned option pattern",
            })
            print(f"[DEBUG] Question {index}: rejected — banned option pattern")
            continue

        if question.get("difficulty") not in {"Easy", "Medium", "Hard"}:
            question["difficulty"] = "Medium"

        # Require source evidence to appear in the supplied news.
        evidence = question.get("source", "")

        if not isinstance(evidence, str):
            rejections.append({
                "index": index,
                "question": str(question.get("question", ""))[:120],
                "reason": "invalid source",
            })
            print(f"[DEBUG] Question {index}: rejected — invalid source")
            continue

        evidence = evidence.strip()

        if len(evidence) < 15 or evidence.casefold() not in text.casefold():
            rejection = {
                "index": index,
                "question": str(question.get("question", ""))[:120],
                "reason": "source evidence mismatch",
            }
            rejections.append(rejection)
            print(f"[DEBUG] Question {index}: rejected — source evidence mismatch")
            print(f"[DEBUG] Source received: {evidence!r}")
            continue

        # Validate options, answer, explanation, and question structure.
        valid, issues = validate_question(question)

        # Permit a clear direct question if the only failed rule is the
        # existing engine's weak-grounding heuristic.
        if not valid:
            only_grounding_issue = issues == ["question is weakly grounded"]

            question_text = question.get("question", "")
            is_direct_question = (
                isinstance(question_text, str)
                and question_text.strip().endswith("?")
            )

            if not (only_grounding_issue and is_direct_question):
                rejections.append({
                    "index": index,
                    "question": str(question.get("question", ""))[:120],
                    "reason": "; ".join(issues) or "failed validation",
                })
                print(f"[DEBUG] Question {index}: rejected — {issues}")
                continue

        question_text = question.get("question", "")

        if not isinstance(question_text, str) or not question_text.strip():
            rejections.append({
                "index": index,
                "question": "",
                "reason": "empty question",
            })
            print(f"[DEBUG] Question {index}: rejected — empty question")
            continue

        question_key = " ".join(question_text.casefold().split())

        if question_key in seen_questions:
            rejections.append({
                "index": index,
                "question": question_text[:120],
                "reason": "duplicate",
            })
            print(f"[DEBUG] Question {index}: rejected — duplicate")
            continue

        seen_questions.add(question_key)
        valid_questions.append(question)

        print(f"[DEBUG] Question {index}: accepted")

        if len(valid_questions) >= question_count:
            break

    # Assign unique, sequential IDs after all validation is complete.
    for index, question in enumerate(valid_questions, start=1):
        question["id"] = f"{id_prefix}-{index}"

    print(f"[DEBUG] Final accepted question count: {len(valid_questions)}")

    return valid_questions, rejections


def analyze_news_gemini(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
) -> Dict[str, Any]:
    """Generate exam-focused news analysis using Gemini (direct path)."""
    text = clean_text(text)

    if len(text) < 80:
        raise ValueError("Please provide at least 80 characters of news content.")

    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    classification = classify_news(text, exam)
    generated = generate_raw_questions(text, exam, question_count)
    valid_questions, _ = validate_questions(
        generated.get("questions"),
        text,
        question_count,
    )

    return {
        "app": "NewQ",
        "version": "0.3-gemini",
        "exam": exam,
        "subject": generated.get("subject") or classification["subject"],
        "topic": generated.get("topic") or classification["topic"],
        "relevance": classification["relevance"],
        "relevance_score": classification["relevance_score"],
        "confidence_note": (
            "Gemini-generated analysis. Questions are checked against "
            "NewQ validation rules and source evidence."
        ),
        "keywords": generated.get("keywords", []),
        "summary": generated.get("summary", ""),
        "signals": classification["signals"],
        "subject_scores": classification["subject_scores"],
        "question_count": len(valid_questions),
        "questions": valid_questions,
    }
