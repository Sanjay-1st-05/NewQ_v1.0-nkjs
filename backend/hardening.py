"""Stage 6 backend hardening: rate limiting, input sanitization, logging.

Rate limiting is a per-IP in-memory sliding window — appropriate for a
single-process LAN/local deployment (the current NewQ topology). For a
multi-worker or hosted deployment, swap the bucket store for Redis.

Env overrides:
    NEWQ_RATE_LIMIT_ANALYZE     default 10/min
    NEWQ_RATE_LIMIT_EXTRACT     default 20/min
    NEWQ_RATE_LIMIT_DEFAULT     default 120/min
    NEWQ_MAX_CONTENT_LENGTH     default 20000 characters
"""

import logging
import os
import re
import time
from collections import defaultdict, deque
from typing import Callable, Dict, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("newq")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s","event":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


RATE_LIMITS: Dict[str, int] = {  # requests per minute per client IP
    "/api/analyze": _int_env("NEWQ_RATE_LIMIT_ANALYZE", 10),
    "/api/extract-text": _int_env("NEWQ_RATE_LIMIT_EXTRACT", 20),
    "/api/news-feed": _int_env("NEWQ_RATE_LIMIT_DEFAULT", 120),
}
DEFAULT_LIMIT = RATE_LIMITS["/api/news-feed"]

MAX_CONTENT_LENGTH = _int_env("NEWQ_MAX_CONTENT_LENGTH", 20000)

# Control characters that should never survive into prompt or storage,
# excluding \n, \r, \t which are legitimate formatting in pasted articles.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_news_content(text: str) -> str:
    """Strip control characters without altering legitimate content."""
    return _CONTROL_CHARS.sub(" ", text)


# Module-level bucket store so tests can reset state between runs.
_BUCKETS: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=240))


def _reset_buckets() -> None:
    _BUCKETS.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter keyed by client IP and route tier."""

    def limit_for(self, path: str) -> int:
        return RATE_LIMITS.get(path, DEFAULT_LIMIT)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        window = 60.0
        now = time.monotonic()
        bucket = _BUCKETS[(client_ip, path)]

        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= self.limit_for(path):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": "60"},
            )

        bucket.append(now)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """One structured line per request with route, status and duration."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.error(
                "%s %s 500 %dms error=%s: %s",
                request.method,
                request.url.path,
                elapsed,
                type(exc).__name__,
                exc,
            )
            raise

        elapsed = int((time.perf_counter() - started) * 1000)
        logger.info(
            "%s %s %d %dms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response


def add_hardening(app) -> None:
    """Wire all Stage 6 middleware onto a FastAPI app."""
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
