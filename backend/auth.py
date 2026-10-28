"""Stage 7: Firebase ID-token authentication guard.

Protects the write-heavy AI endpoints (POST /api/analyze, POST
/api/extract-text) by verifying Firebase ID tokens issued to the mobile
client's anonymous sessions. Local-only discovery endpoints (/health,
/api/exams, /api/news-feed) stay open.

Enforcement modes (NEWQ_REQUIRE_AUTH env var):
- "auto"  (default): enforce only when a service-account JSON is found.
          Keeps local development and the existing test suite frictionless.
- "on"/"1": always enforce. With no service account configured every
          protected call fails 503 so misconfiguration is loud, not silent.
- "off"/"0": never enforce (explicit opt-out, e.g. shared demo machines).

The service account JSON (Project settings -> Service accounts ->
"Generate new private key" in the Firebase console) is a SECRET: it is
git-ignored and never ships with the repo or the mobile bundle.
"""

import os
import re
import time

# Project-root default: the backend runs from the repo root via uvicorn.
DEFAULT_SERVICE_ACCOUNT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "firebase-service-account.json",
)

import fastapi

FIREBASE_ADMIN_AVAILABLE = False
try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth, credentials

    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in unit tests
    firebase_admin = None
    firebase_auth = None
    credentials = None

_initialized = False
_init_error = None


def _service_account_path() -> str:
    return os.getenv("FIREBASE_SERVICE_ACCOUNT", DEFAULT_SERVICE_ACCOUNT)


def _enforcement_raw() -> str:
    return os.getenv("NEWQ_REQUIRE_AUTH", "auto").strip().lower()


def is_service_account_configured() -> bool:
    """True when the service-account JSON exists on disk."""
    path = _service_account_path()
    return bool(path) and os.path.isfile(path)


def is_auth_required() -> bool:
    """Whether protected endpoints currently demand a Bearer ID token."""
    mode = _enforcement_raw()

    if mode in ("on", "1", "true", "yes"):
        return True
    if mode in ("off", "0", "false", "no"):
        return False

    # auto: enforce when the credentials are actually present.
    return FIREBASE_ADMIN_AVAILABLE and is_service_account_configured()


def _ensure_initialized():
    """Initialize the Firebase Admin SDK once, lazily."""
    global _initialized, _init_error

    if _initialized:
        return True
    if _init_error:
        return False

    if not FIREBASE_ADMIN_AVAILABLE:
        _init_error = "firebase-admin is not installed"
        return False

    path = _service_account_path()
    if not path or not os.path.isfile(path):
        _init_error = f"service-account JSON not found at {path}"
        return False

    try:
        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)
        _initialized = True
        print("[AUTH] Firebase Admin SDK initialized from", path)
        return True
    except Exception as exc:  # bad JSON, wrong shape, etc.
        _init_error = f"{type(exc).__name__}: {exc}"
        print(f"[AUTH] Firebase Admin init FAILED: {_init_error}")
        return False


def verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token and return its decoded claims.

    Raises firebase_admin.auth.InvalidIdTokenError (and related auth
    errors) on invalid/expired tokens so the endpoint layer can map them
    to 401 without import gymnastics.
    """
    _ensure_initialized()

    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as exc:
        # Clock-skew tolerance: when the local clock lags Google's, a
        # freshly minted token carries an iat slightly in the future and
        # Firebase rejects it with "Token used too early". The error
        # message contains both Unix timestamps — wait exactly the
        # missing time (capped at 10 s) and retry once.
        # Google's message format is "Token used too early, {now} < {iat}"
        # (verified in google/auth/jwt.py), so group 1 is the server's
        # current time and group 2 is the token's issue time. Wait exactly
        # the missing span plus a one-second margin, then retry once.
        message = str(exc)
        skew_match = re.search(r"(\d{9,12})\s*<\s*(\d{9,12})", message)
        if skew_match and "too early" in message.lower():
            wait = float(skew_match.group(2)) - float(skew_match.group(1)) + 1.0
            if wait > 0:
                time.sleep(min(wait, 10.0))
                decoded = firebase_auth.verify_id_token(token)
            else:
                raise
        else:
            raise

    # Anonymous users carry the "firebase" sign-in provider claim; reject
    # tokens that are not authentic Firebase sessions.
    if not decoded.get("sub"):
        raise ValueError("Token has no subject claim")
    return decoded


def auth_error_detail(exc: Exception) -> str:
    """Map a token-verification failure to a friendly client message."""
    name = type(exc).__name__ or ""
    if "expired" in name.lower() or "Expired" in str(exc):
        return "Session expired. Reopen the app and try again."
    if "revoked" in str(exc).lower():
        return "Session was revoked. Reopen the app and try again."
    return "Invalid or missing authentication token."


def auth_state() -> dict:
    """Public shape for /health and diagnostics."""
    return {
        "auth_required": is_auth_required(),
        "service_account_configured": is_service_account_configured(),
        "firebase_admin_available": FIREBASE_ADMIN_AVAILABLE,
        "init_error": _init_error,
    }


async def require_firebase_user(
    authorization: str = fastapi.Header(default=None),
) -> dict:
    """FastAPI dependency guarding sensitive endpoints.

    Reads `Authorization: Bearer <firebase-id-token>`. In open mode
    (auth not required) it short-circuits through so existing clients
    and tests behave unchanged.
    """
    if not is_auth_required():
        return {"uid": None, "mode": "open"}

    if _init_error and not _initialized:
        raise fastapi.HTTPException(
            status_code=503,
            detail=(
                "Authentication is required but not configured on the "
                "server (missing or invalid service-account JSON). "
                f"Reason: {_init_error}"
            ),
        )

    scheme, _, token = (authorization or "").partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise fastapi.HTTPException(
            status_code=401,
            detail="Missing bearer token. Sign in to NewQ and retry.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decoded = verify_firebase_token(token)
    except Exception as exc:
        print(
            f"[AUTH] Token verification failed: {type(exc).__name__}: {exc}"
        )
        raise fastapi.HTTPException(
            status_code=401,
            detail=auth_error_detail(exc),
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from exc

    return {
        "uid": decoded.get("uid") or decoded.get("user_id") or decoded.get("sub"),
        "provider": decoded.get("firebase", {}).get("sign_in_provider"),
        "mode": "firebase",
    }
