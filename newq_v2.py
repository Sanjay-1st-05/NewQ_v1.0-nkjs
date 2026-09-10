import re
from collections import Counter

# ============================================================
# NewQ — Basic NLP Functions
# ============================================================

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was",
    "were", "to", "of", "in", "on", "for", "with", "by", "from",
    "at", "as", "this", "that", "it", "its", "be", "has", "have",
    "had", "will", "would", "can", "could", "about", "into",
    "their", "they", "them", "he", "she", "his", "her", "we",
    "our", "you", "your", "I"
}


def preprocess(text):
    """
    Convert text into useful lowercase tokens.
    Removes punctuation and common stopwords.
    """
    words = re.findall(r"\b[a-zA-Z][a-zA-Z'-]*\b", text.lower())

    return [
        word
        for word in words
        if word not in STOPWORDS and len(word) > 2
    ]


def sent_tokenize(text):
    """
    Simple sentence tokenizer.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def is_good_mcq_sentence(sentence):
    """
    Checks whether a sentence contains enough information
    to potentially create an MCQ.
    """
    words = preprocess(sentence)

    # Very short sentences are not useful
    if len(words) < 6:
        return False

    return True


def generate_mcq(sentence, freq):
    """
    Basic rule-based MCQ generator.

    This is NOT an LLM.
    It creates a question by hiding one important word
    from the sentence.
    """

    words = preprocess(sentence)

    if len(words) < 6:
        return None

    # Choose the most frequent meaningful word in the sentence
    candidate_words = [
        word for word in words
        if len(word) >= 4
    ]

    if not candidate_words:
        return None

    target = max(
        candidate_words,
        key=lambda word: freq.get(word, 0)
    )

    # Replace the first occurrence of the target
    pattern = re.compile(
        rf"\b{re.escape(target)}\b",
        re.IGNORECASE
    )

    question = pattern.sub("________", sentence, count=1)

    # Create distractors from other frequent words
    distractors = [
        word
        for word, _ in freq.most_common(20)
        if word != target
        and len(word) >= 4
    ]

    distractors = distractors[:3]

    if len(distractors) < 3:
        return None

    options = [target] + distractors[:3]

    # Shuffle options
    import random
    random.shuffle(options)

    correct_index = options.index(target)
    correct_label = "abcd"[correct_index]

    return {
        "question": question,
        "options": options,
        "answer": f"{correct_label}) {target}"
    }


# ============================================================
# NewQ Interactive Application
# ============================================================

def run_newq_interactive():

    print("=" * 55)
    print("        NewQ — News To Questions")
    print("        Read Less. Revise More.")
    print("=" * 55)

    print("\nPaste your news article below.")
    print("Press Enter twice when done:\n")

    # --------------------------------------------------------
    # User Input
    # --------------------------------------------------------

    lines = []

    while True:
        line = input()

        if line == "":
            break

        lines.append(line)

    news = " ".join(lines)

    # --------------------------------------------------------
    # Input Validation
    # --------------------------------------------------------

    if len(news.strip()) < 50:
        print(
            "\n⚠️  Article too short. "
            "Please paste a proper news paragraph."
        )
        return

    # --------------------------------------------------------
    # Analysis
    # --------------------------------------------------------

    print("\n🔍 Analyzing your article...")

    freq = Counter(preprocess(news))
    sentences = sent_tokenize(news)

    # --------------------------------------------------------
    # Keywords
    # --------------------------------------------------------

    top_keywords = [
        word for word, _ in freq.most_common(5)
    ]

    print("\n📌 Key topics detected:")

    for keyword in top_keywords:
        print(f"   • {keyword.capitalize()}")

    # --------------------------------------------------------
    # Sentence Scoring
    # --------------------------------------------------------

    scores = {}

    for sentence in sentences:

        score = sum(
            freq.get(token, 0)
            for token in preprocess(sentence)
        )

        scores[sentence] = score

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    ranked_sentences = sorted(
        scores,
        key=scores.get,
        reverse=True
    )

    print("\n📰 Quick summary:")

    summary = ranked_sentences[:2]

    for sentence in summary:
        print(f"   - {sentence}")

    # --------------------------------------------------------
    # MCQ Generation
    # --------------------------------------------------------

    print("\n" + "=" * 55)
    print("           ❓ Quiz Time!")
    print("=" * 55)

    mcqs = []

    for sentence in ranked_sentences:

        if not is_good_mcq_sentence(sentence):
            continue

        mcq = generate_mcq(sentence, freq)

        if mcq:
            mcqs.append(mcq)

        # Maximum 3 questions
        if len(mcqs) == 3:
            break

    # --------------------------------------------------------
    # No MCQs
    # --------------------------------------------------------

    if not mcqs:

        print(
            "\n⚠️  Could not generate strong MCQs. "
            "Try a longer article."
        )

        return

    # --------------------------------------------------------
    # User Answers
    # --------------------------------------------------------

    score = 0

    for i, mcq in enumerate(mcqs):

        print(f"\nQ{i + 1}: {mcq['question']}")

        for j, option in enumerate(mcq["options"]):

            print(
                f"  {'abcd'[j]}) {option}"
            )

        user_answer = input(
            "\nYour answer (a/b/c/d): "
        ).strip().lower()

        correct_label = mcq["answer"][0]

        if user_answer == correct_label:

            print("  ✅ Correct!")

            score += 1

        else:

            print(
                f"  ❌ Wrong! "
                f"Correct answer: {mcq['answer']}"
            )

    # --------------------------------------------------------
    # Final Score
    # --------------------------------------------------------

    print("\n" + "=" * 55)

    print(
        f"  Your Score: {score} / {len(mcqs)}"
    )

    if score == len(mcqs):

        print(
            "  🏆 Perfect! You're ready for the exam!"
        )

    elif score >= len(mcqs) // 2:

        print(
            "  👍 Good effort! "
            "Revise the topics you missed."
        )

    else:

        print(
            "  📖 Keep reading! "
            "Practice makes perfect."
        )

    print("=" * 55)


# ============================================================
# Run NewQ
# ============================================================

if __name__ == "__main__":
    run_newq_interactive()