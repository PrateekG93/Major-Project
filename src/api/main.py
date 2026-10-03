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

    # Seed the question bank if it doesn't exist
    try:
        from src.interviewer.scraper_pipeline import seed_question_bank
        question_bank_path = os.getenv("QUESTION_BANK_PATH", "./data/question_bank/questions.json")
        if not os.path.exists(question_bank_path):
            seed_question_bank()
            logger.info("Question bank seeded successfully")
    except Exception as e:
        logger.warning(f"Could not seed question bank: {e}")

    # Pre-train ML model if not already trained
    try:
        from src.ml_scoring.model import train_model
        model_path = os.getenv("SCORING_MODEL_PATH", "./models/scoring_model.joblib")
        if not os.path.exists(model_path):
            metrics = train_model()
            logger.info(f"ML model trained: {metrics}")
    except Exception as e:
        logger.warning(f"Could not pre-train ML model: {e}")

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
from src.api.routes import auth, admin, upload, ask, interview, score, mcq_interview

app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin Portal"])
app.include_router(upload.router, prefix="/api/v1", tags=["Document Upload"])
app.include_router(ask.router, prefix="/api/v1", tags=["RAG Q&A"])
app.include_router(interview.router, prefix="/api/v1", tags=["Mock Interview (Open-Ended)"])
app.include_router(mcq_interview.router, prefix="/api/v1", tags=["Mock Interview (MCQ)"])
app.include_router(score.router, prefix="/api/v1", tags=["Scoring & Recommendations"])


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

    # Check ML model
    model_path = os.getenv("SCORING_MODEL_PATH", "./models/scoring_model.joblib")
    components["ml_model"] = "healthy" if os.path.exists(model_path) else "not_trained"

    # Check question bank
    qb_path = os.getenv("QUESTION_BANK_PATH", "./data/question_bank/questions.json")
    components["question_bank"] = "healthy" if os.path.exists(qb_path) else "not_seeded"

    # Check HF token
    hf_token = os.getenv("HF_API_TOKEN", "")
    components["llm_api"] = "configured" if hf_token and hf_token != "hf_your_free_token_here" else "not_configured"

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
