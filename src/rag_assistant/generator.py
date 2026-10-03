"""
LLM Response Generator
=======================
Module 2 - RAG Assistant (Part 3)

Constructs grounded prompts from retrieved context chunks and generates
answers via the Hugging Face Serverless Inference API (free tier).

Supports automatic fallback between primary and backup models.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

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

# System prompt for interview evaluation
INTERVIEW_SYSTEM_PROMPT = """You are a senior technical interviewer conducting a mock interview. Your role is to:
1. Ask clear, well-structured technical questions appropriate for the candidate's target role.
2. Evaluate answers fairly based on accuracy, completeness, and depth.
3. Provide constructive feedback that helps the candidate improve.
4. Adapt your follow-up questions based on the candidate's performance."""


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


def generate_interview_question(
    role: str,
    skills: list[str],
    previous_qa: list[dict] = None,
    difficulty: str = "medium",
) -> str:
    """
    Generate a dynamic follow-up interview question using the LLM.

    Args:
        role: Target job role (e.g., "Machine Learning Engineer").
        skills: List of skill topics to focus on.
        previous_qa: List of previous Q&A pairs for context.
        difficulty: Difficulty level ('easy', 'medium', 'hard').

    Returns:
        A question string.
    """
    prev_context = ""
    if previous_qa:
        prev_context = "\n".join(
            f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}"
            for qa in previous_qa[-3:]  # Last 3 Q&A pairs for context
        )

    prompt = f"""Generate a single technical interview question for a {role} position.

Skills to assess: {', '.join(skills)}
Difficulty: {difficulty}
{f'Previous Q&A context:{chr(10)}{prev_context}' if prev_context else ''}

Requirements:
- The question should be specific and testable
- It should assess practical understanding, not just memorization
- Output ONLY the question text, nothing else"""

    messages = [
        {"role": "system", "content": INTERVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    answer, _ = _call_llm(messages, max_tokens=256, temperature=0.7)
    return answer.strip()


def evaluate_answer_with_llm(
    question: str,
    user_answer: str,
    reference_answer: Optional[str] = None,
    topic: str = "",
) -> dict:
    """
    Use the LLM to evaluate a candidate's answer quality.

    Returns:
        Dictionary with 'score' (0-1), 'feedback', 'strengths', 'weaknesses'.
    """
    ref_block = f"\nREFERENCE ANSWER: {reference_answer}" if reference_answer else ""

    prompt = f"""Evaluate the following interview answer.

TOPIC: {topic}
QUESTION: {question}
CANDIDATE'S ANSWER: {user_answer}{ref_block}

Provide your evaluation in EXACTLY this format:
SCORE: [a number between 0.0 and 1.0]
FEEDBACK: [2-3 sentences of constructive feedback]
STRENGTHS: [key strengths in the answer]
WEAKNESSES: [areas for improvement]"""

    messages = [
        {"role": "system", "content": "You are an expert technical evaluator. Be fair but rigorous."},
        {"role": "user", "content": prompt},
    ]

    response, _ = _call_llm(messages, max_tokens=512, temperature=0.2)
    return _parse_evaluation(response)


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
    Call the LLM with automatic fallback.

    Returns:
        Tuple of (response_text, model_id_used).
    """
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
            logger.info(f"LLM response generated using {model_id}")
            return answer, model_id

        except Exception as e:
            logger.warning(f"LLM call failed for {model_id}: {e}")
            continue

    # If all models fail, return a graceful error message
    logger.error("All LLM models failed. Returning fallback message.")
    return (
        "I'm unable to generate a response at the moment due to API limitations. "
        "Please try again in a few moments, or check your HF_API_TOKEN in the .env file.",
        "none",
    )


def _parse_evaluation(response: str) -> dict:
    """Parse the structured evaluation response from the LLM."""
    result = {
        "score": 0.5,
        "feedback": "",
        "strengths": "",
        "weaknesses": "",
    }

    lines = response.strip().split("\n")
    for line in lines:
        line_clean = line.strip()
        if line_clean.upper().startswith("SCORE:"):
            try:
                score_str = line_clean.split(":", 1)[1].strip()
                # Handle scores like "0.85" or "85%"
                score = float(score_str.replace("%", "").strip())
                if score > 1:
                    score = score / 100.0
                result["score"] = max(0.0, min(1.0, score))
            except (ValueError, IndexError):
                pass
        elif line_clean.upper().startswith("FEEDBACK:"):
            result["feedback"] = line_clean.split(":", 1)[1].strip()
        elif line_clean.upper().startswith("STRENGTHS:"):
            result["strengths"] = line_clean.split(":", 1)[1].strip()
        elif line_clean.upper().startswith("WEAKNESSES:"):
            result["weaknesses"] = line_clean.split(":", 1)[1].strip()

    return result
