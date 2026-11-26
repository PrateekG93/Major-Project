"""
Adaptive Conversational AI Audio Interview Orchestrator
=======================================================
Stateful, dynamic interview engine combining:
- Integrated Question Bank retrieval (topic & round aware)
- Groq LLM evaluation with BeFluent-style Pydantic validation & JSON repair
- Adaptive next-action orchestration: FOLLOW_UP | NEXT_QUESTION | END_INTERVIEW
- Knowledge gap tracking, duplicate follow-up prevention, difficulty adaptation
- Comprehensive final performance report with RAG remediation links
"""

import json
import os
import time
import uuid
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from src.interviewer.ingestion import normalize_text
from src.interviewer.question_bank_service import retrieve_questions_by_topic, search_questions
from src.interviewer.role_matcher import get_interview_topics
from src.utils.checkpoint import _get_connection
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

MAX_FOLLOWUPS_PER_QUESTION = 2

INTERVIEW_ROUNDS = ("Technical", "HR / Behavioral", "System Design", "Managerial")


def normalize_interview_round(round_val: Optional[str]) -> str:
    """Normalize any round alias into one of the four canonical Interview Round options."""
    key = (round_val or "").strip().lower().replace("_", " ").replace("-", " ")
    if any(tok in key for tok in ("hr", "behavioral", "behavioural")):
        return "HR / Behavioral"
    if "system" in key and "design" in key:
        return "System Design"
    if "manager" in key:
        return "Managerial"
    return "Technical"


DEFAULT_SCORING_WEIGHTS: dict[str, dict[str, int]] = {
    "Technical": {
        "technical_correctness": 30,
        "conceptual_understanding": 20,
        "relevance": 15,
        "completeness": 15,
        "clarity": 10,
        "communication": 10,
    },
    "HR / Behavioral": {
        "technical_correctness": 10,
        "conceptual_understanding": 15,
        "relevance": 25,
        "completeness": 15,
        "clarity": 15,
        "communication": 20,
    },
    "System Design": {
        "technical_correctness": 25,
        "conceptual_understanding": 25,
        "relevance": 15,
        "completeness": 15,
        "clarity": 10,
        "communication": 10,
    },
    "Managerial": {
        "technical_correctness": 10,
        "conceptual_understanding": 20,
        "relevance": 20,
        "completeness": 15,
        "clarity": 15,
        "communication": 20,
    },
}


# ============================================================
# Structured LLM Output Schemas (Pydantic Validated)
# ============================================================

class EvaluationScores(BaseModel):
    score: float = Field(ge=0, le=100)
    technical_correctness: float = Field(ge=0, le=100)
    conceptual_understanding: float = Field(ge=0, le=100)
    relevance: float = Field(ge=0, le=100)
    completeness: float = Field(ge=0, le=100)
    clarity: float = Field(ge=0, le=100)
    communication: float = Field(ge=0, le=100)


class AdaptiveTurnLLMOutput(BaseModel):
    evaluation: EvaluationScores
    answer_category: Literal[
        "excellent", "good", "incomplete", "incorrect", "irrelevant", "too_short"
    ] = "incomplete"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    correct_concepts: list[str] = Field(default_factory=list)
    incorrect_concepts: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    feedback: str = ""
    communication_feedback: str = ""
    next_action: Literal["FOLLOW_UP", "NEXT_QUESTION", "END_INTERVIEW"] = "NEXT_QUESTION"
    next_question: str = ""
    reason_for_next_question: str = ""
    recommended_difficulty: Literal["easy", "medium", "hard"] = "medium"


def get_weights_for_round(
    interview_round: str, custom_weights: Optional[dict[str, int]] = None
) -> dict[str, int]:
    """Return scoring rubric weights summing to 100 for the given Interview Round."""
    canon_round = normalize_interview_round(interview_round)
    base = dict(DEFAULT_SCORING_WEIGHTS.get(canon_round, DEFAULT_SCORING_WEIGHTS["Technical"]))
    if custom_weights:
        for k in base:
            if k in custom_weights and isinstance(custom_weights[k], (int, float)) and custom_weights[k] >= 0:
                base[k] = int(custom_weights[k])
        total = sum(base.values())
        if total > 0 and total != 100:
            # Normalize to sum to 100
            scaled = {k: round(v * 100 / total) for k, v in base.items()}
            diff = 100 - sum(scaled.values())
            first_key = next(iter(scaled))
            scaled[first_key] += diff
            return scaled
    return base


