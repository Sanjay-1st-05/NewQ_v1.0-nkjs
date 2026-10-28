"""Gemini Vision service for extracting article text from photos.

Separate from the analysis engines so that /api/analyze behavior is
unaffected. Reuses the same Gemini client configuration and model
environment variable as the rest of the backend.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

client = genai.Client(api_key=API_KEY) if API_KEY else None

# Accepted image upload types guarded against contradictory uploads.
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


class UnsupportedImageError(ValueError):
    """Raised for invalid image type or size. Treated as a client error."""


class UnreadableImageError(ValueError):
    """Raised when Gemini cannot extract meaningful article text."""


EXTRACTION_PROMPT = """You are the text-extraction component of NewQ, an exam-preparation news analysis app.

Transcribe the news article text visible in this photograph of a printed
newspaper, magazine, or printed article.

Rules:
- Return ONLY the visible article text as plain running text.
- Preserve the original wording, numbers, dates and institution names.
- Omit page furniture that is not part of an article: page numbers,
  headers, footers, website URLs, advert text and photos captions UNLESS
  the caption is directly attached to the story.
- Do not summarize, translate, or add any commentary.
- If the photograph does not show readable news article text, reply with
  only: NO_TEXT_FOUND
"""


def extract_text_from_image(
    image_bytes: bytes,
    mime_type: Optional[str],
) -> str:
    """Extract visible news article text from an image using Gemini Vision.

    Raises:
        UnsupportedImageError: for a missing/unsupported image type or an
            empty upload.
        UnreadableImageError: when Gemini returns no meaningful article text.
        RuntimeError: when the Gemini client is not configured or the
            provider call fails.
    """
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if not mime_type or mime_type not in SUPPORTED_IMAGE_TYPES:
        raise UnsupportedImageError(
            "Unsupported image type. Upload a JPEG, PNG, WebP, or HEIC image."
        )

    if not image_bytes:
        raise UnsupportedImageError("The uploaded image file is empty.")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise UnsupportedImageError(
            "Image is too large. Maximum allowed size is 10 MB."
        )

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                EXTRACTION_PROMPT,
            ],
        )
    except genai_errors.APIError as exc:
        # Provider 4xx responses (e.g. an upload that is not actually a
        # valid image) are client problems; 5xx are provider outages.
        if exc.code is not None and exc.code >= 500:
            raise RuntimeError(
                "Gemini vision is temporarily unavailable."
            ) from exc
        raise UnsupportedImageError(
            "The uploaded file could not be processed as a photo. "
            "Please retake the picture and try again."
        ) from exc

    if not response or not response.text:
        raise RuntimeError("Gemini vision returned an empty response.")

    text = response.text.strip()

    if not text or text.upper().startswith("NO_TEXT_FOUND") or len(text) < 20:
        raise UnreadableImageError(
            "No readable news article text could be recognized in this image."
        )

    return text


def is_provider_error(exc: Exception) -> bool:
    """Identify Gemini API provider failures for upstream error mapping."""
    return isinstance(exc, (genai_errors.APIError, RuntimeError))
