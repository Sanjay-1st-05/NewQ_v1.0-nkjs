"""Stage 6 hardening tests: rate limiting, sanitization, length caps.

The rate-limit test uses an unsupported exam so requests fail fast at the
400 boundary — no Gemini/network cost while exercising the limiter.
"""

import pytest
from fastapi.testclient import TestClient

from backend import hardening
from backend.main import app


@pytest.fixture()
def client():
    hardening._reset_buckets()
    original_limits = dict(hardening.RATE_LIMITS)

    with TestClient(app) as test_client:
        yield test_client

    hardening._reset_buckets()
    hardening.RATE_LIMITS.clear()
    hardening.RATE_LIMITS.update(original_limits)


def test_health_reports_stage6_fields(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.3.0"
    assert isinstance(body["uptime_seconds"], int)
    assert "agent_enabled" in body


def test_sanitize_strips_control_characters_only():
    dirty = "RBI announced\x00 change\x07 with \n normal line breaks \x0b."
    clean = hardening.sanitize_news_content(dirty)

    assert "\x00" not in clean
    assert "\x07" not in clean
    assert "\x0b" not in clean
    assert "\n" in clean  # legitimate formatting preserved
    assert "RBI" in clean


def test_content_too_long_returns_422(client):
    response = client.post(
        "/api/analyze",
        json={
            "exam": "UPSC",
            "content": "x" * (hardening.MAX_CONTENT_LENGTH + 1),
            "question_count": 5,
        },
    )

    assert response.status_code == 422
    assert "too long" in response.json()["detail"].lower()


def test_short_content_still_422(client):
    response = client.post(
        "/api/analyze",
        json={"exam": "UPSC", "content": "Too short.", "question_count": 5},
    )

    assert response.status_code == 422


def test_bad_exam_still_400(client):
    response = client.post(
        "/api/analyze",
        json={"exam": "NEET", "content": "x" * 200, "question_count": 5},
    )

    assert response.status_code == 400


def test_rate_limit_returns_429(client):
    hardening.RATE_LIMITS["/api/analyze"] = 2

    # Unsupported exam → 400 fast; still counts against the limiter.
    assert (
        client.post(
            "/api/analyze",
            json={"exam": "NEET", "content": "x" * 200},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/analyze",
            json={"exam": "NEET", "content": "x" * 200},
        ).status_code
        == 400
    )

    limited = client.post(
        "/api/analyze",
        json={"exam": "NEET", "content": "x" * 200},
    )

    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    assert "too many" in limited.json()["detail"].lower()
