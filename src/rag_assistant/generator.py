"""
LLM Response Generator
=======================
Module 2 - RAG Assistant (Part 3)

Constructs grounded prompts from retrieved context chunks and generates
answers via Groq / Hugging Face Serverless Inference API.

Supports automatic fallback between primary and backup models.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# LLM Provider & Credentials
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

# Hugging Face Settings (Secondary Fallback)
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
PRIMARY_MODEL = os.getenv("PRIMARY_LLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
FALLBACK_MODEL = os.getenv("FALLBACK_LLM_MODEL", "HuggingFaceH4/zephyr-7b-beta")

# System prompt for grounded academic Q&A
ACADEMIC_SYSTEM_PROMPT = """You are an expert academic tutor and study assistant. Your role is to help students understand their course material deeply and accurately.

RULES:
1. Answer ONLY based on the provided context from the student's own notes and course materials.
2. If the context does not contain enough information to fully answer the question, clearly state what you can answer and what is missing.
3. Always cite which source document and section your answer comes from.
4. Use clear, educational language suitable for engineering students.
5. When explaining concepts, provide examples where possible.
6. NEVER fabricate information that is not supported by the provided context."""


def _get_client(model_id: Optional[str] = None) -> InferenceClient:
    """Create a Hugging Face InferenceClient for the specified model."""
    return InferenceClient(
        model=model_id or PRIMARY_MODEL,
        token=HF_API_TOKEN if HF_API_TOKEN else None,
    )


def generate_answer(
    query: str,
    context_chunks: list[dict],
    system_prompt: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict:
    """
    Generate a grounded answer using retrieved context and the HF Inference API.

    Args:
        query: The user's question.
        context_chunks: List of retrieved chunks (each has 'text', 'metadata', 'score').
        system_prompt: Custom system prompt. Defaults to academic tutor prompt.
        max_tokens: Maximum tokens in the generated response.
        temperature: Sampling temperature (lower = more deterministic).

    Returns:
        Dictionary with keys: 'answer', 'sources', 'model_used'.
    """
    if not system_prompt:
        system_prompt = ACADEMIC_SYSTEM_PROMPT

    # Build context block from retrieved chunks
    context_block = _build_context_block(context_chunks)

    # Construct the user message with context injection
    user_message = f"""CONTEXT FROM STUDENT'S COURSE MATERIALS:
---
{context_block}
---

STUDENT'S QUESTION: {query}

Please provide a thorough, accurate answer based ONLY on the context above. Cite the source documents."""

    # Build messages for chat completion
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Try primary model, fall back to backup
    answer_text, model_used = _call_llm(messages, max_tokens, temperature)

    # Extract source citations from context
    sources = _extract_sources(context_chunks)

    return {
        "answer": answer_text,
        "sources": sources,
        "model_used": model_used,
    }


def _build_context_block(chunks: list[dict]) -> str:
    """Format retrieved chunks into a structured context block."""
    if not chunks:
        return "No relevant context found in the student's materials."

    blocks = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("metadata", {}).get("source_file", "Unknown")
        section = chunk.get("metadata", {}).get("section", "")
        page = chunk.get("metadata", {}).get("page", "")
        score = chunk.get("score", 0)

        header = f"[Source {i}: {source}"
        if section:
            header += f" | Section: {section}"
        if page:
            header += f" | Page: {page}"
        header += f" | Relevance: {score:.2f}]"

        blocks.append(f"{header}\n{chunk['text']}")

    return "\n\n".join(blocks)


def _extract_sources(chunks: list[dict]) -> list[dict]:
    """Extract source citations from retrieved chunks."""
    sources = []
    seen = set()

    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source_file = meta.get("source_file", "Unknown")
        if source_file not in seen:
            seen.add(source_file)
            sources.append(
                {
                    "document": source_file,
                    "page": meta.get("page", None),
                    "section": meta.get("section", None),
                    "relevance_score": chunk.get("score", 0),
                }
            )

    return sources


def _call_llm(
    messages: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> tuple[str, str]:
    """
    Call the LLM with automatic multi-tier fallback (Groq -> HF -> graceful message).

    Returns:
        Tuple of (response_text, model_id_used).
    """
    # 1. Try Groq if configured
    if (LLM_PROVIDER == "groq" or GROQ_API_KEY) and GROQ_API_KEY.strip():
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY.strip())
            groq_models = [GROQ_PRIMARY_MODEL, GROQ_FALLBACK_MODEL, "qwen/qwen3.8-27b"]
            for model_id in groq_models:
                try:
                    response = client.chat.completions.create(
                        messages=messages,
                        model=model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    answer = response.choices[0].message.content
                    logger.info(f"LLM response generated using Groq model {model_id}")
                    return answer, f"groq:{model_id}"
                except Exception as e:
                    logger.warning(f"Groq model call failed for {model_id}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Groq initialization/execution failed: {e}")

    # 2. Try Hugging Face fallback
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    for model_id in models_to_try:
        try:
            client = _get_client(model_id)
            response = client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            answer = response.choices[0].message.content
            logger.info(f"LLM response generated using Hugging Face model {model_id}")
            return answer, f"hf:{model_id}"

        except Exception as e:
            logger.warning(f"Hugging Face call failed for {model_id}: {e}")
            continue

    # If all models fail, return a graceful error message
    logger.error("All LLM models failed. Returning fallback message.")
    return (
        "I'm unable to generate a response at the moment due to API limitations. "
        "Please try again in a few moments, or check your GROQ_API_KEY/HF_API_TOKEN in the .env file.",
        "none",
    )

