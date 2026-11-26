"""
Build & Validate the Centralized Interview Question Bank
========================================================
Generates original, non-duplicate interview questions aligned to the courses
and skills in project.tex across a fixed 11-topic taxonomy:

  - 200 unique questions per topic (2,200 total)
  - Exact split per topic: 40 easy (20%), 100 medium (50%), 60 hard (30%)
  - Plain text / Markdown only (never HTML)
  - Idempotent checkpointed generation + global normalized & lexical dedup
  - Saves output to data/question_bank/questions.json and optionally seeds SQLite

Usage:
  python scripts/build_question_bank.py            # Build & validate JSON (resumes idempotently)
  python scripts/build_question_bank.py --seed     # Build, validate, and seed SQLite database
  python scripts/build_question_bank.py --rebuild  # Regenerate from scratch
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.text_utils import contains_html_tag, strip_html_markup  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_PATH = Path(
    os.getenv("QUESTION_BANK_PATH", str(PROJECT_ROOT / "data" / "question_bank" / "questions.json"))
)
SEED_BATCHES_DIR = PROJECT_ROOT / "scripts" / "seed_batches"

TARGET_COUNTS = {"easy": 40, "medium": 100, "hard": 60}
TOTAL_PER_TOPIC = sum(TARGET_COUNTS.values())  # 200
VALID_ROUNDS = ("Coding", "Technical", "HR")

# Fixed 11-topic curriculum aligned with project.tex and course pack
TOPIC_CURRICULUM: dict[str, dict] = {
    "Data Structures & Algorithms": {
        "is_technical": True,
        "default_round": "Coding",
        "allowed_rounds": ("Coding", "Technical"),
        "subtopics": [
            "Arrays and Two Pointers",
            "Strings and Sliding Window",
            "Singly and Doubly Linked Lists",
            "Stacks and Monotonic Stacks",
            "Queues, Deques, and Priority Queues / Heaps",
            "Hash Tables and Collision Handling",
            "Binary Trees and Binary Search Trees",
            "AVL Trees, Tries, and Segment Trees",
            "Graphs, BFS/DFS, Topological Sort, and Shortest Paths",
            "Dynamic Programming, Greedy Algorithms, and Backtracking",
        ],
    },
    "Python": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Coding", "Technical"),
        "subtopics": [
            "Built-in Data Types, Lists, Tuples, Sets, and Dicts",
            "Mutability, Shallow vs Deep Copy, and Object Identity",
            "Functions, Closures, Scope (LEGB), and Lambda Expressions",
            "Decorators and Higher-Order Functions",
            "Generators, Iterators, Yield, and Comprehensions",
            "Object Model, Dunder Methods, and Metaclasses",
            "Memory Management, Reference Counting, and Cyclic GC",
            "Multithreading, Multiprocessing, and the GIL",
            "Asyncio, Coroutines, and Event Loops",
            "Context Managers, Exception Handling, Dataclasses, and Typing",
        ],
    },
    "SQL & Databases": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Coding", "Technical"),
        "subtopics": [
            "SELECT Queries, Filtering, and NULL Semantics",
            "INNER, LEFT, RIGHT, FULL, and Self JOINs",
            "GROUP BY, HAVING, and Aggregate Functions",
            "Window Functions (ROW_NUMBER, RANK, LAG/LEAD) and CTEs",
            "Subqueries, EXISTS vs IN, and Set Operations",
            "Database Normalization (1NF, 2NF, 3NF, BCNF) and Denormalization",
            "ER Modeling, Keys, Referential Integrity, and Constraints",
            "B+Tree vs Hash Indexes and Composite Index Design",
            "ACID Transactions, Locks, Deadlocks, and Isolation Levels",
            "Query Execution Plans (EXPLAIN), Sharding, and Partitioning",
        ],
    },
    "Operating Systems": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical", "Coding"),
        "subtopics": [
            "Kernel Mode vs User Mode and System Calls",
            "Process States, PCB, Fork, and Exec",
            "Threads, User-Level vs Kernel-Level Threads, and Context Switching",
            "CPU Scheduling Algorithms (FCFS, SJF, RR, MLFQ)",
            "Critical Section, Race Conditions, Mutexes, and Semaphores",
            "Classic Synchronization Problems (Producer-Consumer, Readers-Writers)",
            "Deadlock Conditions, Banker's Algorithm, and Recovery",
            "Paging, Segmentation, TLB, and Multi-Level Page Tables",
            "Virtual Memory, Demand Paging, Page Faults, and Thrashing",
            "File Systems, Inodes, Buffering, and I/O Scheduling",
        ],
    },
    "Computer Networks": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical",),
        "subtopics": [
            "OSI 7-Layer and TCP/IP 4-Layer Reference Models",
            "Ethernet, Switching, ARP, and MAC Addressing",
            "IPv4, IPv6, CIDR Subnetting, and NAT",
            "Routing Protocols (Distance Vector, Link State, OSPF, BGP)",
            "TCP vs UDP Reliability and Header Mechanics",
            "TCP 3-Way Handshake, Flow Control, and Congestion Control",
            "DNS Resolution Hierarchy and DHCP",
            "HTTP/1.1, HTTP/2, HTTP/3, Keep-Alive, and Multiplexing",
            "TLS/SSL Handshake, Certificates, and HTTPS Security",
            "Load Balancers, Proxies, CDNs, and Socket Programming",
        ],
    },
    "Object-Oriented Programming": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical", "Coding"),
        "subtopics": [
            "Classes, Objects, Constructors, and Destructors",
            "Encapsulation, Information Hiding, and Access Modifiers",
            "Inheritance, Method Resolution Order (MRO), and Diamond Problem",
            "Compile-Time Overloading vs Runtime Polymorphism / Vtables",
            "Abstract Classes vs Interfaces and Mixins",
            "Composition vs Inheritance and Association/Aggregation",
            "SOLID Design Principles (SRP, OCP, LSP, ISP, DIP)",
            "Creational Patterns (Singleton, Factory, Abstract Factory, Builder)",
            "Structural Patterns (Adapter, Decorator, Facade, Proxy)",
            "Behavioral Patterns (Observer, Strategy, Command, Iterator)",
        ],
    },
    "System Design": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical",),
        "subtopics": [
            "Vertical vs Horizontal Scaling and Latency vs Throughput",
            "DNS, CDN, Edge Caching, and Static Asset Delivery",
            "L4 vs L7 Load Balancing Algorithms and Health Checks",
            "Distributed Caching, Eviction Policies (LRU/LFU), and Cache Invalidation",
            "Database Replication (Leader-Follower, Multi-Leader) and Sharding",
            "CAP Theorem, PACELC, and Strong vs Eventual Consistency",
            "Consistent Hashing, Virtual Nodes, and Distributed ID Generators",
            "Message Queues, Event Streams (Kafka), and Backpressure",
            "Rate Limiting, API Gateways, Idempotency, and Circuit Breakers",
            "End-to-End Architecture (URL Shortener, Chat, News Feed, Search)",
        ],
    },
    "Machine Learning": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical", "Coding"),
        "subtopics": [
            "Supervised, Unsupervised, and Semi-Supervised Learning",
            "Bias-Variance Tradeoff, Overfitting, and Underfitting",
            "Linear Regression, Gradient Descent, and Feature Scaling",
            "Logistic Regression, Decision Boundaries, and Loss Functions",
            "Regularization (L1 Lasso, L2 Ridge, ElasticNet) and Feature Selection",
            "Decision Trees (Gini, Entropy) and Pruning",
            "Bagging and Random Forest Ensembles",
            "Gradient Boosting, XGBoost, and Hyperparameter Tuning",
            "Support Vector Machines, Kernel Trick, and k-NN",
            "Clustering (K-Means, Hierarchical, DBSCAN), PCA, and Evaluation Metrics",
        ],
    },
    "Deep Learning & NLP": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Technical", "Coding"),
        "subtopics": [
            "Neurons, Activation Functions (ReLU, GELU, Sigmoid, Softmax)",
            "Backpropagation, Chain Rule, and Vanishing/Exploding Gradients",
            "Optimizers (SGD, Momentum, RMSProp, AdamW) and LR Schedules",
            "Batch Normalization, Layer Normalization, Dropout, and Residual Skip Connections",
            "Convolutional Neural Networks (CNNs), Pooling, and Computer Vision",
            "Sequential Models: RNNs, LSTMs, GRUs, and Seq2Seq",
            "Text Preprocessing: Tokenization (BPE/WordPiece), Stemming, and TF-IDF",
            "Word and Sentence Embeddings (Word2Vec, GloVe, SBERT Cosine Similarity)",
            "Transformers, Scaled Dot-Product Self-Attention, BERT vs GPT",
            "Retrieval-Augmented Generation (RAG), Hybrid BM25+Dense, RRF, and Reranking",
        ],
    },
    "Web Development": {
        "is_technical": True,
        "default_round": "Technical",
        "allowed_rounds": ("Coding", "Technical"),
        "subtopics": [
            "Semantic HTML, Accessibility (ARIA), and Browser Rendering Pipeline",
            "CSS Box Model, Flexbox, CSS Grid, and Responsive Design",
            "JavaScript Event Loop, Microtasks, Closures, and Prototypes",
            "Promises, Async/Await, Fetch API, and Error Boundaries",
            "REST API Principles, HTTP Methods, Idempotency, and Status Codes",
            "Authentication & Authorization: JWT, Session Cookies, OAuth2",
            "Web Security: CORS, CSRF, XSS, SQL Injection, and Input Validation",
            "FastAPI / Python Web Backends, Dependency Injection, and Validation",
            "GraphQL vs REST, WebSockets, and Server-Sent Events",
            "Caching Headers (ETag, Cache-Control), Compression, and Deployment",
        ],
    },
    "Behavioral & HR": {
        "is_technical": False,
        "default_round": "HR",
        "allowed_rounds": ("HR",),
        "subtopics": [
            "Self-Introduction, Academic Background, and Role Alignment",
            "STAR Framework and Explaining Complex Projects Concisely",
            "Cross-Functional Teamwork and Knowledge Sharing",
            "Handling Technical Disagreements and Code Review Conflict",
            "Working Under Tight Deadlines and Prioritizing Scope",
            "Owning Mistakes, Production Bugs, and Learning from Failure",
            "Receiving Critical Feedback and Iterating Quickly",
            "Demonstrating Initiative, Ownership, and Mentoring Peers",
            "Navigating Ambiguity and Learning Unfamiliar Stacks Rapidly",
            "Communication with Non-Technical Stakeholders and Career Goals",
        ],
    },
}


def normalize_question_text(text: str) -> str:
    """Normalize text for exact + near-duplicate checks."""
    t = strip_html_markup(text).lower().strip()
    t = re.sub(r"^(?:q\d*[\.\):\s]+|question\s*\d*[\.\):\s]+)", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def fingerprint_text(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _clean_round(raw_round: str, topic: str) -> str:
    cfg = TOPIC_CURRICULUM[topic]
    allowed = cfg["allowed_rounds"]
    r = (raw_round or "").strip().lower()
    if r == "hr" and "HR" in allowed:
        return "HR"
    if r == "coding" and "Coding" in allowed:
        return "Coding"
    if r == "technical" and "Technical" in allowed:
        return "Technical"
    return cfg["default_round"]


def _get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        raise RuntimeError("GROQ_API_KEY must be configured in .env to generate question batches.")
    from groq import Groq
    return Groq(api_key=api_key)


import itertools
import threading

_MODEL_POOL = [
    "qwen/qwen3.8-27b",
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b"),
]
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {m: 0.0 for m in _MODEL_POOL}
_MODEL_RR_IDX = 0
_CYCLE_LOCK = threading.Lock()
_SAVE_LOCK = threading.Lock()


def _pick_available_model() -> str:
    """Pick the next model not currently in rate-limit cooldown, waiting only the shortest reset window."""
    global _MODEL_RR_IDX
    while True:
        with _CYCLE_LOCK:
            now = time.time()
            for offset in range(len(_MODEL_POOL)):
                idx = (_MODEL_RR_IDX + offset) % len(_MODEL_POOL)
                m = _MODEL_POOL[idx]
                if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now:
                    _MODEL_RR_IDX = (idx + 1) % len(_MODEL_POOL)
                    return m
            earliest = min(_MODEL_COOLDOWN_UNTIL.values())
            wait_s = max(0.5, min(25.0, earliest - now))
        time.sleep(wait_s)


def _mark_model_cooldown(model_id: str, seconds: float) -> None:
    with _CYCLE_LOCK:
        _MODEL_COOLDOWN_UNTIL[model_id] = max(_MODEL_COOLDOWN_UNTIL.get(model_id, 0.0), time.time() + seconds)


def _call_batch_llm(topic: str, difficulty: str, subtopics: list[str], count: int, existing_samples: list[str]) -> list[dict]:
    """Request one batch of distinct original questions using cooldown-aware Groq rotation."""
    client = _get_groq_client()
    cfg = TOPIC_CURRICULUM[topic]
    rounds_str = " or ".join(cfg["allowed_rounds"])
    avoid_snippet = ""
    if existing_samples:
        sample_lines = "; ".join(s[:55] for s in existing_samples[-15:])
        avoid_snippet = f"\nAlready covered (do NOT repeat/reword): {sample_lines}\n"

    diff_guidance = {
        "easy": "foundational concepts, clear definitions, core mechanics",
        "medium": "practical trade-offs, scenario reasoning, comparisons",
        "hard": "deep internals, tricky edge cases, scalability/rigor",
    }[difficulty]

    prompt = (
        f"Generate {count} DISTINCT original '{difficulty.upper()}' interview questions for '{topic}'.\n"
        f"Subtopics: {'; '.join(subtopics)}. Depth: {diff_guidance}.\n"
        f"Rules: Plain text/Markdown ONLY (NO HTML); NO company/website names; NO near-duplicates.\n"
        f'Return ONLY raw JSON array: [{{"question_text":"...","reference_answer":"1 crisp technical sentence","round":"{rounds_str.split(" or ")[0]}","tags":["t1","t2"]}}]'
        f" (round in [{rounds_str}]).{avoid_snippet}"
    )

    for attempt in range(8):
        model_id = _pick_available_model()
        try:
            kwargs = dict(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1900,
            )
            if "gpt-oss" in model_id:
                kwargs["reasoning_effort"] = "low"
            resp = client.chat.completions.create(**kwargs)
            raw = (resp.choices[0].message.content or "").strip()
            s, e = raw.find("["), raw.rfind("]") + 1
            if s != -1 and e > s:
                parsed = json.loads(raw[s:e])
                if isinstance(parsed, list) and parsed:
                    return parsed
            _mark_model_cooldown(model_id, 2.0)
        except Exception as exc:
            err_str = str(exc)
            m_min_sec = re.search(r"try again in\s*(?:(\d+)m)?([\d.]+)s", err_str, re.IGNORECASE)
            if m_min_sec:
                mins = int(m_min_sec.group(1) or 0)
                secs = float(m_min_sec.group(2))
                wait_s = mins * 60 + secs + 1.0
            else:
                wait_s = 20.0 if ("429" in err_str or "rate" in err_str.lower()) else 4.0
            _mark_model_cooldown(model_id, min(120.0, wait_s))
            print(f"    [cooldown {model_id} {wait_s:.1f}s] {topic}/{difficulty}", flush=True)
    return []


def _is_valid_unique(
    cand: dict,
    topic: str,
    global_norms: set[str],
    topic_norms: list[str],
) -> tuple[bool, dict | None]:
    q_text = strip_html_markup(cand.get("question_text", ""))
    ref_ans = strip_html_markup(cand.get("reference_answer", ""))
    if not q_text or len(q_text) < 18 or len(q_text.split()) < 4:
        return False, None
    if contains_html_tag(q_text) or contains_html_tag(ref_ans):
        return False, None
    if not ref_ans or len(ref_ans) < 15:
        return False, None

    norm = normalize_question_text(q_text)
    if not norm or norm in global_norms:
        return False, None

    # Reject near-duplicate wording inside the same topic (SequenceMatcher >= 0.84)
    for existing in topic_norms:
        if abs(len(existing) - len(norm)) > max(len(norm), len(existing)) * 0.30:
            continue
        if SequenceMatcher(None, norm, existing).ratio() >= 0.84:
            return False, None

    tags = cand.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
    clean_tags = [strip_html_markup(str(t)).lower() for t in tags if str(t).strip()][:5]
    if not clean_tags:
        clean_tags = [topic.lower()]

    item = {
        "question_text": q_text,
        "topic": topic,
        "difficulty": "",  # set by caller
        "round": _clean_round(cand.get("round", ""), topic),
        "reference_answer": ref_ans,
        "tags": clean_tags,
        "is_technical": TOPIC_CURRICULUM[topic]["is_technical"],
        "normalized_text": norm,
    }
    return True, item


def _load_existing_bank(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        cleaned = []
        seen = set()
        for row in data:
            topic = row.get("topic", "").strip()
            diff = row.get("difficulty", "").strip().lower()
            if topic not in TOPIC_CURRICULUM or diff not in TARGET_COUNTS:
                continue
            qt = strip_html_markup(row.get("question_text", ""))
            ra = strip_html_markup(row.get("reference_answer", ""))
            if not qt or not ra or contains_html_tag(qt) or contains_html_tag(ra):
                continue
            norm = normalize_question_text(qt)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            cleaned.append({
                "question_text": qt,
                "topic": topic,
                "difficulty": diff,
                "round": _clean_round(row.get("round", ""), topic),
                "reference_answer": ra,
                "tags": [str(t).lower() for t in (row.get("tags") or [topic.lower()])][:5],
                "is_technical": TOPIC_CURRICULUM[topic]["is_technical"],
                "normalized_text": norm,
            })
        return cleaned
    except Exception:
        return []


def _save_bank(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for idx, q in enumerate(items, 1):
        serializable.append({
            "id": f"qb_{idx:04d}",
            "question_text": q["question_text"],
            "topic": q["topic"],
            "difficulty": q["difficulty"],
            "round": q["round"],
            "reference_answer": q["reference_answer"],
            "tags": q["tags"],
            "is_technical": q["is_technical"],
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)


def _generate_for_topic_slice(
    topic: str,
    by_topic_ref: dict[str, list[dict]],
    global_norms: set[str],
) -> list[dict]:
    """Generate remaining easy/medium/hard questions in targeted subtopic batches, saving after every batch."""
    subtopics = TOPIC_CURRICULUM[topic]["subtopics"]
    collected: list[dict] = list(by_topic_ref[topic])
    topic_norms = [q["normalized_text"] for q in collected]

    for diff in ("easy", "medium", "hard"):
        target = TARGET_COUNTS[diff]
        have = sum(1 for q in collected if q["difficulty"] == diff)
        if have >= target:
            continue

        st_idx = 0
        max_rounds = 18
        rounds_run = 0
        while have < target and rounds_run < max_rounds:
            rounds_run += 1
            remaining = target - have
            ask_n = min(18, remaining + 4)
            batch_subtopics = [subtopics[(st_idx + j) % len(subtopics)] for j in range(min(5, len(subtopics)))]
            st_idx = (st_idx + 5) % len(subtopics)

            existing_diff_qs = [q["question_text"] for q in collected if q["difficulty"] == diff]
            raw_batch = _call_batch_llm(topic, diff, batch_subtopics, ask_n, existing_diff_qs)

            added_this_round = 0
            with _SAVE_LOCK:
                for cand in raw_batch:
                    if have >= target:
                        break
                    ok, clean_item = _is_valid_unique(cand, topic, global_norms, topic_norms)
                    if ok and clean_item is not None:
                        clean_item["difficulty"] = diff
                        collected.append(clean_item)
                        global_norms.add(clean_item["normalized_text"])
                        topic_norms.append(clean_item["normalized_text"])
                        have += 1
                        added_this_round += 1
                by_topic_ref[topic] = list(collected)
                merged = [q for t_name in TOPIC_CURRICULUM for q in by_topic_ref[t_name]]
                _save_bank(OUTPUT_PATH, merged)
            print(f"  [{topic} | {diff}] +{added_this_round} -> {have}/{target} (total saved: {len(merged)})", flush=True)

    return collected


def validate_and_summarize(items: list[dict]) -> dict[str, dict[str, int]]:
    """
    Validate exact per-topic and per-difficulty counts plus zero HTML/duplicates.
    Fails loudly if any topic falls short.
    """
    seen_norms: set[str] = set()
    counts: dict[str, dict[str, int]] = {
        t: {"easy": 0, "medium": 0, "hard": 0, "total": 0}
        for t in TOPIC_CURRICULUM
    }

    for q in items:
        topic = q["topic"]
        diff = q["difficulty"]
        if topic not in counts or diff not in TARGET_COUNTS:
            raise ValueError(f"Invalid topic/difficulty entry: {topic} / {diff}")
        if contains_html_tag(q["question_text"]) or contains_html_tag(q["reference_answer"]):
            raise ValueError(f"HTML tag detected in question: {q['question_text'][:80]}")
        norm = normalize_question_text(q["question_text"])
        if norm in seen_norms:
            raise ValueError(f"Duplicate question normalized_text found: {q['question_text'][:80]}")
        seen_norms.add(norm)
        counts[topic][diff] += 1
        counts[topic]["total"] += 1

    shortfalls = []
    for topic, c in counts.items():
        for diff, req in TARGET_COUNTS.items():
            if c[diff] != req:
                shortfalls.append(f"{topic} ({diff}: {c[diff]}/{req})")

    if shortfalls:
        raise RuntimeError(
            "Question bank validation failed! Topic/difficulty target mismatch:\n  - "
            + "\n  - ".join(shortfalls)
        )
    return counts


def print_summary_table(counts: dict[str, dict[str, int]]) -> None:
    print("\n" + "=" * 72)
    print(f"{'TOPIC':<32} | {'EASY':>6} | {'MEDIUM':>6} | {'HARD':>6} | {'TOTAL':>6}")
    print("-" * 72)
    tot_e = tot_m = tot_h = tot_all = 0
    for topic, c in counts.items():
        print(f"{topic:<32} | {c['easy']:>6} | {c['medium']:>6} | {c['hard']:>6} | {c['total']:>6}")
        tot_e += c["easy"]
        tot_m += c["medium"]
        tot_h += c["hard"]
        tot_all += c["total"]
    print("-" * 72)
    print(f"{'TOTAL':<32} | {tot_e:>6} | {tot_m:>6} | {tot_h:>6} | {tot_all:>6}")
    print("=" * 72 + "\n")


def _load_seed_batches(batch_dir: Path) -> list[dict]:
    """Load curated question batches stored under scripts/seed_batches/*.json."""
    if not batch_dir.exists():
        return []
    rows: list[dict] = []
    for p in sorted(batch_dir.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        rows.append(item)
        except Exception as exc:
            print(f"[WARN] Could not parse seed batch {p.name}: {exc}", flush=True)
    return rows


def build_question_bank(
    rebuild: bool = False,
    seed_db: bool = False,
    workers: int = 3,
    use_llm: bool = True,
) -> dict[str, dict[str, int]]:
    existing = [] if rebuild else _load_existing_bank(OUTPUT_PATH)

    by_topic: dict[str, list[dict]] = {t: [] for t in TOPIC_CURRICULUM}
    for q in existing:
        t = q["topic"]
        d = q["difficulty"]
        have_d = sum(1 for x in by_topic[t] if x["difficulty"] == d)
        if have_d < TARGET_COUNTS[d]:
            by_topic[t].append(q)

    global_norms = {q["normalized_text"] for lst in by_topic.values() for q in lst}
    topic_norms_map: dict[str, list[str]] = {
        t: [q["normalized_text"] for q in by_topic[t]] for t in TOPIC_CURRICULUM
    }

    # Deterministically merge curated batch files (idempotent across reruns)
    for cand in _load_seed_batches(SEED_BATCHES_DIR):
        t = str(cand.get("topic", "")).strip()
        d = str(cand.get("difficulty", "")).strip().lower()
        if t not in TOPIC_CURRICULUM or d not in TARGET_COUNTS:
            continue
        have_d = sum(1 for x in by_topic[t] if x["difficulty"] == d)
        if have_d >= TARGET_COUNTS[d]:
            continue
        ok, clean_item = _is_valid_unique(cand, t, global_norms, topic_norms_map[t])
        if ok and clean_item is not None:
            clean_item["difficulty"] = d
            by_topic[t].append(clean_item)
            global_norms.add(clean_item["normalized_text"])
            topic_norms_map[t].append(clean_item["normalized_text"])

    incomplete_topics = [
        t for t in TOPIC_CURRICULUM
        if any(sum(1 for x in by_topic[t] if x["difficulty"] == d) < req for d, req in TARGET_COUNTS.items())
    ]

    if incomplete_topics and use_llm:
        print(f"Generating questions for {len(incomplete_topics)} topic(s) using {workers} worker(s)...", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(_generate_for_topic_slice, t, by_topic, global_norms): t
                for t in incomplete_topics
            }
            for fut in as_completed(futs):
                t = futs[fut]
                by_topic[t] = fut.result()
                print(f"[DONE TOPIC] {t} ({len(by_topic[t])}/{TOTAL_PER_TOPIC})", flush=True)

        # Top up sequentially if any topic fell short
        for t in TOPIC_CURRICULUM:
            if any(sum(1 for x in by_topic[t] if x["difficulty"] == d) < req for d, req in TARGET_COUNTS.items()):
                by_topic[t] = _generate_for_topic_slice(t, by_topic, global_norms)

    final_items = [q for t_name in TOPIC_CURRICULUM for q in by_topic[t_name]]
    _save_bank(OUTPUT_PATH, final_items)

    counts = validate_and_summarize(final_items)
    print_summary_table(counts)

    if seed_db:
        from src.interviewer.scraper_pipeline import seed_question_bank
        seeded = seed_question_bank(str(OUTPUT_PATH), replace=True)
        print(f"Seeded SQLite database with {seeded} validated canonical questions.")

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build & validate the 11-topic interview question bank.")
    parser.add_argument("--rebuild", action="store_true", help="Regenerate the entire dataset from scratch")
    parser.add_argument("--seed", action="store_true", help="Seed SQLite database from generated dataset")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent topic generation workers")
    parser.add_argument("--no-llm", action="store_true", help="Validate/merge curated batches without calling Groq LLM")
    args = parser.parse_args()
    build_question_bank(rebuild=args.rebuild, seed_db=args.seed, workers=args.workers, use_llm=not args.no_llm)
