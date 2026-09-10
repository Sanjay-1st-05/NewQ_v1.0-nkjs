from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords, wordnet
from nltk.stem import WordNetLemmatizer
from collections import Counter
import random
import nltk

# -- preprocess ------------------------------------
def preprocess(text):
    tokens = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    tokens = [t for t in tokens if t.isalpha() and t not in stop_words]
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(t) for t in tokens]
    return tokens

# ── Find best word to blank ──────────────────────────────
def find_blank_word(sentence, freq):
    tokens = word_tokenize(sentence)
    tagged = nltk.pos_tag(tokens)

    # Score each word by type + frequency
    scored = []
    for word, tag in tagged:
        if len(word) <= 3 or not word.isalpha():
            continue

        score = freq.get(word.lower(), 0)

        # Boost score based on word type
        if tag == 'NNP':    # Proper noun (ISRO, India)
            score += 10
        elif tag == 'NN':   # Common noun (docking, satellite)
            score += 5
        elif tag == 'NNS':  # Plural noun (missions, satellites)
            score += 3

        # Extra boost for longer words (usually more specific/technical)
        if len(word) > 6:
            score += 2

        scored.append((word, score))

    if not scored:
        return None

    # Return highest scored word
    best = max(scored, key=lambda x: x[1])
    return best[0]

# ── Get distractors from WordNet ─────────────────────────
def get_distractors(word, n=3):
    distractors = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            name = lemma.name().replace('_', ' ')
            if name.lower() != word.lower():
                distractors.add(name.capitalize())
        if len(distractors) >= n * 2:
            break

    # Fallback if WordNet finds nothing
    fallback = ['Authority', 'Institution', 'Agency', 'Department', 'Organisation']
    while len(distractors) < n:
        fb = random.choice(fallback)
        if fb not in distractors:
            distractors.add(fb)

    return random.sample(list(distractors), min(n, len(distractors)))

# ── Generate one MCQ from a sentence ────────────────────
def generate_mcq(sentence, freq):
    answer = find_blank_word(sentence, freq)
    if not answer:
        return None

    question = sentence.replace(answer, '______', 1)
    distractors = get_distractors(answer, n=3)

    options = list(set(distractors + [answer.capitalize()]))[:4]

    # Pad to 4 options if needed
    extras = ['System', 'Process', 'Policy', 'Framework']
    while len(options) < 4:
        e = random.choice(extras)
        if e not in options:
            options.append(e)

    random.shuffle(options)
    labels = ['a', 'b', 'c', 'd']
    correct = options.index(answer.capitalize())

    return {
        'question': question,
        'options': options,
        'answer': f"{labels[correct]}) {answer.capitalize()}"
    }

# ── Full NewQ pipeline ───────────────────────────────────
def is_good_mcq_sentence(sentence):
    tokens = word_tokenize(sentence)
    tagged = nltk.pos_tag(tokens)

    has_proper_noun = any(tag == 'NNP' for _, tag in tagged)
    has_technical_word = any(len(w) > 7 and w.isalpha() for w in tokens)

    # New: skip short or generic sentences
    meaningful_words = [w for w in tokens if w.isalpha() and len(w) > 4]
    too_generic = len(meaningful_words) < 5

    return (has_proper_noun or has_technical_word) and not too_generic

def run_newq(news):
    freq = Counter(preprocess(news))
    sentences = sent_tokenize(news)

    # Score sentences
    scores = {}
    for sent in sentences:
        score = sum(freq.get(t, 0) for t in preprocess(sent))
        scores[sent] = score

    top_sentences = sorted(scores, key=scores.get, reverse=True)[:5]

    print("\n=== Generated MCQs ===")
    mcq_count = 0
    for sent in top_sentences:
        if not is_good_mcq_sentence(sent):   # ← skip weak sentences
            continue
        mcq = generate_mcq(sent, freq)
        if mcq:
            mcq_count += 1
            print(f"\nQ{mcq_count}: {mcq['question']}")
            for i, opt in enumerate(mcq['options']):
                print(f"  {'abcd'[i]}) {opt}")
            print(f"  ✅ Answer: {mcq['answer']}")

    print(f"\nTotal: {mcq_count} MCQs generated!")

def run_newq_interactive():
    print("=" * 55)
    print("        NewQ — News To Questions")
    print("        Read Less. Revise More.")
    print("=" * 55)
    print("\nPaste your news article below.")
    print("Press Enter twice when done:\n")

    # ── User input ───────────────────────────────────────
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)

    news = " ".join(lines)

    if len(news.strip()) < 50:
        print("\n⚠️  Article too short. Please paste a proper news paragraph.")
        return

    # ── Analysis ─────────────────────────────────────────
    print("\n🔍 Analyzing your article...")

    freq = Counter(preprocess(news))
    sentences = sent_tokenize(news)

    # Keywords
    top_keywords = [w for w, _ in freq.most_common(5)]
    print("\n📌 Key topics detected:")
    for k in top_keywords:
        print(f"   • {k.capitalize()}")

    # Summary
    scores = {}
    for sent in sentences:
        score = sum(freq.get(t, 0) for t in preprocess(sent))
        scores[sent] = score

    top_sentences = sorted(scores, key=scores.get, reverse=True)[:5]

    print("\n📰 Quick summary:")
    summary = sorted(scores, key=scores.get, reverse=True)[:2]
    for s in summary:
        print(f"   - {s}")

    # ── MCQ Generation ───────────────────────────────────
    print("\n" + "=" * 55)
    print("           ❓ Quiz Time!")
    print("=" * 55)

    mcqs = []
    for sent in top_sentences:
        if not is_good_mcq_sentence(sent):
            continue
        mcq = generate_mcq(sent, freq)
        if mcq:
            mcqs.append(mcq)
        if len(mcqs) == 3:      # limit to 3 MCQs per session
            break

    if not mcqs:
        print("\n⚠️  Could not generate strong MCQs. Try a longer article.")
        return

    # ── User answers ─────────────────────────────────────
    score = 0
    for i, mcq in enumerate(mcqs):
        print(f"\nQ{i+1}: {mcq['question']}")
        for j, opt in enumerate(mcq['options']):
            print(f"  {'abcd'[j]}) {opt}")

        user_ans = input("\nYour answer (a/b/c/d): ").strip().lower()

        correct_label = mcq['answer'][0]     # first character: a/b/c/d

        if user_ans == correct_label:
            print("  ✅ Correct!")
            score += 1
        else:
            print(f"  ❌ Wrong! Correct answer: {mcq['answer']}")

    # ── Score ─────────────────────────────────────────────
    print("\n" + "=" * 55)
    print(f"  Your Score: {score} / {len(mcqs)}")

    if score == len(mcqs):
        print("  🏆 Perfect! You're ready for the exam!")
    elif score >= len(mcqs) // 2:
        print("  👍 Good effort! Revise the topics you missed.")
    else:
        print("  📖 Keep reading! Practice makes perfect.")

    print("=" * 55)

# ── Run ───────────────────────────────────────────────────
run_newq_interactive()