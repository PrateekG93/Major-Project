# Week 2 Report — Repository Scaffold, Data Collection & Document Intelligence

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 15 Sep 2026 – 21 Sep 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Scaffold the full project repository with all directories and configuration files
2. Collect sample academic documents for testing
3. Curate the interview question bank
4. Implement Module 1: Document Intelligence (parser + chunker)
5. Set up utility modules (logging, checkpointing)

## Work Completed

### 1. Repository Scaffold
- Created the complete directory structure matching the README specification
- Set up `requirements.txt` with all 25+ Python dependencies
- Created `.env.example` with documented configuration variables
- Added `__init__.py` files for all Python packages
- Added `.gitkeep` files for empty data directories

### 2. Data Collection
- Curated a question bank of **40+ interview questions** across 9 categories:
  - Python (7 questions), DSA (6), Machine Learning (7), Deep Learning (4)
  - SQL (6), System Design (4), NLP (4), Computer Vision (1), Data Science (2)
- Each question includes: topic, difficulty level, question text, and reference answer
- Questions cover easy/medium/hard difficulty tiers

### 3. Module 1: Document Intelligence — Implemented
**`parser.py`** (Document Parser):
- Supports 5 formats: PDF, DOCX, PPTX, TXT, MD
- Returns structured `DocumentContent` with per-page text and metadata
- Implements graceful degradation — partial parse failures don't crash the system
- Factory pattern with `parse_document()` dispatcher

**`chunker.py`** (Text Chunker):
- Heading-aware splitting using regex pattern matching
- Slide-aware splitting for PowerPoint files
- Configurable chunk size (default 512 words) and overlap (64 words)
- UUID-based chunk identification with full metadata tagging

### 4. Utility Modules — Implemented
**`logger.py`**: Structured logging with configurable log level from `.env`
**`checkpoint.py`**: SQLite-backed session persistence with:
- `session_checkpoints` table for interview state serialization
- `performance_scores` table for per-answer scoring data
- Functions: `save_checkpoint()`, `load_checkpoint()`, `save_score()`, `get_topic_averages()`

### 5. Unit Tests Written
- `test_parser.py`: 7 test cases covering text parsing, markdown parsing, unsupported formats, missing files, metadata assignment, and format constants
- All tests pass with `pytest`

## Technical Decisions Made
1. **Structure-aware chunking over fixed-size**: Academic documents have natural boundaries (headings, slides) that should be preserved
2. **UUID for chunk IDs**: Avoids collision issues when multiple documents are indexed
3. **SQLite for checkpointing**: Single-file database, zero configuration, survives process restarts

## Challenges Faced
- PyPDF2 sometimes extracts garbled text from scanned PDFs — added graceful fallback
- python-pptx doesn't extract text from images/charts in slides — documented as a known limitation
- Some PPTX files have text in grouped shapes that aren't directly accessible

## Next Week's Plan
- Implement Module 2: RAG Assistant (embeddings, hybrid retriever, LLM generator)
- Set up ChromaDB persistent storage
- Integrate BM25 + dense vector search with RRF fusion
- Connect to Hugging Face free Inference API for text generation
