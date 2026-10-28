import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_engine import analyze_news

NEWS = "The Reserve Bank of India announced a new monetary policy framework aimed at maintaining price stability and supporting economic growth. The policy focuses on managing inflation, maintaining adequate liquidity and strengthening financial stability. The Reserve Bank said the new measures would help improve the resilience of India's financial system."

def test_analysis():
    result = analyze_news(NEWS, "UPSC", 5)
    assert result["subject"] == "Economy"
    assert result["topic"] == "Monetary Policy"
    assert result["question_count"] >= 1
    for q in result["questions"]:
        assert len(q["options"]) == 4
        assert q["answer"] in q["options"]
