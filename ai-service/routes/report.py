"""
POST /generate-report
Accepts { "text": "..." } and returns a structured formal compliance report.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from services.groq_client import call_groq
from services.cache import cache_get, cache_set, make_cache_key
from routes.helpers import load_prompt, sanitise_input, extract_json, make_fallback

logger = logging.getLogger(__name__)

report_bp = Blueprint("report", __name__)

FALLBACK_RESPONSE = {
    "title": "Compliance Report — AI Unavailable",
    "summary": "The AI report generation service is temporarily unavailable.",
    "overview": "Please review the original submission manually and generate a report.",
    "key_items": [],
    "recommendations": [],
    "generated_at": None,
    "is_fallback": True,
}


@report_bp.route("/generate-report", methods=["POST"])
def generate_report():
    # ── Validate request body ──────────────────────────────────────────────────
    body = request.get_json(silent=True)
    if not body:
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
    cache_key = make_cache_key("generate-report", clean_text)
    try:
        cached = cache_get(cache_key)
        if cached is not None:
            logger.info("Cache HIT for /generate-report")
            result = {**cached, "generated_at": datetime.now(timezone.utc).isoformat()}
            return jsonify(result), 200
    except Exception as exc:
        logger.warning("Cache read failed for /generate-report: %s", exc)

    # ── Build prompt ───────────────────────────────────────────────────────────
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        template = load_prompt("report_prompt.txt")
        # Use str.replace() for user-controlled fields to avoid KeyError on curly braces.
        prompt = (
            template
            .replace("{text}", clean_text)
            .replace("{generated_at}", generated_at)
        )
    except Exception as exc:
        logger.error("Failed to load report prompt: %s", exc)
        return jsonify({"error": "Internal server error loading prompt."}), 500

    # ── Call Groq ──────────────────────────────────────────────────────────────
    try:
        raw_response = call_groq(prompt, temperature=0.4, max_tokens=1500)
    except Exception as exc:
        logger.error("Groq call failed for /generate-report: %s", exc)
        return jsonify(make_fallback(FALLBACK_RESPONSE, generated_at)), 200

    # ── Parse JSON ─────────────────────────────────────────────────────────────
    try:
        parsed = extract_json(raw_response)
    except ValueError as exc:
        logger.error(
            "JSON parse failed for /generate-report: %s | raw: %s", exc, raw_response[:300]
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
            logger.warning("Cache write failed for /generate-report: %s", exc)

    return jsonify(parsed), 200
