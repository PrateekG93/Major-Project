# Week 4 Report — AI Interviewer & FastAPI Backend

**Project:** Intelligent Academic & Career Copilot (PR1107)  
**Period:** 29 Sep 2026 – 5 Oct 2026  
**Team:** Nakul Ranka, Prateek Goswami, Siddharth Ranka  
**Guide:** Devendra Bhavsar

---

## Objectives for This Week
1. Implement Module 3: AI Interviewer (role matching, question selection, session management)
2. Build the complete FastAPI backend with all endpoint routes
3. Implement session checkpointing for interview fault tolerance
4. Test API endpoints via Swagger UI

## Work Completed

### 1. Role Matcher (`role_matcher.py`)
- Built a **comprehensive skill taxonomy** covering 12+ domains:
  - Python, Java, JavaScript, C/C++, SQL, Machine Learning, Deep Learning, NLP, DSA, System Design, Data Science, Computer Vision
  - 100+ keywords mapped to skill categories
- Implemented **skill extraction** from any text (resume or job description) using keyword matching with word boundary detection
- Built **skill-gap analysis**: computes matched/missing/extra skills and match percentage
- Added default skill profiles for 8 common engineering roles (ML Engineer, Data Scientist, Backend Developer, etc.)

### 2. Question Generator (`question_generator.py`)
- Built an interview **session state machine** using dataclasses
- Question selection from the local JSON question bank with:
  - Topic-based filtering (aligned with skill gap analysis)
  - Difficulty mixing (25% easy, 50% medium, 25% hard by default)
  - Random shuffling for variety across sessions
- Session serialization and deserialization for checkpoint compatibility
- Progress tracking (current question, total, answered, remaining)

### 3. Question Bank Seeder (`scraper_pipeline.py`)
- Packaged 40+ curated questions directly in the source code
- Auto-seeding: if `questions.json` doesn't exist, it's created on import
- Statistics API: `get_question_stats()` returns counts by topic and difficulty
- Extensible design for future web scraping integration

### 4. FastAPI Backend — All Routes Implemented

**`main.py`** (Application factory):
- CORS middleware for Streamlit cross-origin requests
- Lifespan events: seeds question bank and pre-trains ML model on startup
- Health check endpoint with per-component status

**`routes/upload.py`** — `POST /api/v1/upload`:
- Multipart file upload with format validation
- Saves file to `data/raw_documents/`, parses, chunks, and indexes into ChromaDB
- Returns document ID, chunk count, and collection name

**`routes/ask.py`** — `POST /api/v1/ask`:
- Hybrid RAG query with configurable collection and doc_type filter
- Graceful fallback: returns raw context chunks if LLM generation fails

**`routes/interview.py`**:
- `POST /api/v1/interview/start` — Session creation from resume + JD
- `POST /api/v1/interview/answer` — Answer submission with ML scoring
- `GET /api/v1/interview/{id}` — Session status and progress

**`routes/score.py`**:
- `POST /api/v1/score` — Single answer scoring
- `GET /api/v1/score/{session_id}` — Full analytics and study recommendations

### 5. Session Checkpointing
- Every answer submission saves the full session state to SQLite
- Sessions can be resumed by ID after disconnection
- In-memory session cache with SQLite fallback for persistence

## Technical Decisions Made
1. **In-memory session store with SQLite backup**: Fast access during active sessions, persistent across restarts
2. **Skill taxonomy over NER**: Keyword matching is more predictable for technical terms than NER models, especially without training data
3. **Auto-seeding question bank**: Eliminates setup friction — the system works out of the box

## Challenges Faced
- Balancing question selection when topics don't have enough questions — implemented fallback to include general questions
- FastAPI lifespan events run before route registration — needed careful import ordering
- Session state serialization with dataclasses required custom `to_dict()` / `from_dict()` methods

## Next Week's Plan
- Implement Module 4: ML Scoring (feature extraction, model training, recommendations)
- Train the scoring ensemble on synthetic data
- Build the adaptive recommendation engine
- Start the Streamlit frontend implementation