def _extract_json_block(raw_text: str) -> dict:
    """Extract JSON from LLM response, stripping markdown code fences cleanly."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _call_groq_chat(messages: list[dict], temperature: float = 0.25, max_tokens: int = 1200) -> tuple[str, str]:
    """Call Groq LLM with automatic model fallback, reusing project config."""
    load_dotenv(override=False)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    primary = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    fallback = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
    models = []
    for m in [primary, fallback, "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
        if m and m not in models:
            models.append(m)

    if api_key and api_key != "your_groq_api_key_here":
        from groq import Groq
        client = Groq(api_key=api_key)
        for model_id in models:
            try:
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or ""
                if content.strip():
                    return content, f"groq:{model_id}"
            except Exception as e:
                logger.warning(f"Audio interviewer Groq call failed ({model_id}): {e}")

    # Fall back to project's HF generator if Groq failed
    from src.rag_assistant.generator import _call_llm
    return _call_llm(messages, max_tokens=max_tokens, temperature=temperature)


def _build_main_questions(
    company: str,
    job_role: str,
    interview_round: str,
    difficulty: str,
    max_questions: int,
    resume_text: str = "",
    jd_text: str = "",
    initial_question: str = "",
    initial_topic: str = "",
) -> list[dict]:
    """
    Build initial main question pool from integrated Question Bank,
    supplemented with LLM generation when needed.
    """
    canon_round = normalize_interview_round(interview_round)
    questions: list[dict] = []
    seen_norm: set[str] = set()

    if initial_question and initial_question.strip():
        qn = normalize_text(initial_question)
        seen_norm.add(qn)
        questions.append({
            "question_text": initial_question.strip(),
            "topic": initial_topic or "Core Engineering",
            "difficulty": difficulty,
            "reference_answer": "",
            "source": "question_bank_selected",
        })

    # Determine topics from resume/JD or role + Interview Round
    topics = (
        get_interview_topics(resume_text, jd_text, job_role)
        if (resume_text or job_role)
        else ["Python", "Data Structures & Algorithms", "SQL", "System Design"]
    )
    if canon_round == "HR / Behavioral":
        topics = ["HR Questions", "Behavioral Questions", "Communication"] + topics[:2]
    elif canon_round == "System Design":
        topics = ["System Design", "DBMS", "Computer Networks"] + topics[:2]
    elif canon_round == "Managerial":
        topics = ["Behavioral Questions", "System Design", "Software Engineering", "Communication"]

    # Query integrated Question Bank via search_questions
    is_tech_filter = None
    round_filter = ""
    if canon_round == "HR / Behavioral":
        is_tech_filter = False
    elif canon_round == "Technical":
        is_tech_filter = True
    elif canon_round == "System Design":
        is_tech_filter = True

    if canon_round == "System Design":
        sd_res = search_questions(topic="System Design", is_technical=True, page=1, page_size=max_questions * 2)
        for item in sd_res.get("items", []):
            qn = normalize_text(item["question_text"])
            if qn not in seen_norm:
                seen_norm.add(qn)
                questions.append({
                    "question_text": item["question_text"],
                    "topic": item["topic"],
                    "difficulty": item["difficulty"],
                    "reference_answer": item.get("reference_answer", ""),
                    "source": "question_bank",
                })

    if len(questions) < max_questions:
        q_type = "hr" if canon_round in ("HR / Behavioral", "Managerial") else "open_ended"
        retrieved = retrieve_questions_by_topic(
            topics=topics,
            num_questions=max_questions * 2,
            question_type=q_type,
        )
        for item in retrieved:
            qn = normalize_text(item["question_text"])
            if qn not in seen_norm:
                seen_norm.add(qn)
                questions.append({
                    "question_text": item["question_text"],
                    "topic": item.get("topic", "General"),
                    "difficulty": item.get("difficulty", difficulty),
                    "reference_answer": item.get("reference_answer", ""),
                    "source": "question_bank",
                })

    # General bank fallback if still short
    if len(questions) < max_questions:
        general_res = search_questions(
            interview_round=round_filter,
            is_technical=is_tech_filter,
            page=1,
            page_size=max_questions * 2,
        )
        for item in general_res.get("items", []):
            qn = normalize_text(item["question_text"])
            if qn not in seen_norm:
                seen_norm.add(qn)
                questions.append({
                    "question_text": item["question_text"],
                    "topic": item["topic"],
                    "difficulty": item["difficulty"],
                    "reference_answer": item.get("reference_answer", ""),
                    "source": "question_bank",
                })

    # Generate additional tailored questions via LLM if still fewer than max_questions
    if len(questions) < max_questions:
        needed = max_questions - len(questions)
        try:
            prompt = (
                f"Generate {needed} distinct {difficulty} {canon_round} interview questions "
                f"for a {job_role} candidate"
                f"{f' applying to {company}' if company else ''}. "
                f"Respond ONLY with a JSON array of objects: "
                f'[{{"question_text": "...", "topic": "...", "difficulty": "{difficulty}", "reference_answer": "..."}}]'
            )
            raw, _ = _call_groq_chat(
                [{"role": "user", "content": prompt}], temperature=0.5, max_tokens=900
            )
            arr_start, arr_end = raw.find("["), raw.rfind("]") + 1
            if arr_start != -1 and arr_end > arr_start:
                gen_list = json.loads(raw[arr_start:arr_end])
                for g in gen_list:
                    qt = g.get("question_text", "").strip()
                    if qt and normalize_text(qt) not in seen_norm:
                        seen_norm.add(normalize_text(qt))
                        questions.append({
                            "question_text": qt,
                            "topic": g.get("topic", job_role),
                            "difficulty": g.get("difficulty", difficulty),
                            "reference_answer": g.get("reference_answer", ""),
                            "source": "llm_generated",
                        })
        except Exception as e:
            logger.warning(f"Supplementary question generation skipped: {e}")

    return questions[:max_questions]


def _evaluate_and_decide_next(
    session_meta: dict,
    current_question: dict,
    transcript: str,
    history_turns: list[dict],
    weights: dict[str, int],
    followups_on_current: int,
    main_questions_asked: int,
    max_questions: int,
    elapsed_minutes: float,
    max_duration_minutes: int,
    asked_questions_norm: set[str],
    next_main_candidate: Optional[dict],
) -> tuple[AdaptiveTurnLLMOutput, str]:
    """
    Call Groq LLM with BeFluent-style Pydantic validation & retry loop
    to evaluate the spoken transcript and dynamically decide FOLLOW_UP / NEXT_QUESTION / END_INTERVIEW.
    """
    recent_history = "\n".join(
        f"Turn {t['turn_index'] + 1} ({'Follow-up' if t['is_followup'] else 'Main'}): "
        f"Q: {t['question_text']}\nCandidate: {t['transcript'][:300]}\nScore: {t['score']}/100"
        for t in history_turns[-4:]
    )

    can_followup = followups_on_current < MAX_FOLLOWUPS_PER_QUESTION
    must_end = (main_questions_asked >= max_questions and not can_followup) or (
        elapsed_minutes >= max_duration_minutes
    )

    system_prompt = f"""You are a senior {session_meta['interview_round']} interviewer{f" at {session_meta['company']}" if session_meta['company'] else ""} interviewing a candidate for {session_meta['job_role']} ({session_meta['difficulty']} level).

