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

NOTE: If a new endpoint adds a user-supplied field that is injected into a
prompt, add that field name to the loop on line 68 below.
"""

import uuid
import logging
from flask import request, jsonify, g

from routes.helpers import sanitise_input

logger = logging.getLogger(__name__)

# Endpoints that carry a user-supplied "text" or "query" field in the JSON body.
# If a new endpoint is added, register its path here.
_TEXT_ENDPOINTS = {"/describe", "/recommend", "/generate-report", "/query"}


def sanitise_middleware():
    """
    Before-request hook — runs on every incoming request.

    1. Reads or generates X-Request-ID and stores in g.request_id
    2. Enforces Content-Type: application/json on POST endpoints
    3. Rejects oversized JSON key counts (JSON bomb protection)
    4. Sanitises text/query fields and stores cleaned values in g.clean_fields
    """
    # 1. Correlation ID
    g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    if request.method != "POST" or request.path not in _TEXT_ENDPOINTS:
        return None

    # 2. Enforce Content-Type
    content_type = request.content_type or ""
    if "application/json" not in content_type:
        logger.warning(
            "Rejected non-JSON Content-Type '%s' on %s (request_id=%s)",
            content_type, request.path, g.request_id,
        )
        return jsonify({"error": "Content-Type must be application/json."}), 415

    # 3. Parse body
    # ME-7 FIX: Use `is None` — an empty JSON object {} is valid and should
    # pass through to the route handler for its own field validation.
    body = request.get_json(silent=True)
    if body is None:
        return None

    # 4. JSON bomb protection — reject if too many keys
    if len(body) > 20:
        logger.warning(
            "Rejected request with %d JSON keys on %s (request_id=%s)",
            len(body), request.path, g.request_id,
        )
        return jsonify({"error": "Request body contains too many fields."}), 400

    # 5. Sanitise text/query fields
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
                "Sanitisation blocked %s (field=%s, request_id=%s): %s",
                request.path, field, g.request_id, exc,
            )
            return jsonify({"error": str(exc)}), 400

    g.sanitised = True
    return None
