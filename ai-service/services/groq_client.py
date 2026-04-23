import os
import json
import time
import logging
from groq import Groq
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
# Day 3 update
# Initialize Groq client once at module load
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts/ folder."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "prompts", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def describe_complaint(complaint: str) -> dict:
    """
    Send complaint to Groq and return structured JSON description.
    Retries up to 3 times with exponential backoff on failure.
    Returns fallback dict if all attempts fail.
    """
    template = load_prompt("describe_prompt.txt")
    generated_at = datetime.now(timezone.utc).isoformat()

    # Fill in placeholders
    prompt = template.replace("{complaint}", complaint).replace("{generated_at}", generated_at)

    for attempt in range(3):
        try:
            logger.info(f"Calling Groq API — attempt {attempt + 1}")

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600
            )

            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if model adds them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            result = json.loads(raw)
            logger.info("Groq response parsed successfully")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error on attempt {attempt + 1}: {e}")
            logger.error(f"Raw response was: {raw!r}")
            if attempt == 2:
                return _fallback(generated_at)

        except Exception as e:
            logger.error(f"Groq API error on attempt {attempt + 1}: {e}")
            if attempt == 2:
                return _fallback(generated_at)
            wait = 2 ** attempt  # 1s, 2s
            logger.info(f"Retrying in {wait}s...")
            time.sleep(wait)

    return _fallback(generated_at)


def _fallback(generated_at: str) -> dict:
    """Return a safe fallback response when Groq is unavailable."""
    return {
        "title": "Unable to process complaint",
        "description": "The AI service is temporarily unavailable. Your complaint has been received. Please try again shortly.",
        "category": "Other",
        "severity": "Medium",
        "severity_reason": "Severity could not be determined — AI service unavailable.",
        "suggested_department": "Compliance",
        "is_anonymous_safe": True,
        "generated_at": generated_at,
        "is_fallback": True
    }
