
from ai_engine.gemini_engine import analyze_news_gemini

sample_news = """
The Reserve Bank of India announced a new monetary policy framework
aimed at maintaining price stability and supporting economic growth.
The framework outlines measures to monitor inflation and improve
the transmission of monetary policy across the economy.
"""

result = analyze_news_gemini(
    text=sample_news,
    exam="UPSC",
    question_count=3,
)

print("Subject:", result["subject"])
print("Topic:", result["topic"])
print("Summary:", result["summary"])
print("Questions generated:", result["question_count"])

for question in result["questions"]:
    print("\nQuestion:", question["question"])
    print("Options:", question["options"])
    print("Answer:", question["answer"])
    print("Source:", question["source"])
