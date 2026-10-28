"""Stage 7 auth-guard tests.

Unit-level: the firebase token verifier is stubbed so tests run without
the service-account JSON. Live end-to-end verification (real anonymous
token minted through Google's identitytoolkit REST API and a real
protected call) is performed against the running server once the
service-account JSON is placed in the repo root — unit stubs are never
used as evidence of the live path.
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend import auth as stage7_auth
from backend.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def enforce(monkeypatch):
    """Force auth enforcement on with a stubbed token verifier."""
    monkeypatch.setattr(stage7_auth, "is_auth_required", lambda: True)
    monkeypatch.setattr(
        stage7_auth,
        "is_service_account_configured",
        lambda: True,
    )
    monkeypatch.setattr(stage7_auth, "_initialized", True)
    monkeypatch.setattr(stage7_auth, "_init_error", None)

    def fake_verify(token):
        if token == "good-token":
            return {
                "uid": "test-uid-123",
                "sub": "test-uid-123",
                "firebase": {"sign_in_provider": "anonymous"},
            }
        error = stage7_auth.firebase_auth.InvalidIdTokenError(
            "token rejected"
        ) if stage7_auth.FIREBASE_ADMIN_AVAILABLE else RuntimeError(
            "token rejected"
        )
        raise error

    monkeypatch.setattr(stage7_auth, "verify_firebase_token", fake_verify)


def test_open_mode_by_default(client, monkeypatch):
    # No service-account JSON in a clean checkout: enforcement stays off
    # (auto mode), so the analyze endpoint behaves exactly as in stage 6.
    monkeypatch.delenv("NEWQ_REQUIRE_AUTH", raising=False)
    monkeypatch.setattr(
        stage7_auth,
        "is_service_account_configured",
        lambda: False,
    )

    health = client.get("/health").json()
    assert health["auth_required"] is False
    assert health["service_account_configured"] is False
    assert "firebase_admin_available" in health

    # A protected endpoint answers with normal validation (422 for short
    # content), NOT 401 — proving the guard passed through.
    response = client.post(
        "/api/analyze",
        json={"exam": "UPSC", "content": "too short"},
    )
    assert response.status_code == 422


def test_auth_enforced_missing_token_is_401(client, enforce):
    response = client.post(
        "/api/analyze",
        json={"exam": "Banking", "content": "x" * 100},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_auth_enforced_bad_scheme_is_401(client, enforce):
    response = client.post(
        "/api/analyze",
        headers={"Authorization": "Basic not-a-jwt"},
        json={"exam": "Banking", "content": "x" * 100},
    )

    assert response.status_code == 401


def test_auth_enforced_invalid_token_is_401(client, enforce):
    response = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer bad-token"},
        json={"exam": "Banking", "content": "x" * 100},
    )

    assert response.status_code == 401
    assert "Invalid" in response.json()["detail"]


def test_auth_enforced_valid_token_passes_guard(client, enforce):
    # Passing auth means the request reaches the endpoint's own
    # validation, which rejects an unsupported exam with 400.
    response = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer good-token"},
        json={"exam": "NOT-AN-EXAM", "content": "x" * 100},
    )

    assert response.status_code == 400
    assert "Unsupported exam" in response.json()["detail"]


def test_explicit_on_without_service_account_is_503(client, monkeypatch):
    monkeypatch.setenv("NEWQ_REQUIRE_AUTH", "on")
    monkeypatch.setattr(
        stage7_auth,
        "is_service_account_configured",
        lambda: False,
    )
    monkeypatch.setattr(stage7_auth, "_initialized", False)
    monkeypatch.setattr(
        stage7_auth,
        "_init_error",
        "service-account JSON not found somewhere",
    )

    health = client.get("/health").json()
    assert health["auth_required"] is True

    response = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer whatever"},
        json={"exam": "Banking", "content": "x" * 100},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_explicit_off_never_enforces(client, monkeypatch):
    monkeypatch.setenv("NEWQ_REQUIRE_AUTH", "off")

    assert stage7_auth.is_auth_required() is False
