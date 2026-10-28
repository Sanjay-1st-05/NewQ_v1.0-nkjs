import re
import random
from collections import Counter

# ============================================================
# NewQ — News To Questions
# NLP Prototype
# ============================================================

APP_NAME = "NewQ — News To Questions"
TAGLINE = "Read Less. Revise More."

# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was",
    "were", "to", "of", "in", "on", "for", "with", "by", "from",
    "at", "as", "this", "that", "it", "its", "be", "has", "have",
    "had", "will", "would", "can", "could", "about", "into",
    "their", "they", "them", "he", "she", "his", "her", "we",
    "our", "you", "your", "i", "which", "who", "what", "when",
    "where", "while", "than", "then", "also", "been", "being",
    "through", "during", "after", "before", "over", "under",
    "from", "more", "most", "such", "these", "those"
}

# ============================================================
# EXAM DATABASE
# ============================================================

EXAMS = {
    "1": "UPSC",
    "2": "TNPSC",
    "3": "SSC",
    "4": "Banking",
    "5": "Defence"
}

# ============================================================
# SUBJECT KEYWORDS
# Prototype rule-based classification
# ============================================================

SUBJECT_KEYWORDS = {

    "Polity": {
        "government", "parliament", "constitution", "president",
        "minister", "ministry", "court", "supreme", "law",
        "bill", "election", "democracy", "judiciary", "cabinet",
        "lok", "sabha", "rajya", "assembly", "legislature",
        "governance", "amendment", "constitutional"
    },

    "Economy": {
        "economy", "economic", "rbi", "bank", "inflation",
        "gdp", "tax", "revenue", "finance", "financial",
        "monetary", "fiscal", "market", "investment", "trade",
        "export", "import", "interest", "repo", "currency",
        "budget", "employment", "unemployment"
    },

    "Environment": {
        "environment", "climate", "forest", "wildlife",
        "biodiversity", "pollution", "carbon", "emission",
        "renewable", "energy", "tiger", "elephant", "ecosystem",
        "conservation", "species", "greenhouse", "wetland"
    },

    "Science & Technology": {
        "science", "technology", "space", "satellite",
        "isro", "ai", "artificial", "intelligence", "robot",
        "quantum", "digital", "cyber", "software", "research",
        "innovation", "semiconductor", "nuclear", "mission"
    },

    "International Relations": {
        "india", "united", "nations", "country", "countries",
        "bilateral", "international", "summit", "treaty",
        "diplomatic", "diplomacy", "foreign", "agreement",
        "prime minister", "minister", "g20", "brics", "asean"
    },

    "Defence": {
        "defence", "defense", "army", "navy", "airforce",
        "military", "missile", "weapon", "fighter", "aircraft",
        "warship", "submarine", "border", "security", "drone",
        "operation", "exercise"
    },

    "Government Schemes": {
        "scheme", "yojana", "initiative", "programme", "program",
        "beneficiaries", "launched", "welfare", "subsidy",
        "government", "portal", "mission"
    },

    "Geography": {
        "river", "mountain", "ocean", "sea", "earth", "geography",
        "island", "coast", "rainfall", "monsoon", "soil",
        "region", "district", "state", "latitude", "longitude"
    },

    "Awards & Appointments": {
        "award", "awarded", "appointed", "appointment", "honour",
        "honored", "prize", "medal", "winner", "chairperson",
        "director", "chief", "president"
    },

    "Sports": {
        "cricket", "football", "hockey", "tennis", "badminton",
        "athlete", "player", "tournament", "championship",
        "olympics", "medal", "sport", "match", "team"
    }
}

# ============================================================
# PREPROCESSING
# ============================================================

def preprocess(text):
    """
    Convert text into meaningful lowercase tokens.
    """

    words = re.findall(
        r"\b[a-zA-Z][a-zA-Z'-]*\b",
        text.lower()
    )

    return [
        word
        for word in words
        if word not in STOPWORDS
        and len(word) > 2
    ]

# ============================================================
# SENTENCE TOKENIZATION
# ============================================================

def sent_tokenize(text):
    """
    Split article into sentences.
    """

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text.strip()
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]

# ============================================================
# KEYWORD EXTRACTION
# ============================================================

