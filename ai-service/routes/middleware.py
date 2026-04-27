"""
Global request sanitisation middleware.
Registered in app.py via app.before_request.

Fix #10: Middleware is the single sanitisation layer for registered endpoints.
Individual routes no longer call sanitise_input() on the same field — the
middleware sets flask.g.sanitised = True so routes know the check was done.

I-11 FIX: Read X-Request-ID from incoming headers (set by the Java backend)
and store it in flask.g so every subsequent log line in that request cycle
can include it.  This enables distributed tracing across the Java <-> Flask
service boundary.
"""

import uuid
import logging
from flask import request, jsonify, g

from routes.helpers import sanitise_input

logger = logging.getLogger(__name__)

# Endpoints that carry a user-supplied "text" field in the JSON body
_TEXT_ENDPOINTS = {"/describe", "/recommend", "/generate-report", "/query"}


def sanitise_middleware():
    """
    Before-request hook.

    1. Reads X-Request-ID header (set by Java backend) or generates a new UUID
       and stores it in g.request_id for use in log messages and response headers.
    2. For POST endpoints that accept a 'text' or 'query' field, validate and
       sanitise it.  Stores the cleaned value in g.clean_fields so routes can
       read the sanitised text directly.  Sets g.sanitised = True after a
       successful check so individual routes can skip redundant sanitisation.

    Returns a 400 response immediately if input is invalid.
    Returns None to let Flask continue processing normally.
    """
    # I-11 FIX: Correlation ID - read from incoming header or generate a new one.
    g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    logger.debug(
        "Request %s %s  request_id=%s",
        request.method,
        request.path,
        g.request_id,
    )

    if request.method != "POST" or request.path not in _TEXT_ENDPOINTS:
        return None

    body = request.get_json(silent=True)
    if not body:
        return None  # Individual routes handle missing/invalid JSON

    # Check both 'text' (describe/recommend/report) and 'query' (/query)
    g.clean_fields = {}

    for field in ("text", "query"):
        raw_value = body.get(field, "")
        if not raw_value:
            continue
        try:
            cleaned = sanitise_input(raw_value)
            g.clean_fields[field] = cleaned
        except ValueError as exc:
            logger.warning(
                "Sanitisation middleware blocked request to %s (field=%s, request_id=%s): %s",
                request.path, field, g.request_id, exc,
            )
            return jsonify({"error": str(exc)}), 400

    # Signal to routes that sanitisation has already been performed
    g.sanitised = True
    return None
