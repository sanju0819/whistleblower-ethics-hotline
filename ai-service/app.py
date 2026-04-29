"""
ai-service — Flask microservice for Tool-70 Whistleblower & Ethics Hotline
Port: 5000
"""

import os
import time
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# CR-2 FIX: Module-level lock protects the RESPONSE_TIMES deque from
# concurrent append + iteration across Gunicorn threads.
_times_lock = threading.Lock()

# Named constant for response time window size
_RESPONSE_WINDOW = 100


def create_app() -> Flask:
    """
    Application factory.

    Calling load_dotenv() here ensures env vars are set before any
    blueprint or service module is imported, without needing mid-file
    imports with # noqa: E402 suppression.
    """
    # Always load .env from the same directory as app.py — works correctly
    # regardless of which folder the user runs `python app.py` from.
    _env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=_env_path)

    # ── Logging ────────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger = logging.getLogger(__name__)

    application = Flask(__name__)

    # ── Validate critical env vars at startup (fail fast) ─────────────────────
    # SKIP_GROQ_VALIDATION=true lets CI/test environments bypass this check
    # without removing the production guard.
    _skip_validation = os.getenv("SKIP_GROQ_VALIDATION", "false").lower() == "true"
    _groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not _skip_validation:
        if not _groq_key or _groq_key == "your_groq_api_key_here":
            logger.error(
                "GROQ_API_KEY is not set or is still the placeholder value. "
                "Copy .env.example to ai-service/.env and set a real key. "
                "Get a free key at https://console.groq.com"
            )
            raise RuntimeError(
                "GROQ_API_KEY is missing. Set it in ai-service/.env before starting."
            )
    # HI-2 FIX: Log boolean confirmation, not key length — length is
    # distinctive metadata that narrows the keyspace.
    logger.info("GROQ_API_KEY loaded successfully.")

    # CR-1 FIX: Initialise RESPONSE_TIMES deque BEFORE any hooks that use it.
    application.config["RESPONSE_TIMES"] = deque(maxlen=_RESPONSE_WINDOW)

    # ── Rate limiter: 30 requests / minute per IP ──────────────────────────────
    # Fix #4: Use Redis for shared state across Gunicorn workers.
    # Falls back to memory:// only when REDIS_URL is not set (local dev without Redis).
    redis_url = os.getenv("REDIS_URL")
    if redis_url is None:
        logger.warning(
            "REDIS_URL not set — rate limiter using in-memory storage (dev only). "
            "Set REDIS_URL in .env for production."
        )
    limiter = Limiter(
        key_func=get_remote_address,
        app=application,
        default_limits=["30 per minute"],
        storage_uri=redis_url or "memory://",
    )
    application.config["LIMITER"] = limiter

    # ── CORS protection ────────────────────────────────────────────────────────
    # Only allow requests from the Java backend (port 8080) and localhost.
    # Deny all browser-originated cross-origin requests from unknown origins.
    try:
        from flask_cors import CORS

        allowed_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080"
        )
        CORS(
            application,
            origins=allowed_origins.split(","),
            methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
            max_age=600,
        )
        logger.info("CORS configured — allowed origins: %s", allowed_origins)
    except ImportError:
        logger.warning(
            "flask-cors is not installed — CORS headers will NOT be set. "
            "Install Flask-Cors to enable CORS protection."
        )

    # I-7 FIX: Cap incoming request body size before route handlers run.
    # Field-level 5000-char checks fire AFTER Flask reads the full body;
    # this rejects oversized payloads early (16 KB is ample for any valid request).
    _MAX_CONTENT_BYTES = 16 * 1024  # 16 KB
    application.config["MAX_CONTENT_LENGTH"] = _MAX_CONTENT_BYTES

    # ── Register middleware ────────────────────────────────────────────────────
    from routes.middleware import sanitise_middleware
    application.before_request(sanitise_middleware)

    @application.before_request
    def record_start_time():
        g.start_time = time.time()

    # ── Register blueprints ────────────────────────────────────────────────────
    from routes.describe import describe_bp
    from routes.recommend import recommend_bp
    from routes.report import report_bp
    from routes.query import query_bp

    application.register_blueprint(describe_bp)
    application.register_blueprint(recommend_bp)
    application.register_blueprint(report_bp)
    application.register_blueprint(query_bp)

    # ── Security response headers ──────────────────────────────────────────────
    @application.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # X-XSS-Protection is deprecated in modern browsers (Chrome removed
        # XSS Auditor in 2019) but retained for legacy IE compatibility.
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Remove server fingerprint header
        response.headers.pop("Server", None)
        # HI-1 FIX: Only set X-Request-ID if the middleware generated one.
        # An empty string is worse than absent — some proxies treat "" as valid.
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    @application.after_request
    def record_response_time(response):
        start = getattr(g, "start_time", None)
        if start is not None:
            elapsed = time.time() - start
            with _times_lock:
                times = application.config.get("RESPONSE_TIMES")
                if times is not None:
                    times.append(elapsed)
        return response

    # ── Fix #15: Capture start time BEFORE slow VectorStore init ──────────────
    # The /health uptime metric must reflect the true service start time.
    application.config["START_TIME"] = time.time()

    # ── Pre-load vector store (model + ChromaDB collection) ───────────────────
    try:
        from services.vector_store import initialise as _vs_init
        _vs_init()
        logger.info("VectorStore pre-load complete.")
    except Exception as _vs_exc:
        logger.warning(
            "VectorStore pre-load failed — /query will initialise lazily. Error: %s",
            _vs_exc,
        )

    # ── Health endpoint ────────────────────────────────────────────────────────
    @application.route("/health", methods=["GET"])
    def health():
        # ME-2 FIX: Import constants from their source modules so /health
        # never drifts out of sync with the actual model in use.
        from services.groq_client import GROQ_MODEL
        from services.vector_store import EMBEDDING_MODEL_NAME, document_count

        uptime_seconds = int(time.time() - application.config["START_TIME"])
        try:
            doc_count = document_count()
        except Exception:
            doc_count = -1
        with _times_lock:
            times = list(application.config["RESPONSE_TIMES"])
        avg_response_ms = round(sum(times) / len(times) * 1000, 1) if times else 0.0
        return jsonify({
            "status": "ok",
            "model": GROQ_MODEL,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "vector_store_documents": doc_count,
            "uptime_seconds": uptime_seconds,
            "avg_response_ms": avg_response_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200

    # ── Ping endpoint (liveness probe) ────────────────────────────────────────
    @application.route("/ping", methods=["GET"])
    def ping():
        """Lightweight liveness probe — used by ZAP and load balancers."""
        return jsonify({"pong": True}), 200

    # ── Global error handlers ──────────────────────────────────────────────────
    @application.errorhandler(404)
    def not_found(_err):
        return jsonify({"error": "Endpoint not found."}), 404

    @application.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify({"error": "Method not allowed."}), 405

    # HI-1 FIX: Flask's MAX_CONTENT_LENGTH raises RequestEntityTooLarge which
    # returns an HTML page by default.  Return JSON so the Java backend can
    # parse it correctly.
    @application.errorhandler(413)
    def payload_too_large(_err):
        return jsonify({"error": "Request payload too large."}), 413

    @application.errorhandler(429)
    def rate_limit_exceeded(_err):
        return jsonify({"error": "Rate limit exceeded. Try again in a moment."}), 429

    @application.errorhandler(500)
    def internal_error(_err):
        logger.exception("Unhandled internal error")
        return jsonify({"error": "Internal server error."}), 500

    return application


app = create_app()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _logger = logging.getLogger(__name__)
    port = int(os.getenv("AI_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    _logger.warning(
        "Running with app.run() — for LOCAL DEVELOPMENT only. "
        "Use Gunicorn for production."
    )
    _logger.info("Starting ai-service on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