def extract_keywords(text, limit=7):

    words = preprocess(text)

    frequency = Counter(words)

    return [
        word
        for word, _ in frequency.most_common(limit)
    ]

# ============================================================
# SUBJECT DETECTION
# ============================================================

def detect_subject(text):

    words = set(preprocess(text))

    subject_scores = {}

    for subject, keywords in SUBJECT_KEYWORDS.items():

        score = len(words.intersection(keywords))

        if score > 0:
            subject_scores[subject] = score

    if not subject_scores:
        return "General Current Affairs"

    return max(
        subject_scores,
        key=subject_scores.get
    )

# ============================================================
# TOPIC DETECTION
# ============================================================

def detect_topic(text):

    subject = detect_subject(text)

    words = set(preprocess(text))

    matching_keywords = []

    if subject in SUBJECT_KEYWORDS:

        matching_keywords = list(
            words.intersection(
                SUBJECT_KEYWORDS[subject]
            )
        )

    if matching_keywords:

        return matching_keywords[0].replace(
            "_", " "
        ).title()

    return subject

# ============================================================
# EXAM RELEVANCE
# ============================================================

def calculate_relevance(text, exam):

    words = set(preprocess(text))

    # General keywords important for competitive exams
    relevance_keywords = {
        "government",
        "india",
        "policy",
        "scheme",
        "rbi",
        "economy",
        "climate",
        "environment",
        "science",
        "technology",
        "international",
        "defence",
        "parliament",
        "court",
        "constitution",
        "election",
        "summit",
        "agreement",
        "mission",
        "research"
    }

    matches = words.intersection(
        relevance_keywords
    )

    score = len(matches)

    if score >= 4:
        level = "HIGH"
    elif score >= 2:
        level = "MEDIUM"
    else:
        level = "LOW"

    return level, score

# ============================================================
# SENTENCE SCORING
# ============================================================

def score_sentences(text):

    sentences = sent_tokenize(text)
    frequency = Counter(preprocess(text))

    scores = {}

    for sentence in sentences:

        tokens = preprocess(sentence)

        score = sum(
            frequency.get(token, 0)
            for token in tokens
        )

        # Give additional weight to numbers
        if re.search(r"\d", sentence):
            score += 2

        # Give additional weight to important terms
        important_terms = {
            "government",
            "scheme",
            "policy",
            "minister",
            "rbi",
            "india",
            "launched",
            "announced",
            "appointed",
            "agreement",
            "mission"
        }

        for term in important_terms:
            if term in tokens:
                score += 2

        scores[sentence] = score

    return scores

# ============================================================
# SUMMARY
# ============================================================

def generate_summary(text, max_sentences=2):

    scores = score_sentences(text)

    ranked = sorted(
        scores,
        key=scores.get,
        reverse=True
    )

    return ranked[:max_sentences]

# ============================================================
# MCQ CANDIDATE CHECK
# ============================================================

def is_good_mcq_sentence(sentence):

    words = preprocess(sentence)

    if len(words) < 7:
        return False

    # Avoid extremely long sentences
    if len(words) > 45:
        return False

    return True

# ============================================================
# DIFFICULTY ESTIMATION
# ============================================================

def estimate_difficulty(sentence):

    words = preprocess(sentence)

    word_count = len(words)

    has_number = bool(
        re.search(r"\d", sentence)
    )

    complex_terms = {
        "constitutional",
        "international",
        "monetary",
        "biodiversity",
        "geopolitical",
        "infrastructure",
        "semiconductor",
        "sustainability"
    }

    complex_count = sum(
        1
        for word in words
        if word in complex_terms
    )

    if word_count <= 12 and not has_number:
        return "Easy"

    if word_count >= 25 or complex_count >= 1 or has_number:
        return "Medium"

    return "Easy"

# ============================================================
# DISTRACTOR GENERATION
# ============================================================

def generate_distractors(target, frequency):

    distractors = []

    for word, _ in frequency.most_common(50):

        if word == target:
            continue

        if len(word) < 4:
            continue

        if word in STOPWORDS:
            continue

        if word not in distractors:
            distractors.append(word)

        if len(distractors) == 3:
            break

    return distractors

