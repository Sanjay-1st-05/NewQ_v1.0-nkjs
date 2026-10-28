"""Agent orchestration tests.

The generator is stubbed to exercise the repair loop deterministically;
validation and classification run for real. The real-Gemini integration
path is verified separately on a live server, not here.
"""

import pytest

from ai_engine import agent


BASE_TEXT = (
    "The Reserve Bank of India announced a new monetary policy framework "
    "aimed at maintaining price stability and supporting economic growth. "
    "The policy focuses on managing inflation, maintaining adequate "
    "liquidity and strengthening financial stability."
)


def make_question(index: int, text_key: str = "framework") -> dict:
    return {
        "type": "Multiple Choice",
        "question": f"What did the Reserve Bank of India announce about its {text_key} policy {index}?",
        "options": [
            "A stable framework for price stability",
            "Privatizing all public sector banks",
            "Ending all lending controls",
            "Replacing the finance ministry",
        ],
        "answer": "A stable framework for price stability",
        "explanation": "The news states the framework aims at price stability.",
        "source": "announced a new monetary policy framework",
        "difficulty": "Easy",
        "topic": "Monetary Policy",
    }


class StubGenerator:
    """Returns a scripted sequence of payloads instead of calling Gemini."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
        self.feedbacks = []

    def __call__(self, text, exam, question_count, repair_feedback=""):
        self.calls.append({"exam": exam, "count": question_count})
        self.feedbacks.append(repair_feedback)
        return self.payloads.pop(0)


@pytest.fixture(autouse=True)
def restored_settings(monkeypatch):
    yield
    # Agent settings come from env at import; tests do not mutate them.


def test_single_clean_pass_skips_repair():
    payload = {"questions": [make_question(i) for i in range(1, 4)]}
    stub = StubGenerator([payload])
    original = agent.generate_raw_questions
    agent.generate_raw_questions = stub

    try:
        result = agent.analyze_with_agent(BASE_TEXT, "Banking", 3)
    finally:
        agent.generate_raw_questions = original

    assert result["question_count"] == 3
    assert len(stub.calls) == 1
    assert stub.calls[0]["exam"] == "Banking"
    assert [q["id"] for q in result["questions"]] == [
        "agent-1",
        "agent-2",
        "agent-3",
    ]
    steps = [entry["step"] for entry in result["agent_trace"]]
    assert steps == ["classify", "generate+validate", "assemble"]
    assert result["agent_stats"]["generator_calls"] == 1


def test_repair_loop_recovers_rejected_questions():
    # First pass: question 2 has a source excerpt not in the news.
    bad = make_question(2)
    bad["source"] = "completely fabricated quote not present anywhere"
    first = {"questions": [make_question(1), bad, make_question(3)]}
    second = {
        "questions": [make_question(1), make_question(2), make_question(3)],
    }
    stub = StubGenerator([first, second])
    original = agent.generate_raw_questions
    agent.generate_raw_questions = stub

    try:
        result = agent.analyze_with_agent(BASE_TEXT, "Banking", 3)
    finally:
        agent.generate_raw_questions = original

    assert result["question_count"] == 3
    assert result["agent_stats"]["generator_calls"] == 2
    assert result["agent_stats"]["raw_generated"] == 6

    # The repair call carried the rejection feedback.
    assert "source evidence mismatch" in stub.feedbacks[1]

    # No duplicates survived the merge.
    question_texts = [q["question"] for q in result["questions"]]
    assert len(set(question_texts)) == 3

    generate_steps = [
        entry
        for entry in result["agent_trace"]
        if entry["step"] == "generate+validate"
    ]
    assert generate_steps[0]["rejected"] >= 1
    assert any(
        entry["step"] == "repair-feedback-sent"
        for entry in result["agent_trace"]
    )


def test_no_repair_when_target_already_met():
    # First pass returns 3 valid (target met). Even though later questions
    # could exist, the agent must not burn an extra generator call.
    payload = {"questions": [make_question(i) for i in range(1, 4)]}
    stub = StubGenerator([payload, payload])
    original = agent.generate_raw_questions
    agent.generate_raw_questions = stub

    try:
        result = agent.analyze_with_agent(BASE_TEXT, "Banking", 3)
    finally:
        agent.generate_raw_questions = original

    assert result["question_count"] == 3
    assert len(stub.calls) == 1


def test_repair_respects_disabled_config(monkeypatch):
    monkeypatch.setattr(agent, "AGENT_MAX_REPAIRS", 0)
    bad = make_question(2)
    bad["source"] = "completely fabricated quote not present anywhere"
    first = {"questions": [make_question(1), bad, make_question(3)]}
    stub = StubGenerator([first, first])
    original = agent.generate_raw_questions
    agent.generate_raw_questions = stub

    try:
        result = agent.analyze_with_agent(BASE_TEXT, "Banking", 3)
    finally:
        agent.generate_raw_questions = original

    # No repair pass budgeted → only one generator call.
    assert len(stub.calls) == 1
    assert result["question_count"] >= 2
