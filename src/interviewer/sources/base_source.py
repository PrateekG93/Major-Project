"""
Base Source Interface
======================
Abstract base class for all interview question data source integrations.
Provides robots.txt compliance checks, anti-bot/paywall respect,
exponential backoff retries, rate-limiting, and unified result structures.
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

RATE_LIMIT_SECONDS = float(os.getenv("SCRAPE_RATE_LIMIT_SECONDS", "3"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

ANTI_BOT_MARKERS = (
    "cf-browser-verification",
    "verify you are human",
    "captcha",
    "g-recaptcha",
    "h-captcha",
    "just a moment...",
    "access denied",
)


@dataclass
class RawQuestion:
    """A single question before deduplication and canonical storage."""

    question_text: str
    source_url: str = ""
    role: str = ""
    interview_round: str = "Technical"  # Coding | Technical | HR
    topic: str = ""
    is_technical: bool = True
    difficulty: str = "medium"
    question_type: str = "open_ended"  # open_ended | mcq | coding | hr
    reference_answer: str = ""
    original_wording: str = ""
    reported_at: str = ""
    tags: list[str] = field(default_factory=list)
    collected_at: Optional[float] = None


@dataclass
class ScrapeResult:
    """Result from a single source collection run."""

    questions: list[RawQuestion] = field(default_factory=list)
    pages_scraped: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True


class BaseSource(ABC):
    """
    Abstract base class for modular interview question data sources.

    Enforces:
      - robots.txt compliance check before fetching external URLs
      - Rate limiting between requests
      - Respectful abort on HTTP 403/429/CAPTCHA (never bypasses protections)
      - Exponential backoff retries only on transient errors (5xx / timeout)
    """

    def __init__(self, source_name: str, check_robots: bool = True):
        self.source_name = source_name
        self.check_robots = check_robots
        self._last_request_time: float = 0
        self._robots_cache: dict[str, Optional[RobotFileParser]] = {}

    def _is_allowed_by_robots(self, url: str) -> bool:
        """Check robots.txt for the target URL. Returns True if permitted or robots unreachable."""
        if not self.check_robots:
            return True
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return True
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in self._robots_cache:
                import requests
                rp = RobotFileParser()
                robots_url = f"{origin}/robots.txt"
                try:
                    resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=5)
                    if resp.status_code == 200:
                        rp.parse(resp.text.splitlines())
                        self._robots_cache[origin] = rp
                    else:
                        self._robots_cache[origin] = None
                except Exception:
                    self._robots_cache[origin] = None

            rp = self._robots_cache.get(origin)
            if rp is not None:
                allowed = rp.can_fetch(USER_AGENT, url) or rp.can_fetch("*", url)
                if not allowed:
                    logger.warning(f"[{self.source_name}] Blocked by robots.txt: {url}")
                return allowed
            return True
        except Exception:
            return True

    def _rate_limit(self) -> None:
        """Enforce minimum delay between HTTP requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            sleep_time = RATE_LIMIT_SECONDS - elapsed
            logger.debug(f"[{self.source_name}] Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _safe_request(self, url: str, timeout: int = 15, max_retries: int = 2) -> Optional[str]:
        """
        Make a compliant HTTP GET request with robots.txt check, rate limiting,
        anti-bot detection, and transient retry with exponential backoff.
        """
        import requests

        if not self._is_allowed_by_robots(url):
            return None

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(max_retries + 1):
            self._rate_limit()
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)

                # Never bypass 401/403/429 or anti-bot walls
                if resp.status_code in (401, 403, 429):
                    logger.warning(
                        f"[{self.source_name}] Access restricted (HTTP {resp.status_code}) at {url}. Stopping respectfully."
                    )
                    return None

                if resp.status_code >= 500 and attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"[{self.source_name}] Server error {resp.status_code}, retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue

                resp.raise_for_status()
                body_lower = resp.text[:4000].lower()
                if any(marker in body_lower for marker in ANTI_BOT_MARKERS):
                    logger.warning(f"[{self.source_name}] Anti-bot/CAPTCHA gate detected at {url}. Aborting without bypass.")
                    return None

                logger.info(f"[{self.source_name}] Fetched {url} ({resp.status_code})")
                return resp.text

            except requests.Timeout:
                logger.warning(f"[{self.source_name}] Timeout fetching {url} (attempt {attempt + 1})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except requests.HTTPError as e:
                logger.warning(f"[{self.source_name}] HTTP error fetching {url}: {e}")
                return None
            except requests.ConnectionError as e:
                logger.warning(f"[{self.source_name}] Connection error for {url}: {e}")
                return None
            except Exception as e:
                logger.error(f"[{self.source_name}] Unexpected error fetching {url}: {e}")
                return None

        return None

    @abstractmethod
    def collect_questions(self, topic: str = "", max_pages: int = 3) -> ScrapeResult:
        """Collect interview questions for a given topic or dataset."""
        ...
