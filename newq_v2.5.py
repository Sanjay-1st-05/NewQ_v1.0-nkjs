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