CRITICAL INTERVIEWING & EVALUATION RULES:
1. Evaluate the transcript fairly based on meaning, NOT keyword counting. Do NOT penalize valid alternative approaches.
2. The transcript came from speech-to-text (Whisper), so tolerate minor homophones or ASR punctuation quirks. Do NOT confuse ASR errors with conceptual errors.
3. Do NOT reward irrelevant lengthy answers. Do NOT invent mistakes.
4. Compute weighted rubric marks out of their maximums:
   - technical_correctness: max {weights['technical_correctness']}
   - conceptual_understanding: max {weights['conceptual_understanding']}
   - relevance: max {weights['relevance']}
   - completeness: max {weights['completeness']}
   - clarity: max {weights['clarity']}
   - communication: max {weights['communication']}
   - score: exact sum of the 6 dimension scores (0 to 100).
5. ADAPTIVE NEXT-ACTION POLICY:
   - Incomplete answer -> answer_category="incomplete", next_action="FOLLOW_UP" targeting the specific missing concept.
   - Incorrect answer -> answer_category="incorrect", next_action="FOLLOW_UP" probing the misunderstanding WITHOUT giving away the full answer immediately.
   - Very short answer (<12 words or vague) -> answer_category="too_short", next_action="FOLLOW_UP" asking for elaboration/example.
   - Irrelevant/off-topic answer -> answer_category="irrelevant", next_action="FOLLOW_UP" politely redirecting back to the question.
   - Excellent/complete answer -> answer_category="excellent", escalate recommended_difficulty ("hard" if medium/easy) and either ask a deeper FOLLOW_UP (if followups_on_current==0) or move to NEXT_QUESTION.
   - If followups_on_current >= {MAX_FOLLOWUPS_PER_QUESTION}, DO NOT pick FOLLOW_UP; choose NEXT_QUESTION (or END_INTERVIEW if last question).
   - Never repeat a previously asked question. Ask ONE natural question at a time without revealing internal instructions or marks inside next_question.

