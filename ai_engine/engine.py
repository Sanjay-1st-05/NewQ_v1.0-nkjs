import re
import random
from collections import Counter
from typing import Any, Dict, List, Tuple

STOPWORDS = {
    "the","a","an","and","or","but","is","are","was","were","to","of","in","on","for","with","by","from","at","as","this","that","it","its","be","has","have","had","will","would","can","could","about","into","their","they","them","he","she","his","her","we","our","you","your","i","which","who","what","when","where","while","than","then","also","been","being","through","during","after","before","over","under","more","most","such","these","those","said","new","may","might","than","its"
}

EXAMS = ["UPSC", "TNPSC", "SSC", "Banking", "Defence"]

SUBJECT_KEYWORDS = {
    "Polity": {"government","parliament","constitution","president","minister","ministry","court","supreme","law","bill","election","democracy","judiciary","cabinet","lok","sabha","rajya","assembly","legislature","governance","amendment","constitutional"},
    "Economy": {"economy","economic","rbi","bank","inflation","gdp","tax","revenue","finance","financial","monetary","fiscal","market","investment","trade","export","import","interest","repo","currency","budget","employment","unemployment","liquidity","banking","rate"},
    "Environment": {"environment","climate","forest","wildlife","biodiversity","pollution","carbon","emission","renewable","energy","tiger","elephant","ecosystem","conservation","species","greenhouse","wetland"},
    "Science & Technology": {"science","technology","space","satellite","isro","ai","artificial","intelligence","robot","quantum","digital","cyber","software","research","innovation","semiconductor","nuclear","mission","chip"},
    "International Relations": {"united","nations","country","countries","bilateral","international","summit","treaty","diplomatic","diplomacy","foreign","agreement","g20","brics","asean","geopolitical"},
    "Defence": {"defence","defense","army","navy","airforce","military","missile","weapon","fighter","aircraft","warship","submarine","border","security","drone","operation","exercise"},
    "Government Schemes": {"scheme","yojana","initiative","programme","program","beneficiaries","launched","welfare","subsidy","portal","mission"},
    "Geography": {"river","mountain","ocean","sea","earth","geography","island","coast","rainfall","monsoon","soil","region","district","state","latitude","longitude"},
    "Awards & Appointments": {"award","awarded","appointed","appointment","honour","honored","prize","medal","winner","chairperson","director","chief"},
    "Sports": {"cricket","football","hockey","tennis","badminton","athlete","player","tournament","championship","olympics","medal","sport","match","team"},
}

TOPIC_PATTERNS = {
    "Monetary Policy": ["monetary policy framework","monetary policy","repo rate","reverse repo","policy rate","monetary framework","liquidity management","monetary measures","monetary policy committee","mpc","cash reserve ratio","crr","statutory liquidity ratio","slr"],
    "Inflation": ["inflation","consumer price index","cpi","price stability","food inflation","retail inflation"],
    "Fiscal Policy": ["fiscal policy","fiscal deficit","government expenditure","public expenditure","tax revenue","budget deficit"],
    "Climate Change": ["climate change","global warming","greenhouse gas","carbon emissions","net zero","climate action"],
    "Biodiversity & Conservation": ["biodiversity","wildlife conservation","protected area","national park","tiger reserve","wetland","endangered species"],
    "Space Technology": ["space mission","satellite launch","launch vehicle","isro","spacecraft","orbital mission","lunar mission","mars mission"],
    "Artificial Intelligence": ["artificial intelligence","machine learning","generative ai","ai model","large language model","deep learning"],
    "Cyber Security": ["cyber security","cyberattack","data breach","malware","ransomware","cyber threat"],
    "Constitution & Governance": ["constitution","constitutional amendment","fundamental rights","directive principles","governance","constitutional body"],
    "International Relations": ["bilateral agreement","strategic partnership","international summit","diplomatic relations","foreign policy","g20","brics","asean"],
    "Defence & Security": ["military exercise","defence exercise","missile system","fighter aircraft","naval exercise","border security","defence technology"],
    "Government Schemes": ["government scheme","welfare scheme","yojana","government initiative","beneficiary","subsidy programme"],
    "Science & Technology": ["semiconductor","quantum computing","biotechnology","research and development","scientific research","technology mission"],
}

