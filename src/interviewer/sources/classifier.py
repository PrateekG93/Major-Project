"""
Question Topic & Round Classifier (Fixed 11-Topic Curriculum)
=============================================================
Standardizes topics, rounds, and tags across question ingestion and search
using the fixed 11-topic curriculum aligned with project.tex.
"""

import re
from typing import Tuple

FIXED_TOPICS: tuple[str, ...] = (
    "Data Structures & Algorithms",
    "Python",
    "SQL & Databases",
    "Operating Systems",
    "Computer Networks",
    "Object-Oriented Programming",
    "System Design",
    "Machine Learning",
    "Deep Learning & NLP",
    "Web Development",
    "Behavioral & HR",
)

FIXED_ROUNDS: tuple[str, ...] = ("Coding", "Technical", "HR")

TOPIC_KEYWORD_RULES: list[tuple[str, bool, list[str]]] = [
    ("Data Structures & Algorithms", True, [
        "data structure", "algorithm", "array", "linked list", "stack", "queue",
        "binary tree", "bst", "avl", "red-black", "graph", "hash map", "hash table",
        "sorting", "quicksort", "mergesort", "binary search", "dynamic programming",
        "greedy", "backtracking", "bfs", "dfs", "dijkstra", "heap", "trie",
        "time complexity", "space complexity", "big o", "recursion", "sliding window",
    ]),
    ("Python", True, [
        "python", "gil", "decorator", "generator", "metaclass", "pytest",
        "pydantic", "list", "tuple", "asyncio", "coroutine", "dunder",
    ]),
    ("SQL & Databases", True, [
        "sql", "dbms", "rdbms", "acid", "normalization", "1nf", "2nf", "3nf", "bcnf",
        "join", "index", "b-tree", "b+tree", "transaction", "nosql", "mongodb",
        "postgresql", "mysql", "sharding", "replication", "foreign key", "primary key",
        "window function", "cte", "group by", "having",
    ]),
    ("Operating Systems", True, [
        "operating system", "process", "thread", "deadlock", "mutex", "semaphore",
        "virtual memory", "paging", "segmentation", "scheduling", "context switch",
        "kernel", "system call", "concurrency", "race condition", "thrashing", "inode",
    ]),
    ("Computer Networks", True, [
        "tcp", "udp", "http", "https", "dns", "osi model", "ip address", "subnet",
        "routing", "socket", "tls", "ssl", "handshake", "firewall", "arp", "icmp",
        "packet", "bandwidth", "latency", "computer network", "cidr", "nat",
    ]),
    ("Object-Oriented Programming", True, [
        "oop", "object-oriented", "polymorphism", "inheritance", "encapsulation",
        "abstraction", "interface", "abstract class", "overloading", "overriding",
        "solid principles", "constructor", "destructor", "virtual function",
        "singleton", "factory pattern", "design pattern",
    ]),
    ("System Design", True, [
        "system design", "scalability", "microservices", "load balancer", "caching",
        "redis", "kafka", "message queue", "distributed", "cap theorem",
        "consistent hashing", "rate limiter", "cdn", "api gateway", "availability",
        "fault tolerance", "url shortener",
    ]),
    ("Machine Learning", True, [
        "machine learning", "supervised", "unsupervised", "regression", "classification",
        "clustering", "random forest", "xgboost", "gradient boosting", "decision tree",
        "svm", "bias-variance", "overfitting", "regularization", "ridge", "lasso",
        "cross-validation", "pca", "k-means", "precision", "recall", "f1 score", "roc",
        "eda", "exploratory data", "hypothesis testing",
    ]),
    ("Deep Learning & NLP", True, [
        "deep learning", "neural network", "transformer", "attention mechanism",
        "llm", "rag", "retrieval-augmented", "bert", "gpt", "cnn", "rnn", "lstm",
        "backpropagation", "relu", "vanishing gradient", "nlp", "word2vec", "glove",
        "tokenization", "tf-idf", "embedding", "computer vision", "bert", "batch norm",
    ]),
    ("Web Development", True, [
        "html", "css", "javascript", "typescript", "react", "angular", "vue",
        "node.js", "express", "rest api", "graphql", "cors", "dom", "jwt",
        "session", "cookie", "browser", "frontend", "backend", "fastapi", "django",
        "flask", "xss", "csrf", "websocket",
    ]),
    ("Behavioral & HR", False, [
        "tell me about yourself", "why do you want", "strengths", "weaknesses",
        "conflict", "teamwork", "challenging project", "mistake", "failure",
        "deadline", "pressure", "leadership", "disagreement", "star method",
        "tell me about a time", "describe a situation", "handle criticism",
        "stakeholder", "career goal", "salary",
    ]),
]

