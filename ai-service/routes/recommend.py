"""
POST /recommend
Accepts { "text": "..." } and returns 3 structured compliance recommendations.

Response shape:
{
  "recommendations": [
    {
      "action_type": "...",
      "description": "...",
      "priority": "High | Medium | Low"
    },
    ...
  ]
}
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from services.groq_client import call_groq
from services.cache import cache_get, cache_set, make_cache_key
from routes.helpers import load_prompt, sanitise_input, extract_json, make_fallback

logger = logging.getLogger(__name__)

recommend_bp = Blueprint("recommend", __name__)

VALID_PRIORITIES = {"High", "Medium", "Low"}

# Fallback returned when the AI service is unavailable
FALLBACK_RESPONSE = {
    "recommendations": [
        {
            "action_type": "Investigation",
            "description": "Conduct an internal investigation into the reported matter.",
            "priority": "High",
        },
        {
            "action_type": "Documentation",
            "description": "Document all available evidence and witness statements.",
            "priority": "Medium",
        },
        {
            "action_type": "Policy Review",
            "description": "Review relevant policies to identify any gaps related to the report.",
            "priority": "Low",
        },
    ],
    "is_fallback": True,
}


def _validate_recommendations(data: dict) -> bool:
    """
    Return True if the parsed dict contains a valid 'recommendations' list
    with at least 3 items, each having the required fields.
    The Java backend contract requires exactly 3 recommendations.
    """
    recs = data.get("recommendations")
    if not isinstance(recs, list) or len(recs) < 3:
        return False
    for rec in recs:
        if not isinstance(rec, dict):
            return False
        if not rec.get("action_type") or not rec.get("description"):
            return False
        if rec.get("priority") not in VALID_PRIORITIES:
            # Normalise capitalisation before rejecting
            normalised = str(rec.get("priority", "")).capitalize()
            if normalised not in VALID_PRIORITIES:
                return False
            rec["priority"] = normalised
    return True


@recommend_bp.route("/recommend", methods=["POST"])
def recommend():
    # ── Validate request body ──────────────────────────────────────────────────
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    raw_text = body.get("text", "")
    if not raw_text or not raw_text.strip():
        return jsonify({"error": "Field 'text' is required and must not be empty."}), 400

    if len(raw_text) > 5000:
        return jsonify({"error": "Field 'text' must not exceed 5000 characters."}), 400

    # ── Sanitise input (Fix #10: use middleware-cleaned value if available) ────
    if getattr(g, "sanitised", False):
        clean_text = g.clean_fields.get("text", raw_text.strip())
    else:
        try:
            clean_text = sanitise_input(raw_text)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    # ── Check cache ─────────────────────────────────────────────────────────────
    cache_key = make_cache_key("recommend", clean_text)
    try:
        cached = cache_get(cache_key)
        if cached is not None:
            logger.info("Cache HIT for /recommend")
            result = {**cached, "generated_at": datetime.now(timezone.utc).isoformat()}
            return jsonify(result), 200
    except Exception as exc:
        logger.warning("Cache read failed for /recommend: %s", exc)

    # ── Build prompt ───────────────────────────────────────────────────────────
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        template = load_prompt("recommend_prompt.txt")
        # Use str.replace() for user-controlled field to avoid KeyError on curly braces.
        prompt = template.replace("{text}", clean_text)
    except Exception as exc:
        logger.error("Failed to load recommend prompt: %s", exc)
        return jsonify({"error": "Internal server error loading prompt."}), 500

    # ── Call Groq ──────────────────────────────────────────────────────────────
    try:
        raw_response = call_groq(prompt, temperature=0.3)
    except Exception as exc:
        logger.error("Groq call failed for /recommend: %s", exc)
        return jsonify(make_fallback(FALLBACK_RESPONSE, generated_at)), 200

    # ── Parse JSON ─────────────────────────────────────────────────────────────
    try:
        parsed = extract_json(raw_response)
    except ValueError as exc:
        # Log only error and response length — not raw content (may contain PII).
        logger.error(
            "JSON parse failed for /recommend: %s | raw response length: %d chars",
            exc, len(raw_response),
        )
        return jsonify(make_fallback(FALLBACK_RESPONSE, generated_at)), 200

    # ── Validate structure ─────────────────────────────────────────────────────
    if not _validate_recommendations(parsed):
        recs = parsed.get("recommendations")
        logger.warning(
            "Groq /recommend response failed structure validation — "
            "recommendations count: %d, using fallback.",
            len(recs) if isinstance(recs, list) else -1,
        )
        return jsonify(make_fallback(FALLBACK_RESPONSE, generated_at)), 200

    # I-1 FIX: Guarantee consistent envelope on all routes regardless of LLM output.
    parsed.setdefault("is_fallback", False)
    parsed.setdefault("generated_at", generated_at)

    # ── Cache successful (non-fallback) responses ──────────────────────────────
    if not parsed.get("is_fallback", False):
        try:
            cache_set(cache_key, parsed)
        except Exception as exc:
            logger.warning("Cache write failed for /recommend: %s", exc)

    return jsonify(parsed), 200
