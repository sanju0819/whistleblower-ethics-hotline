"""
POST /generate-report
Accepts { "text": "..." } and returns a structured formal compliance report.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from services.groq_client import call_groq
from routes.helpers import load_prompt, sanitise_input, extract_json

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

    # ── Sanitise input (Fix #10: skip if middleware already handled it) ────────
    if not getattr(g, "sanitised", False):
        try:
            clean_text = sanitise_input(raw_text)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    else:
        clean_text = raw_text.strip()

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
        fallback = dict(FALLBACK_RESPONSE)
        fallback["generated_at"] = generated_at
        return jsonify(fallback), 200

    # ── Parse JSON ─────────────────────────────────────────────────────────────
    try:
        parsed = extract_json(raw_response)
    except ValueError as exc:
        logger.error(
            "JSON parse failed for /generate-report: %s | raw: %s", exc, raw_response[:300]
        )
        fallback = dict(FALLBACK_RESPONSE)
        fallback["generated_at"] = generated_at
        return jsonify(fallback), 200

    # I-1 FIX: Guarantee consistent envelope on all routes regardless of LLM output.
    parsed.setdefault("is_fallback", False)
    parsed.setdefault("generated_at", generated_at)

    return jsonify(parsed), 200
