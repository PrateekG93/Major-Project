# EXPLANATION.md — Technical Implementation Guide

## Intelligent Academic & Career Copilot (RAG + ML)

**Project Code:** PR1107 | **Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Institution:** IET, JK Lakshmipat University | **Guide:** Devendra Bhavsar

---

## 1. What This Project Is

This project is an **end-to-end academic and career preparation platform** that helps engineering students:
1. Upload their course materials (syllabi, lecture notes, exam papers, resumes)
2. Ask questions answered from their own notes using RAG (Retrieval-Augmented Generation)
3. Take mock technical interviews tailored to their resume and target job role
4. Receive ML-powered performance diagnostics and personalized study plans

The key innovation is the **closed-loop feedback system** — instead of generic study advice, the system identifies exactly which topics the student is weak in, retrieves the specific sections from their own lecture notes, and generates targeted retesting.

---

## 2. Architecture Decisions & Rationale

### Why 4 Separate Modules?
We split the system into 4 independent modules to enable parallel development and clear separation of concerns:

| Module | Responsibility | Why Separate? |
|--------|---------------|---------------|
| **Document Intelligence** | Parsing & chunking files | Different file formats need different parsers; chunking strategy is independent of retrieval |
| **RAG Assistant** | Retrieval + LLM generation | Core academic Q&A engine; can be used independently |
| **AI Interviewer** | Question selection & session management | Interview logic is stateful and complex; independent of Q&A |
| **ML Scoring** | Feature extraction, prediction, recommendations | ML pipeline is trainable and versioned separately |

### Why Hybrid Retrieval (BM25 + Dense Vectors)?
Neither sparse nor dense retrieval alone is sufficient for academic content:

- **BM25 handles exact matches**: Technical terms like "Dijkstra", "PCA", "ACID", "GIL" need exact keyword matching. Dense models sometimes miss these.
- **Dense vectors handle semantic meaning**: Questions phrased differently from notes (e.g., "What is dimensionality reduction?" vs notes saying "PCA reduces feature dimensions") need semantic similarity.
- **Reciprocal Rank Fusion (RRF)** merges both result lists with configurable weights (default: 40% BM25, 60% Dense).

### Why Hugging Face Free API (Not OpenAI)?
- **Zero cost**: The Hugging Face Serverless Inference API is completely free for models under 10B parameters
- **No vendor lock-in**: Uses open-weight models (Mistral-7B, Zephyr-7B) that can be run locally if needed
- **Automatic fallback**: If the primary model fails, the system tries a backup model before giving up

### Why ChromaDB (Not FAISS)?
- ChromaDB provides **persistent storage** — indexed documents survive server restarts
- Built-in **metadata filtering** — allows filtering by doc_type (syllabus vs notes)
- Simple Python API with no compilation/installation issues on Windows
- FAISS would require additional persistence code and doesn't support metadata natively

### Why SQLite (Not PostgreSQL)?
- **Zero configuration**: No separate database server needed
- Perfect for single-user academic projects
- Session checkpointing and score persistence don't need advanced DB features
- Easy to upgrade to PostgreSQL later if needed

---

## 3. Module-by-Module Implementation Details

### Module 1: Document Intelligence (`src/document_intelligence/`)

**`parser.py`** — Multi-format document parser
- Uses `PyPDF2` for PDFs (extracts text page by page)
- Uses `python-docx` for Word files (extracts paragraphs)
- Uses `python-pptx` for PowerPoint (extracts text from each slide shape)
- Uses native file I/O for text/markdown files
- Returns a `DocumentContent` dataclass with per-page text and metadata
- Implements **graceful degradation**: if a file partially fails to parse, it returns whatever it can extract rather than crashing

**`chunker.py`** — Structure-aware text splitter
- **Heading-based splitting**: Uses regex to detect Markdown-style headings (`#`, `##`, etc.) and splits at heading boundaries
- **Slide-based splitting**: For PPTX files, each slide becomes a separate chunk
- **Size-based splitting**: Long sections are further split into 512-word chunks with 64-word overlap
- Each chunk gets a UUID and is tagged with metadata: `source_file`, `section`, `page`, `doc_type`, `chunk_index`

### Module 2: RAG Assistant (`src/rag_assistant/`)

