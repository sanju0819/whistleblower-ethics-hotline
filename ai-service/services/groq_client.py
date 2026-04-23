import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds


def call_groq(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """
    Call the Groq API with retry + exponential backoff.
    Returns the raw text content of the model response.
    Raises RuntimeError if all retries fail.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    last_error = None
    for attempt, wait in enumerate(RETRY_BACKOFF, start=1):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("Groq call succeeded on attempt %d", attempt)
            return content
        except Exception as exc:
            last_error = exc
            logger.warning("Groq attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    raise RuntimeError(f"Groq API failed after {MAX_RETRIES} attempts: {last_error}")
