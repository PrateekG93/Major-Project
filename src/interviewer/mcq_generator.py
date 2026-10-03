"""
MCQ Question Generator
========================
Generates MCQ questions from admin-uploaded textbook content
based on the user's JD and resume.

Flow:
1. Extract key topics from JD + resume
2. Search admin_course_materials for relevant textbook content
3. Use LLM to generate MCQs from retrieved content
4. Fallback to curated MCQ bank if LLM fails
"""

import json
import random
import uuid
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

ADMIN_COLLECTION = "admin_course_materials"


def _extract_topics_from_jd(jd_text: str, resume_text: str) -> list[str]:
    """Extract key technical topics from JD and resume using keyword matching."""
    from src.interviewer.role_matcher import SKILL_TAXONOMY

    combined = (jd_text + " " + resume_text).lower()
    matched_topics = []

    for topic, data in SKILL_TAXONOMY.items():
        keywords = data.get("keywords", [])
        match_count = sum(1 for kw in keywords if kw.lower() in combined)
        if match_count >= 1:
            matched_topics.append((topic, match_count))

    # Sort by match count and return top topics
    matched_topics.sort(key=lambda x: x[1], reverse=True)
    topics = [t[0] for t in matched_topics[:8]]

    if not topics:
        topics = ["General Knowledge", "Aptitude", "Logical Reasoning"]

    logger.info(f"Extracted topics from JD: {topics}")
    return topics


