"""
Interview Question Generator & Session Manager
================================================
Module 3 - AI Interviewer (Part 2)

Manages interview sessions: selects questions from the local question bank,
generates dynamic follow-ups via LLM, and tracks session progress.
"""

import json
import os
import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

from src.interviewer.role_matcher import get_interview_topics
from src.rag_assistant.generator import generate_interview_question
from src.utils.checkpoint import save_checkpoint, load_checkpoint
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

QUESTION_BANK_PATH = os.getenv(
    "QUESTION_BANK_PATH", "./data/question_bank/questions.json"
)
QUESTIONS_PER_SESSION = int(os.getenv("QUESTIONS_PER_SESSION", "10"))


@dataclass
class InterviewQuestion:
    """A single interview question with metadata."""

    question_id: str
    topic: str
    difficulty: str  # easy, medium, hard
    question_text: str
    reference_answer: str = ""
    source: str = "question_bank"  # question_bank | llm_generated
    category: str = ""


@dataclass
class InterviewSession:
    """Tracks the state of an active interview session."""

    session_id: str
    target_role: str
    topics: list[str]
    questions: list[InterviewQuestion] = field(default_factory=list)
    current_index: int = 0
    answers: list[dict] = field(default_factory=list)
    is_complete: bool = False
    experience_level: str = "Junior"

    @property
    def current_question(self) -> Optional[InterviewQuestion]:
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    @property
    def progress(self) -> dict:
        return {
            "current": self.current_index + 1,
            "total": len(self.questions),
            "answered": len(self.answers),
            "remaining": len(self.questions) - self.current_index,
        }

    def to_dict(self) -> dict:
        """Serialize session state for checkpointing."""
        return {
            "session_id": self.session_id,
            "target_role": self.target_role,
            "topics": self.topics,
            "questions": [
                {
                    "question_id": q.question_id,
                    "topic": q.topic,
                    "difficulty": q.difficulty,
                    "question_text": q.question_text,
                    "reference_answer": q.reference_answer,
                    "source": q.source,
                    "category": q.category,
                }
                for q in self.questions
            ],
            "current_index": self.current_index,
            "answers": self.answers,
            "is_complete": self.is_complete,
            "experience_level": self.experience_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewSession":
        """Restore session from checkpoint data."""
        session = cls(
            session_id=data["session_id"],
            target_role=data["target_role"],
            topics=data["topics"],
            current_index=data.get("current_index", 0),
            answers=data.get("answers", []),
            is_complete=data.get("is_complete", False),
            experience_level=data.get("experience_level", "Junior"),
        )
        session.questions = [
            InterviewQuestion(**q) for q in data.get("questions", [])
        ]
        return session


def _load_question_bank() -> list[dict]:
    """Load the curated question bank from JSON file."""
    if not os.path.exists(QUESTION_BANK_PATH):
        logger.warning(f"Question bank not found at {QUESTION_BANK_PATH}")
        return []

    with open(QUESTION_BANK_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    logger.info(f"Loaded {len(questions)} questions from question bank")
    return questions


def _select_questions(
    topics: list[str],
    num_questions: int = QUESTIONS_PER_SESSION,
    difficulty_mix: Optional[dict] = None,
) -> list[InterviewQuestion]:
    """
    Select questions from the question bank matching the given topics.

    Args:
        topics: List of skill topics to focus on.
        num_questions: Number of questions to select.
        difficulty_mix: Optional dict like {'easy': 3, 'medium': 4, 'hard': 3}.

    Returns:
        List of selected InterviewQuestion objects.
    """
    bank = _load_question_bank()
    if not bank:
        return []

    if not difficulty_mix:
        difficulty_mix = {
            "easy": max(1, num_questions // 4),
            "medium": num_questions // 2,
            "hard": num_questions - max(1, num_questions // 4) - num_questions // 2,
        }

    # Filter questions by matching topics
    topic_lower = {t.lower() for t in topics}
    matching = [
        q for q in bank
        if q.get("topic", "").lower() in topic_lower
        or any(t in q.get("topic", "").lower() for t in topic_lower)
    ]

    # If not enough topic matches, include all questions as fallback
    if len(matching) < num_questions:
        remaining = [q for q in bank if q not in matching]
        random.shuffle(remaining)
        matching.extend(remaining[: num_questions - len(matching)])

    selected = []
    for difficulty, count in difficulty_mix.items():
        diff_questions = [
            q for q in matching if q.get("difficulty", "medium") == difficulty
        ]
        random.shuffle(diff_questions)
        for q in diff_questions[:count]:
            selected.append(
                InterviewQuestion(
                    question_id=q.get("id", str(uuid.uuid4())[:8]),
                    topic=q.get("topic", "General"),
                    difficulty=q.get("difficulty", "medium"),
                    question_text=q.get("question_text", ""),
                    reference_answer=q.get("reference_answer", ""),
                    source="question_bank",
                    category=q.get("category", ""),
                )
            )

    # Pad with remaining questions if we don't have enough
    if len(selected) < num_questions:
        remaining_bank = [q for q in matching if q.get("id") not in {s.question_id for s in selected}]
        random.shuffle(remaining_bank)
        for q in remaining_bank[: num_questions - len(selected)]:
            selected.append(
                InterviewQuestion(
                    question_id=q.get("id", str(uuid.uuid4())[:8]),
                    topic=q.get("topic", "General"),
                    difficulty=q.get("difficulty", "medium"),
                    question_text=q.get("question_text", ""),
                    reference_answer=q.get("reference_answer", ""),
                    source="question_bank",
                    category=q.get("category", ""),
                )
            )

    random.shuffle(selected)
    return selected[:num_questions]


def create_interview_session(
    resume_text: str,
    target_role: str,
    jd_text: Optional[str] = None,
    experience_level: str = "Junior",
    num_questions: int = QUESTIONS_PER_SESSION,
) -> InterviewSession:
    """
    Initialize a new mock interview session.

    Args:
        resume_text: The candidate's resume text.
        target_role: Target job role (e.g., "Machine Learning Engineer").
        jd_text: Optional job description text.
        experience_level: Experience level for difficulty calibration.
        num_questions: Number of questions in the session.

    Returns:
        A fully initialized InterviewSession ready to begin.
    """
    session_id = f"sess_{uuid.uuid4().hex[:8]}"

    # Determine interview topics from resume + JD/role
    topics = get_interview_topics(resume_text, jd_text, target_role)
    logger.info(f"Interview topics for {target_role}: {topics}")

    # Select questions from the bank
    questions = _select_questions(topics, num_questions)

    session = InterviewSession(
        session_id=session_id,
        target_role=target_role,
        topics=topics,
        questions=questions,
        experience_level=experience_level,
    )

    # Save initial checkpoint
    save_checkpoint(session_id, "interview", session.to_dict())

    logger.info(
        f"Interview session created: {session_id}, role={target_role}, "
        f"questions={len(questions)}, topics={topics}"
    )
    return session


def submit_answer(
    session: InterviewSession,
    answer_text: str,
    response_time: float,
) -> dict:
    """
    Record an answer and advance to the next question.

    Args:
        session: The active InterviewSession.
        answer_text: The candidate's answer text.
        response_time: Time taken to answer in seconds.

    Returns:
        Dict with 'question' (answered), 'answer_recorded', 'next_question' (or None).
    """
    current_q = session.current_question
    if not current_q:
        return {"error": "No more questions in this session"}

    # Record the answer
    session.answers.append(
        {
            "question_id": current_q.question_id,
            "topic": current_q.topic,
            "question_text": current_q.question_text,
            "answer": answer_text,
            "response_time": response_time,
            "reference_answer": current_q.reference_answer,
        }
    )

    session.current_index += 1

    # Check if session is complete
    if session.current_index >= len(session.questions):
        session.is_complete = True

    # Save checkpoint after each answer
    save_checkpoint(session.session_id, "interview", session.to_dict())

    next_q = session.current_question
    return {
        "question_answered": current_q.question_text,
        "answer_recorded": True,
        "next_question": {
            "question_id": next_q.question_id,
            "topic": next_q.topic,
            "difficulty": next_q.difficulty,
            "question_text": next_q.question_text,
        }
        if next_q
        else None,
        "is_complete": session.is_complete,
        "progress": session.progress,
    }


def resume_session(session_id: str) -> Optional[InterviewSession]:
    """
    Resume an interview session from a checkpoint.

    Args:
        session_id: The session ID to resume.

    Returns:
        The restored InterviewSession, or None if not found.
    """
    state = load_checkpoint(session_id)
    if state:
        session = InterviewSession.from_dict(state)
        logger.info(f"Session {session_id} resumed at question {session.current_index + 1}")
        return session
    return None
