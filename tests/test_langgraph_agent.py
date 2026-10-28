"""LangGraph agent graph tests (generator stubbed, validation real)."""

import pytest

from ai_engine import langgraph_agent as lg_agent

from tests.test_agent_orchestration import (
    BASE_TEXT,
    StubGenerator,
    make_question,
)


@pytest.fixture()
def patched_generator(monkeypatch):
    def install(payloads):
        stub = StubGenerator(payloads)
        monkeypatch.setattr(lg_agent, "generate_raw_questions", stub)
        return stub

    return install


def test_langgraph_available():
    assert lg_agent.LANGGRAPH_AVAILABLE, "LangGraph must be installed for these tests"


def test_clean_single_pass(patched_generator):
    payload = {"questions": [make_question(i) for i in range(1, 4)]}
    stub = patched_generator([payload])

    result = lg_agent.analyze_with_langgraph_agent(BASE_TEXT, "Banking", 3)

    assert result["question_count"] == 3
    assert result["agent_framework"] == "langgraph"
    assert result["agent_stats"]["framework"] == "langgraph"
    assert result["agent_stats"]["generator_calls"] == 1
    assert [q["id"] for q in result["questions"]] == ["agent-1", "agent-2", "agent-3"]

    steps = [entry["step"] for entry in result["agent_trace"]]
    assert steps[0] == "classify"
    assert "assemble" in steps
    assert "repair-feedback-sent" not in steps


def test_repair_loop_runs_through_graph(patched_generator):
    bad = make_question(2)
    bad["source"] = "a fabricated quote that appears nowhere in the news text"
    first = {"questions": [make_question(1), bad, make_question(3)]}
    second = {"questions": [make_question(1), make_question(2), make_question(3)]}
    stub = patched_generator([first, second])

    result = lg_agent.analyze_with_langgraph_agent(BASE_TEXT, "Banking", 3)

    assert result["question_count"] == 3
    assert result["agent_stats"]["generator_calls"] == 2
    assert "source evidence mismatch" in stub.feedbacks[1]

    texts = [q["question"] for q in result["questions"]]
    assert len(set(texts)) == 3

    generate_steps = [
        entry
        for entry in result["agent_trace"]
        if entry["step"] == "generate+validate"
    ]
    assert len(generate_steps) == 2
    assert generate_steps[0]["rejected"] == 1
    assert generate_steps[1]["rejected"] == 0


def test_budget_limits_repair_passes(monkeypatch, patched_generator):
    monkeypatch.setattr(lg_agent, "AGENT_MAX_REPAIRS", 0)
    bad = make_question(2)
    bad["source"] = "a fabricated quote that appears nowhere in the news text"
    first = {"questions": [make_question(1), bad, make_question(3)]}
    stub = patched_generator([first, first])

    result = lg_agent.analyze_with_langgraph_agent(BASE_TEXT, "Banking", 3)

    assert len(stub.calls) == 1
    assert result["agent_stats"]["generator_calls"] == 1
