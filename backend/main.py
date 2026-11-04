
import asyncio
import os
import time

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ai_engine import analyze_news, EXAMS
from ai_engine.agent import AGENT_ENABLED, analyze_with_agent
from ai_engine.gemini_engine import analyze_news_gemini
from ai_engine.ollama_engine import (
    OLLAMA_MODEL,
    analyze_news_ollama,
    is_ollama_available,
)
from backend.auth import auth_state, require_firebase_user

# Preferred agent runtime: the LangGraph state machine when available,
# falling back to the built-in orchestrator loop otherwise.
_langgraph_agent = None
if AGENT_ENABLED:
    try:
        from ai_engine.langgraph_agent import (
            LANGGRAPH_AVAILABLE,
            analyze_with_langgraph_agent,
        )
    except ImportError:
        pass
    else:
        if LANGGRAPH_AVAILABLE:
            _langgraph_agent = analyze_with_langgraph_agent
from backend.hardening import (
    MAX_CONTENT_LENGTH,
    add_hardening,
    sanitize_news_content,
)
from backend.news_feed_service import get_news_feed
from backend.vision_service import (
    extract_text_from_image,
    is_provider_error,
)
from ai_engine.rag_agent import (
    refresh_index as rag_refresh_index,
    load_index as rag_load_index,
    retrieve_for_exam as rag_retrieve_for_exam,
    EXAM_TOPICS as RAG_EXAM_TOPICS,
)

RAG_REFRESH_SECONDS = int(os.getenv("NEWQ_RAG_REFRESH_SECONDS", "300"))

app = FastAPI(title="NewQ API", version="0.3.0")
add_hardening(app)


@asynccontextmanager
async def lifespan(_application: FastAPI):
    """Publish server presence to Firestore for mobile auto-discovery and
    keep the RAG feed index fresh."""
    import asyncio
    from backend import server_presence

    await server_presence.start_presence(
        int(os.getenv("NEWQ_PORT", "8000"))
    )

    async def rag_refresh_loop():
        try:
            await asyncio.to_thread(rag_refresh_index)
        except Exception as exc:
            print(f"[WARN] RAG initial refresh failed: "
                  f"{type(exc).__name__}: {exc}")
        while True:
            await asyncio.sleep(RAG_REFRESH_SECONDS)
            try:
                await asyncio.to_thread(rag_refresh_index)
            except Exception as exc:
                print(f"[WARN] RAG refresh failed: "
                      f"{type(exc).__name__}: {exc}")

    rag_task = asyncio.create_task(rag_refresh_loop())
    yield
    rag_task.cancel()
    server_presence.stop_presence()


app.router.lifespan_context = lifespan

_STARTED_AT = time.monotonic()


class AnalyzeRequest(BaseModel):
    exam: str = Field(default="UPSC")
    content: str
    question_count: int = Field(default=5, ge=1, le=10)


@app.get("/health")
def health():
    health_payload = {
        "status": "ok",
        "service": "newq-api",
        "version": "0.3.0",
        "agent_enabled": AGENT_ENABLED,
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
    }
    health_payload.update(auth_state())
    health_payload["offline_engine"] = {
        "available": is_ollama_available(),
        "model": OLLAMA_MODEL,
    }
    try:
        rag_state = rag_load_index()
        health_payload["rag"] = (
            {
                "embedder": rag_state.get("embedder"),
                "indexed": len(rag_state.get("entries", [])),
            }
            if rag_state
            else {"indexed": 0}
        )
    except Exception:
        health_payload["rag"] = {"indexed": 0}
    return health_payload


@app.get("/api/exams")
def exams():
    return {"exams": EXAMS}


@app.get("/api/news-feed")
def news_feed():
    """Current-affairs discovery from the configured public RSS feeds."""
    try:
        return get_news_feed()
    except Exception as exc:
        print(f"[WARN] News feed failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="News feeds are temporarily unavailable. Please try again.",
        ) from exc