def _get_textbook_context(topics: list[str], top_k: int = 10) -> list[str]:
    """Search admin course materials for relevant textbook content."""
    try:
        from src.rag_assistant.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(collection_name=ADMIN_COLLECTION)

        if retriever.get_document_count() == 0:
            logger.warning("No admin course materials indexed")
            return []

        all_chunks = []
        for topic in topics[:5]:
            results = retriever.search(query=topic, top_k=top_k // len(topics[:5]))
            for r in results:
                all_chunks.append(r.get("text", ""))

        return all_chunks
    except Exception as e:
        logger.warning(f"Could not fetch textbook context: {e}")
        return []


def _generate_mcqs_via_llm(
    topics: list[str],
    context_chunks: list[str],
    num_questions: int = 10,
    jd_text: str = "",
) -> list[dict]:
    """Use LLM to generate MCQ questions from textbook content."""
    try:
        from src.rag_assistant.generator import _get_client

        context = "\n\n".join(context_chunks[:5])  # Limit context size

        prompt = f"""You are an expert exam creator. Generate exactly {num_questions} multiple-choice aptitude questions.

TOPICS TO COVER: {', '.join(topics)}

JOB DESCRIPTION CONTEXT:
{jd_text[:500] if jd_text else 'General technical role'}

TEXTBOOK CONTENT FOR REFERENCE:
{context[:2000] if context else 'Use your knowledge on the topics above.'}

RULES:
1. Each question must have exactly 4 options labeled A, B, C, D
2. Only ONE option should be correct
3. Mix difficulty levels (easy, medium, hard)
4. Questions should be aptitude/knowledge-based (not subjective)
5. Cover different topics from the list

OUTPUT FORMAT - Return a valid JSON array of objects. Each object must have:
- "question_text": The question
- "options": Array of 4 strings ["A. ...", "B. ...", "C. ...", "D. ..."]
- "correct_answer": The letter of the correct option (A, B, C, or D)
- "explanation": Brief explanation of why the answer is correct
- "topic": Which topic this question covers
- "difficulty": "easy", "medium", or "hard"

Return ONLY the JSON array, no other text."""

        client = _get_client()
        response = client.text_generation(
            prompt,
            max_new_tokens=3000,
            temperature=0.5,
        )

        # Try to parse JSON from response
        text = response.strip()

        # Find JSON array in response
        start_idx = text.find("[")
        end_idx = text.rfind("]") + 1

        if start_idx >= 0 and end_idx > start_idx:
            json_str = text[start_idx:end_idx]
            questions = json.loads(json_str)

            # Validate structure
            valid_questions = []
            for q in questions:
                if (
                    isinstance(q, dict)
                    and "question_text" in q
                    and "options" in q
                    and "correct_answer" in q
                    and len(q["options"]) == 4
                    and q["correct_answer"] in ("A", "B", "C", "D")
                ):
                    valid_questions.append({
                        "question_text": q["question_text"],
                        "options": q["options"],
                        "correct_answer": q["correct_answer"],
                        "explanation": q.get("explanation", ""),
                        "topic": q.get("topic", topics[0] if topics else "General"),
                        "difficulty": q.get("difficulty", "medium"),
                    })

            if valid_questions:
                logger.info(f"LLM generated {len(valid_questions)} valid MCQs")
                return valid_questions[:num_questions]

        logger.warning("LLM response could not be parsed as valid MCQ JSON")
        return []
    except Exception as e:
        logger.error(f"LLM MCQ generation failed: {e}")
        return []


# ============================================================
# Curated MCQ Fallback Bank
# ============================================================

FALLBACK_MCQ_BANK = [
    {
        "question_text": "What is the time complexity of binary search?",
        "options": ["A. O(n)", "B. O(log n)", "C. O(n²)", "D. O(1)"],
        "correct_answer": "B",
        "explanation": "Binary search halves the search space in each step, giving O(log n) complexity.",
        "topic": "Data Structures & Algorithms",
        "difficulty": "easy",
    },
    {
        "question_text": "Which data structure uses FIFO (First In First Out) principle?",
        "options": ["A. Stack", "B. Queue", "C. Tree", "D. Graph"],
        "correct_answer": "B",
        "explanation": "Queue follows FIFO - the element inserted first is the first to be removed.",
        "topic": "Data Structures & Algorithms",
        "difficulty": "easy",
    },
    {
        "question_text": "In Python, what is the output of: len({'a': 1, 'b': 2, 'a': 3})?",
        "options": ["A. 2", "B. 3", "C. Error", "D. 1"],
        "correct_answer": "A",
        "explanation": "Dictionary keys must be unique. The key 'a' is overwritten, so only 2 keys remain: 'a' and 'b'.",
        "topic": "Python",
        "difficulty": "easy",
    },
    {
        "question_text": "What does SQL JOIN do?",
        "options": [
            "A. Deletes rows from multiple tables",
            "B. Combines rows from two or more tables based on a related column",
            "C. Creates a new table",
            "D. Sorts the table",
        ],
        "correct_answer": "B",
        "explanation": "JOIN combines rows from multiple tables based on matching column values.",
        "topic": "SQL",
        "difficulty": "easy",
    },
    {
        "question_text": "Which activation function is most commonly used in hidden layers of deep neural networks?",
        "options": ["A. Sigmoid", "B. Tanh", "C. ReLU", "D. Softmax"],
        "correct_answer": "C",
        "explanation": "ReLU (Rectified Linear Unit) is the most popular due to its simplicity and effectiveness against vanishing gradients.",
        "topic": "Deep Learning",
        "difficulty": "medium",
    },
    {
        "question_text": "What is the primary purpose of regularization in machine learning?",
        "options": [
            "A. Speed up training",
            "B. Prevent overfitting",
            "C. Increase model complexity",
            "D. Reduce training data size",
        ],
        "correct_answer": "B",
        "explanation": "Regularization (L1/L2) adds a penalty for complexity, discouraging overfitting to training data.",
        "topic": "Machine Learning",
        "difficulty": "easy",
    },
    {
        "question_text": "In a hash table, what is a collision?",
        "options": [
            "A. When the hash table is full",
            "B. When two different keys hash to the same index",
            "C. When a key is not found",
            "D. When the hash function fails",
        ],
        "correct_answer": "B",
        "explanation": "A collision occurs when two different keys produce the same hash value, mapping to the same slot.",
        "topic": "Data Structures & Algorithms",
        "difficulty": "medium",
    },
    {
        "question_text": "What does ACID stand for in database systems?",
        "options": [
            "A. Atomicity, Consistency, Isolation, Durability",
            "B. Association, Consistency, Integrity, Durability",
            "C. Atomicity, Completeness, Isolation, Data",
            "D. Access, Consistency, Isolation, Durability",
        ],
        "correct_answer": "A",
        "explanation": "ACID properties ensure reliable database transactions: Atomicity, Consistency, Isolation, Durability.",
        "topic": "SQL",
        "difficulty": "medium",
    },
    {
        "question_text": "What is the worst-case time complexity of QuickSort?",
        "options": ["A. O(n log n)", "B. O(n²)", "C. O(n)", "D. O(log n)"],
        "correct_answer": "B",
        "explanation": "Worst case occurs when the pivot is always the smallest/largest element, leading to O(n²).",
        "topic": "Data Structures & Algorithms",
        "difficulty": "medium",
    },
    {
        "question_text": "Which of the following is NOT a valid Python data type?",
        "options": ["A. list", "B. tuple", "C. array", "D. dictionary"],
        "correct_answer": "C",
        "explanation": "Python doesn't have a built-in 'array' data type. Arrays are available through the 'array' module or NumPy.",
        "topic": "Python",
        "difficulty": "easy",
    },
    {
        "question_text": "What is the purpose of the 'self' keyword in Python?",
        "options": [
            "A. It refers to the class itself",
            "B. It refers to the current instance of the class",
            "C. It is a reserved keyword with no purpose",
            "D. It creates a static method",
        ],
        "correct_answer": "B",
        "explanation": "'self' refers to the current instance of the class, allowing access to instance attributes and methods.",
        "topic": "Python",
        "difficulty": "easy",
    },
    {
        "question_text": "What is gradient descent used for in machine learning?",
        "options": [
            "A. Feature selection",
            "B. Data preprocessing",
            "C. Optimizing model parameters by minimizing the loss function",
            "D. Splitting data into train/test sets",
        ],
        "correct_answer": "C",
        "explanation": "Gradient descent iteratively adjusts model parameters in the direction that minimizes the loss function.",
        "topic": "Machine Learning",
        "difficulty": "medium",
    },
    {
        "question_text": "Which sorting algorithm has the best average-case time complexity?",
        "options": ["A. Bubble Sort O(n²)", "B. Merge Sort O(n log n)", "C. Selection Sort O(n²)", "D. Insertion Sort O(n²)"],
        "correct_answer": "B",
        "explanation": "Merge Sort has O(n log n) average-case complexity, better than the O(n²) of the other options.",
        "topic": "Data Structures & Algorithms",
        "difficulty": "easy",
    },
    {
        "question_text": "What is the difference between supervised and unsupervised learning?",
        "options": [
            "A. Supervised uses labeled data; unsupervised uses unlabeled data",
            "B. Supervised is faster; unsupervised is slower",
            "C. Supervised works only on images; unsupervised works on text",
            "D. There is no difference",
        ],
        "correct_answer": "A",
        "explanation": "Supervised learning uses labeled training data (input-output pairs), while unsupervised learning finds patterns in unlabeled data.",
        "topic": "Machine Learning",
        "difficulty": "easy",
    },
    {
        "question_text": "In SQL, what does GROUP BY do?",
        "options": [
            "A. Sorts the results",
            "B. Filters rows based on a condition",
            "C. Groups rows with the same values in specified columns, often used with aggregate functions",
            "D. Joins two tables",
        ],
        "correct_answer": "C",
        "explanation": "GROUP BY groups rows sharing specified column values, enabling aggregate operations like COUNT, SUM, AVG.",
        "topic": "SQL",
        "difficulty": "medium",
    },
    {
        "question_text": "What is a deadlock in operating systems?",
        "options": [
            "A. When a process runs too long",
            "B. When two or more processes are waiting for each other to release resources, causing a standstill",
            "C. When memory is full",
            "D. When CPU utilization is 100%",
        ],
        "correct_answer": "B",
        "explanation": "Deadlock occurs when processes hold resources while waiting for others, creating a circular dependency.",
        "topic": "Operating Systems",
        "difficulty": "medium",
    },
    {
        "question_text": "What is polymorphism in OOP?",
        "options": [
            "A. Hiding internal details",
            "B. Ability of objects of different classes to respond to the same method call",
            "C. Creating multiple objects",
            "D. Restricting access to variables",
        ],
        "correct_answer": "B",
        "explanation": "Polymorphism allows different classes to be treated through the same interface, with each class implementing methods differently.",
        "topic": "Object-Oriented Programming",
        "difficulty": "medium",
    },
    {
        "question_text": "What is the purpose of normalization in databases?",
        "options": [
            "A. To speed up queries",
            "B. To reduce data redundancy and improve data integrity",
            "C. To encrypt data",
            "D. To backup data",
        ],
        "correct_answer": "B",
        "explanation": "Normalization organizes data to reduce redundancy (duplicate data) and improve data integrity through decomposition into related tables.",
        "topic": "SQL",
        "difficulty": "medium",
    },
    {
        "question_text": "What is the vanishing gradient problem in deep learning?",
        "options": [
            "A. When the learning rate is too high",
            "B. When gradients become extremely small during backpropagation, making earlier layers learn very slowly",
            "C. When the model has too few layers",
            "D. When the training data is insufficient",
        ],
        "correct_answer": "B",
        "explanation": "Vanishing gradients occur when gradients shrink exponentially through layers, preventing deep networks from learning effectively.",
        "topic": "Deep Learning",
        "difficulty": "hard",
    },
    {
        "question_text": "What is Big-O notation used for?",
        "options": [
            "A. Measuring exact running time of algorithms",
            "B. Describing the upper bound of an algorithm's growth rate",
            "C. Counting lines of code",
            "D. Measuring memory usage only",
        ],
        "correct_answer": "B",
        "explanation": "Big-O notation describes the worst-case upper bound of an algorithm's time or space complexity as input grows.",
        "topic": "Data Structures & Algorithms",
        "difficulty": "easy",
    },
]


def generate_mcq_questions(
    jd_text: str,
    resume_text: str,
    num_questions: int = 10,
) -> list[dict]:
    """
    Generate MCQ questions based on JD, resume, and textbook content.

    Args:
        jd_text: Job description text.
        resume_text: Resume text.
        num_questions: Number of questions to generate.

    Returns:
        List of MCQ question dicts.
    """
    # Step 1: Extract topics
    topics = _extract_topics_from_jd(jd_text, resume_text)

    # Step 2: Get textbook context
    context_chunks = _get_textbook_context(topics)

    # Step 3: Try LLM generation
    questions = _generate_mcqs_via_llm(topics, context_chunks, num_questions, jd_text)

    # Step 4: Fill remaining from fallback bank if needed
    if len(questions) < num_questions:
        logger.info(f"LLM generated {len(questions)} questions, filling from fallback bank")
        remaining = num_questions - len(questions)

        # Filter fallback questions by matching topics
        topic_lower = {t.lower() for t in topics}
        matching_fallback = [
            q for q in FALLBACK_MCQ_BANK
            if q["topic"].lower() in topic_lower
            or any(t in q["topic"].lower() for t in topic_lower)
        ]

        # If not enough matches, use all fallback
        if len(matching_fallback) < remaining:
            matching_fallback = FALLBACK_MCQ_BANK.copy()

        random.shuffle(matching_fallback)

        # Avoid duplicates
        existing_texts = {q["question_text"] for q in questions}
        for fq in matching_fallback:
            if fq["question_text"] not in existing_texts and len(questions) < num_questions:
                questions.append(fq)
                existing_texts.add(fq["question_text"])

    # Shuffle final questions
    random.shuffle(questions)
    return questions[:num_questions]
