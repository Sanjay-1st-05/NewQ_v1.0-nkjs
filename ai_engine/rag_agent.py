"""NewQ RAG agent (Stage 9 phase 1-3).

Retrieval side of the pipeline: keeps a local embeddded index of the RSS
feed items the backend already fetches, and correlates each indexed chunk
with the topic taxonomy of a chosen government exam so the app can say
"these are the items most likely to produce this exam's question types".

Design constraints:
- Reuses backend.news_feed_service (same cached feeds, no page scraping).
- Embeddings come from the Gemini text-embedding-004 REST API with the
  existing server-side key; when the key or network is unavailable the
  module falls back to a deterministic keyword-vector embedder so retrieval
  keeps working offline. The embedder actually used is stored in the index
  (`embedder` field) and every query is scored in the same space.
- The index persists to backend/rag_index.json and is refreshed on a timer
  from the backend lifespan; nothing here touches question generation.
"""

import hashlib
import json
import math
import os
import time
import urllib.request
from typing import Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(REPO_ROOT, 'backend', 'rag_index.json')

EMBED_MODEL = 'text-embedding-004'
EMBED_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    f'{EMBED_MODEL}:embedContent'
)
KEYWORD_DIMS = 256
DEFAULT_TOP_K = 5
ITEM_TTL_SECONDS = 24 * 60 * 60


# Curated, human-editable topic taxonomy per exam. Each phrase embeds into
# the exam's category profile; matching chunks inherit the closest phrase
# as their "topic" label.
EXAM_TOPICS: Dict[str, List[str]] = {
    'Banking': [
        'RBI monetary policy repo rate inflation',
        'banking regulation and public sector banks',
        'UPI payments digital transactions fintech',
        'government budget fiscal deficit',
        'SEBI stock market financial regulation',
    ],
    'UPSC': [
        'constitutional amendments supreme court verdicts governance',
        'international relations treaties summits diplomacy',
        'economy growth infrastructure investment',
        'environment climate pollution conservation',
        'science technology space defence research',
    ],
    'SSC': [
        'national current affairs government schemes',
        'economy and budget basics',
        'sports awards appointments culture',
    ],
    'BPSC': [
        'Bihar state government policies and news',
        'national politics and governance',
        'economy and budget',
    ],
    'Defence': [
        'military exercises joint drills army navy airforce',
        'defence procurement deals missiles equipment',
        'border security strategy conflicts',
    ],
}

# Phrase families that decide the confidence band shown in the UI.
BAND_STRONG = 0.75       # similarity threshold for "strong", keyword space
BAND_MODERATE = 0.55     # ... and "moderate"; tuned per embedder below


# ---------------------------------------------------------------------------
# Embedders. Both map text -> fixed-size L2-normalized vector. The active
# embedder is recorded in the index so scoring always happens in one space.
# ---------------------------------------------------------------------------

