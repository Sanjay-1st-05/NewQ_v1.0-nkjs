import random
from collections import Counter
import re

text = input("Enter new Text:\n")

# 🔹 Step 1: Clean text
text = text.replace("\n", " ")

# Better sentence split
sentences = re.split(r'[.!?]', text)
sentences = [s.strip() for s in sentences if s.strip() != ""]

# 🔹 Step 2: Stopwords
stopwords = ["the", "is", "a", "an", "to", "of", "and", "in", "on", "for", "which", "have", "been", "by", "with", "that"]

# 🔹 Step 3: Word processing
words = re.findall(r'\w+', text.lower())
filtered_words = [w for w in words if w not in stopwords and len(w) > 3]

# 🔹 Step 4: Frequency
word_freq = Counter(filtered_words)

# 🔹 Step 5: Sentence scoring
sentence_scores = {}

for sentence in sentences:
    score = 0
    for word in sentence.lower().split():
        clean_word = re.sub(r'\W+', '', word)
        if clean_word in word_freq:
            score += word_freq[clean_word]
    sentence_scores[sentence] = score

# Get top 2 sentences
summary = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:2]

print("\nSummary:")
for s in summary:
    print("-", s)

# 🔹 Step 6: Keywords (better)
keyword_freq = Counter(filtered_words)
top_keywords = [w for w, _ in keyword_freq.most_common(3)]

print("\nKeywords:")
for k in top_keywords:
    print("-", k.capitalize())

# 🔹 Step 7: MCQ Generation

print("\nMCQs:")

for i, sentence in enumerate(summary):

    words = sentence.split()

    # Filter meaningful words only
    valid_words = []

    for idx, word in enumerate(words):
        clean_word = re.sub(r'\W+', '', word).lower()

        if clean_word not in stopwords and len(clean_word) > 4:
            # Avoid verbs (basic filtering)
            if not clean_word.endswith("ed") and not clean_word.endswith("ing"):
                valid_words.append((idx, word))

    if not valid_words:
        continue

    # Choose good word
    blank_index, answer = random.choice(valid_words)

    answer_clean = re.sub(r'\W+', '', answer)
    answer_final = answer_clean.capitalize()

    words[blank_index] = "______"
    question = " ".join(words)

    print(f"\nQ{i+1}: {question}")

    # Context-based distractors
    if "government" in answer_clean:
        distractors = ["authority", "administration", "body"]

    elif "vendors" in answer_clean:
        distractors = ["workers", "sellers", "agents"]

    elif "footpaths" in answer_clean:
        distractors = ["roads", "streets", "lanes"]

    elif "satellite" in answer_clean:
        distractors = ["rocket", "missile", "drone"]

    else:
        distractors = ["system", "process", "method"]

    options = distractors + [answer_final]
    random.shuffle(options)

    labels = ['a', 'b', 'c', 'd']

    for j in range(4):
        print(f"{labels[j]}) {options[j]}")

    correct_index = options.index(answer_final)
    print(f"Correct Answer: {labels[correct_index]}) {answer_final}")