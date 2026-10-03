# Intelligent Academic & Career Copilot (RAG + ML)

[![Project Status: Active Development](https://img.shields.io/badge/Project%20Status-Active%20Development-blue.svg)](#project-roadmap)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI%20%7C%20Streamlit-orange.svg)](#technology-stack)
[![RAG Pipeline](https://img.shields.io/badge/RAG-Hybrid%20BM25%20%2B%20Dense%20Vector-green.svg)](#module-2-rag-assistant)
[![Evaluation](https://img.shields.io/badge/Eval-RAGAS%20%7C%20TruLens-purple.svg)](#evaluation--quality-assurance)

An end-to-end academic and career acceleration platform combining **Retrieval-Augmented Generation (RAG)** and **Supervised Machine Learning**. The system ingests student course materials and resumes, generates tailored mock interviews aligned with industry job descriptions, diagnoses granular topic-level weaknesses using predictive ML, and closes the learning gap through an adaptive recommendation loop linked back to student notes.

---

## Metadata & Academic Details

| Attribute | Details |
| :--- | :--- |
| **Project Code** | **PR1107** (Major Project) |
| **Institution** | Institute of Engineering and Technology (IET), JK Lakshmipat University (JKLU) |
| **Faculty Guide** | **Devendra Bhavsar** |
| **Team Members** | • **Nakul Ranka** (`2023Btech050`)<br>• **Prateek Goswami** (`2023Btech058`)<br>• **Siddharth Ranka** (`2023Btech082`) |
| **Synopsis Date** | August 14, 2026 |
| **Current Milestone**| Week 1 Completed (Architecture, Data Pipeline Design & Schema Finalized) |

---

## Table of Contents

- [Intelligent Academic \& Career Copilot (RAG + ML)](#intelligent-academic--career-copilot-rag--ml)
  - [Metadata \& Academic Details](#metadata--academic-details)
  - [Table of Contents](#table-of-contents)
  - [Project Overview \& Problem Statement](#project-overview--problem-statement)
    - [The Problem](#the-problem)
    - [The Proposed Solution](#the-proposed-solution)
  - [Key Features](#key-features)
  - [System Architecture](#system-architecture)
    - [High-Level Architectural Flow](#high-level-architectural-flow)
    - [Detailed Data \& Component Flowchart](#detailed-data--component-flowchart)
  - [Core Modules Breakdown](#core-modules-breakdown)
    - [Module 1: Document Intelligence](#module-1-document-intelligence)
    - [Module 2: RAG Assistant (Hybrid Retrieval + Reranking)](#module-2-rag-assistant-hybrid-retrieval--reranking)
    - [Module 3: AI Interviewer \& Industry Knowledge Base](#module-3-ai-interviewer--industry-knowledge-base)
    - [Module 4: ML-Based Skill Analysis \& Adaptive Learning Loop](#module-4-ml-based-skill-analysis--adaptive-learning-loop)
  - [Evaluation \& Quality Assurance](#evaluation--quality-assurance)
  - [Fault Tolerance \& Reliability](#fault-tolerance--reliability)
  - [Technology Stack](#technology-stack)
  - [Project Repository Structure](#project-repository-structure)
  - [API Specification (Draft)](#api-specification-draft)
  - [Local Setup \& Installation](#local-setup--installation)
    - [Prerequisites](#prerequisites)
    - [Step-by-Step Setup](#step-by-step-setup)
    - [Environment Variables Configuration (`.env`)](#environment-variables-configuration-env)
    - [Running the Applications](#running-the-applications)
  - [Project Roadmap \& Milestones](#project-roadmap--milestones)
  - [Academic References](#academic-references)

---

## Project Overview & Problem Statement

### The Problem
Preparing for academic examinations and technical job interviews presents major friction points for engineering students:
1. **Generic Preparation**: Standard question banks and AI chatbots lack alignment with specific course syllabi, university exam patterns, and target job descriptions (JDs).
2. **One-Way Interaction**: Current study assistants answer queries statically without assessing whether the student actually internalized the concepts or retained prerequisite knowledge.
3. **No Closed-Loop Feedback**: Students rarely receive automated, quantitative diagnosis of their topic-level weak points (e.g., scoring 82% in Python, but failing SQL queries at 61%), nor do they receive a direct path back to relevant lecture notes to bridge that gap.

### The Proposed Solution
The **Intelligent Academic & Career Copilot** introduces a closed-loop preparation engine:
1. Ingests user documents (syllabi, lecture notes, exam papers, and resumes).
2. Conducts realistic mock interviews driven by real-world interview datasets (AmbitionBox, GeeksforGeeks).
3. Analyzes candidate responses using both semantic heuristics and trained Machine Learning models (Random Forest / XGBoost) across multiple dimensions (accuracy, response latency, conceptual depth, confidence).
4. Generates a personalized remediation plan pointing back to specific sections within the user's uploaded notes, followed by targeted re-examination.

---

## Key Features

- 📄 **Multi-Format Document Parsing**: Native extraction of syllabi, resumes, lecture presentations, and question papers (`.pdf`, `.docx`, `.pptx`, `.txt`).
- 🔍 **Hybrid RAG Pipeline**: Combines sparse lexical matching (**BM25**) with dense semantic vector embeddings (**Sentence-Transformers**) and a neural cross-encoder **Reranker** to minimize context noise.
- 🎯 **Industry-Aligned Mock Interviews**: Parses student resumes alongside target Job Descriptions (e.g., Machine Learning Engineer, Backend Developer) and injects real interview questions mined from career portals.
- 📊 **Predictive ML Skill Diagnostic**: Scikit-Learn / XGBoost models that classify competency scores, detect weak sub-domains, and predict exam/interview readiness.
- 🔁 **Adaptive Retesting Loop**: Re-evaluates identified weak spots by dynamically generating targeted micro-quizzes referencing the student's own curriculum.
- 🛡️ **Reliability & Hallucination Guard**: Automated groundedness checking (TruLens/RAGAS) and checkpointing to preserve session states during dropouts.

---

## System Architecture

### High-Level Architectural Flow

```mermaid
flowchart TD
    subgraph UI_Layer ["Presentation Layer (Streamlit / Gradio)"]
        UI_Upload["Upload UI\n(Resume, Syllabus, Notes)"]
        UI_Chat["Academic Q&A Chat UI"]
        UI_Interview["Interactive Mock Interview UI"]
        UI_Dashboard["Performance & Weakness Dashboard"]
    end

    subgraph API_Layer ["Backend API (FastAPI / Flask)"]
        EP_Upload["/upload"]
        EP_Ask["/ask"]
        EP_Interview["/interview"]
        EP_Score["/score"]
    end

    subgraph Core_Engine ["Core Processing Engines"]
        DocIntel["Module 1: Document Intelligence\n(Chunking, Metadata Extraction)"]
        RAGAssist["Module 2: RAG Assistant\n(Hybrid BM25 + Dense Search + Reranker)"]
        AIInterviewer["Module 3: AI Interviewer\n(Resume + JD Match, Question Gen)"]
        MLScoring["Module 4: ML Skill Analysis\n(Random Forest, XGBoost, Weak-Area Detection)"]
    end

    subgraph Storage_Layer ["Data & Storage Layer"]
        VecDB[("Vector Database\n(ChromaDB / FAISS)\n• Personal Docs Collection\n• Shared Question Bank")]
        RelDB[("Relational Database\n(SQLite / PostgreSQL)\n• User Profiles\n• Session Checkpoints\n• Performance Scores")]
        ScraperPipe["Knowledge Base Pipeline\n(Scraped GeeksforGeeks / AmbitionBox Questions)"]
    end

    subgraph Eval_Layer ["Evaluation & Quality Layer"]
        RAGAS["RAGAS / TruLens\n(Faithfulness, Context Relevance, Hallucination Detection)"]
        FaultTol["Fault Tolerance Layer\n(State Checkpointing, Error Fallbacks)"]
    end

    %% Connections
    UI_Upload --> EP_Upload
    UI_Chat --> EP_Ask
    UI_Interview --> EP_Interview
    UI_Dashboard --> EP_Score

    EP_Upload --> DocIntel
    EP_Ask --> RAGAssist
    EP_Interview --> AIInterviewer
    EP_Score --> MLScoring

    DocIntel --> VecDB
    ScraperPipe --> VecDB
    RAGAssist <--> VecDB
    AIInterviewer <--> VecDB
    AIInterviewer --> MLScoring
    MLScoring --> RelDB

    RAGAssist -.-> RAGAS
    AIInterviewer -.-> FaultTol
    MLScoring -->|"Adaptive Feedback Loop\n(Remediation & Retesting)"| RAGAssist
```

### Detailed Data & Component Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor Student as User / Student
    participant UI as Streamlit/Gradio Interface
    participant API as FastAPI Backend
    participant DocEngine as Document Parser & Vector Store
    participant Interviewer as AI Interviewer (LLM)
    participant ML as ML Scoring Model (XGBoost/RF)
    participant RAG as RAG Assistant (Hybrid Search)

    Student->>UI: Uploads Resume + Target Job Description + Syllabus
    UI->>API: POST /upload
    API->>DocEngine: Parse & Chunk Documents -> Generate Embeddings
    DocEngine-->>API: Status: Indexed in ChromaDB/FAISS

    Student->>UI: Start Mock Interview Session
    UI->>API: POST /interview (Session Init)
    API->>Interviewer: Match Resume against JD & pull role-specific questions
    Interviewer-->>UI: Deliver Technical Question (e.g., Python, SQL, ML)

    Student->>UI: Submits Answers (Text / Audio Transcript)
    UI->>API: POST /score (Answer Payload, Response Time)
    API->>ML: Evaluate Accuracy, Completeness, Latency & Confidence
    ML-->>API: Topic Performance Profile (e.g., Python: 82%, SQL: 61%)

    API->>RAG: Query Student Notes for Weak Topics (SQL)
    RAG-->>API: Extracted Note Snippets & Suggested Study Materials
    API-->>UI: Render Visual Dashboard + Weakness Breakdown + Study Plan
    UI-->>Student: Display Study Plan & Prompt for Adaptive Retest
```

---

## Core Modules Breakdown

### Module 1: Document Intelligence
- **Responsibilities**:
  - Ingestion of heterogeneous files: PDF course packs, DOCX assignments, PPT/PPTX slide decks, markdown notes, text syllabi, and resumes.
  - Structure-aware chunking: Splits academic text based on headings, lecture slides, sections, and questions rather than arbitrary token boundaries.
  - Metadata enrichment: Tags chunks with source filename, section, course module, and document category (`syllabus`, `lecture_note`, `exam_paper`, `resume`).

### Module 2: RAG Assistant (Hybrid Retrieval + Reranking)
- **Hybrid Retrieval Architecture**:
  - **Lexical Search (BM25)**: Ensures exact keyword retrieval for technical acronyms, algorithms (e.g., "PCA", "Dijkstra", "Backpropagation"), and equation names.
  - **Dense Vector Search**: Powered by `Sentence-Transformers` (`all-MiniLM-L6-v2` or `bge-small-en-v1.5`) stored in ChromaDB/FAISS for semantic intent matching.
  - **Reciprocal Rank Fusion (RRF) / Cross-Encoder Reranker**: Re-orders candidate chunks to maximize precision before prompt injection.
- **Generation & LLM Support**:
  - Supports open-weight LLMs including **Mistral-7B-Instruct** and **Llama-3-8B-Instruct** running locally (Ollama / vLLM) or via the Hugging Face Inference API.
  - Orchestration handled by **LlamaIndex** / **LangChain**.

### Module 3: AI Interviewer & Industry Knowledge Base
- **Role Profiling**:
  - Parses uploaded resume and target Job Description (e.g., Machine Learning Engineer, Data Analyst, Software Engineer).
  - Performs skill-gap alignment mapping between candidate background and job prerequisites.
- **Shared Industry Question Bank**:
  - Integrates pre-curated and periodically scraped interview patterns from developer and career portals (AmbitionBox, GeeksforGeeks).
  - Categorizes queries into core disciplines: Programming Languages, Data Structures & Algorithms, Machine Learning Theory, System Design, and SQL/Databases.
  - Generates follow-up dynamic probes based on previous candidate answers.

### Module 4: ML-Based Skill Analysis & Adaptive Learning Loop
- **Predictive Scoring**:
  - Evaluates student response characteristics: semantic accuracy against reference knowledge, conceptual coverage, response time, and vocabulary confidence.
  - Supervised ML models (Random Forest, XGBoost) classify readiness levels and output granular topic-level percentages (e.g., Python: 82%, Deep Learning: 74%, SQL: 61%).
- **Adaptive Remediation Engine**:
  - Translates diagnosed weak areas into focused RAG queries against the student's personal notes and official course syllabus.
  - Assembles custom micro-study guides emphasizing the exact topics requiring revision.
  - Triggers automated retesting with targeted questions to verify concept mastery.

---

## Evaluation & Quality Assurance

To ensure the assistant provides reliable, factual, and hallucination-free guidance, the RAG and interview pipelines are evaluated using standard LLM evaluation frameworks:

| Metric Category | Metric Name | Target Benchmark | Measurement Tool |
| :--- | :--- | :--- | :--- |
| **Retrieval Quality** | Context Precision | $> 0.85$ | RAGAS |
| **Retrieval Quality** | Context Recall | $> 0.80$ | RAGAS |
| **Generation Quality**| Faithfulness (Groundedness) | $> 0.90$ (Zero hallucination) | RAGAS / TruLens |
| **Generation Quality**| Answer Relevance | $> 0.85$ | RAGAS |
| **ML Scoring** | Skill Prediction Accuracy | $\text{RMSE} < 0.12$ / $F_1 > 0.82$ | Scikit-Learn Metrics |

---

## Fault Tolerance & Reliability

The application implements enterprise-grade resilience mechanisms for long interview sessions and large document uploads:

- **State Checkpointing**: Interview sessions are serialized after each response. If network disconnection occurs, the user resumes from the exact question without losing score history.
- **Multi-Tier Fallbacks**:
  - *Vector Search Failure*: Degrades gracefully to BM25 keyword search if the vector index is unreachable.
  - *Inference API Failure*: Automatically switches between primary LLM provider (e.g., Hugging Face Inference API) and local fallback instances (e.g., local quantized Mistral/Llama via Ollama).
- **Graceful Degradation**: If document parsing encounters corrupted PDF pages or unreadable slides, the system isolates faulty pages, logs a warning, and indexes valid content without terminating the batch.
- **Hallucination Detection Guard**: Queries yielding low context similarity are rejected with explicit guidance rather than allowing the LLM to invent unsupported facts.

---

## Technology Stack

```
├── Backend API:            Python 3.10+, FastAPI / Flask
├── Frontend Application:   Streamlit / Gradio
├── Embeddings:             Sentence-Transformers (all-MiniLM-L6-v2 / BAAI/bge-small-en-v1.5)
├── Vector Storage:         FAISS / ChromaDB
├── Hybrid Search:          Rank-BM25 + Dense Cosine Similarity + Cross-Encoder Reranker
├── LLM Inference:          Mistral-7B-Instruct / Llama-3-8B-Instruct (Local / Hugging Face API)
├── Orchestration:          LlamaIndex / LangChain
├── Machine Learning:       Scikit-Learn (RandomForest, Logistic Regression), XGBoost
├── Evaluation:             RAGAS, TruLens
└── Deployment Target:      Hugging Face Spaces / Render (Free Tier) / Docker
```

---

## Project Repository Structure

```
Major_Project/
├── README.md                           # Master project documentation (this file)
├── requirements.txt                    # Python dependencies
├── .env.example                        # Template environment variables
├── data/
│   ├── raw_documents/                  # Uploaded user syllabi, notes, resumes
│   ├── processed_chunks/               # Serialized text chunks and metadata
│   ├── question_bank/                  # Scraped AmbitionBox & GFG interview question datasets
│   └── vector_store/                   # Persistent ChromaDB / FAISS index storage
├── src/
│   ├── __init__.py
│   ├── api/                            # FastAPI backend service
│   │   ├── __init__.py
│   │   ├── main.py                     # API router entry point
│   │   └── routes/
│   │       ├── upload.py               # Document ingestion endpoint
│   │       ├── ask.py                  # RAG Q&A endpoint
│   │       ├── interview.py            # Mock interview state machine
│   │       └── score.py                # ML scoring and recommendation endpoint
│   ├── document_intelligence/          # Module 1: Parsing & Chunking
│   │   ├── __init__.py
│   │   ├── parser.py                   # PDF, DOCX, PPTX extractors
│   │   └── chunker.py                  # Syllabus & slide-aware text splitters
│   ├── rag_assistant/                  # Module 2: Hybrid RAG Engine
│   │   ├── __init__.py
│   │   ├── embeddings.py               # Sentence-Transformers wrapper
│   │   ├── hybrid_retriever.py         # BM25 + Vector Search + Reranker
│   │   └── generator.py                # LLM prompt manager & responder
│   ├── interviewer/                    # Module 3: Interviewer & Question Bank
│   │   ├── __init__.py
│   │   ├── role_matcher.py             # Resume-to-JD skill extractor
│   │   ├── question_generator.py       # Dynamic query synthesizer
│   │   └── scraper_pipeline.py         # Question bank updater (GFG, AmbitionBox)
│   ├── ml_scoring/                     # Module 4: Performance & Diagnostics
│   │   ├── __init__.py
│   │   ├── feature_extractor.py        # Latency, accuracy, confidence metrics
│   │   ├── model.py                    # Random Forest / XGBoost classifiers
│   │   └── recommendation_engine.py    # Notes mapping & re-test question selector
│   └── utils/
│       ├── checkpoint.py               # Session saving & fault tolerance
│       └── logger.py                   # Structured error logging
├── evaluation/                         # Benchmarking & Validation
│   ├── eval_ragas.py                   # RAGAS metrics execution
│   └── eval_trulens.py                 # Groundedness & hallucination test suites
├── tests/                              # Unit and integration test suites
│   ├── test_parser.py
│   ├── test_rag.py
│   └── test_scoring.py
└── ui/                                 # Streamlit frontend presentation
    ├── app.py                          # Streamlit navigation entry point
    ├── views/
    │   ├── upload_view.py              # File upload interface
    │   ├── chat_view.py                # RAG Study Q&A interface
    │   ├── interview_view.py           # Mock interview interactive session
    │   └── dashboard_view.py           # Skill analytics & study plan view
```

---

## API Specification (Draft)

### 1. Document Ingestion
- **Route**: `POST /api/v1/upload`
- **Payload**: `multipart/form-data` (`file`, `doc_type`: `syllabus|notes|resume|exam`)
- **Response**:
```json
{
  "status": "success",
  "document_id": "doc_8f9a2b",
  "filename": "Machine_Learning_Syllabus.pdf",
  "chunks_indexed": 42,
  "vector_collection": "user_personal_docs"
}
```

### 2. Academic Q&A (RAG Assistant)
- **Route**: `POST /api/v1/ask`
- **Payload**:
```json
{
  "query": "Explain Principal Component Analysis and its assumptions.",
  "collection_filter": "syllabus",
  "top_k": 3
}
```
- **Response**:
```json
{
  "answer": "Principal Component Analysis (PCA) is an unsupervised dimensionality reduction technique...",
  "sources": [
    {
      "document": "Unit_3_Unsupervised_Learning.pdf",
      "page": 14,
      "relevance_score": 0.93
    }
  ]
}
```

### 3. Interview Session Initializer
- **Route**: `POST /api/v1/interview/start`
- **Payload**:
```json
{
  "target_role": "Machine Learning Engineer",
  "resume_id": "doc_resume_nakul",
  "experience_level": "Junior / Entry-Level"
}
```
- **Response**:
```json
{
  "session_id": "sess_91238a",
  "matched_skills": ["Python", "Machine Learning", "Deep Learning", "SQL", "RAG"],
  "first_question": {
    "question_id": "q_101",
    "topic": "Machine Learning",
    "prompt": "How does Ridge regression differ from Lasso regression in feature selection?"
  }
}
```

### 4. Answer Evaluation & Skill Analysis
- **Route**: `POST /api/v1/score`
- **Payload**:
```json
{
  "session_id": "sess_91238a",
  "question_id": "q_101",
  "user_answer": "Lasso uses L1 penalty which zeroes out weights, while Ridge uses L2 penalty.",
  "response_time_seconds": 24.5
}
```
- **Response**:
```json
{
  "score": 0.85,
  "topic_breakdown": {
    "Python": 82.0,
    "Machine Learning": 74.0,
    "SQL": 61.0
  },
  "detected_weaknesses": ["SQL Subqueries and Window Functions"],
  "recommended_materials": [
    {
      "source_doc": "DBMS_Lecture_Notes_Unit4.pdf",
      "recommended_sections": ["Window Functions: RANK and DENSE_RANK"]
    }
  ]
}
```

---

## Local Setup & Installation

### Prerequisites
- Python **3.10** or higher
- Git
- Virtual environment manager (`venv` or `conda`)
- Optional: CUDA-compatible GPU for accelerated local embeddings/LLM inference

### Step-by-Step Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/Major_Project.git
   cd Major_Project
   ```

2. **Create and Activate a Virtual Environment**:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Environment Variables Configuration (`.env`)
Create a `.env` file in the root directory:
```ini
# Core Configuration
ENVIRONMENT=development
DEBUG=True
LOG_LEVEL=INFO

# Model & LLM Settings
LLM_PROVIDER=huggingface          # Options: 'huggingface', 'ollama', 'openai'
HF_API_TOKEN=your_huggingface_token_here
PRIMARY_LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.2
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Storage & Vector DB Paths
VECTOR_DB_TYPE=chromadb           # Options: 'chromadb', 'faiss'
CHROMA_PERSIST_DIR=./data/vector_store/chroma
SQLITE_DB_PATH=./data/copilot_app.db

# Evaluation Settings
ENABLE_RAGAS_EVAL=True
```

### Running the Applications

1. **Start the FastAPI Backend Service**:
   ```bash
   uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *Swagger API Documentation will be accessible at: `http://127.0.0.1:8000/docs`*

2. **Start the Streamlit User Interface**:
   ```bash
   streamlit run ui/app.py
   ```
   *Frontend UI will open automatically at: `http://localhost:8501`*

---

## Project Roadmap & Milestones

| Timeline | Phase | Deliverables / Status |
| :--- | :--- | :--- |
| **Week 1** *(8 Sep 2026)* | **System Architecture & Data Modeling** | • Finalize 4-module split (Doc Intelligence, RAG, Interviewer, ML).<br>• Map complete user journey.<br>• Finalize hybrid storage design (Personal docs + shared question bank).<br>• Define technology stack. ✅ **Completed** |
| **Week 2** | **Data Collection & Repository Scaffold** | • Gather sample syllabi, question papers, lecture notes, resumes.<br>• Harvest initial batch of role-skill pairs & questions from GFG/AmbitionBox.<br>• Scaffold repository directories, database schemas, and baseline dependencies. 🔄 **In Progress** |
| **Week 3 - 4** | **Document Intelligence & Hybrid RAG Engine** | • Implement multi-format document parser (`.pdf`, `.docx`, `.pptx`).<br>• Configure BM25 + ChromaDB/FAISS hybrid retriever with reranking.<br>• Integrate Mistral-7B / Llama 3 via LangChain/LlamaIndex. |
| **Week 5 - 6** | **AI Interviewer & Shared Question Bank** | • Implement resume & Job Description skill extraction parser.<br>• Build interactive mock interview state machine.<br>• Implement session checkpointing and fallback mechanisms. |
| **Week 7 - 8** | **ML Skill Diagnostics & Adaptive Feedback Loop** | • Train Scikit-Learn / XGBoost models on simulated candidate response metrics.<br>• Build the note-recommendation engine linking weak topics to uploaded course packs.<br>• Develop automated retesting question generator. |
| **Week 9 - 10** | **UI Assembly, Evaluation & Deployment** | • Build Streamlit multi-tab interface (Upload, Chat, Interview, Analytics Dashboard).<br>• Run RAGAS and TruLens benchmarks (Context precision, Recall, Faithfulness).<br>• Package Docker container and deploy to Hugging Face Spaces / Render. |

---

## Academic References

1. **Lewis, P. et al. (2020)**. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. Advances in Neural Information Processing Systems (NeurIPS). [arXiv:2005.11401](https://arxiv.org/abs/2005.11401)
2. **Reimers, N., & Gurevych, I. (2019)**. *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. In Proceedings of EMNLP-IJCNLP. [arXiv:1908.10084](https://arxiv.org/abs/1908.10084)
3. **Meta AI (2024)**. *Llama 3 Model Card and Architecture*. [Meta Llama 3](https://huggingface.co/meta-llama)
4. **Mistral AI (2023)**. *Mistral 7B*. [Mistral-7B Release](https://huggingface.co/mistralai)
5. **Johnson, J., Douze, M., & Jégou, H. (2021)**. *Billion-Scale Similarity Search with GPUs (FAISS)*. IEEE Transactions on Big Data. [FAISS Repository](https://github.com/facebookresearch/faiss)
6. **Chroma Core Team (2023)**. *Chroma: The AI-native Open-Source Embedding Database*. [ChromaDB](https://github.com/chroma-core/chroma)
7. **Es, S. et al. (2023)**. *RAGAS: Automated Evaluation of Retrieval Augmented Generation*. [RAGAS Repository](https://github.com/explodinggradients/ragas)
