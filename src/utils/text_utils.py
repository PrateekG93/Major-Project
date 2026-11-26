"""
Plain-Text & HTML Sanitization Utilities
========================================
Ensures stored interview questions, MCQ options, explanations, and reference
answers remain clean plain text or Markdown without embedded HTML tags/styles.
"""

import html
import re

# Matches opening/closing/self-closing HTML tags and comments: e.g. <div>, </span >, <!-- ... -->
_HTML_TAG_RE = re.compile(r"<!--[\s\S]*?-->|<\/?[a-zA-Z][a-zA-Z0-9:-]*(?:\s+[^<>]*)?\/?>")
_HAS_TAG_NAME_RE = re.compile(r"<\/?[a-zA-Z]")


def strip_html_markup(text: object) -> str:
    """
    Remove HTML tags and inline style markup from text and decode HTML entities,
    preserving clean plain text / Markdown newlines.
    """
    if text is None:
        return ""
    cleaned = str(text)
    if not cleaned:
        return ""

    # Unescape HTML entities up to twice in case content was double-escaped
    for _ in range(2):
        unescaped = html.unescape(cleaned)
        if unescaped == cleaned:
            break
        cleaned = unescaped

    # Replace block/line-break tags with readable whitespace before stripping all tags
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(?:p|div|h[1-6]|li|tr|blockquote)>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)

    # Collapse excess spaces per line while preserving deliberate newlines
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in cleaned.splitlines()]
    lines = [ln for ln in lines if ln]
    result = "\n".join(lines).strip()

    # Final safety pass if unescaping exposed nested tags
    if _HAS_TAG_NAME_RE.search(result):
        result = _HTML_TAG_RE.sub("", result)
        result = re.sub(r"\s+", " ", result).strip()

    return result


def contains_html_tag(text: object) -> bool:
    """Return True if text contains '<' followed by an HTML tag name (e.g. <div>, </span>, <h3>)."""
    if not text:
        return False
    return bool(_HAS_TAG_NAME_RE.search(str(text)))
