# NewQ — News to Questions

A working prototype for converting current-affairs news into exam-oriented analysis and practice questions.

## Today's demo flow

`News Input → NLP Analysis → Subject → Topic → Exam Relevance → MCQs → Answers → Explanations → Score`

## Run the demo

### Windows PowerShell

```powershell
cd C:\Users\<your-user>\Desktop\NewQ
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit, normally `http://localhost:8501`.

## Run the API

```powershell
uvicorn backend.main:app --reload
```

API endpoints:

- `GET /health`
- `GET /api/exams`
- `POST /api/analyze`

## Test

```powershell
python -m pytest
```

## Current implementation status

The prototype uses an explainable NLP/rule-based engine. It is intentionally structured so that domain-specific ML classifiers, embeddings, LLM question generation, OCR and database persistence can be added without changing the demo workflow.

This version does not claim that the current rule engine is trained machine learning. The next AI/ML stage is to build a labelled news dataset and evaluate topic/relevance classification, then add source-grounded generation and validation.
