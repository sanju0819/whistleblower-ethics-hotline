"""
Shared utilities used across all route modules.
"""

import os
import re
import json
import html
import logging

logger = logging.getLogger(__name__)

# ── Prompt loader ──────────────────────────────────────────────────────────────

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

# Fix #9: Module-level cache — prompts are read from disk only once.
_prompt_cache: dict[str, str] = {}


def load_prompt(filename: str) -> str:
    """
    Read a prompt template from the prompts/ directory.
    Results are cached in memory after the first read — prompts never change at runtime.
    """
    if filename not in _prompt_cache:
        path = os.path.join(PROMPTS_DIR, filename)
        with open(path, "r", encoding="utf-8") as fh:
            _prompt_cache[filename] = fh.read()
    return _prompt_cache[filename]


# ── Input sanitisation ─────────────────────────────────────────────────────────

# Patterns that suggest prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(a\s+)?(?:different|new|another)",
    r"forget\s+(everything|all)",
    r"system\s*:\s*",
    r"<\s*/?(?:script|iframe|object|embed|form)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitise_input(text: str) -> str:
    """
    Strip HTML entities and detect prompt injection.
    Returns the cleaned string.
    Raises ValueError if injection is detected.
    """
    cleaned = html.unescape(text).strip()
    # Strip residual HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    if _INJECTION_RE.search(cleaned):
        raise ValueError("Input contains potentially malicious content.")
    return cleaned


# ── JSON extraction ────────────────────────────────────────────────────────────

def extract_json(raw: str) -> dict:
    """
    Parse the first balanced JSON object from a raw model response.

    Fix #13: Uses a brace-depth counter instead of a greedy regex so nested
    objects and multiple JSON blobs in one response are handled correctly.

    Raises ValueError on failure.
    """
    # Remove markdown fences if present
    text = re.sub(r"```(?:json)?", "", raw).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")

    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        raise ValueError("Unbalanced JSON braces in model response.")

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON from model response: {exc}") from exc
