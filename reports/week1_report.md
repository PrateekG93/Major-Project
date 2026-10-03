# Week 1 Report — System Architecture & Data Modeling

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 8 Sep 2026 – 14 Sep 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Finalize the system architecture with clear module boundaries
2. Map the complete user journey from document upload to adaptive retesting
3. Design the hybrid storage schema (vector store + relational DB)
4. Select and lock the technology stack
5. Create project documentation (synopsis, README)

## Work Completed

### 1. Architecture Design
- Designed a **4-module architecture** separating concerns:
  - Module 1: Document Intelligence (parsing, chunking)
  - Module 2: RAG Assistant (hybrid retrieval, LLM generation)
  - Module 3: AI Interviewer (role matching, question selection)
  - Module 4: ML Scoring (feature extraction, predictions, recommendations)
- Defined clear interfaces between modules to enable parallel development
- Mapped the presentation layer (Streamlit), API layer (FastAPI), core engine layer, and storage layer

### 2. User Journey Mapping
- Documented the end-to-end flow: Upload → Index → Query/Interview → Score → Diagnose → Recommend → Retest
- Created sequence diagrams showing data flow between components
- Identified the adaptive feedback loop as the key differentiator from existing tools

### 3. Storage Schema Design
- **Vector Store (ChromaDB)**: Separate collections for personal documents and shared question bank
- **Relational DB (SQLite)**: Tables for session checkpoints and performance scores
- Designed metadata schema for chunks: source_file, section, page, doc_type, chunk_index

### 4. Technology Stack Selection

| Component | Selected Technology | Rationale |
|-----------|-------------------|-----------|
| Backend API | FastAPI | Async support, auto-generated docs, type validation |
| Frontend | Streamlit | Rapid prototyping, built-in data visualization |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Runs locally, free, 384-dim vectors |
| Vector DB | ChromaDB | Persistent, metadata filtering, easy Python API |
| LLM | Mistral-7B via HF Inference API | Free tier, open-weight, good instruction following |
| ML Models | Scikit-Learn + XGBoost | Well-documented, no GPU required |
| Evaluation | RAGAS | Standard RAG evaluation framework |

### 5. Documentation
- Created the project synopsis document
- Drafted the comprehensive README.md

## Technical Decisions Made
1. **Hybrid retrieval over pure dense search**: Academic content contains many technical acronyms (PCA, GIL, ACID) that benefit from exact keyword matching via BM25
2. **Free API only**: Using HF Serverless Inference API (free tier) instead of paid OpenAI to keep the project accessible
3. **SQLite over PostgreSQL**: Simpler deployment for an academic project with no need for concurrent multi-user access
4. **Reciprocal Rank Fusion (RRF)** over learned combination for merging BM25 and dense results

## Challenges Faced
- Choosing between LangChain and LlamaIndex for orchestration — decided to use HuggingFace InferenceClient directly for simplicity
- Balancing the question bank size — too small limits question variety, too large makes curation difficult

## Next Week's Plan
- Set up the repository scaffold with all directories and configuration files
- Collect sample academic documents (syllabi, notes, exam papers)
- Curate the initial interview question bank (40+ questions across 6 categories)
- Implement the document parser and text chunker (Module 1)
