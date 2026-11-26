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


COMMON_ROLE_TITLES = [
    "Software Development Engineer",
    "Software Engineer",
    "Senior Software Engineer",
    "Full Stack Developer",
    "Full Stack Engineer",
    "Backend Engineer",
    "Backend Developer",
    "Frontend Engineer",
    "Frontend Developer",
    "AI/ML Engineer",
    "AI / ML Engineer",
    "AIML Engineer",
    "Machine Learning Engineer",
    "Deep Learning Engineer",
    "NLP Engineer",
    "Data Scientist",
    "Data Engineer",
    "Data Analyst",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Cloud Engineer",
    "Systems Engineer",
    "Specialist Programmer",
    "Quantitative Analyst",
    "Research Intern",
    "Product Manager",
    "Engineering Manager",
]


def parse_jd_metadata(jd_text: str, filename: str = "") -> tuple[str, str]:
    """
    Extract (job_role, organization) from a Job Description document and optional filename.
    Returns (role, organization) with sensible fallback for role and '' if organization is absent.
    """
    text = re.sub(r"[ \t]+", " ", (jd_text or "").replace("\r\n", "\n"))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    role = ""
    organization = ""

    # 1. Explicit key-value headers for role
    role_pat = re.compile(
        r"^(?:\d+[\.\)]\s*)?(?:job\s*title|role|position(?:\s*title)?|designation|profile)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    )
    for ln in lines[:40]:
        m = role_pat.match(ln)
        if m:
            cand = re.split(r"[|•]", m.group(1))[0].strip(" .,-:")
            if 2 <= len(cand) <= 80 and not cand.lower().startswith(("http", "www")):
                role = cand
                break

    # 2. Match well-known engineering role titles inside JD text
    if not role:
        head_block = "\n".join(lines[:25])
        for title in COMMON_ROLE_TITLES:
            if re.search(rf"\b{re.escape(title)}\b", head_block, re.IGNORECASE):
                role = title
                break

    # 3. '@' or 'at' pattern like "Software Development Engineer @ Google"
    if not role or not organization:
        at_match = re.search(
            r"\b([A-Z][A-Za-z0-9/&+\- ]{2,50}?)\s*(?:@|\bat\b)\s*([A-Z][A-Za-z0-9&.\- ]{1,40})\b",
            "\n".join(lines[:15]),
        )
        if at_match:
            if not role:
                role = at_match.group(1).strip(" .,-:")
            if not organization:
                organization = at_match.group(2).strip(" .,-:")

    # 4. Explicit key-value headers for organization/company
    org_pat = re.compile(
        r"^(?:\d+[\.\)]\s*)?(?:company(?:\s*name)?|organization|employer|client)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    )
    for ln in lines[:40]:
        m = org_pat.match(ln)
        if m:
            cand = re.split(r"[|•]", m.group(1))[0].strip(" .,-:")
            if 2 <= len(cand) <= 60 and cand.lower() not in ("profile", "overview", "description"):
                organization = cand
                break

    # 5. Sentence pattern (single-line only): "<Name> is a/an ... (company|organization|firm|startup)"
    if not organization:
        for ln in lines[:25]:
            prof_match = re.match(
                r"^([A-Z][A-Za-z0-9&.\-]+(?:[ \t]+[A-Z][A-Za-z0-9&.\-]+){0,3})[ \t]+is[ \t]+(?:a|an|one[ \t]+of)[ \t]+[^.\n]{3,80}?\b(?:company|firm|organization|startup|enterprise|leader|consultancy|studio|platform|labs)\b",
                ln,
                re.IGNORECASE,
            )
            if prof_match:
                cand = prof_match.group(1).strip(" .,-:")
                if cand.lower() not in ("it", "this", "the", "there", "we", "our", "company profile"):
                    organization = cand
                    break

    # 6. Filename fallback for role (skip generic names like pasted_text)
    if not role and filename and filename != "pasted_text":
        stem = re.sub(r"\.[^.]+$", "", filename)
        stem = re.sub(r"[_\-]+", " ", stem).strip()
        if 2 <= len(stem) <= 60:
            role = stem

    return role or "Software Engineer", organization


# Mapping from extracted SKILL_TAXONOMY / JD keywords onto fixed Question Bank topics
_JD_TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "Machine Learning": (
        "machine learning", "ml", "aiml", "ai/ml", "scikit-learn", "sklearn",
        "xgboost", "lightgbm", "random forest", "supervised learning", "unsupervised",
        "feature engineering", "classification", "regression", "clustering", "data science",
        "statistics", "hypothesis testing", "model evaluation", "mlops", "predictive modeling",
    ),
    "Deep Learning & NLP": (
        "deep learning", "nlp", "natural language processing", "pytorch", "tensorflow",
        "keras", "transformer", "transformers", "llm", "llms", "large language model",
        "rag", "retrieval augmented", "vector database", "chromadb", "faiss", "bert",
        "gpt", "embeddings", "hugging face", "langchain", "computer vision", "opencv",
        "cnn", "rnn", "lstm", "neural network", "generative ai", "genai",
    ),
    "Python": (
        "python", "pandas", "numpy", "scipy", "fastapi", "flask", "django",
        "pydantic", "pytest", "asyncio", "streamlit", "celery",
    ),
    "SQL & Databases": (
        "sql", "mysql", "postgresql", "postgres", "sqlite", "mongodb", "nosql",
        "database", "dbms", "rdbms", "data warehouse", "etl", "indexing", "acid",
        "stored procedure", "query optimization", "redis",
    ),
    "Data Structures & Algorithms": (
        "data structures", "algorithms", "dsa", "problem solving", "leetcode",
        "dynamic programming", "graph", "trees", "coding", "complexity",
    ),
    "System Design": (
        "system design", "distributed systems", "microservices", "scalability",
        "high availability", "load balancer", "caching", "kafka", "message queue",
        "kubernetes", "docker", "aws", "gcp", "azure", "architecture", "cloud",
    ),
    "Web Development": (
        "web development", "frontend", "backend", "full stack", "fullstack", "react",
        "javascript", "typescript", "node.js", "nodejs", "next.js", "html", "css",
        "rest api", "restful", "graphql", "http", "fastapi", "express", "jwt", "oauth",
    ),
    "Object-Oriented Programming": (
        "object-oriented", "oop", "oops", "design patterns", "solid", "java",
        "c++", "cpp", "inheritance", "polymorphism", "encapsulation",
    ),
    "Operating Systems": (
        "operating system", "linux", "unix", "concurrency", "multithreading",
        "process", "thread", "deadlock", "memory management", "kernel", "posix",
    ),
    "Computer Networks": (
        "computer networks", "networking", "tcp", "udp", "http", "https", "dns",
        "tls", "ssl", "ip routing", "load balancing", "cdn", "websocket",
    ),
    "Behavioral & HR": (
        "communication", "leadership", "collaboration", "stakeholder", "ownership",
        "mentoring", "agile", "scrum", "teamwork", "cross-functional",
    ),
}


def get_jd_question_bank_topics(jd_text: str, parsed_role: str = "") -> list[str]:
    """
    Map a candidate's Job Description (and parsed role title) onto the fixed
    11 Question Bank topics, ordered from highest JD relevance to lowest.
    """
    combined = f"{parsed_role or ''}\n{jd_text or ''}".strip()
    if not combined:
        return []

    text_lower = combined.lower()
    scores: dict[str, int] = {}

    for topic, keywords in _JD_TOPIC_RULES.items():
        hits = 0
        for kw in keywords:
            if len(kw) <= 3 or kw.isalpha():
                if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                    hits += 1
            elif kw in text_lower:
                hits += 1
        if hits > 0:
            scores[topic] = hits

    # Boost topics implied by the role title itself
    role_lower = (parsed_role or "").lower()
    role_boosts = {
        ("ai", "ml", "aiml", "machine learning", "nlp", "data scientist"): [
            "Machine Learning", "Deep Learning & NLP", "Python", "SQL & Databases",
        ],
        ("backend", "api", "server"): [
            "Python", "SQL & Databases", "System Design", "Web Development",
        ],
        ("frontend", "ui", "web"): [
            "Web Development",
        ],
        ("full stack", "fullstack"): [
            "Web Development", "Python", "SQL & Databases", "System Design",
        ],
        ("software engineer", "software developer", "sde"): [
            "Data Structures & Algorithms", "Object-Oriented Programming", "System Design", "Python",
        ],
        ("data engineer", "analytics"): [
            "SQL & Databases", "Python", "System Design",
        ],
    }
    for triggers, boosted_topics in role_boosts.items():
        if any(re.search(rf"\b{re.escape(t)}\b", role_lower) or (len(t) > 3 and t in role_lower) for t in triggers):
            for idx, bt in enumerate(boosted_topics):
                scores[bt] = scores.get(bt, 0) + max(1, 3 - idx)

    # Secondary boost via general skill extractor
    profile = extract_skills(combined, "job_description")
    skill_topic_map = {
        "Python": "Python",
        "SQL": "SQL & Databases",
        "Machine Learning": "Machine Learning",
        "Data Science": "Machine Learning",
        "Deep Learning": "Deep Learning & NLP",
        "NLP": "Deep Learning & NLP",
        "Computer Vision": "Deep Learning & NLP",
        "Data Structures & Algorithms": "Data Structures & Algorithms",
        "System Design": "System Design",
        "JavaScript": "Web Development",
        "Java": "Object-Oriented Programming",
        "C/C++": "Object-Oriented Programming",
    }
    for sk in profile.matched_skills:
        mapped = skill_topic_map.get(sk)
        if mapped:
            scores[mapped] = scores.get(mapped, 0) + 1

    # Always return matched topics sorted by descending relevance score
    ordered = [t for t, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ordered
