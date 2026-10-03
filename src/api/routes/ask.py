"""
RAG Q&A Route
==============
POST /api/v1/ask — Queries admin-uploaded course materials using hybrid RAG.
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from src.auth.session_manager import validate_session
from src.rag_assistant.hybrid_retriever import HybridRetriever
from src.rag_assistant.generator import generate_answer
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# All Q&A queries go against admin-uploaded materials
ADMIN_COLLECTION = "admin_course_materials"


class AskRequest(BaseModel):
    query: str = Field(..., description="The academic question to answer")
    top_k: int = Field(5, description="Number of context chunks to retrieve", ge=1, le=20)


class SourceInfo(BaseModel):
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    relevance_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    model_used: str
    chunks_retrieved: int


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    x_session_token: Optional[str] = Header(None),
):
    """
    Ask a question against admin-uploaded course materials.

    Uses hybrid BM25 + dense vector retrieval to find relevant context,
    then generates a grounded answer using the LLM.
    """
    # Auth check
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = validate_session(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Initialize retriever for admin materials collection
    try:
        retriever = HybridRetriever(collection_name=ADMIN_COLLECTION)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize retriever: {str(e)}",
        )

    # Check if any documents are indexed
    if retriever.get_document_count() == 0:
        raise HTTPException(
            status_code=404,
            detail="No course materials available. Please ask your administrator to upload textbooks and lecture notes.",
        )

    # Perform hybrid search
    try:
        results = retriever.search(query=request.query, top_k=request.top_k)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )

    if not results:
        return AskResponse(
            answer="I couldn't find any relevant information in the course materials for this question. Please try rephrasing or ask your instructor to upload additional materials.",
            sources=[],
            model_used="none",
            chunks_retrieved=0,
        )

    # Generate grounded answer
    try:
        response = generate_answer(
            query=request.query,
            context_chunks=results,
        )
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # Fallback: return raw context chunks
        fallback_text = "\n\n".join(
            f"From {r['metadata'].get('source_file', 'Unknown')}: {r['text'][:300]}..."
            for r in results[:3]
        )
        return AskResponse(
            answer=f"LLM is temporarily unavailable. Here are the most relevant passages:\n\n{fallback_text}",
            sources=[
                SourceInfo(
                    document=r["metadata"].get("source_file", "Unknown"),
                    page=r["metadata"].get("page"),
                    section=r["metadata"].get("section"),
                    relevance_score=r.get("score", 0),
                )
                for r in results
            ],
            model_used="fallback",
            chunks_retrieved=len(results),
        )

    return AskResponse(
        answer=response["answer"],
        sources=[
            SourceInfo(
                document=s["document"],
                page=s.get("page"),
                section=s.get("section"),
                relevance_score=s.get("relevance_score", 0),
            )
            for s in response["sources"]
        ],
        model_used=response["model_used"],
        chunks_retrieved=len(results),
    )