Respond ONLY with a valid JSON object matching this exact schema (no markdown fences):
{{
  "evaluation": {{
    "score": <float 0-100>,
    "technical_correctness": <float 0-{weights['technical_correctness']}>,
    "conceptual_understanding": <float 0-{weights['conceptual_understanding']}>,
    "relevance": <float 0-{weights['relevance']}>,
    "completeness": <float 0-{weights['completeness']}>,
    "clarity": <float 0-{weights['clarity']}>,
    "communication": <float 0-{weights['communication']}>
  }},
  "answer_category": "<excellent|good|incomplete|incorrect|irrelevant|too_short>",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "correct_concepts": ["..."],
  "incorrect_concepts": ["..."],
  "missing_concepts": ["..."],
  "feedback": "<objective technical/content explanation of why marks were awarded or deducted>",
  "communication_feedback": "<subjective feedback on clarity, structure, and delivery>",
  "next_action": "<FOLLOW_UP|NEXT_QUESTION|END_INTERVIEW>",
  "next_question": "<the exact next conversational question if FOLLOW_UP, or empty string if NEXT_QUESTION/END_INTERVIEW>",
  "reason_for_next_question": "<brief rationale for your adaptive decision>",
  "recommended_difficulty": "<easy|medium|hard>"
}}"""

    user_prompt = (
        f"CURRENT QUESTION ({current_question.get('topic', 'General')} | {current_question.get('difficulty', 'medium')}):\n"
        f"{current_question['question_text']}\n\n"
        f"REFERENCE BENCHMARK (for evaluator only, never reveal verbatim): {current_question.get('reference_answer', 'N/A')}\n\n"
        f"CANDIDATE TRANSCRIPT:\n\"\"\"\n{transcript}\n\"\"\"\n\n"
        f"SESSION PROGRESS: main_questions_asked={main_questions_asked}/{max_questions}, "
        f"followups_on_current={followups_on_current}/{MAX_FOLLOWUPS_PER_QUESTION}, "
        f"can_followup={can_followup}, must_end={must_end}\n"
        f"{f'RECENT CONVERSATION:{chr(10)}{recent_history}' if recent_history else ''}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    model_used = "fallback"
    parsed_result: Optional[AdaptiveTurnLLMOutput] = None
    last_err: Optional[Exception] = None

    for attempt in range(3):
        raw_text, model_used = _call_groq_chat(messages, temperature=0.2, max_tokens=1300)
        try:
            raw_dict = _extract_json_block(raw_text)
            # Clamp dimension scores cleanly to their configured weights before validation
            ev = raw_dict.get("evaluation", {})
            dim_sum = 0.0
            for k, max_w in weights.items():
                val = float(ev.get(k, max_w * 0.5))
                val = max(0.0, min(float(max_w), val))
                ev[k] = round(val, 1)
                dim_sum += val
            ev["score"] = round(min(100.0, max(0.0, dim_sum)), 1)
            raw_dict["evaluation"] = ev

            parsed_result = AdaptiveTurnLLMOutput.model_validate(raw_dict)
            break
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
            last_err = e
            logger.warning(f"Adaptive eval JSON parse failed (attempt {attempt + 1}): {e}")
            messages.append({"role": "assistant", "content": raw_text})
            messages.append({
                "role": "user",
                "content": f"Invalid JSON/schema: {e}. Return ONLY a valid JSON object matching the exact schema.",
            })

    if parsed_result is None:
        logger.error(f"All LLM adaptive evaluation attempts failed ({last_err}). Using deterministic fallback.")
        word_cnt = len(transcript.split())
        base_ratio = 0.25 if word_cnt < 10 else 0.55 if word_cnt < 35 else 0.72
        ev_scores = {k: round(w * base_ratio, 1) for k, w in weights.items()}
        ev_scores["score"] = round(sum(ev_scores.values()), 1)
        parsed_result = AdaptiveTurnLLMOutput(
            evaluation=EvaluationScores(**ev_scores),
            answer_category="too_short" if word_cnt < 12 else "incomplete",
            strengths=["Attempted to address the prompt"] if word_cnt >= 5 else [],
            weaknesses=["Elaborate with concrete technical details and examples"],
            missing_concepts=["Core mechanism and trade-offs"],
            feedback="Evaluated with heuristic fallback because structured LLM parsing failed.",
            communication_feedback="Speak clearly and structure your answer into definition, mechanism, and example.",
            next_action="FOLLOW_UP" if (word_cnt < 12 and can_followup) else "NEXT_QUESTION",
            next_question="Could you elaborate further on the core mechanics and give a concrete example?" if (word_cnt < 12 and can_followup) else "",
            reason_for_next_question="Fallback probing on brief answer",
            recommended_difficulty=current_question.get("difficulty", "medium"),
        )

    # --- Backend Orchestration Guardrails ---
    if must_end:
        parsed_result.next_action = "END_INTERVIEW"
        parsed_result.next_question = ""
    elif parsed_result.next_action == "FOLLOW_UP":
        if not can_followup or not parsed_result.next_question.strip():
            parsed_result.next_action = "NEXT_QUESTION" if main_questions_asked < max_questions else "END_INTERVIEW"
        elif normalize_text(parsed_result.next_question) in asked_questions_norm:
            # Prevent duplicate follow-up
            parsed_result.next_action = "NEXT_QUESTION" if main_questions_asked < max_questions else "END_INTERVIEW"
            parsed_result.next_question = ""

    if parsed_result.next_action == "END_INTERVIEW" and main_questions_asked < max_questions and not must_end:
        # Don't prematurely end before min/max questions unless user stops or duration exceeded
        parsed_result.next_action = "NEXT_QUESTION"

    if parsed_result.next_action == "NEXT_QUESTION":
        if main_questions_asked >= max_questions:
            parsed_result.next_action = "END_INTERVIEW"
            parsed_result.next_question = ""
        elif next_main_candidate:
            parsed_result.next_question = next_main_candidate["question_text"]

    return parsed_result, model_used


def start_audio_interview(
    email: str,
    job_role: str,
    company: str = "",
    difficulty: str = "medium",
    interview_round: str = "Technical",
    max_questions: int = 5,
    max_duration_minutes: int = 20,
    custom_weights: Optional[dict[str, int]] = None,
    resume_text: str = "",
    jd_text: str = "",
    initial_question: str = "",
    initial_topic: str = "",
) -> dict:
    """Create and persist a new stateful adaptive audio interview session."""
    session_id = f"aud_{uuid.uuid4().hex[:10]}"
    now = time.time()
    canon_round = normalize_interview_round(interview_round)
    weights = get_weights_for_round(canon_round, custom_weights)

    question_queue = _build_main_questions(
        company=company,
        job_role=job_role,
        interview_round=canon_round,
        difficulty=difficulty,
        max_questions=max_questions,
        resume_text=resume_text,
        jd_text=jd_text,
        initial_question=initial_question,
        initial_topic=initial_topic,
    )

    if not question_queue:
        question_queue = [{
            "question_text": f"Walk me through a challenging technical problem you solved relevant to a {job_role} role.",
            "topic": "Problem Solving",
            "difficulty": difficulty,
            "reference_answer": "",
            "source": "fallback",
        }]

    first_q = question_queue[0]
    remaining_queue = question_queue[1:]
    state = {
        "main_queue": remaining_queue,
        "main_questions_asked": 1,
        "asked_questions_norm": [normalize_text(first_q["question_text"])],
        "knowledge_gaps": [],
        "current_parent_turn_index": 0,
    }

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audio_interview_sessions (
                session_id, email, company, job_role, difficulty, interview_round,
                max_questions, max_duration_minutes, scoring_weights_json, status,
                current_question_index, followups_on_current, current_question_json,
                state_json, started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, 0, ?, ?, ?, ?)
            """,
            (
                session_id, email.strip().lower(), company.strip(), job_role.strip(),
                difficulty.strip().lower(), canon_round,
                max_questions, max_duration_minutes, json.dumps(weights),
                json.dumps(first_q), json.dumps(state), now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"Started adaptive audio interview {session_id} for {email} (role={job_role}, round={canon_round})")
    return {
        "session_id": session_id,
        "company": company,
        "job_role": job_role,
        "interview_round": canon_round,
        "difficulty": difficulty,
        "max_questions": max_questions,
        "max_duration_minutes": max_duration_minutes,
        "scoring_weights": weights,
        "current_question": first_q,
        "turn_index": 0,
        "main_question_number": 1,
        "is_followup": False,
    }


