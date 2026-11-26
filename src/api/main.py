"""
FastAPI Application Entry Point
=================================
Main application factory with CORS, lifespan events, and route mounting.
Initializes core services (vector store, ML model) on startup.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs initialization on startup and cleanup on shutdown.
    """
    # --- Startup ---
    logger.info("🚀 Starting Intelligent Academic & Career Copilot API...")

    # Initialize database tables
    try:
        from src.utils.checkpoint import _get_connection
        conn = _get_connection()
        conn.close()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.warning(f"Database init warning: {e}")

    # Seed the question bank if it doesn't exist in DB or JSON
    try:
        from src.interviewer.scraper_pipeline import seed_question_bank
        from src.interviewer.ingestion import get_canonical_question_count
        question_bank_path = os.getenv("QUESTION_BANK_PATH", "./data/question_bank/questions.json")
        if get_canonical_question_count() == 0 or not os.path.exists(question_bank_path):
            seed_question_bank()
            logger.info("Question bank seeded successfully into DB and JSON")
    except Exception as e:
        logger.warning(f"Could not seed question bank: {e}")

    # Maintenance cleanup: expired OTPs and retained audio recordings
    try:
        from src.auth.otp_manager import cleanup_expired_otps
        from src.interviewer.audio_service import cleanup_expired_audio
        cleanup_expired_otps()
        cleanup_expired_audio()
    except Exception as e:
        logger.warning(f"Startup cleanup warning: {e}")

    logger.info("✅ API startup complete")

    yield  # Application runs here

    # --- Shutdown ---
    logger.info("🛑 Shutting down API...")


# Create FastAPI application
app = FastAPI(
    title="Intelligent Academic & Career Copilot",
    description=(
        "An end-to-end academic and career acceleration platform combining "
        "Retrieval-Augmented Generation (RAG) and Supervised Machine Learning. "
        "Upload course materials, ask questions, take MCQ mock interviews, and "
        "receive adaptive study recommendations with ATS resume analysis."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount route modules
from src.api.routes import (
    admin,
    ask,
    audio_interview,
    auth,
    mcq_interview,
    questions,
    score,
    scraping,
    upload,
)

app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin Portal"])
app.include_router(upload.router, prefix="/api/v1", tags=["Document Upload"])
app.include_router(ask.router, prefix="/api/v1", tags=["RAG Q&A"])
app.include_router(mcq_interview.router, prefix="/api/v1", tags=["Mock Interview (MCQ)"])
app.include_router(audio_interview.router, prefix="/api/v1", tags=["AI Audio Interview"])
app.include_router(questions.router, prefix="/api/v1", tags=["Centralized Question Bank"])
app.include_router(scraping.router, prefix="/api/v1", tags=["Dynamic Question Bank & Scraping"])
app.include_router(score.router, prefix="/api/v1", tags=["ATS Scoring & Analytics"])


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "Intelligent Academic & Career Copilot",
        "status": "running",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check with component status."""
    components = {}

    # Check vector store
    try:
        from src.rag_assistant.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever("health_check")
        components["vector_store"] = "healthy"
    except Exception as e:
        components["vector_store"] = f"unhealthy: {str(e)}"

    # Check question bank
    qb_path = os.getenv("QUESTION_BANK_PATH", "./data/question_bank/questions.json")
    components["question_bank"] = "healthy" if os.path.exists(qb_path) else "not_seeded"

    # Check LLM API configuration
    groq_key = os.getenv("GROQ_API_KEY", "")
    hf_token = os.getenv("HF_API_TOKEN", "")
    components["llm_api"] = (
        "configured"
        if (groq_key and groq_key != "your_groq_api_key_here")
        or (hf_token and hf_token != "hf_your_free_token_here")
        else "not_configured"
    )

    # Check database
    try:
        from src.utils.checkpoint import _get_connection
        conn = _get_connection()
        conn.close()
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"

    overall = "healthy" if all(
        v in ("healthy", "configured") for v in components.values()
    ) else "degraded"

    return {
        "status": overall,
        "components": components,
    }
