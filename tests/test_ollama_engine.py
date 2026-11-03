"""Stage 7c: Ollama offline engine tests (no live model required)."""

import json

import pytest
from fastapi.testclient import TestClient

from ai_engine import ollama_engine
from ai_engine.ollama_engine import (
    _extract_json,
    analyze_news_ollama,
    is_ollama_available,
)
from backend import auth as stage7_auth
from backend.main import app

NEWS = (
    "The Reserve Bank of India announced a new monetary policy framework "
    "aimed at maintaining price stability and supporting economic growth. "
    "The framework keeps the inflation target and reinforces liquidity "
    "management measures for scheduled commercial banks."
)


@pytest.fixture()
def open_mode(monkeypatch):
    monkeypatch.setattr(stage7_auth, "is_auth_required", lambda: False)
    yield


@pytest.fixture()
def client(open_mode):
    return TestClient(app)


def test_extract_json_plain():
    payload = {"subject": "Economy", "questions": []}
    assert _extract_json(json.dumps(payload)) == payload


def test_extract_json_tolerates_code_fences():
    payload = {"questions": [{"question": "q"}]}
    raw = "```json\n" + json.dumps(payload) + "\n```"
    assert _extract_json(raw) == payload


def test_extract_json_rejects_garbage():
    with pytest.raises(RuntimeError):
        _extract_json("this is not json at all")


def test_unavailable_when_no_ollama(monkeypatch):
    monkeypatch.setattr(
        ollama_engine, "_get_json",
        lambda url, timeout=3.0: (_ for _ in ()).throw(OSError("refused")),
    )
    ollama_engine._availability_cache["checked_at"] = 0.0  # force re-probe
    assert is_ollama_available() is False
    ollama_engine._availability_cache["checked_at"] = 0.0


def test_available_when_model_pulled(monkeypatch):
    monkeypatch.setattr(
        ollama_engine, "_get_json",
        lambda url, timeout=3.0: {"models": [{"name": "llama3.2:3b"}]},
    )
    ollama_engine._availability_cache["checked_at"] = 0.0
    assert is_ollama_available() is True
    ollama_engine._availability_cache["checked_at"] = 0.0


def test_generate_raises_when_model_missing(monkeypatch):
    monkeypatch.setattr(ollama_engine, "is_ollama_available", lambda: False)
    with pytest.raises(RuntimeError, match="not pulled"):
        ollama_engine.generate_raw_questions_ollama(NEWS, "Banking", 3)


def _canned_ollama_response() -> dict:
    question = {
        "type": "News Fact",
        "question": "Which institution announced the new monetary policy framework?",
        "options": [
            "Reserve Bank of India",
            "State Bank of India",
            "NITI Aayog",
            "Ministry of Finance",
        ],
        "answer": "Reserve Bank of India",
        "explanation": "The source states the Reserve Bank of India announced it.",
        "source": (
            "The Reserve Bank of India announced a new monetary policy "
            "framework aimed at maintaining price stability"
        ),
        "difficulty": "Easy",
        "topic": "Monetary Policy",
    }
    return {
        "subject": "Economy",
        "topic": "Monetary Policy",
        "summary": "RBI announced a monetary policy framework.",
        "keywords": ["RBI", "monetary policy"],
        "questions": [question, question],  # second is a duplicate -> rejected
    }


def test_analyze_news_ollama_end_to_end(monkeypatch):
    monkeypatch.setattr(ollama_engine, "is_ollama_available", lambda: True)
    monkeypatch.setattr(
        ollama_engine,
        "_post_json",
        lambda url, payload, timeout: {"response": json.dumps(_canned_ollama_response())},
    )

    result = analyze_news_ollama(NEWS, exam="Banking", question_count=3)

    assert result["version"] == "0.3-ollama"
    assert result["exam"] == "Banking"
    assert result["question_count"] == 1  # duplicate rejected by validator
    assert result["questions"][0]["id"] == "ollama-1"
    assert "local Ollama" in result["confidence_note"]


def test_analyze_endpoint_prefers_ollama_before_rules(client, monkeypatch):
    # Force the cloud path to fail so the request must reach Ollama.
    from backend import main as backend_main

    monkeypatch.setattr(
        backend_main, "primary_engine_names", {}, raising=False
    )
    monkeypatch.setattr(backend_main, "_langgraph_agent", None)
    monkeypatch.setattr(backend_main, "AGENT_ENABLED", False)
    monkeypatch.setattr(
        backend_main, "analyze_news_gemini",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("server offline")),
    )
    monkeypatch.setattr(backend_main, "is_ollama_available", lambda: True)
    monkeypatch.setattr(
        backend_main, "analyze_news_ollama",
        lambda *a, **k: {
            "app": "NewQ", "version": "0.3-ollama", "exam": "Banking",
            "subject": "Economy", "topic": "Monetary Policy",
            "relevance": "HIGH", "relevance_score": 0.9,
            "confidence_note": "offline", "keywords": [],
            "summary": "", "signals": [], "subject_scores": {},
            "question_count": 1,
            "questions": [{"id": "ollama-1", "question": "q", "options": ["a"],
                           "answer": "a", "explanation": "e",
                           "difficulty": "Easy", "topic": "t"}],
        },
    )

    response = client.post(
        "/api/analyze",
        json={"exam": "Banking", "content": NEWS, "question_count": 3},
    )

    assert response.status_code == 200
    assert response.json()["version"] == "0.3-ollama"


def test_health_reports_offline_engine(client):
    response = client.get("/health")
    payload = response.json()
    assert "offline_engine" in payload
    assert "available" in payload["offline_engine"]
    assert payload["offline_engine"]["model"]