# ============================================================
# EXPLANATION
# ============================================================

def generate_explanation(sentence, target):

    return (
        f"The correct answer is '{target}' "
        f"because it is directly supported by the source sentence."
    )

# ============================================================
# MCQ GENERATION
# ============================================================

def generate_mcq(sentence, frequency):

    words = preprocess(sentence)

    if len(words) < 7:
        return None

    candidates = [
        word
        for word in words
        if len(word) >= 4
        and word not in STOPWORDS
    ]

    if not candidates:
        return None

    # Prefer words appearing more frequently
    target = max(
        candidates,
        key=lambda word: frequency.get(
            word, 0
        )
    )

    pattern = re.compile(
        rf"\b{re.escape(target)}\b",
        re.IGNORECASE
    )

    question = pattern.sub(
        "________",
        sentence,
        count=1
    )

    distractors = generate_distractors(
        target,
        frequency
    )

    if len(distractors) < 3:
        return None

    options = [
        target,
        distractors[0],
        distractors[1],
        distractors[2]
    ]

    random.shuffle(options)

    correct_index = options.index(
        target
    )

    correct_label = "abcd"[correct_index]

    return {
        "question": question,
        "options": options,
        "answer": target,
        "label": correct_label,
        "difficulty": estimate_difficulty(
            sentence
        ),
        "explanation": generate_explanation(
            sentence,
            target
        ),
        "source": sentence
    }

# ============================================================
# DUPLICATE PREVENTION
# ============================================================

def remove_duplicate_mcqs(mcqs):

    unique = []
    seen = set()

    for mcq in mcqs:

        question_key = mcq["question"].lower().strip()

        if question_key not in seen:

            seen.add(question_key)
            unique.append(mcq)

    return unique

# ============================================================
# DISPLAY ARTICLE ANALYSIS
# ============================================================

def display_analysis(
    exam,
    keywords,
    subject,
    topic,
    relevance,
    summary
):

    print("\n" + "=" * 60)
    print("                 NEWS ANALYSIS")
    print("=" * 60)

    print(f"\n🎯 Selected Exam : {exam}")

    print(f"📚 Subject       : {subject}")

    print(f"📌 Main Topic    : {topic}")

    print(f"🎯 Relevance     : {relevance}")

    print("\n🔑 Key Topics / Keywords:")

    for keyword in keywords:
        print(f"   • {keyword.capitalize()}")

    print("\n📰 Quick Summary:")

    for sentence in summary:
        print(f"   • {sentence}")

# ============================================================
# DISPLAY MCQ
# ============================================================

def display_mcq(number, mcq):

    print("\n" + "-" * 60)

    print(
        f"Q{number}. {mcq['question']}"
    )

    print(
        f"Difficulty: {mcq['difficulty']}"
    )

    for index, option in enumerate(
        mcq["options"]
    ):

        print(
            f"  {'abcd'[index]}) "
            f"{option.capitalize()}"
        )

# ============================================================
# EXAM SELECTION
# ============================================================

def select_exam():

    print("\nSelect your examination:")

    for number, exam in EXAMS.items():

        print(
            f"  {number}. {exam}"
        )

    while True:

        choice = input(
            "\nEnter choice (1-5): "
        ).strip()

        if choice in EXAMS:

            return EXAMS[choice]

        print(
            "⚠️ Invalid choice. "
            "Please enter 1-5."
        )

# ============================================================
# MAIN APPLICATION
# ============================================================

