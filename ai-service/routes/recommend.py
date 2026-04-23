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

from flask import Blueprint, request, jsonify

from services.groq_client import call_groq
from routes.helpers import load_prompt, sanitise_input, extract_json

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
    with at least one item, each having the required fields.
    """
    recs = data.get("recommendations")
    if not isinstance(recs, list) or len(recs) == 0:
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
    if not body:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    raw_text = body.get("text", "")
    if not raw_text or not raw_text.strip():
        return jsonify({"error": "Field 'text' is required and must not be empty."}), 400

    if len(raw_text) > 5000:
        return jsonify({"error": "Field 'text' must not exceed 5000 characters."}), 400

    # ── Sanitise input ─────────────────────────────────────────────────────────
    try:
        clean_text = sanitise_input(raw_text)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # ── Build prompt ───────────────────────────────────────────────────────────
    try:
        template = load_prompt("recommend_prompt.txt")
        prompt = template.format(text=clean_text)
    except Exception as exc:
        logger.error("Failed to load recommend prompt: %s", exc)
        return jsonify({"error": "Internal server error loading prompt."}), 500

    # ── Call Groq ──────────────────────────────────────────────────────────────
    try:
        raw_response = call_groq(prompt, temperature=0.3)
    except Exception as exc:
        logger.error("Groq call failed for /recommend: %s", exc)
        return jsonify(FALLBACK_RESPONSE), 200

    # ── Parse JSON ─────────────────────────────────────────────────────────────
    try:
        parsed = extract_json(raw_response)
    except ValueError as exc:
        logger.error("JSON parse failed for /recommend: %s | raw: %s", exc, raw_response[:300])
        return jsonify(FALLBACK_RESPONSE), 200

    # ── Validate structure ─────────────────────────────────────────────────────
    if not _validate_recommendations(parsed):
        logger.warning(
            "Groq /recommend response failed structure validation, using fallback. "
            "Parsed: %s", parsed
        )
        return jsonify(FALLBACK_RESPONSE), 200

    return jsonify(parsed), 200
