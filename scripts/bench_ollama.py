"""Benchmark an Ollama model through the real NewQ engine path.

Usage:
    python scripts\\bench_ollama.py <model> [question_count]

Times analyze_news_ollama() end to end (prompt build -> generate ->
strict validation) and prints the accepted questions so quality can be
compared fairly between models on identical input.
"""

import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from ai_engine.ollama_engine import analyze_news_ollama  # noqa: E402

NEWS = (
    "The Reserve Bank of India announced a new monetary policy framework "
    "aimed at maintaining price stability and supporting economic growth. "
    "The framework keeps the inflation target unchanged and reinforces "
    "liquidity management measures for scheduled commercial banks across "
    "major cities."
)


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else 'llama3.2:3b'
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    os.environ['NEWQ_OLLAMA_MODEL'] = model
    # Re-read the module-level constant after the env override.
    import ai_engine.ollama_engine as engine
    engine.OLLAMA_MODEL = model

    available = engine.is_ollama_available()
    print(f'model: {model} | available: {available}')
    if not available:
        return 1

    t0 = time.time()
    result = engine.analyze_news_ollama(NEWS, exam='Banking', question_count=count)
    elapsed = time.time() - t0

    print(f'elapsed: {elapsed:.0f}s | version: {result["version"]} '
          f'| questions accepted: {result["question_count"]}')
    for i, question in enumerate(result['questions'], 1):
        print(f'{i}. {question["question"]}')
        print(f'   answer: {question["answer"]} | '
              f'source: {str(question.get("source", ""))[:60]}...')
    print('summary:', str(result['summary'])[:120])
    return 0


if __name__ == '__main__':
    sys.exit(main())