@app.get("/api/rag/topics")
def rag_topics(
    exam: str,
    k: int = 5,
    user: dict = Depends(require_firebase_user),
):
    """Exam-correlated feed items from the RAG index (Stage 9 phase 3).

    Returns the top-k feed items most aligned with the exam's topic
    taxonomy, each with its matched topics and a confidence band.
    """
    if exam not in RAG_EXAM_TOPICS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown exam category: {exam}. "
            f"Available: {', '.join(sorted(RAG_EXAM_TOPICS))}",
        )

    index = rag_load_index()
    if index is None:
        raise HTTPException(
            status_code=503,
            detail="The RAG index is still building. Try again shortly.",
        )

    try:
        return rag_retrieve_for_exam(
            index, exam, top_k=max(1, min(int(k), 20)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user: dict = Depends(require_firebase_user)):
    if req.exam not in EXAMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exam. Choose from: {', '.join(EXAMS)}"
        )

    # Stage 6 hardening: strip control characters and enforce the length
    # ceiling before anything reaches an engine.
    content = sanitize_news_content(req.content)

    # Validate length here so that legitimate input-validation errors keep
    # returning 422 directly, while any failure inside the Gemini engine
    # (including SDK validation errors that subclass ValueError) reaches the
    # rule-based fallback instead of being mistaken for bad input.
    if len(content.strip()) < 80:
        raise HTTPException(
            status_code=422,
            detail="Please provide at least 80 characters of news content."
        )

    if len(content) > MAX_CONTENT_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                "News content is too long "
                f"(maximum {MAX_CONTENT_LENGTH} characters)."
            ),
        )

    if AGENT_ENABLED and _langgraph_agent is not None:
        primary_engine = _langgraph_agent
    elif AGENT_ENABLED:
        primary_engine = analyze_with_agent
    else:
        primary_engine = analyze_news_gemini

    cloud_result = None
    try:
        # Primary engine: agent pipeline (classify → generate → validate →
        # repair) falling back to the direct Gemini engine when disabled.
        cloud_result = primary_engine(content, req.exam, req.question_count)

        if cloud_result.get("question_count", 0) > 0:
            return cloud_result

        print("[WARN] AI engine returned no valid questions; trying offline engine.")

    except Exception as exc:
        # Keep the API available if Gemini is temporarily unavailable.
        print(
            f"[WARN] AI engine failed: {type(exc).__name__}: {exc}. "
            "Trying offline engine."
        )

    # Stage 7c: local offline engine (Ollama) before the rule fallback, so
    # analysis keeps working with no internet and no Gemini quota.
    try:
        if is_ollama_available():
            offline_result = analyze_news_ollama(content, req.exam, req.question_count)

            if offline_result.get("question_count", 0) > 0:
                return offline_result

            print("[WARN] Ollama returned no valid questions; using rule-based fallback.")

    except Exception as exc:
        print(
            f"[WARN] Ollama engine failed: {type(exc).__name__}: {exc}. "
            "Using rule-based fallback."
        )

    # Fallback engine: existing rule-based analysis
    try:
        return analyze_news(
            req.content,
            req.exam,
            req.question_count
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/extract-text")
async def extract_text(
    file: UploadFile = File(...),
    user: dict = Depends(require_firebase_user),
):
    """Extract visible article text from a photo of printed news.

    Returns a minimal, predictable payload; verification of
    /api/analyze behavior is intentionally unaffected by this endpoint.
    """
    data = await file.read()

    try:
        text = extract_text_from_image(data, file.content_type)
    except ValueError as exc:
        # Unsupported type/size/empty upload (UnsupportedImageError) or
        # unreadable image (UnreadableImageError) => client-side problem.
        status = 400 if "image" in str(exc).lower() or "empty" in str(exc).lower() else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    except Exception as exc:
        if is_provider_error(exc):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Image extraction is temporarily unavailable. "
                    "Please try again shortly."
                ),
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while extracting text.",
        ) from exc

    return {
        "text": text,
        "character_count": len(text),
    }
