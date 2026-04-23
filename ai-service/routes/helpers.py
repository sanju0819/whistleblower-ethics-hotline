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


def load_prompt(filename: str) -> str:
    """Read a prompt template from the prompts/ directory."""
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


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
    Attempt to parse a JSON object from a raw model response.
    Handles cases where the model wraps output in markdown fences.
    Returns the parsed dict or raises ValueError on failure.
    """
    # Remove markdown fences if present
    text = re.sub(r"```(?:json)?", "", raw).strip()
    # Find the first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response.")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON from model response: {exc}") from exc
