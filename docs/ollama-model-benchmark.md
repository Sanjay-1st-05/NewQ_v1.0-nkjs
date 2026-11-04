# Ollama offline model benchmark (Stage 8c)

Date: 2026-11-04 · Machine: Intel UHD 620 (CPU-only inference), 16 GB RAM

## Decision

`NEWQ_OLLAMA_MODEL` default stays **`llama3.2:3b`**.

## Head-to-head (same news input, same strict validator, 3 trials each)

| Model | Accepted questions | Avg time | Failure mode |
|---|---|---|---|
| llama3.2:3b | **8 / 9** | ~105 s | Occasional produced no source evidence (rejected, correct) |
| qwen2.5:3b | **0 / 9** | ~131 s | Paraphrased source evidence + missing explanations → validator rejects |

Both models produce ~3 raw JSON questions per run; the difference is that
llama3.2 returns evidence quoted verbatim from the article, while qwen2.5
rewrites sentences (caught by the grounding rule) and often omits the
explanation field.

## Why not qwen2.5:7b

Measured constraint, not speculation: 16 GB total RAM with only ~1.6 GB
free in typical use (browser + NewQ server running). A 7B q4 model needs a
~5–6 GB working set → heavy swapping while multitasking.

## Notes

- Run-to-run variance for 3B models is real (yesterday llama scored 3/3 on
  the same input); trials, not single runs, were used for the decision.
- If a better candidate appears later, benchmark with
  `python scripts/bench_ollama.py <model> 3` and require a multi-trial
  head-to-head win against llama3.2:3b before changing the default.
- `qwen2.5:3b` was pulled during evaluation and removed afterwards.
