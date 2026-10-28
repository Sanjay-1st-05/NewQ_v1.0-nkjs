import json
import streamlit as st
from ai_engine import EXAMS, analyze_news

st.set_page_config(page_title="NewQ — News to Questions", page_icon="📰", layout="wide")

st.markdown("""
<style>
.main-title {font-size: 42px; font-weight: 800; margin-bottom: 0;}
.subtitle {font-size: 17px; color: #64748b; margin-bottom: 24px;}
.card {padding: 18px; border: 1px solid #e2e8f0; border-radius: 14px; background: #ffffff; margin-bottom: 12px;}
.small {font-size: 13px; color: #64748b;}
</style>
""", unsafe_allow_html=True)

if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "answers" not in st.session_state:
    st.session_state.answers = {}

st.markdown('<div class="main-title">📰 NewQ</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">News → Analysis → Questions → Practice</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("NewQ Demo")
    exam = st.selectbox("Select examination", EXAMS, index=0)
    count = st.slider("Questions", 3, 5, 5)
    st.divider()
    st.caption("AI/ML Prototype")
    st.caption("Current engine: explainable NLP/rule-based pipeline. ML classifiers and model-based generation can be integrated next.")

DEFAULT_NEWS = """The Reserve Bank of India announced a new monetary policy framework aimed at maintaining price stability and supporting economic growth. The policy focuses on managing inflation, maintaining adequate liquidity and strengthening financial stability. The Reserve Bank said the new measures would help improve the resilience of India's financial system."""

st.subheader("1. News Input")
input_text = st.text_area("Paste a news article or current-affairs passage", value=DEFAULT_NEWS, height=220, placeholder="Paste news content here...")

col1, col2 = st.columns([1, 5])
with col1:
    analyze_clicked = st.button("🔍 Analyze News", type="primary", use_container_width=True)
with col2:
    st.caption("For today's demo, text input is implemented first. Newspaper-image OCR is planned as the next input module.")

if analyze_clicked:
    try:
        with st.spinner("Analyzing news and generating questions..."):
            st.session_state.analysis = analyze_news(input_text, exam, count)
            st.session_state.answers = {}
    except ValueError as e:
        st.error(str(e))

result = st.session_state.analysis
if result:
    st.divider()
    st.subheader("2. AI News Analysis")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Exam", result["exam"])
    c2.metric("Subject", result["subject"])
    c3.metric("Relevance", result["relevance"])
    c4.metric("Score", f"{result['relevance_score']:.2f}")

    left, right = st.columns([2, 1])
    with left:
        st.markdown("### Main Topic")
        st.info(result["topic"])
        st.markdown("### Summary")
        for s in result["summary"]:
            st.write("• " + s)
    with right:
        st.markdown("### Keywords")
        st.write(" · ".join(k.title() for k in result["keywords"]))
        st.markdown("### Relevance Signals")
        st.write(" · ".join(result["signals"]) if result["signals"] else "No strong signals detected")

    st.divider()
    st.subheader("3. Generated Questions")
    if not result["questions"]:
        st.warning("The current prototype could not generate reliable questions from this passage. Try a more detailed news article.")
    else:
        for i, q in enumerate(result["questions"], 1):
            st.markdown(f"### Q{i}. {q['question']}")
            st.caption(f"{q['type']} · {q['difficulty']} · Topic: {q['topic']}")
            key = f"q_{i}"
            selected = st.radio("Select an answer", q["options"], key=key, index=None)
            if selected is not None:
                st.session_state.answers[i] = selected
                if selected == q["answer"]:
                    st.success("Correct")
                else:
                    st.error(f"Incorrect — correct answer: {q['answer']}")
                st.info(q["explanation"])
            with st.expander("View source evidence"):
                st.write(q["source"])
            st.divider()

        answered = len(st.session_state.answers)
        correct = sum(1 for i, q in enumerate(result["questions"], 1) if st.session_state.answers.get(i) == q["answer"])
        st.subheader("4. Quiz Result")
        r1, r2, r3 = st.columns(3)
        r1.metric("Answered", f"{answered}/{len(result['questions'])}")
        r2.metric("Score", f"{correct}/{len(result['questions'])}")
        pct = (correct / len(result["questions"]) * 100) if result["questions"] else 0
        r3.metric("Accuracy", f"{pct:.0f}%")

    with st.expander("Developer Output — API-ready JSON"):
        st.json(result)
