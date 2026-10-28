"""LangGraph-backed NewQ analysis agent.

Implements the same classify -> generate -> validate -> repair pipeline as
`ai_engine.agent`, but orchestrated as an explicit state machine with
LangGraph (github.com/langchain-ai/langgraph, MIT) so the agentic
architecture is a recognized, inspectable graph rather than a hand-rolled
loop:

    START -> classify -> generate -> validate --(rejections, budget left)
              ^                |                     -> repair -> (back to generate)
              |                +----------------------(clean or budget spent)
            assemble -> END

Tools used by the agent nodes:
- classify_news        (deterministic NewQ NLP classifier)
- generate_raw_questions (Gemini generator, contract-swappable)
- validate_questions   (source-evidence + option-quality validator)

If LangGraph is not importable, callers fall back to the built-in loop in
`ai_engine.agent` — the output shape is identical.
"""

import operator
import os
from typing import Annotated, Any, Dict, List, TypedDict

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False

from ai_engine.agent import _merge_attempts, _repair_feedback
from ai_engine.gemini_engine import (
    classify_news,
    generate_raw_questions,
    validate_questions,
)

# State reducers: trace and gathered MUST accumulate across nodes (the
# LangGraph default for plain fields is overwrite, which would drop every
# earlier trace entry).
AdditiveList = Annotated[List[Any], operator.add]

AGENT_MAX_REPAIRS = max(
    0,
    int(os.getenv("NEWQ_AGENT_MAX_REPAIRS", "1")),
)


class AgentState(TypedDict, total=False):
    """State passed between the graph nodes."""

    text: str
    exam: str
    question_count: int

    # Classification results (from the classify node).
    classification: Dict[str, Any]

    # Accumulated generation results.
    gathered: AdditiveList
    rejections: List[Dict[str, Any]]
    feedback: str
    last_generated: Dict[str, Any]
    last_raw_count: int

    # Bookkeeping.
    attempts: int
    total_raw: int
    total_rejected: int
    trace: AdditiveList


def _classify(state: AgentState) -> Dict[str, Any]:
    classification = classify_news(state["text"], state["exam"])
    trace_entry = {
        "step": "classify",
        "subject": classification["subject"],
        "topic": classification["topic"],
        "relevance": classification["relevance"],
    }
    return {"classification": classification, "trace": [trace_entry]}


def _generate(state: AgentState) -> Dict[str, Any]:
    generated = generate_raw_questions(
        state["text"],
        state["exam"],
        state["question_count"],
        repair_feedback=state.get("feedback", ""),
    )
    raw = generated.get("questions", [])
    raw_count = len(raw) if isinstance(raw, list) else 0

    return {
        "last_generated": generated,
        "last_raw_count": raw_count,
        "attempts": state.get("attempts", 0) + 1,
        "total_raw": state.get("total_raw", 0) + raw_count,
    }


def _validate(state: AgentState) -> Dict[str, Any]:
    generated = state.get("last_generated", {})
    attempt_valid, rejections = validate_questions(
        generated.get("questions"),
        state["text"],
        state["question_count"],
        id_prefix=f"agent-a{state['attempts']}",
    )

    trace_entry = {
        "step": "generate+validate",
        "attempt": state["attempts"],
        "generated": state.get("last_raw_count", 0),
        "accepted": len(attempt_valid),
        "rejected": len(rejections),
        "reasons": [entry["reason"] for entry in rejections][:5],
    }

    return {
        "gathered": state.get("gathered", []) + attempt_valid,
        "rejections": rejections,
        "total_rejected": state.get("total_rejected", 0) + len(rejections),
        "trace": [trace_entry],
    }


def _needs_repair(state: AgentState) -> str:
    if not state.get("rejections"):
        return "assemble"
    if state["attempts"] > AGENT_MAX_REPAIRS:
        return "assemble"
    if len(state.get("gathered", [])) >= state["question_count"]:
        return "assemble"
    return "repair"


def _repair(state: AgentState) -> Dict[str, Any]:
    feedback = _repair_feedback(state["rejections"])
    return {
        "feedback": feedback,
        "trace": [{"step": "repair-feedback-sent", "issues": len(state["rejections"])}],
    }


def _assemble(state: AgentState) -> Dict[str, Any]:
    return {"trace": [{"step": "assemble"}]}


def build_graph():
    """Compile the NewQ analysis agent graph."""
    graph = StateGraph(AgentState)
    graph.add_node("classify", _classify)
    graph.add_node("generate", _generate)
    graph.add_node("validate", _validate)
    graph.add_node("repair", _repair)
    graph.add_node("assemble", _assemble)

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", _needs_repair)
    graph.add_edge("repair", "generate")
    graph.add_edge("assemble", END)

    return graph.compile()


_compiled = None


def _get_compiled():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def analyze_with_langgraph_agent(
    text: str,
    exam: str = "UPSC",
    question_count: int = 5,
) -> Dict[str, Any]:
    """Run the NewQ analysis agent as a LangGraph state machine."""
    import time

    started = time.perf_counter()

    state: AgentState = {
        "text": text,
        "exam": exam,
        "question_count": question_count,
        "gathered": [],
        "attempts": 0,
        "total_raw": 0,
        "total_rejected": 0,
        "feedback": "",
    }

    final = _get_compiled().invoke(state)

    classification = final.get("classification", {})
    merged = _merge_attempts(final.get("gathered", []), question_count)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    trace = final.get("trace", [])

    assemble_entry = {
        "step": "assemble",
        "final_questions": len(merged),
        "attempts": final.get("attempts", 0),
        "elapsed_ms": elapsed_ms,
        "framework": "langgraph",
    }

    # The assemble node contributes an entry; enrich it with the final
    # stats instead of appending a duplicate.
    if trace and trace[-1].get("step") == "assemble":
        trace[-1] = {
            **trace[-1],
            "final_questions": len(merged),
            "attempts": final.get("attempts", 0),
            "elapsed_ms": elapsed_ms,
            "framework": "langgraph",
        }
    else:
        trace.append(assemble_entry)

    last_generated = final.get("last_generated", {})

    return {
        "app": "NewQ",
        "version": "0.3-agent",
        "agent_framework": "langgraph",
        "exam": exam,
        "subject": last_generated.get("subject") or classification.get("subject"),
        "topic": last_generated.get("topic") or classification.get("topic"),
        "relevance": classification.get("relevance"),
        "relevance_score": classification.get("relevance_score"),
        "confidence_note": (
            "LangGraph agent: generated by AI, validated and repaired "
            "against NewQ source-evidence and option-quality rules."
        ),
        "keywords": last_generated.get("keywords", []),
        "summary": last_generated.get("summary", ""),
        "signals": classification.get("signals", []),
        "subject_scores": classification.get("subject_scores", {}),
        "question_count": len(merged),
        "questions": merged,
        "agent_trace": trace,
        "agent_stats": {
            "framework": "langgraph",
            "generator_calls": final.get("attempts", 0),
            "raw_generated": final.get("total_raw", 0),
            "rejected": final.get("total_rejected", 0),
        },
    }