def _load_session_and_turns(session_id: str) -> tuple[Optional[dict], list[dict]]:
    """Fetch audio session row and turns from SQLite."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT session_id, email, company, job_role, difficulty, interview_round,
                   max_questions, max_duration_minutes, scoring_weights_json, status,
                   current_question_index, followups_on_current, current_question_json,
                   state_json, overall_score, report_json, started_at, ended_at
            FROM audio_interview_sessions WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if not row:
            return None, []

        session = {
            "session_id": row[0],
            "email": row[1],
            "company": row[2],
            "job_role": row[3],
            "difficulty": row[4],
            "interview_round": normalize_interview_round(row[5]),
            "max_questions": row[6],
            "max_duration_minutes": row[7],
            "scoring_weights": json.loads(row[8]),
            "status": row[9],
            "current_question_index": row[10],
            "followups_on_current": row[11],
            "current_question": json.loads(row[12]),
            "state": json.loads(row[13]),
            "overall_score": row[14],
            "report": json.loads(row[15]) if row[15] else {},
            "started_at": row[16],
            "ended_at": row[17],
        }

        turn_rows = conn.execute(
            """
            SELECT turn_index, is_followup, parent_turn_index, question_text, question_source,
                   topic, difficulty, audio_path, audio_duration, transcript, stt_confidence,
                   fluency_json, evaluation_json, score, next_action, reason_for_next, created_at
            FROM audio_interview_turns WHERE session_id = ? ORDER BY turn_index ASC
            """,
            (session_id,),
        ).fetchall()

        turns = [
            {
                "turn_index": tr[0],
                "is_followup": bool(tr[1]),
                "parent_turn_index": tr[2],
                "question_text": tr[3],
                "question_source": tr[4],
                "topic": tr[5],
                "difficulty": tr[6],
                "audio_path": tr[7],
                "audio_duration": tr[8],
                "transcript": tr[9],
                "stt_confidence": tr[10],
                "fluency_metrics": json.loads(tr[11]) if tr[11] else {},
                "evaluation": json.loads(tr[12]) if tr[12] else {},
                "score": tr[13],
                "next_action": tr[14],
                "reason_for_next": tr[15],
                "created_at": tr[16],
            }
            for tr in turn_rows
        ]
        return session, turns
    finally:
        conn.close()


def submit_audio_turn(
    session_id: str,
    email: str,
    transcript: str,
    audio_duration: float = 0.0,
    stt_confidence: float = 1.0,
    fluency_metrics: Optional[dict] = None,
    audio_path: str = "",
) -> dict:
    """
    Evaluate candidate transcript, persist turn, decide adaptive next step,
    and update session in SQLite.
    """
    session, turns = _load_session_and_turns(session_id)
    if not session:
        raise ValueError("Audio interview session not found.")
    if session["email"] != email.strip().lower():
        raise PermissionError("Access denied to another user's audio interview session.")
    if session["status"] != "active":
        raise ValueError(f"Interview session is already {session['status']}.")

    clean_transcript = transcript.strip()
    if not clean_transcript:
        raise ValueError("Transcript cannot be empty. Please record or provide a spoken answer.")

    state = session["state"]
    current_q = session["current_question"]
    turn_index = session["current_question_index"]
    followups_on_current = session["followups_on_current"]
    main_questions_asked = state.get("main_questions_asked", 1)
    main_queue: list[dict] = state.get("main_queue", [])
    asked_norm = set(state.get("asked_questions_norm", []))
    elapsed_minutes = (time.time() - session["started_at"]) / 60.0

    next_main_candidate = main_queue[0] if main_queue else None

    llm_out, model_used = _evaluate_and_decide_next(
        session_meta=session,
        current_question=current_q,
        transcript=clean_transcript,
        history_turns=turns,
        weights=session["scoring_weights"],
        followups_on_current=followups_on_current,
        main_questions_asked=main_questions_asked,
        max_questions=session["max_questions"],
        elapsed_minutes=elapsed_minutes,
        max_duration_minutes=session["max_duration_minutes"],
        asked_questions_norm=asked_norm,
        next_main_candidate=next_main_candidate,
    )

    now = time.time()
    is_followup_turn = followups_on_current > 0
    parent_idx = state.get("current_parent_turn_index", 0) if is_followup_turn else None

    eval_payload = llm_out.model_dump()
    turn_score = llm_out.evaluation.score

    # Update knowledge gaps
    gaps = state.get("knowledge_gaps", [])
    for mc in llm_out.missing_concepts + llm_out.incorrect_concepts:
        if mc and mc not in gaps:
            gaps.append(mc)
    state["knowledge_gaps"] = gaps

    # Determine next question state
    next_q_obj: Optional[dict] = None
    is_complete = False
    new_followups = followups_on_current

    if llm_out.next_action == "FOLLOW_UP":
        new_followups = followups_on_current + 1
        next_q_obj = {
            "question_text": llm_out.next_question.strip(),
            "topic": current_q.get("topic", "General"),
            "difficulty": llm_out.recommended_difficulty,
            "reference_answer": "",
            "source": "adaptive_followup",
            "company": session["company"],
            "is_followup": True,
        }
        asked_norm.add(normalize_text(next_q_obj["question_text"]))
    elif llm_out.next_action == "NEXT_QUESTION":
        new_followups = 0
        state["current_parent_turn_index"] = turn_index + 1
        if main_queue:
            next_q_obj = main_queue.pop(0)
        else:
            # Dynamically synthesize next question at adapted difficulty
            gen = _build_main_questions(
                company=session["company"],
                job_role=session["job_role"],
                interview_round=session["interview_round"],
                difficulty=llm_out.recommended_difficulty,
                max_questions=1,
            )
            next_q_obj = gen[0]
        next_q_obj["difficulty"] = llm_out.recommended_difficulty
        next_q_obj["is_followup"] = False
        state["main_questions_asked"] = main_questions_asked + 1
        state["main_queue"] = main_queue
        asked_norm.add(normalize_text(next_q_obj["question_text"]))
    else:
        is_complete = True

    state["asked_questions_norm"] = list(asked_norm)

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audio_interview_turns (
                session_id, turn_index, is_followup, parent_turn_index, question_text,
                question_source, topic, difficulty, audio_path, audio_duration,
                transcript, stt_confidence, fluency_json, evaluation_json, score,
                next_action, reason_for_next, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, turn_index, 1 if is_followup_turn else 0, parent_idx,
                current_q["question_text"], current_q.get("source", "question_bank"),
                current_q.get("topic", "General"), current_q.get("difficulty", "medium"),
                audio_path, audio_duration, clean_transcript, stt_confidence,
                json.dumps(fluency_metrics or {}), json.dumps(eval_payload), turn_score,
                llm_out.next_action, llm_out.reason_for_next_question, now,
            ),
        )

        if is_complete:
            conn.execute(
                """
                UPDATE audio_interview_sessions
                SET current_question_index = ?, followups_on_current = ?, state_json = ?,
                    status = 'completing', updated_at = ?
                WHERE session_id = ?
                """,
                (turn_index + 1, new_followups, json.dumps(state), now, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE audio_interview_sessions
                SET current_question_index = ?, followups_on_current = ?,
                    current_question_json = ?, state_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (turn_index + 1, new_followups, json.dumps(next_q_obj), json.dumps(state), now, session_id),
            )
        conn.commit()
    finally:
        conn.close()

    report = None
    if is_complete:
        report = finalize_audio_interview(session_id, email)

    return {
        "session_id": session_id,
        "turn_index": turn_index,
        "evaluation": eval_payload,
        "model_used": model_used,
        "next_action": llm_out.next_action,
        "reason_for_next_question": llm_out.reason_for_next_question,
        "next_question": next_q_obj,
        "is_followup": bool(next_q_obj and next_q_obj.get("is_followup")),
        "main_question_number": state.get("main_questions_asked", 1),
        "max_questions": session["max_questions"],
        "is_complete": is_complete,
        "report": report,
    }


def finalize_audio_interview(session_id: str, email: str) -> dict:
    """Complete the interview session and generate a comprehensive performance report."""
    session, turns = _load_session_and_turns(session_id)
    if not session:
        raise ValueError("Session not found.")
    if session["email"] != email.strip().lower():
        raise PermissionError("Access denied.")

    if session["status"] == "completed" and session.get("report"):
        return session["report"]

    total_turns = len(turns)
    followup_count = sum(1 for t in turns if t["is_followup"])
    main_count = total_turns - followup_count

    weights = session["scoring_weights"]
    overall_score = round(sum(t["score"] for t in turns) / max(total_turns, 1), 1) if turns else 0.0

    # Compute normalized % per rubric dimension
    dim_totals = {k: 0.0 for k in weights}
    for t in turns:
        ev = t.get("evaluation", {}).get("evaluation", {})
        for k, max_w in weights.items():
            if max_w > 0:
                dim_totals[k] += (float(ev.get(k, 0.0)) / max_w) * 100.0
    dimension_percentages = {
        k: round(dim_totals[k] / max(total_turns, 1), 1) if turns else 0.0
        for k in weights
    }

    # Aggregate strengths, weaknesses, incorrect & missing concepts
    strengths, weaknesses, incorrect_concepts, missing_concepts = [], [], [], []
    topic_scores: dict[str, list[float]] = {}
    for t in turns:
        ev = t.get("evaluation", {})
        strengths.extend(ev.get("strengths", []))
        weaknesses.extend(ev.get("weaknesses", []))
        incorrect_concepts.extend(ev.get("incorrect_concepts", []))
        missing_concepts.extend(ev.get("missing_concepts", []))
        tp = t.get("topic", "General")
        topic_scores.setdefault(tp, []).append(t["score"])

    dedup = lambda lst: list(dict.fromkeys([x for x in lst if x]))
    topic_averages = {tp: round(sum(vals) / len(vals), 1) for tp, vals in topic_scores.items()}
    weak_topics = [tp for tp, avg in topic_averages.items() if avg < 70.0]

    # Fetch RAG syllabus notes for weak topics if indexed
    revision_notes = []
    if weak_topics:
        try:
            from src.rag_assistant.hybrid_retriever import HybridRetriever
            retriever = HybridRetriever("admin_course_materials")
            if retriever.get_document_count() > 0:
                for wt in weak_topics[:3]:
                    chunks = retriever.search(wt, top_k=2)
                    for ch in chunks:
                        revision_notes.append({
                            "topic": wt,
                            "source_file": ch.get("metadata", {}).get("source_file", "Course Notes"),
                            "excerpt": ch.get("text", "")[:240] + "...",
                        })
        except Exception:
            pass

    # Personalized practice questions from bank
    practice_questions = []
    if weak_topics or missing_concepts:
        try:
            for wt in (weak_topics or list(topic_averages.keys()))[:3]:
                res = search_questions(topic=wt, page=1, page_size=2)
                for item in res.get("items", []):
                    practice_questions.append({
                        "question_text": item["question_text"],
                        "topic": item["topic"],
                        "difficulty": item["difficulty"],
                    })
        except Exception:
            pass

    action_plan = [
        f"Revise core concepts in {', '.join(weak_topics)}" if weak_topics else "Maintain mastery by attempting Hard-tier system & algorithmic drills",
        f"Address specific conceptual gaps: {', '.join(dedup(missing_concepts)[:4])}" if missing_concepts else "Review edge cases and alternative architectural trade-offs",
        "Practice structured speaking (Definition -> Mechanism -> Trade-offs -> Concrete Example) to keep answers crisp and complete.",
    ]

    report = {
        "session_id": session_id,
        "company": session["company"],
        "job_role": session["job_role"],
        "interview_round": session["interview_round"],
        "difficulty": session["difficulty"],
        "overall_score": overall_score,
        "total_questions_asked": total_turns,
        "main_questions_count": main_count,
        "followup_questions_count": followup_count,
        "technical_knowledge_score": dimension_percentages.get("technical_correctness", 0.0),
        "conceptual_understanding_score": dimension_percentages.get("conceptual_understanding", 0.0),
        "communication_score": dimension_percentages.get("communication", 0.0),
        "completeness_score": dimension_percentages.get("completeness", 0.0),
        "dimension_percentages": dimension_percentages,
        "topic_averages": topic_averages,
        "strengths": dedup(strengths)[:8],
        "weaknesses": dedup(weaknesses)[:8],
        "incorrect_concepts": dedup(incorrect_concepts)[:8],
        "missing_concepts": dedup(missing_concepts)[:8],
        "weak_topics": weak_topics,
        "recommended_revision_topics": weak_topics or list(topic_averages.keys())[:3],
        "revision_notes": revision_notes,
        "personalized_practice_questions": practice_questions[:6],
        "action_plan": action_plan,
        "turns": turns,
        "completed_at": time.time(),
    }

    now = time.time()
    conn = _get_connection()
    try:
        conn.execute(
            """
            UPDATE audio_interview_sessions
            SET status = 'completed', overall_score = ?, report_json = ?, ended_at = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (overall_score, json.dumps(report), now, now, session_id),
        )
        conn.commit()
    finally:
        conn.close()

    return report


def get_audio_session_state(session_id: str, email: str) -> dict:
    """Get full session state for resumption or review."""
    session, turns = _load_session_and_turns(session_id)
    if not session:
        raise ValueError("Session not found.")
    if session["email"] != email.strip().lower():
        raise PermissionError("Access denied.")
    return {"session": session, "turns": turns}


def get_user_audio_history(email: str) -> list[dict]:
    """List all audio interview sessions for the authenticated user."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT session_id, company, job_role, interview_round, difficulty,
                   max_questions, status, overall_score, started_at, ended_at
            FROM audio_interview_sessions
            WHERE email = ?
            ORDER BY started_at DESC
            """,
            (email.strip().lower(),),
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "company": r[1],
                "job_role": r[2],
                "interview_round": normalize_interview_round(r[3]),
                "difficulty": r[4],
                "max_questions": r[5],
                "status": r[6],
                "overall_score": r[7],
                "started_at": r[8],
                "ended_at": r[9],
            }
            for r in rows
        ]
    finally:
        conn.close()
