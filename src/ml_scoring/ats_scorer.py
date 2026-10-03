"""
ATS (Applicant Tracking System) Scorer
========================================
Computes resume-vs-JD keyword match score and generates
improvement suggestions to maximize ATS pass rate.
"""

import re
from collections import Counter
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Common ATS keywords by category
ATS_KEYWORD_CATEGORIES = {
    "technical_skills": [
        "python", "java", "javascript", "c++", "sql", "html", "css", "react",
        "angular", "node.js", "django", "flask", "fastapi", "spring", "git",
        "docker", "kubernetes", "aws", "azure", "gcp", "linux", "rest api",
        "graphql", "mongodb", "postgresql", "mysql", "redis", "kafka",
        "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
        "machine learning", "deep learning", "natural language processing",
        "computer vision", "data science", "data engineering", "devops",
        "ci/cd", "agile", "scrum", "microservices", "cloud computing",
    ],
    "soft_skills": [
        "leadership", "communication", "teamwork", "problem solving",
        "analytical", "critical thinking", "project management", "collaboration",
        "adaptability", "time management", "mentoring",
    ],
    "education": [
        "bachelor", "master", "phd", "b.tech", "m.tech", "mba", "bsc", "msc",
        "computer science", "engineering", "mathematics", "statistics",
    ],
    "action_verbs": [
        "developed", "implemented", "designed", "built", "optimized",
        "managed", "led", "achieved", "improved", "reduced", "increased",
        "delivered", "architected", "deployed", "automated", "analyzed",
        "collaborated", "mentored", "created", "engineered",
    ],
}

# Resume section checklist
RECOMMENDED_SECTIONS = [
    "education", "experience", "skills", "projects",
    "certifications", "summary", "objective", "achievements",
]


def _extract_keywords(text: str) -> set[str]:
    """Extract lowercase keywords from text."""
    text = text.lower()
    # Remove special characters but keep meaningful ones
    text = re.sub(r'[^\w\s\.\+\#\-/]', ' ', text)
    words = text.split()
    # Also extract bigrams
    bigrams = {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}
    return set(words) | bigrams


def _extract_jd_requirements(jd_text: str) -> dict:
    """Extract requirements from job description."""
    jd_lower = jd_text.lower()
    jd_keywords = _extract_keywords(jd_text)

    requirements = {
        "technical_skills": [],
        "soft_skills": [],
        "education": [],
        "all_keywords": set(),
    }

    for category, keywords in ATS_KEYWORD_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in jd_lower:
                if category == "technical_skills":
                    requirements["technical_skills"].append(kw)
                elif category == "soft_skills":
                    requirements["soft_skills"].append(kw)
                elif category == "education":
                    requirements["education"].append(kw)
                requirements["all_keywords"].add(kw.lower())

    return requirements


def compute_ats_score(resume_text: str, jd_text: str) -> dict:
    """
    Compute ATS compatibility score between resume and JD.

    Returns:
        Dictionary with score, matched/missing keywords, and breakdown.
    """
    resume_lower = resume_text.lower()
    jd_requirements = _extract_jd_requirements(jd_text)

    all_jd_keywords = jd_requirements["all_keywords"]
    if not all_jd_keywords:
        # If no keywords extracted, use basic word overlap
        jd_words = _extract_keywords(jd_text)
        resume_words = _extract_keywords(resume_text)
        common = jd_words & resume_words
        return {
            "ats_score": min(round(len(common) / max(len(jd_words), 1) * 100, 1), 100),
            "matched_keywords": list(common)[:20],
            "missing_keywords": list(jd_words - resume_words)[:20],
            "technical_match": {},
            "soft_skills_match": {},
            "sections_found": [],
            "sections_missing": [],
        }

    # Check which JD keywords appear in resume
    matched = []
    missing = []
    for kw in all_jd_keywords:
        if kw in resume_lower:
            matched.append(kw)
        else:
            missing.append(kw)

    # Category-specific matching
    tech_matched = [k for k in jd_requirements["technical_skills"] if k.lower() in resume_lower]
    tech_missing = [k for k in jd_requirements["technical_skills"] if k.lower() not in resume_lower]

    soft_matched = [k for k in jd_requirements["soft_skills"] if k.lower() in resume_lower]
    soft_missing = [k for k in jd_requirements["soft_skills"] if k.lower() not in resume_lower]

    # Check resume sections
    sections_found = []
    sections_missing = []
    for section in RECOMMENDED_SECTIONS:
        if section in resume_lower:
            sections_found.append(section)
        else:
            sections_missing.append(section)

    # Check for action verbs
    action_verbs_found = [
        v for v in ATS_KEYWORD_CATEGORIES["action_verbs"]
        if v in resume_lower
    ]

    # Compute score (weighted)
    keyword_score = len(matched) / max(len(all_jd_keywords), 1) * 100
    section_score = len(sections_found) / len(RECOMMENDED_SECTIONS) * 100
    verb_score = min(len(action_verbs_found) / 5 * 100, 100)  # Having 5+ verbs = 100%

    # Check for quantified achievements (numbers in resume)
    has_numbers = len(re.findall(r'\d+%|\d+\+|\$\d+|\d+ years?', resume_lower)) > 0
    quant_score = 100 if has_numbers else 0

    # Weighted ATS score
    ats_score = round(
        keyword_score * 0.50 +  # Keywords match is most important
        section_score * 0.20 +  # Proper sections
        verb_score * 0.15 +     # Action verbs
        quant_score * 0.15,     # Quantified achievements
        1,
    )
    ats_score = min(ats_score, 100)

    return {
        "ats_score": ats_score,
        "keyword_score": round(keyword_score, 1),
        "section_score": round(section_score, 1),
        "verb_score": round(verb_score, 1),
        "quant_score": round(quant_score, 1),
        "matched_keywords": matched,
        "missing_keywords": missing,
        "technical_match": {"found": tech_matched, "missing": tech_missing},
        "soft_skills_match": {"found": soft_matched, "missing": soft_missing},
        "action_verbs_found": action_verbs_found,
        "sections_found": sections_found,
        "sections_missing": sections_missing,
        "has_quantified_achievements": has_numbers,
    }


