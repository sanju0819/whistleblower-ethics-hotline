"""
Global request sanitisation middleware.
Registered in app.py via app.before_request.
"""

import logging
from flask import request, jsonify

from routes.helpers import sanitise_input

logger = logging.getLogger(__name__)

# Endpoints that carry a user-supplied "text" field in the JSON body
_TEXT_ENDPOINTS = {"/describe", "/recommend", "/generate-report"}


def sanitise_middleware():
    """
    Before-request hook.
    For POST endpoints that accept a 'text' field, validate and sanitise it.
    Returns a 400 response immediately if input is invalid.
    Returns None to let Flask continue processing normally.
    """
    if request.method != "POST" or request.path not in _TEXT_ENDPOINTS:
        return None

    body = request.get_json(silent=True)
    if not body:
        return None  # Individual routes handle missing/invalid JSON

    raw_text = body.get("text", "")
    if not raw_text:
        return None  # Individual routes handle missing text

    try:
        sanitise_input(raw_text)
    except ValueError as exc:
        logger.warning("Sanitisation middleware blocked request to %s: %s", request.path, exc)
        return jsonify({"error": str(exc)}), 400

    return None
