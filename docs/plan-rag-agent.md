# Integration Plan: RAG Agent for Exam-Targeted Question Retrieval

## Overview and objectives

NewQ already turns a pasted news article into exam MCQs. This plan adds a
Retrieval-Augmented Generation (RAG) agent that **inverts the flow**: given an
exam category (e.g. Banking, UPSC, SSC, Defence), it retrieves the news
content most likely to yield that exam's question types, and correlates each
retrieved item with the exam's topic taxonomy before PDF generation.

Objectives:
1. Keep the news source as RSS only — the same feeds the app already fetches
   (`backend/news_feed_service.py`, cached, no page scraping).
2. Retrieve per-exam: match feed items against a curated topic map so the
   agent surfaces "RBI monetary policy" items for Banking, not general
   headlines.
3. No disruption: the existing analyze chain (agent/Gemini → Ollama → rules)
   and the `/api/analyze` contract stay unchanged. RAG is an additional
   retrieval layer, not a replacement.

Established fact: our current pipeline already stores feed items with title,
summary, source, and link. Retrieval therefore works on real published
metadata — no invented content.

## Implementation phases

### Phase 1 — Indexing (ingest + chunk)
Ingest the cached feed items on a refresh timer in the backend lifespan
(alongside the existing presence publisher). Each item becomes one or two
text chunks (title + summary are short, so chunking is simple). Every chunk
is embedded at ingestion time and stored with `{exam_tags, source, link,
published_at}` in a local JSON index (`backend/rag_index.json`). Embeddings
use the **Gemini `text-embedding-004` API** with the existing server-side key;
if the key or network is unavailable, the agent falls back to a deterministic
keyword-vector embedding — retrieval quality drops, but the feature keeps
working offline, matching NewQ's existing degradation pattern.

### Phase 2 — Exam categorization framework
A curated, human-editable map (`ai_engine/rag_agent.py::EXAM_TOPICS`) lists
the question-relevant topics per exam, e.g.

| Exam | Topic taxonomy (examples) |
|---|---|
| Banking | RBI/monetary policy, banking regulation, payments & UPI, fiscal policy, financial markets |
| UPSC | polity & governance, international relations, economy, environment, science & tech |
| SSC | static GK, current affairs (general), schemes |
| BPSC | state-specific news, national politics, economy |
| Defence | exercises & drills, procurement, strategic developments |

Each exam's taxonomy drives a **category query vector**: the agent embeds the
topic list plus a set of high-recall descriptor phrases, producing a per-exam
"what this exam asks about" profile. Retrieval then matches item chunks to
this profile rather than to raw popularity.

### Phase 3 — Retrieval + correlation endpoint
New protected endpoint `GET /api/rag/topics?exam=<name>`:
- scores all indexed chunks against the exam profile (cosine similarity),
- returns top-k items with their matched topics and similarity bands
  (strong / moderate / weak) so the UI can show confidence,
- optionally filters to the last N days.

### Phase 4 — User-facing flow
The Dashboard gains an "exam feed" strip (planned after this backend slice):
pick Banking → the agent lists today's strongest-correlation items; tap one →
the article is pre-filled into analyze. Generation always uses the existing
validated chain. RAG output is a **retrieval surface**, never generated text.

## Expected outputs (concrete examples)

- Query: `/api/rag/topics?exam=Banking&k=3` →
  `[ {title: "RBI keeps repo rate unchanged…", topics: ["monetary policy"],
      similarity: 0.83, band: "strong"}, … ]`
- Question types surfaced for Banking: rate decisions, CRR/SLR changes,
  payment-system stats; for UPSC: court verdicts, cabinet Bills, summit
  outcomes. The mapping lives in the taxonomy table — visible, editable,
  testable.

## Testing and validation

1. **Unit** — chunking stability, deterministic keyword fallback, cosine
   scorer properties, taxonomy assignment (pure functions, no network).
2. **Live** — real feeds against the real Gemini embeddings; regression:
   `/api/analyze` response shape unchanged; offline fallback still returns
   `0.3-ollama`.
3. **Retrieval quality panel** — an editable fixture of 20 known
   item→(exam, topic) pairs; measure top-3 hit rate. Target set *after* the
   first measurements (no unsubstantiated accuracy claims).
4. **Latency** — retrieve+correlate must stay well under the generation
   budget; embeddings are computed at ingest, not at query time.

## Challenges and mitigations

| Challenge | Strategy |
|---|---|
| Short RSS summaries carry little text | Retrieval improves relevance/package-selection, not generation; richer text is **exploration**, not assumed |
| Embedding API quota/policy changes | Keyword-vector fallback, cached embeddings, refresh interval configurable |
| Feed churn (links die, sources drop) | Item TTL + source status surfaced in `/api/news-feed` (already exists) |
| Topic map drift from real exams | Keep taxonomy in one reviewed module; the quality panel makes regressions measurable |
| Cost of failure | New endpoint + optional UI strip only; core analyze path untouched by design |

## Facts vs. to-be-validated

Fact: feeds, embedding access, generation chain, and storage all exist today.
To be validated by the quality panel: per-exam hit rate and how often
retrieved items translate into accepted questions — the panel exists
precisely to turn these unknowns into measured numbers.