def generate_resume_suggestions(ats_result: dict, jd_text: str = "") -> list[dict]:
    """
    Generate actionable resume improvement suggestions based on ATS analysis.

    Returns:
        List of suggestion dicts with priority, category, and description.
    """
    suggestions = []

    # Missing technical skills
    tech_missing = ats_result.get("technical_match", {}).get("missing", [])
    if tech_missing:
        suggestions.append({
            "priority": "HIGH",
            "category": "Technical Skills",
            "title": "Add missing technical skills",
            "description": f"Add these skills mentioned in the JD that are missing from your resume: **{', '.join(tech_missing[:8])}**",
            "impact": "This alone can increase your ATS score by 15-30%.",
        })

    # Missing soft skills
    soft_missing = ats_result.get("soft_skills_match", {}).get("missing", [])
    if soft_missing:
        suggestions.append({
            "priority": "MEDIUM",
            "category": "Soft Skills",
            "title": "Incorporate soft skills from JD",
            "description": f"Weave these soft skills into your experience descriptions: **{', '.join(soft_missing[:5])}**",
            "impact": "ATS systems often screen for both technical and soft skills.",
        })

    # Missing sections
    sections_missing = ats_result.get("sections_missing", [])
    if sections_missing:
        important_missing = [s for s in sections_missing if s in ("skills", "experience", "education", "projects")]
        if important_missing:
            suggestions.append({
                "priority": "HIGH",
                "category": "Resume Structure",
                "title": f"Add missing sections: {', '.join(s.capitalize() for s in important_missing)}",
                "description": "Standard ATS-friendly resumes should have clearly labeled sections for Skills, Experience, Education, and Projects.",
                "impact": "ATS parsers look for standard section headers to extract information.",
            })

    # Quantified achievements
    if not ats_result.get("has_quantified_achievements"):
        suggestions.append({
            "priority": "HIGH",
            "category": "Impact Metrics",
            "title": "Quantify your achievements",
            "description": "Add numbers to your accomplishments: '**Improved performance by 30%**', '**Led a team of 5**', '**Reduced costs by $10K**'.",
            "impact": "Quantified achievements stand out to both ATS and human reviewers.",
        })

    # Action verbs
    if len(ats_result.get("action_verbs_found", [])) < 3:
        suggestions.append({
            "priority": "MEDIUM",
            "category": "Language",
            "title": "Use stronger action verbs",
            "description": "Start bullet points with action verbs like: **Developed, Implemented, Architected, Optimized, Deployed, Automated**.",
            "impact": "Action verbs make your contributions clearer and more impactful.",
        })

    # Mirror JD terminology
    if ats_result.get("ats_score", 0) < 60:
        suggestions.append({
            "priority": "HIGH",
            "category": "Keyword Optimization",
            "title": "Mirror the JD's exact terminology",
            "description": "Use the **exact same words and phrases** from the job description. If the JD says 'RESTful APIs', use that phrase — not just 'APIs'.",
            "impact": "ATS systems match exact keywords. Using different synonyms can cause misses.",
        })

    # General tips always
    suggestions.append({
        "priority": "LOW",
        "category": "Formatting",
        "title": "Use a clean, ATS-friendly format",
        "description": "Avoid tables, graphics, headers/footers, and fancy fonts. Use a simple single-column layout with standard section headers.",
        "impact": "Many ATS systems cannot parse complex formatting, columns, or graphics.",
    })

    # Sort by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return suggestions
