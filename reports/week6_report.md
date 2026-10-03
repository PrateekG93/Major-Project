# Week 6 Report — Evaluation, Integration Testing & Documentation

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 13 Oct 2026 – 19 Oct 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Run RAGAS evaluation benchmarks on the RAG pipeline
2. Run TruLens groundedness checks for hallucination detection
3. End-to-end integration testing of all flows
4. Write comprehensive project documentation
5. Create weekly progress reports
6. Final bug fixes and code polish

## Work Completed

### 1. RAGAS Evaluation (`eval_ragas.py`)
- Created a 5-question test dataset covering PCA, bias-variance, ACID, hash maps, and transformers
- Implemented simplified RAGAS-style metrics using embedding similarity:
  - **Answer Relevance**: Cosine similarity between generated answer and ground truth
  - **Context Relevance**: Average similarity between query and retrieved context chunks
  - **Faithfulness**: Similarity between answer and context (groundedness proxy)
- Results saved to `evaluation/ragas_results.json`

### 2. TruLens Groundedness Check (`eval_trulens.py`)
- Implemented `check_groundedness()` function that verifies whether generated answers are supported by retrieved context
- Batch evaluation capability with aggregate statistics
- Flags answers below similarity threshold as "POTENTIALLY HALLUCINATED"
- Results saved to `evaluation/trulens_results.json`
- Tested with sample grounded and ungrounded answers — correctly identifies hallucinations

### 3. Integration Testing
Tested the complete end-to-end flows:

**Flow 1: Document Upload → RAG Q&A**
- ✅ Upload a PDF file via `/api/v1/upload`
- ✅ Document parsed, chunked (42 chunks), and indexed in ChromaDB
- ✅ Ask a question via `/api/v1/ask`
- ✅ Receives grounded answer with source citations

**Flow 2: Mock Interview**
- ✅ Start interview via `/api/v1/interview/start` with resume text
- ✅ 10 questions selected matching candidate's skills
- ✅ Submit answers via `/api/v1/interview/answer`
- ✅ Each answer scored by ML model with grade
- ✅ Session state checkpointed after each answer

**Flow 3: Performance Analytics**
- ✅ Session scores aggregated via `/api/v1/score/{session_id}`
- ✅ Per-topic breakdown computed correctly
- ✅ Weak topics identified (below 70% threshold)
- ✅ Study plan generated with action items
- ✅ Recommended materials retrieved from student's notes via RAG

**Flow 4: Fault Tolerance**
- ✅ Session resumes correctly after simulated disconnection
- ✅ LLM fallback activates when primary model times out
- ✅ Empty/corrupted documents handled gracefully

### 4. Documentation
- **EXPLANATION.md**: Comprehensive technical guide covering:
  - Architecture decisions and rationale
  - Module-by-module implementation details
  - API specification
  - Free API strategy
  - Fault tolerance mechanisms
  - How to run the project

- **6 Weekly Reports** (reports/week1_report.md through week6_report.md):
  - Each covering objectives, work completed, decisions, challenges, and next steps

### 5. Bug Fixes & Polish
- Fixed ChromaDB collection naming collision in health check endpoint
- Fixed interview session progress tracking when resuming from checkpoint
- Added input validation for empty queries and answers
- Improved error messages throughout the API
- Added demo dashboard preview for new users without interview data

### 6. Unit Tests — All Passing
| Test File | Tests | Status |
|-----------|-------|--------|
| `test_parser.py` | 7 tests | ✅ All passing |
| `test_rag.py` | 7 tests | ✅ All passing |
| `test_scoring.py` | 8 tests | ✅ All passing |

## Project Summary & Key Metrics

### Architecture
| Component | Files | Lines of Code (approx.) |
|-----------|-------|------------------------|
| Document Intelligence | 2 files | ~350 lines |
| RAG Assistant | 3 files | ~500 lines |
| AI Interviewer | 3 files | ~800 lines |
| ML Scoring | 3 files | ~550 lines |
| FastAPI Backend | 5 files | ~450 lines |
| Streamlit Frontend | 5 files | ~600 lines |
| Evaluation | 2 files | ~250 lines |
| Tests | 3 files | ~300 lines |
| Documentation | 9 files | ~1500 lines |
| **Total** | **~35 files** | **~5300 lines** |

### Technology Usage
| Technology | Component | Cost |
|-----------|-----------|------|
| Hugging Face Inference API | LLM Generation | Free |
| sentence-transformers | Embeddings | Free (local) |
| ChromaDB | Vector Storage | Free (local) |
| SQLite | Relational DB | Free (local) |
| Scikit-Learn + XGBoost | ML Models | Free (local) |
| FastAPI | Backend | Free |
| Streamlit | Frontend | Free |

### ML Model Performance
| Metric | Value | Target |
|--------|-------|--------|
| RMSE | ~0.06 | < 0.12 ✅ |
| R² Score | ~0.93 | > 0.82 ✅ |
| MAE | ~0.05 | — ✅ |

## Remaining Work (Future Scope)
1. **Deploy to Hugging Face Spaces** or Render for public access
2. **Add real web scraping** for AmbitionBox/GFG questions
3. **Audio input support** for interview answers (speech-to-text)
4. **Cross-encoder reranker** for improved retrieval precision
5. **User authentication** for multi-user support
6. **Train ML model on real user data** as it accumulates
7. **Full RAGAS evaluation** with the official library when documents are indexed

## Lessons Learned
1. **Start with the interfaces, not the implementation**: Defining clear module boundaries early made parallel development possible
2. **Free APIs are viable for prototyping**: The HF free tier, combined with local models for embeddings, provides a fully functional system at zero cost
3. **Checkpoint early, checkpoint often**: Session persistence saved significant debugging time
4. **Hybrid retrieval > pure vector search**: BM25 catches what dense search misses, especially for technical acronyms
