"""
Resume & Job Description Skill Matcher
=======================================
Module 3 - AI Interviewer (Part 1)

Extracts skills from resumes and job descriptions, then computes
a skill-gap alignment matrix to focus interview questions on
relevant and missing competency areas.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Comprehensive skill taxonomy organized by domain
SKILL_TAXONOMY = {
    "Python": {
        "keywords": [
            "python", "django", "flask", "fastapi", "pandas", "numpy",
            "scipy", "matplotlib", "seaborn", "pytest", "pip", "virtualenv",
            "asyncio", "pydantic", "celery", "streamlit",
        ],
        "category": "Programming Languages",
    },
    "Java": {
        "keywords": ["java", "spring", "spring boot", "maven", "gradle", "jvm", "hibernate"],
        "category": "Programming Languages",
    },
    "JavaScript": {
        "keywords": [
            "javascript", "typescript", "react", "angular", "vue", "node.js",
            "nodejs", "express", "next.js", "nextjs",
        ],
        "category": "Programming Languages",
    },
    "C/C++": {
        "keywords": ["c++", "c programming", "cpp", "stl", "pointers", "memory management"],
        "category": "Programming Languages",
    },
    "SQL": {
        "keywords": [
            "sql", "mysql", "postgresql", "sqlite", "mongodb", "nosql",
            "database", "dbms", "rdbms", "joins", "stored procedures",
            "query optimization", "indexing",
        ],
        "category": "Databases",
    },
    "Machine Learning": {
        "keywords": [
            "machine learning", "supervised learning", "unsupervised learning",
            "regression", "classification", "clustering", "random forest",
            "decision tree", "svm", "support vector", "ensemble",
            "gradient boosting", "xgboost", "lightgbm", "scikit-learn",
            "sklearn", "feature engineering", "cross-validation",
            "hyperparameter tuning", "model evaluation",
        ],
        "category": "Machine Learning",
    },
    "Deep Learning": {
        "keywords": [
            "deep learning", "neural network", "cnn", "rnn", "lstm", "gru",
            "transformer", "attention mechanism", "bert", "gpt",
            "tensorflow", "pytorch", "keras", "backpropagation",
            "convolutional", "recurrent", "generative", "gan",
        ],
        "category": "Machine Learning",
    },
    "NLP": {
        "keywords": [
            "natural language processing", "nlp", "text mining", "tokenization",
            "word embeddings", "word2vec", "tfidf", "tf-idf", "sentiment analysis",
            "named entity recognition", "ner", "text classification",
            "language model", "llm", "rag", "retrieval augmented",
            "hugging face", "langchain", "llamaindex",
        ],
        "category": "Machine Learning",
    },
    "Data Structures & Algorithms": {
        "keywords": [
            "data structures", "algorithms", "dsa", "array", "linked list",
            "stack", "queue", "tree", "binary tree", "bst", "graph",
            "hash map", "hash table", "sorting", "searching", "dynamic programming",
            "greedy", "backtracking", "bfs", "dfs", "dijkstra",
            "time complexity", "space complexity", "big o",
        ],
        "category": "Data Structures & Algorithms",
    },
    "System Design": {
        "keywords": [
            "system design", "microservices", "api design", "rest api",
            "load balancer", "caching", "redis", "message queue", "kafka",
            "scalability", "distributed systems", "cloud", "aws", "azure",
            "gcp", "docker", "kubernetes", "ci/cd", "devops",
        ],
        "category": "System Design",
    },
    "Data Science": {
        "keywords": [
            "data science", "data analysis", "data visualization",
            "statistics", "probability", "hypothesis testing", "a/b testing",
            "eda", "exploratory data analysis", "tableau", "power bi",
            "data pipeline", "etl",
        ],
        "category": "Data Science",
    },
    "Computer Vision": {
        "keywords": [
            "computer vision", "image processing", "object detection",
            "image classification", "opencv", "yolo", "image segmentation",
            "face recognition",
        ],
        "category": "Machine Learning",
    },
}


@dataclass
class SkillProfile:
    """Extracted skill profile from a resume or job description."""

    matched_skills: list[str] = field(default_factory=list)
    skill_categories: dict[str, list[str]] = field(default_factory=dict)
    raw_keywords_found: list[str] = field(default_factory=list)
    source_type: str = "resume"  # 'resume' or 'job_description'


@dataclass
class SkillGapAnalysis:
    """Analysis of gaps between candidate skills and job requirements."""

    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)
    match_percentage: float = 0.0
    priority_topics: list[str] = field(default_factory=list)


def extract_skills(text: str, source_type: str = "resume") -> SkillProfile:
    """
    Extract recognized skills from text using the skill taxonomy.

    Args:
        text: Resume or JD text content.
        source_type: Either 'resume' or 'job_description'.

    Returns:
        SkillProfile with matched skills and categories.
    """
    text_lower = text.lower()
    profile = SkillProfile(source_type=source_type)
    categories: dict[str, list[str]] = {}

    for skill_name, skill_data in SKILL_TAXONOMY.items():
        for keyword in skill_data["keywords"]:
            # Use word boundary matching for short keywords
            if len(keyword) <= 3:
                pattern = rf"\b{re.escape(keyword)}\b"
                if re.search(pattern, text_lower):
                    if skill_name not in profile.matched_skills:
                        profile.matched_skills.append(skill_name)
                        profile.raw_keywords_found.append(keyword)

                        category = skill_data["category"]
                        if category not in categories:
                            categories[category] = []
                        if skill_name not in categories[category]:
                            categories[category].append(skill_name)
                    break
            else:
                if keyword in text_lower:
                    if skill_name not in profile.matched_skills:
                        profile.matched_skills.append(skill_name)
                        profile.raw_keywords_found.append(keyword)

                        category = skill_data["category"]
                        if category not in categories:
                            categories[category] = []
                        if skill_name not in categories[category]:
                            categories[category].append(skill_name)
                    break

    profile.skill_categories = categories
    logger.info(
        f"Extracted {len(profile.matched_skills)} skills from {source_type}: "
        f"{profile.matched_skills}"
    )
    return profile


def analyze_skill_gap(
    resume_profile: SkillProfile,
    jd_profile: SkillProfile,
) -> SkillGapAnalysis:
    """
    Compare resume skills against job description requirements.

    Args:
        resume_profile: Skills extracted from the candidate's resume.
        jd_profile: Skills extracted from the target job description.

    Returns:
        SkillGapAnalysis with matched, missing, and extra skills.
    """
    resume_set = set(resume_profile.matched_skills)
    jd_set = set(jd_profile.matched_skills)

    matched = sorted(resume_set & jd_set)
    missing = sorted(jd_set - resume_set)
    extra = sorted(resume_set - jd_set)

    match_pct = (len(matched) / len(jd_set) * 100) if jd_set else 100.0

    # Priority topics: missing skills first, then weaker matched skills
    priority = list(missing) + list(matched)

    analysis = SkillGapAnalysis(
        matched_skills=matched,
        missing_skills=missing,
        extra_skills=extra,
        match_percentage=round(match_pct, 1),
        priority_topics=priority[:10],  # Top 10 priority areas
    )

    logger.info(
        f"Skill gap analysis: {len(matched)} matched, {len(missing)} missing, "
        f"match={match_pct:.1f}%"
    )
    return analysis


def get_interview_topics(
    resume_text: str,
    jd_text: Optional[str] = None,
    target_role: Optional[str] = None,
) -> list[str]:
    """
    Determine which topics to focus the interview on.

    Args:
        resume_text: The candidate's resume text.
        jd_text: Optional job description text.
        target_role: Optional target role name.

    Returns:
        Ordered list of topic names to focus interview questions on.
    """
    resume_profile = extract_skills(resume_text, "resume")

    if jd_text:
        jd_profile = extract_skills(jd_text, "job_description")
        gap = analyze_skill_gap(resume_profile, jd_profile)
        return gap.priority_topics
    elif target_role:
        # Use role-based defaults
        role_defaults = _get_role_default_skills(target_role)
        jd_profile = SkillProfile(matched_skills=role_defaults, source_type="job_description")
        gap = analyze_skill_gap(resume_profile, jd_profile)
        return gap.priority_topics
    else:
        return resume_profile.matched_skills


def _get_role_default_skills(role: str) -> list[str]:
    """Return default expected skills for common engineering roles."""
    role_lower = role.lower()

    role_skill_map = {
        "machine learning": [
            "Python", "Machine Learning", "Deep Learning", "NLP",
            "Data Science", "SQL", "Data Structures & Algorithms",
        ],
        "data scientist": [
            "Python", "Machine Learning", "Data Science", "SQL",
            "Deep Learning", "Data Structures & Algorithms",
        ],
        "backend": [
            "Python", "Java", "SQL", "System Design",
            "Data Structures & Algorithms",
        ],
        "frontend": [
            "JavaScript", "System Design", "Data Structures & Algorithms",
        ],
        "full stack": [
            "Python", "JavaScript", "SQL", "System Design",
            "Data Structures & Algorithms",
        ],
        "software": [
            "Python", "Java", "SQL", "Data Structures & Algorithms",
            "System Design",
        ],
        "data engineer": [
            "Python", "SQL", "System Design", "Data Science",
        ],
        "data analyst": [
            "Python", "SQL", "Data Science",
        ],
    }

    for key, skills in role_skill_map.items():
        if key in role_lower:
            return skills

    # Default fallback
    return ["Python", "Data Structures & Algorithms", "SQL"]