def run_newq():

    print("=" * 60)
    print(f"              {APP_NAME}")
    print(f"              {TAGLINE}")
    print("=" * 60)

    # --------------------------------------------------------
    # Exam Selection
    # --------------------------------------------------------

    exam = select_exam()

    # --------------------------------------------------------
    # News Input
    # --------------------------------------------------------

    print("\nPaste your news article below.")
    print("Press ENTER twice when finished.\n")

    lines = []

    while True:

        line = input()

        if line == "":
            break

        lines.append(line)

    news = "\n".join(lines).strip()

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    if len(news) < 80:

        print(
            "\n⚠️ Article too short."
        )

        print(
            "Please provide a proper news article "
            "with at least 80 characters."
        )

        return

    # --------------------------------------------------------
    # Processing
    # --------------------------------------------------------

    print(
        "\n🔍 Analyzing news..."
    )

    frequency = Counter(
        preprocess(news)
    )

    keywords = extract_keywords(
        news,
        limit=7
    )

    subject = detect_subject(
        news
    )

    topic = detect_topic(
        news
    )

    relevance, relevance_score = calculate_relevance(
        news,
        exam
    )

    summary = generate_summary(
        news,
        max_sentences=2
    )

    # --------------------------------------------------------
    # Analysis Output
    # --------------------------------------------------------

    display_analysis(
        exam=exam,
        keywords=keywords,
        subject=subject,
        topic=topic,
        relevance=relevance,
        summary=summary
    )

    print(
        f"\n📊 Relevance score: "
        f"{relevance_score}"
    )

    # --------------------------------------------------------
    # MCQ Generation
    # --------------------------------------------------------

    print(
        "\n⏳ Generating questions..."
    )

    sentence_scores = score_sentences(
        news
    )

    ranked_sentences = sorted(
        sentence_scores,
        key=sentence_scores.get,
        reverse=True
    )

    mcqs = []

    for sentence in ranked_sentences:

        if not is_good_mcq_sentence(
            sentence
        ):
            continue

        mcq = generate_mcq(
            sentence,
            frequency
        )

        if mcq:
            mcqs.append(mcq)

        if len(mcqs) >= 5:
            break

    mcqs = remove_duplicate_mcqs(
        mcqs
    )

    # --------------------------------------------------------
    # MCQ Validation
    # --------------------------------------------------------

    if not mcqs:

        print(
            "\n⚠️ Could not generate "
            "sufficient questions."
        )

        print(
            "Try providing a longer or more detailed article."
        )

        return

    # --------------------------------------------------------
    # QUIZ
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("                    QUIZ TIME")
    print("=" * 60)

    score = 0

    topic_results = Counter()

    for index, mcq in enumerate(
        mcqs,
        start=1
    ):

        display_mcq(
            index,
            mcq
        )

        while True:

            user_answer = input(
                "\nYour answer (a/b/c/d): "
            ).strip().lower()

            if user_answer in {
                "a", "b", "c", "d"
            }:
                break

            print(
                "⚠️ Please enter only "
                "a, b, c or d."
            )

        correct_label = mcq["label"]

        if user_answer == correct_label:

            print(
                "  ✅ Correct!"
            )

            score += 1

        else:

            print(
                f"  ❌ Wrong!"
            )

            print(
                f"  Correct answer: "
                f"{correct_label}) "
                f"{mcq['answer'].capitalize()}"
            )

        print(
            f"  💡 Explanation: "
            f"{mcq['explanation']}"
        )

        print(
            f"  📖 Source: "
            f"{mcq['source']}"
        )

        topic_results[topic] += (
            1 if user_answer == correct_label
            else 0
        )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    total = len(mcqs)

    percentage = (
        score / total
    ) * 100

    print("\n" + "=" * 60)
    print("                  FINAL RESULT")
    print("=" * 60)

    print(
        f"\n🎯 Exam        : {exam}"
    )

    print(
        f"📚 Subject    : {subject}"
    )

    print(
        f"📌 Topic      : {topic}"
    )

    print(
        f"\n🏆 Score      : {score} / {total}"
    )

    print(
        f"📊 Accuracy   : {percentage:.1f}%"
    )

    # --------------------------------------------------------
    # Performance Feedback
    # --------------------------------------------------------

    if percentage == 100:

        print(
            "\n🏆 Excellent! Perfect score."
        )

    elif percentage >= 70:

        print(
            "\n👍 Good performance."
        )

        print(
            "Revise the questions you missed."
        )

    elif percentage >= 40:

        print(
            "\n📖 Moderate performance."
        )

        print(
            "Review the article and attempt "
            "the questions again."
        )

    else:

        print(
            "\n📚 More revision required."
        )

        print(
            "Read the source carefully and "
            "practice again."
        )

    print("\n" + "=" * 60)
    print("               NEWQ SESSION COMPLETE")
    print("=" * 60)

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    run_newq()

# ========================= END ==============================