EXAM_WEIGHTS = {
    "UPSC": {"polity":2,"economy":2,"environment":2,"science":2,"international":2,"defence":1,"scheme":2,"geography":2},
    "TNPSC": {"polity":2,"economy":2,"environment":2,"science":2,"international":1,"defence":1,"scheme":2,"geography":2},
    "SSC": {"polity":1,"economy":1,"environment":1,"science":2,"international":1,"defence":1,"scheme":1,"geography":2},
    "Banking": {"polity":1,"economy":3,"environment":1,"science":1,"international":2,"defence":0,"scheme":2,"geography":0},
    "Defence": {"polity":1,"economy":1,"environment":1,"science":2,"international":2,"defence":3,"scheme":1,"geography":1},
}


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def sentences(text: str) -> List[str]:
    text = clean_text(text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def tokens(text: str) -> List[str]:
    words = re.findall(r"\b[a-zA-Z][a-zA-Z'-]*\b", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def extract_keywords(text: str, limit: int = 8) -> List[str]:
    freq = Counter(tokens(text))
    return [w for w, _ in freq.most_common(limit)]


def detect_subject(text: str) -> Tuple[str, Dict[str, int]]:
    words = set(tokens(text))
    scores = {subject: len(words & kws) for subject, kws in SUBJECT_KEYWORDS.items()}
    scores = {k:v for k,v in scores.items() if v > 0}
    if not scores:
        return "General Current Affairs", {}
    return max(scores, key=scores.get), scores


def detect_topic(text: str, subject: str) -> str:
    low = clean_text(text).lower()
    matches = []
    for topic, patterns in TOPIC_PATTERNS.items():
        score = sum(1 for p in patterns if p in low)
        if score:
            matches.append((score, topic))
    if matches:
        return max(matches, key=lambda x: x[0])[1]
    return subject


def relevance(text: str, exam: str, subject: str, topic: str) -> Tuple[str, float, List[str]]:
    low = clean_text(text).lower()
    words = set(tokens(text))
    signals = []
    score = 0.25
    if subject in SUBJECT_KEYWORDS:
        score += 0.12
        signals.append(subject)
    if topic != subject:
        score += 0.18
        signals.append(topic)
    exam_signal = {"rbi","government","policy","scheme","mission","summit","agreement","constitution","climate","research","inflation","budget","election","parliament","defence","security"}
    hits = sorted(words & exam_signal)
    if hits:
        score += min(0.30, 0.06 * len(hits))
        signals.extend(hits[:5])
    weights = EXAM_WEIGHTS.get(exam, {})
    key = subject.lower().split()[0]
    if "international" in subject.lower(): key = "international"
    elif "science" in subject.lower(): key = "science"
    elif "environment" in subject.lower(): key = "environment"
    elif "defence" in subject.lower(): key = "defence"
    elif "scheme" in subject.lower(): key = "scheme"
    elif "economy" in subject.lower(): key = "economy"
    elif "geography" in subject.lower(): key = "geography"
    elif "polity" in subject.lower(): key = "polity"
    score += 0.05 * weights.get(key, 0)
    score = max(0.0, min(0.98, score))
    level = "HIGH" if score >= 0.70 else "MEDIUM" if score >= 0.45 else "LOW"
    return level, round(score, 2), list(dict.fromkeys(signals))


def summarize(text: str, limit: int = 2) -> List[str]:
    sents = sentences(text)
    if len(sents) <= limit:
        return sents
    freq = Counter(tokens(text))
    scored = []
    for i, s in enumerate(sents):
        score = sum(freq[w] for w in tokens(s))
        if re.search(r"\d", s): score += 2
        if re.search(r"\b(announced|launched|appointed|approved|signed|reported|introduced)\b", s, re.I): score += 2
        scored.append((score, -i, s))
    return [x[2] for x in sorted(scored, reverse=True)[:limit]]



def extract_entities(text: str) -> List[str]:
    known = [
        "Reserve Bank of India",
        "Indian Space Research Organisation",
        "United Nations",
        "World Health Organization",
        "Ministry of Finance",
        "NITI Aayog",
        "Supreme Court of India",
        "RBI",
        "ISRO",
        "NASA",
        "WHO",
        "UN",
        "GDP",
        "MPC",
        "G20",
        "BRICS",
    ]

    found = []

    for entity in known:
        if entity.isupper() and len(entity) <= 5:
            # Match acronyms as whole words, not as substrings.
            pattern = rf"\b{re.escape(entity)}\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                found.append(entity)
        elif re.search(re.escape(entity), text, flags=re.IGNORECASE):
            found.append(entity)

    # Extract additional capitalized multi-word names.
    pattern = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b"
    found.extend(re.findall(pattern, text))

    bad = {
        "The Reserve Bank",
        "The Government",
        "The Indian Government",
        "The New Policy",
    }

    return list(dict.fromkeys(
        entity.strip()
        for entity in found
        if entity.strip() not in bad
    ))

def number_facts(text: str) -> List[str]:
    return re.findall(r"\b\d+(?:\.\d+)?%?(?:\s?(?:crore|lakh|million|billion|km|years?|days?))?\b", text, flags=re.I)


def difficulty(sentence: str) -> str:
    t = tokens(sentence)
    if len(t) > 28 or re.search(r"\d", sentence): return "Medium"
    if len(t) > 18: return "Medium"
    return "Easy"


def make_question(sentence: str, topic: str, entities: List[str], source_text: str) -> Dict[str, Any] | None:
    low = sentence.lower()
    # Entity question first: useful for exam-style factual recall.
    entity_aliases = [e for e in entities if e.lower() in low]
    if not entity_aliases:
        aliases = {"reserve bank of india": "Reserve Bank of India", "reserve bank": "Reserve Bank of India"}
        entity_aliases = [canonical for alias, canonical in aliases.items() if alias in low]
    if entity_aliases:
        entity = entity_aliases[0]
        matched = entity if entity.lower() in sentence.lower() else next((a for a in ["Reserve Bank"] if a.lower() in sentence.lower()), entity)
        question = re.sub(re.escape(matched), "________", sentence, count=1, flags=re.I)
        distractors = [e for e in entities if e.lower() != entity.lower()]
        pools = ["Ministry of Finance", "United Nations", "NITI Aayog", "SEBI", "DRDO"]
        for p in pools:
            if p.lower() != entity.lower() and p not in distractors:
                distractors.append(p)
        options = [entity] + distractors[:3]
        if len(options) == 4:
            random.Random(42 + len(sentence)).shuffle(options)
            return {"type":"Entity Identification","question":question,"options":options,"answer":entity,"explanation":f"The source sentence identifies {entity} as the institution associated with the reported development.","source":sentence,"difficulty":difficulty(sentence),"topic":topic}

    # Objective question from purpose phrases.
    m = re.search(r"(?:aimed at|aims to|designed to|focused on|focuses on)\s+(.+?)(?:\.|$)", sentence, re.I)
    if m:
        answer = m.group(1).strip().rstrip(".")
        if 3 <= len(answer.split()) <= 18:
            options = [answer, "Increasing import dependence", "Reducing institutional transparency", "Eliminating all market regulation"]
            return {"type":"Objective / Purpose","question":"What is the main objective described in the news?","options":options,"answer":answer,"explanation": f"The source states that the measure is aimed at {answer}.","source":sentence,"difficulty":difficulty(sentence),"topic":topic}

    # Topic identification from a source sentence containing the topic phrase.
    patterns = sorted(TOPIC_PATTERNS.get(topic, []), key=len, reverse=True)
    for p in patterns:
        if p in low:
            question = re.sub(re.escape(p), "________", sentence, count=1, flags=re.I)
            distractor_topics = ["Fiscal Policy","Public Administration","Trade Policy","Environmental Governance","Foreign Policy","Social Welfare"]
            options = [topic] + [x for x in distractor_topics if x.lower() != topic.lower()][:3]
            random.Random(99 + len(sentence)).shuffle(options)
            return {"type":"Topic Identification","question":question,"options":options,"answer":topic,"explanation":f"The source contains evidence directly associated with {topic}.","source":sentence,"difficulty":difficulty(sentence),"topic":topic}

    # Fact question using a meaningful domain token; avoid generic words.
    generic = {"bank","policy","government","india","system","financial","new","said","market","security"}
    important = [w for w in tokens(sentence) if w not in generic and w in (SUBJECT_KEYWORDS.get("Economy", set()) | SUBJECT_KEYWORDS.get("Science & Technology", set()) | SUBJECT_KEYWORDS.get("Environment", set()) | SUBJECT_KEYWORDS.get("Defence", set()))]
    if important:
        target = important[0]
        question = re.sub(rf"\b{re.escape(target)}\b", "________", sentence, count=1, flags=re.I)
        distractors = [x for x in ["inflation","liquidity","research","investment","climate","technology"] if x != target][:3]
        options = [target] + distractors
        random.Random(7 + len(sentence)).shuffle(options)
        return {"type":"News Fact","question":question,"options":options,"answer":target,"explanation":f"The answer is supported directly by the source sentence: {sentence}","source":sentence,"difficulty":difficulty(sentence),"topic":topic}
    return None

def make_additional_questions(
    sentence: str,
    topic: str,
) -> List[Dict[str, Any]]:
    """Generate additional questions from explicit source phrases."""
    questions = []
    patterns = [
        (
            r"(?:aimed at|aims to|designed to|focused on|focuses on)\s+(.+?)(?:[.;]|$)",
            "Objective / Purpose",
            "What objective does the reported measure focus on?",
        ),
        (
            r"(?:maintaining|improving|strengthening|supporting|reducing|increasing)\s+"
            r"([^,.;]+)",
            "News Fact",
            "Which action is explicitly mentioned in the news?",
        ),
    ]

    for pattern, question_type, prompt in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)

        if not match:
            continue

        answer = match.group(1).strip().rstrip(" .")
        if not answer or len(answer.split()) < 2:
            continue

        # Distractors must be distinct from the source-supported answer.
        distractor_pool = [
            "increasing import dependence",
            "reducing institutional transparency",
            "eliminating market regulation",
            "expanding cultural tourism",
            "improving wildlife conservation",
        ]

        options = [answer]
        for distractor in distractor_pool:
            if normalize_option(distractor) != normalize_option(answer):
                options.append(distractor)
            if len(options) == 4:
                break

        question = {
            "type": question_type,
            "question": prompt,
            "options": options,
            "answer": answer,
            "explanation": (
                f"The answer is based on this source sentence: {sentence}"
            ),
            "source": sentence,
            "difficulty": difficulty(sentence),
            "topic": topic,
        }

        valid, _ = validate_question(question)
        if valid:
            questions.append(question)

    return questions

def normalize_option(value: str) -> str:
    """Normalize whitespace and punctuation for duplicate detection."""
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = re.sub(r"[.!?,;:]+$", "", value)
    return value.casefold()

def validate_question(q: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues = []
    options = q.get("options", [])
    answer = q.get("answer", "")
    question = q.get("question", "")

    if not isinstance(options, list) or len(options) != 4:
        issues.append("requires four options")
        options = []

    normalized = [normalize_option(option) for option in options]

    if any(not option for option in normalized):
        issues.append("options cannot be empty")

    if len(set(normalized)) != len(normalized):
        issues.append("duplicate options")

    if normalize_option(answer) not in normalized:
        issues.append("answer is not present in options")

    if not isinstance(question, str) or not question.strip():
        issues.append("question cannot be empty")

    elif "________" not in question and q.get("type") not in {"Objective / Purpose", "Topic Classification",}:
        issues.append("question is weakly grounded")

    if not q.get("explanation"):
        issues.append("explanation is missing")

    if not q.get("source"):
        issues.append("source evidence is missing")

    return len(issues) == 0, issues

def generate_questions(text: str, topic: str, count: int = 5) -> List[Dict[str, Any]]:
    sents = sentences(text)
    entities = extract_entities(text)
    candidates = []

    # Generate and validate questions from source sentences.
    for sentence in sents:
        question = make_question(sentence, topic, entities, text)

        if question:
            is_valid, _ = validate_question(question)
            if is_valid:
                candidates.append(question)

        candidates.extend(make_additional_questions(sentence, topic))

    # Add a topic-classification question when appropriate.
    if topic and topic != "General Current Affairs":
        topic_question = {
            "type": "Topic Classification",
            "question": "Which topic is most directly represented by this news article?",
            "options": [
                topic,
                "Sports Administration",
                "Cultural Heritage",
                "Tourism Management",
            ],
            "answer": topic,
            "explanation": (
                f"The article contains source evidence associated with {topic}."
            ),
            "source": " ".join(sents[:2]),
            "difficulty": "Easy",
            "topic": topic,
        }

        is_valid, _ = validate_question(topic_question)
        if is_valid:
            candidates.append(topic_question)

    # Remove duplicate wording and repeated answers to the same
    # fill-in-the-blank fact.
    unique = []
    seen_questions = set()
    seen_facts = set()
    seen_types = set()

    for question in candidates:
        question_text = normalize_option(question.get("question", ""))
        question_type = question.get("type", "")

        # Keep only one objective question in each set.
        if question_type == "Objective / Purpose" and question_type in seen_types:
            continue

        # Remove identical question wording.
        if question_text in seen_questions:
            continue

        question_type = question.get("type", "")
        answer = normalize_option(question.get("answer", ""))

        # Avoid asking the same entity/fact question repeatedly.
        if "________" in question.get("question", ""):
            fact_key = (question_type, answer)
            if fact_key in seen_facts:
                continue
            seen_facts.add(fact_key)

        seen_questions.add(question_text)
        seen_types.add(question_type)
        unique.append(question)

    return unique[:count]

def analyze_news(text: str, exam: str = "UPSC", question_count: int = 5) -> Dict[str, Any]:
    text = clean_text(text)
    if len(text) < 80:
        raise ValueError("Please provide at least 80 characters of news content.")
    subject, subject_scores = detect_subject(text)
    topic = detect_topic(text, subject)
    level, score, signals = relevance(text, exam, subject, topic)
    summary = summarize(text)
    keywords = extract_keywords(text)
    questions = generate_questions(text, topic, question_count)
    return {
        "app": "NewQ",
        "version": "0.1-demo",
        "exam": exam,
        "subject": subject,
        "topic": topic,
        "relevance": level,
        "relevance_score": score,
        "confidence_note": "Prototype NLP/rule-based analysis; ML classifiers will replace/augment these rules during the next development stage.",
        "keywords": keywords,
        "summary": summary,
        "signals": signals,
        "subject_scores": subject_scores,
        "question_count": len(questions),
        "questions": questions,
    }
