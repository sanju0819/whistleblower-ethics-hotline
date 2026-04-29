"""
services/groq_client.py
Groq API client with retry logic, exponential backoff, and granular error handling.

Validates the API key at module import time so misconfiguration is caught
at startup rather than on the first live request.
"""

import os
import time
import logging
import requests
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv

# I-8 FIX: Call load_dotenv() here so _GROQ_API_KEY is populated correctly
# regardless of whether groq_client is imported before or after create_app().
# load_dotenv() is idempotent — calling it multiple times is safe.
# Use explicit path so it works regardless of CWD.
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3
RETRY_BACKOFF = (1, 2, 4)  # seconds — tuple for immutability
REQUEST_TIMEOUT = 30  # seconds — named constant for HTTP timeout

# Fix #12: Read and validate at module import time — fail fast on missing key.
# Strip whitespace/newlines that .env files occasionally append.
# NOTE: This is a module-level snapshot.  In containerised deployments, restart
# the container to pick up a rotated key.
_GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()


def call_groq(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    system_message: Optional[str] = None,
) -> str:
    """
    Call the Groq API with retry + exponential backoff.

    Args:
        prompt:         User-role message content (the main prompt).
        temperature:    Sampling temperature (0.0–1.0).
        max_tokens:     Maximum tokens in the response.
        system_message: Optional system-role message prepended to the conversation.
                        Used by the RAG /query endpoint to inject retrieved context.

    Returns:
        The raw text content of the model response.
    Raises:
        RuntimeError if all retries fail or the API key is invalid/missing.
    """
    if not _GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {_GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    last_error: Optional[Exception] = None

    # HI-3 FIX: Use a while loop with an explicit attempt counter so that 429
    # rate-limit responses do NOT consume one of the MAX_RETRIES slots.
    # The old `for attempt, wait in enumerate(RETRY_BACKOFF)` always advanced
    # the iterator even on `continue`, exhausting retries after 3 rate-limits.
    attempt = 0
    while attempt < MAX_RETRIES:
        # Clamp index so it never exceeds the backoff tuple length.
        wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
        logger.debug(
            "Groq API call attempt %d/%d (model=%s, temp=%.1f)",
            attempt + 1, MAX_RETRIES, GROQ_MODEL, temperature,
        )
        try:
            response = requests.post(
                GROQ_API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.debug("Groq call succeeded on attempt %d", attempt + 1)
            return content

        except requests.exceptions.Timeout as exc:
            last_error = exc
            logger.warning("Groq attempt %d timed out, retrying …", attempt + 1)

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (401, 403):
                raise RuntimeError(
                    "Groq API key is invalid or unauthorised."
                ) from exc
            # I-2 FIX: On 429 (rate limited), honour Retry-After and do NOT count
            # this attempt against MAX_RETRIES — retrying too early wastes quota.
            if status == 429:
                try:
                    retry_after = int(
                        exc.response.headers.get("Retry-After", wait)
                    )
                except (ValueError, TypeError):
                    retry_after = wait
                logger.warning(
                    "Groq 429 rate-limited on attempt %d — sleeping %ds (Retry-After)",
                    attempt + 1, retry_after,
                )
                time.sleep(retry_after)
                # Do NOT increment attempt — 429 is not a real failure
                continue
            last_error = exc
            logger.warning(
                "Groq HTTP error %d on attempt %d/%d", status, attempt + 1, MAX_RETRIES
            )

        except requests.exceptions.RequestException as exc:
            last_error = exc
            logger.warning(
                "Groq network error on attempt %d/%d: %s", attempt + 1, MAX_RETRIES, exc
            )

        attempt += 1
        if attempt < MAX_RETRIES:
            time.sleep(wait)

    raise RuntimeError(
        f"Groq API failed after {MAX_RETRIES} attempts: {last_error}"
    )