def keyword_embedding(text: str, dims: int = KEYWORD_DIMS):
    """Deterministic hashed bag-of-words vector. No network, stable across
    runs — the offline fallback and the unit-test baseline."""
    vec = [0.0] * dims
    words = (text or '').lower().split()
    for word in words:
        digest = hashlib.md5(word.encode()).digest()
        bucket = int.from_bytes(digest[:4], 'little') % dims
        sign = 1.0 if digest[4] % 2 else -1.0
        vec[bucket] += sign
    # bigram smoothing: pair (w1,w2) adds evidence too
    for a, b in zip(words, words[1:]):
        digest = hashlib.md5((a + '_' + b).encode()).digest()
        bucket = int.from_bytes(digest[:4], 'little') % dims
        vec[bucket] += 0.5

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def gemini_embedding(text: str):
    """Single-text embedding via the Gemini REST API. Raises on failure so
    callers can drop to the keyword embedder."""
    key = os.getenv('GEMINI_API_KEY', '')
    if not key:
        raise RuntimeError('GEMINI_API_KEY is not configured.')

    payload = json.dumps({
        'model': f'models/{EMBED_MODEL}',
        'content': {'parts': [{'text': (text or ' ')[:8000]}]},
    }).encode()

    request = urllib.request.Request(
        f'{EMBED_URL}?key={key}',
        data=payload,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    values = data.get('embedding', {}).get('value')
    if not values:
        raise RuntimeError('Gemini embedding returned no values.')
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def get_embedder(name: str):
    if name == 'gemini':
        return gemini_embedding
    return keyword_embedding


def pick_embedder():
    """Prefer Gemini embeddings; fall back to keyword vectors when the key
    is missing or the first probe fails."""
    if os.getenv('GEMINI_API_KEY'):
        try:
            probe = gemini_embedding('embedding probe')
            if probe:
                return 'gemini', get_embedder('gemini')
        except Exception:
            pass
    return 'keyword', keyword_embedding


def cosine(vec_a, vec_b):
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return dot  # both vectors are L2-normalized


def active_band_thresholds(embedder):
    # Keyword vectors are denser/similar than true embeddings; tighten bands
    # when scanning in that space. Thresholds validated via the quality panel.
    if embedder == 'keyword':
        return 0.18, 0.10
    return BAND_STRONG, BAND_MODERATE


# ---------------------------------------------------------------------------
# Index build and persistence
# ---------------------------------------------------------------------------

def chunk_item(item: Dict) -> str:
    """One chunk per feed item; only non-empty pieces produce separators."""
    parts = [piece.strip() for piece in
             (item.get('title', ''), item.get('summary', '')) if piece.strip()]
    return '. '.join(parts)


def build_index(items: List[Dict], embedder_name=None) -> Dict:
    """Embed freshly fetched feed items into the persisted index shape."""
    if embedder_name is None:
        embedder_name, embed = pick_embedder()
    else:
        embed = get_embedder(embedder_name)

    entries = []
    now = time.time()
    for item in items:
        text = chunk_item(item)
        if not text:
            continue
        try:
            vector = embed(text)
        except Exception:
            embedder_name = 'keyword'
            embed = keyword_embedding
            vector = embed(text)
        entries.append({
            'text': text,
            'url': item.get('url', ''),
            'source': item.get('source', ''),
            'published': item.get('published', ''),
            'embedding': vector,
            'indexed_at': now,
        })

    return {
        'embedder': embedder_name,
        'built_at': now,
        'entries': entries,
    }


def load_index():
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and data.get('entries') else None
    except (OSError, ValueError):
        return None


def save_index(index: Dict) -> None:
    with open(INDEX_PATH, 'w', encoding='utf-8') as handle:
        json.dump(index, handle)


def refresh_index() -> Dict:
    """Fetch live feeds and rebuild the index file. Returns the new index."""
    from backend.news_feed_service import get_news_feed

    feed = get_news_feed(force_refresh=True)
    index = build_index(feed.get('items', []))
    save_index(index)
    return index


# ---------------------------------------------------------------------------
# Exam profiles and retrieval
# ---------------------------------------------------------------------------

def exam_profile(exam: str, embed):
    """Category query vector = mean of the exam's topic-phrase embeddings."""
    phrases = EXAM_TOPICS.get(exam)
    if not phrases:
        return None
    vectors = [embed(phrase) for phrase in phrases]
    dims = len(vectors[0])
    mean = [0.0] * dims
    for vector in vectors:
        for i, value in enumerate(vector):
            mean[i] += value / len(vectors)
    norm = math.sqrt(sum(v * v for v in mean)) or 1.0
    return [v / norm for v in mean], phrases


def topic_of_best_phrase(text: str, phrases: List[str], embed):
    best_label, best_score = '', -1.0
    text_vector = embed(text)
    for phrase in phrases:
        score = cosine(text_vector, embed(phrase))
        if score > best_score:
            best_label, best_score = phrase, score
    return best_label


def match_band(score: float, embedder: str) -> str:
    strong, moderate = active_band_thresholds(embedder)
    if score >= strong:
        return 'strong'
    if score >= moderate:
        return 'moderate'
    return 'weak'


def retrieve_for_exam(index: Dict, exam: str, top_k: int = DEFAULT_TOP_K):
    """Top-k feed items for an exam, with matched topic + confidence band."""
    embedder = index.get('embedder', 'keyword')
    embed = get_embedder(embedder)
    profile = exam_profile(exam, embed)
    if profile is None:
        raise ValueError(f'Unknown exam category: {exam}')

    profile_vector, phrases = profile
    cutoff = time.time() - ITEM_TTL_SECONDS

    # Pre-embed the topic phrases once — each is scored against every entry.
    phrase_vectors = [(phrase, embed(phrase)) for phrase in phrases]

    scored = []
    for entry in index.get('entries', []):
        if entry.get('indexed_at', 0) < cutoff:
            continue
        vector = entry.get('embedding')
        score = cosine(profile_vector, vector) if vector else 0.0
        text = entry.get('text', '')

        topics = []
        for phrase, phrase_vector in phrase_vectors:
            if cosine(phrase_vector, vector) >= active_band_thresholds(embedder)[1]:
                topics.append(phrase)
        if not topics:
            topics = [topic_of_best_phrase(text, phrases, embed)]

        scored.append({
            'title': text.split('. ', 1)[0],
            'url': entry.get('url', ''),
            'source': entry.get('source', ''),
            'published': entry.get('published', ''),
            'topics': topics,
            'similarity': round(score, 3),
            'band': match_band(score, embedder),
        })

    scored.sort(key=lambda row: row['similarity'], reverse=True)
    return {
        'exam': exam,
        'embedder': embedder,
        'count': len(scored),
        'items': scored[:top_k],
    }


def related_for_article(index: Dict, article_text: str, exam: str, top_k: int = 3):
    """Chunks related to a pasted article (used to wire RAG into analyze in
    a later phase; generation itself stays in the existing engine chain)."""
    embedder = index.get('embedder', 'keyword')
    embed = get_embedder(embedder)
    article_vector = embed(article_text)

    profile = exam_profile(exam, embed) if exam in EXAM_TOPICS else None
    scored = []
    for entry in index.get('entries', []):
        vector = entry.get('embedding')
        score = cosine(article_vector, vector) if vector else 0.0
        if profile is not None:
            profile_vector = profile[0]
            score = 0.6 * score + 0.4 * cosine(profile_vector, vector)
        scored.append((score, entry))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            'title': entry['text'].split('. ', 1)[0],
            'url': entry.get('url', ''),
            'similarity': round(score, 3),
        }
        for score, entry in scored[:top_k]
    ]
