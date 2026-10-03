# Week 3 Report — Hybrid RAG Engine Implementation

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 22 Sep 2026 – 28 Sep 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Implement the embedding engine with local sentence-transformers
2. Set up ChromaDB persistent vector storage
3. Build the BM25 sparse retrieval index
4. Implement Reciprocal Rank Fusion (RRF) for hybrid search
5. Connect to Hugging Face free Inference API for LLM generation
6. Test end-to-end retrieval and generation pipeline

## Work Completed

### 1. Embedding Engine (`embeddings.py`)
- Integrated `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional)
- Implemented lazy loading — model downloads only on first use (~80MB)
- L2 normalization for efficient cosine similarity via dot product
- Batch encoding with configurable batch size for large document sets
- Runs entirely on CPU with no external API calls

### 2. ChromaDB Vector Store
- Configured `PersistentClient` with on-disk storage at `data/vector_store/chroma/`
- Collection metadata set to `hnsw:space: cosine` for cosine similarity search
- Batch insertion with 100-document batches (ChromaDB limitation)
- Documents persist across server restarts without re-indexing

### 3. BM25 Sparse Index
- Integrated `rank_bm25.BM25Okapi` for lexical search
- Tokenized corpus stored in memory alongside ChromaDB
- BM25 index automatically rebuilt from ChromaDB on retriever initialization
- Handles exact keyword matching for technical terms (acronyms, algorithm names)

### 4. Reciprocal Rank Fusion (RRF)
- Implemented RRF formula: `score(d) = Σ weight_i / (k + rank_i + 1)`
- Default weights: BM25 = 0.4, Dense = 0.6 (configurable)
- RRF constant `k = 60` (standard value from the literature)
- Retrieves `top_k * 2` candidates from each system before fusion

### 5. LLM Generator (`generator.py`)
- Connected to **Hugging Face Serverless Inference API** using `InferenceClient`
- Primary model: `mistralai/Mistral-7B-Instruct-v0.3`
- Fallback model: `HuggingFaceH4/zephyr-7b-beta`
- Automatic fallback: if primary fails (rate limit, cold start), tries backup
- If both fail, returns a graceful error message
- Separate system prompts for academic Q&A and interview evaluation
- Context injection with source metadata for grounded generation

### 6. End-to-End Testing
- Created `test_rag.py` with tests for:
  - Embedding dimension and type validation
  - Cosine similarity correctness (identical vectors = 1.0)
  - Semantic similarity ordering (related > unrelated)
  - Document indexing and retrieval
  - Empty collection handling
- All 7 RAG tests pass

## Technical Decisions Made
1. **RRF over learned combination**: RRF is parameter-free and well-tested in IR literature; a learned combiner would require labeled relevance data we don't have
2. **Dual-model fallback**: HF free tier has cold starts and rate limits; having a backup model prevents user-facing failures
3. **Context injection over fine-tuning**: Much simpler, requires no training data or GPU, and the free API doesn't support fine-tuned models

## Challenges Faced
- HF Inference API cold starts can take 10-30 seconds for less popular models
- ChromaDB `add()` silently deduplicates by ID — needed to ensure UUIDs are truly unique
- BM25 and ChromaDB return different score ranges — RRF handles this naturally since it uses ranks, not scores

## Next Week's Plan
- Implement Module 3: AI Interviewer (role matcher, question generator, session management)
- Build the FastAPI backend with all 4 route groups
- Connect document upload endpoint to the indexing pipeline
- Implement session checkpointing for interview fault tolerance