**`embeddings.py`** — Local embedding engine
- Uses `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors)
- Runs **100% locally on CPU** — no API calls, no cost, no rate limits
- Lazy-loads the model on first use (model downloads ~80MB on first run)
- L2-normalizes all vectors so cosine similarity = simple dot product

**`hybrid_retriever.py`** — Core search engine
- Maintains both a **BM25 index** (in-memory, from `rank_bm25`) and a **ChromaDB collection** (persistent on disk)
- `add_documents()` indexes into both systems simultaneously
- `search()` queries both, then applies RRF fusion:
  ```
  RRF_score(doc) = Σ (weight_i / (k + rank_i))
  ```
  where `k=60` (tunable), and weights are 0.4 for BM25, 0.6 for dense
- BM25 index is rebuilt from ChromaDB on startup for consistency

**`generator.py`** — LLM response generation
- Uses `huggingface_hub.InferenceClient` to call Mistral-7B-Instruct via the free Serverless API
- Constructs a grounded prompt by injecting retrieved context chunks with source metadata
- Has separate system prompts for academic Q&A vs interview evaluation
- Implements **two-model fallback**: tries Mistral-7B first, falls back to Zephyr-7B if that fails
- If both fail, returns a graceful error message instead of crashing

### Module 3: AI Interviewer (`src/interviewer/`)

**`role_matcher.py`** — Skill extraction and gap analysis
- Contains a **comprehensive skill taxonomy** of 12+ domains with 100+ keywords
- Extracts skills from any text (resume or JD) using keyword matching with word boundary detection
- Computes a **skill-gap matrix**: matched skills (in both resume and JD), missing skills (in JD but not resume), and extra skills (in resume but not JD)
- Includes default skill profiles for 8 common engineering roles

**`question_generator.py`** — Interview session state machine
- Creates sessions with a unique ID, selects questions from the bank, tracks progress
- Supports difficulty mixing (default: 25% easy, 50% medium, 25% hard)
- Every answer submission triggers a checkpoint save to SQLite
- Sessions can be resumed after disconnection using the session ID

**`scraper_pipeline.py`** — Question bank
- Ships **40+ curated interview questions** across Python, DSA, ML, Deep Learning, SQL, System Design, NLP, Computer Vision, and Data Science
- Each question has: topic, difficulty, question text, and reference answer
- Auto-seeds the JSON question bank on first import if the file doesn't exist
- Designed to be extended with web scraping (placeholder for GFG/AmbitionBox integration)

### Module 4: ML Scoring (`src/ml_scoring/`)

**`feature_extractor.py`** — Numerical feature computation
Extracts 6 features from each answer:
1. **Semantic similarity**: Cosine similarity between answer embedding and reference answer embedding
2. **Response time score**: Normalized score based on answer speed (5s=0.9, 30s=0.85, 60s=0.75, 120s+=0.4)
3. **Length score**: Word count normalized to a quality curve (30-120 words = ideal)
4. **Keyword coverage**: Percentage of expected technical terms present in the answer
5. **Confidence score**: Heuristic based on hedging words ("maybe", "I think") vs confident language ("specifically", "fundamentally")
6. **Completeness score**: Based on sentence count (≥3 sentences = fully complete)

**`model.py`** — ML prediction pipeline
- Generates **500 synthetic training samples** across 5 quality tiers (excellent, good, average, poor, bad)
- Trains a **VotingRegressor** ensemble of RandomForest + XGBoost
- Achieves RMSE < 0.1 and R² > 0.9 on test data
- Auto-trains on first prediction if no saved model exists
- Saves trained model to `models/scoring_model.joblib`

**`recommendation_engine.py`** — Adaptive study recommendations
- Identifies topics below a configurable threshold (default: 70%)
- Categorizes severity as critical (<40%), moderate (40-60%), or mild (60-70%)
- Generates study plans with estimated hours, action items, and recommended materials from the student's notes
- Creates retest specifications with difficulty calibrated to severity

---

## 4. API Layer (`src/api/`)

The FastAPI backend exposes 4 endpoint groups:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/upload` | POST | Upload and index documents |
| `/api/v1/ask` | POST | RAG-powered academic Q&A |
| `/api/v1/interview/start` | POST | Initialize mock interview session |
| `/api/v1/interview/answer` | POST | Submit answer, get score + next question |
| `/api/v1/interview/{id}` | GET | Check session status |
| `/api/v1/score` | POST | Score a single answer |
| `/api/v1/score/{session_id}` | GET | Full session analytics + study plan |
| `/health` | GET | Component health check |

The app uses **lifespan events** to seed the question bank and pre-train the ML model on startup.

---

## 5. Frontend Layer (`ui/`)

The Streamlit app has 4 pages:
1. **Upload** — Drag-and-drop file upload with format validation and indexing feedback
2. **Chat** — Chat-style RAG Q&A with source citations and configurable search settings
3. **Interview** — Interactive mock interview with timer, per-question scoring, and progress bar
4. **Dashboard** — Plotly radar and bar charts, weak topic identification, study plan display

---

## 6. Evaluation & Quality (`evaluation/`)

Two evaluation scripts:
- **`eval_ragas.py`**: Computes faithfulness, context relevance, and answer relevance using embedding similarity as proxy metrics
- **`eval_trulens.py`**: Groundedness checking — flags answers that aren't supported by retrieved context

---

## 7. Fault Tolerance Mechanisms

1. **Session Checkpointing**: SQLite-backed checkpoint after every interview answer — survives crashes
2. **LLM Fallback**: Primary model (Mistral-7B) → Backup (Zephyr-7B) → Graceful error message
3. **Search Fallback**: If ChromaDB is unreachable, BM25 alone provides results
4. **Parse Degradation**: Corrupted document pages are skipped; valid pages are still indexed
5. **Groundedness Guard**: Answers with low context similarity are flagged

---

## 8. Free API Strategy

| Component | Solution | Cost |
|-----------|----------|------|
| LLM Text Generation | Hugging Face Serverless Inference API (Mistral-7B) | **Free** |
| Text Embeddings | sentence-transformers/all-MiniLM-L6-v2 (local) | **Free** |
| Vector Database | ChromaDB (local, SQLite-backed) | **Free** |
| ML Models | Scikit-Learn + XGBoost (local) | **Free** |
| Document Parsing | PyPDF2, python-docx, python-pptx (local) | **Free** |
| Database | SQLite (local) | **Free** |

**The only setup requirement is a free Hugging Face token** from huggingface.co/settings/tokens.

---

## 9. How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure environment
cp .env.example .env
# Edit .env and add your free HF_API_TOKEN

# 3. Start the backend
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Start the frontend (new terminal)
streamlit run ui/app.py

# 5. Run tests
python -m pytest tests/ -v
```