LEGACY_TOPIC_MAP: dict[str, str] = {
    "data structures & algorithms": "Data Structures & Algorithms",
    "data structures and algorithms": "Data Structures & Algorithms",
    "dsa": "Data Structures & Algorithms",
    "aptitude": "Data Structures & Algorithms",
    "logical reasoning": "Data Structures & Algorithms",
    "python": "Python",
    "programming languages": "Python",
    "sql": "SQL & Databases",
    "dbms": "SQL & Databases",
    "databases": "SQL & Databases",
    "database management systems": "SQL & Databases",
    "sql & databases": "SQL & Databases",
    "operating systems": "Operating Systems",
    "computer networks": "Computer Networks",
    "object-oriented programming": "Object-Oriented Programming",
    "oop": "Object-Oriented Programming",
    "software engineering": "Object-Oriented Programming",
    "system design": "System Design",
    "machine learning": "Machine Learning",
    "data science": "Machine Learning",
    "deep learning": "Deep Learning & NLP",
    "nlp": "Deep Learning & NLP",
    "artificial intelligence": "Deep Learning & NLP",
    "computer vision": "Deep Learning & NLP",
    "deep learning & nlp": "Deep Learning & NLP",
    "web development": "Web Development",
    "hr questions": "Behavioral & HR",
    "behavioral questions": "Behavioral & HR",
    "communication": "Behavioral & HR",
    "behavioral & hr": "Behavioral & HR",
    "behavioral/hr": "Behavioral & HR",
    "hr": "Behavioral & HR",
}


def normalize_topic(raw_topic: str = "", raw_category: str = "", question_text: str = "") -> str:
    """Map any legacy topic/category into the fixed 11-topic list."""
    for cand in (raw_topic, raw_category):
        key = (cand or "").strip().lower()
        if key in LEGACY_TOPIC_MAP:
            return LEGACY_TOPIC_MAP[key]
        for fixed in FIXED_TOPICS:
            if key == fixed.lower():
                return fixed
    if question_text:
        inferred, _, _ = classify_question(question_text)
        return inferred
    return "Data Structures & Algorithms"


def classify_round(text: str = "", topic: str = "", hint_round: str = "") -> str:
    """Normalize round into one of: Coding, Technical, HR."""
    combined_hint = (hint_round or "").strip().lower()
    if combined_hint in ("hr", "behavioral", "behavioural"):
        return "HR"
    if combined_hint in ("coding", "code"):
        return "Coding"
    if combined_hint == "technical":
        return "Technical"

    if topic == "Behavioral & HR":
        return "HR"

    t_lower = (text or "").lower()
    if any(w in t_lower for w in ("behavioral", "behavioural", "tell me about a time", "conflict", "weakness")):
        return "HR"
    if any(w in t_lower for w in ("implement", "write a function", "write a sql", "find the", "reverse a", "detect a cycle", "time complexity")):
        return "Coding"
    return "Technical"


def classify_question(question_text: str, hint_round: str = "") -> Tuple[str, bool, list[str]]:
    """
    Classify question into (topic, is_technical, tags) within the fixed 11-topic curriculum.
    """
    q_lower = (question_text or "").lower()
    for topic, is_tech, keywords in TOPIC_KEYWORD_RULES:
        matched_kws = []
        for kw in keywords:
            if len(kw) <= 3:
                if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                    matched_kws.append(kw)
            elif kw in q_lower:
                matched_kws.append(kw)
        if matched_kws:
            return topic, is_tech, sorted(set(matched_kws[:4]))

    if (hint_round or "").strip().lower() in ("hr", "behavioral"):
        return "Behavioral & HR", False, ["behavioral"]

    return "Object-Oriented Programming", True, ["software"]
