"""
Shared utilities used across all route modules.
"""

import os
import re
import json
import html
import copy
import logging
from typing import Dict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Prompt loader ──────────────────────────────────────────────────────────────

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

# Fix #9: Module-level cache — prompts are read from disk only once.
_prompt_cache: Dict[str, str] = {}


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

# Maximum depth for html.unescape loop to prevent infinite loops on
# adversarial input that keeps producing new entities.
_MAX_UNESCAPE_DEPTH = 3

# Patterns that suggest prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(a\s+)?(?:different|new|another)",
    r"forget\s+(everything|all)",
    r"system\s*:\s*",
    r"<\s*/?(?:script|iframe|object|embed|form|img|svg|input|button|link|meta)",
    r"javascript\s*:",
    r"data\s*:\s*text/html",
    r"on\w+\s*=",                          # onerror=, onclick=, etc.
    r"prompt\s*injection",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"override\s+(all\s+)?instructions",
    r"new\s+instructions\s*:",
    r"(\{|\[)\s*\"role\"\s*:",              # JSON role injection
    r"<\|(?:im_start|im_end|endoftext)\|>", # special LLM tokens
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitise_input(text: str) -> str:
    """
    Strip HTML entities and detect prompt injection.
    Returns the cleaned string.
    Raises ValueError if injection is detected.

    HI-7 FIX: Calls html.unescape() in a loop (max 3 iterations) to catch
    double-encoded entities like ``&amp;lt;script&amp;gt;``.
    """
    cleaned = text.strip()
    # Iteratively unescape to handle double/triple-encoded entities
    for _ in range(_MAX_UNESCAPE_DEPTH):
        unescaped = html.unescape(cleaned)
        if unescaped == cleaned:
            break
        cleaned = unescaped
    # Strip residual HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    if _INJECTION_RE.search(cleaned):
        raise ValueError("Input contains potentially malicious content.")
    return cleaned


# ── JSON extraction ────────────────────────────────────────────────────────────

def extract_json(raw: str) -> dict:
    """
    Parse the first balanced JSON object from a raw model response.

    HI-6 FIX: Uses a brace-depth counter that is aware of quoted strings
    so that braces inside JSON string values (e.g. ``{"key": "a {b} c"}``)
    do not break the depth counting.

    Raises ValueError on failure.
    """
    # Remove markdown fences if present
    text = re.sub(r"```(?:json)?", "", raw).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")

    depth = 0
    in_string = False
    escape = False
    end = -1

    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
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


# ── Fallback helper ────────────────────────────────────────────────────────────

def make_fallback(template: dict, generated_at: str) -> dict:
    """
    Create a fallback response by deep-copying the template and injecting
    the generated_at timestamp.  Prevents shallow-copy mutations from leaking
    into module-level FALLBACK_RESPONSE constants.
    """
    fallback = copy.deepcopy(template)
    fallback["generated_at"] = generated_at
    return fallback
