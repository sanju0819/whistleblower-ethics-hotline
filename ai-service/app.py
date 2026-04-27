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
    _groq_key = os.getenv("GROQ_API_KEY", "")
    if not _groq_key or _groq_key == "your_groq_api_key_here":
        logger.error(
            "GROQ_API_KEY is not set or is still the placeholder value. "
            "Copy .env.example to ai-service/.env and set a real key. "
            "Get a free key at https://console.groq.com"
        )
        raise RuntimeError(
            "GROQ_API_KEY is missing. Set it in ai-service/.env before starting."
        )
    else:
        logger.info("GROQ_API_KEY loaded successfully (length=%d).", len(_groq_key))

    # CR-1 FIX: Initialise RESPONSE_TIMES deque BEFORE any hooks that use it.
    application.config["RESPONSE_TIMES"] = deque(maxlen=100)

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

    # I-7 FIX: Cap incoming request body size before route handlers run.
    # Field-level 5000-char checks fire AFTER Flask reads the full body;
    # this rejects oversized payloads early (16 KB is ample for any valid request).
    application.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # 16 KB

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

    # ── Security response headers (I-6) ──────────────────────────────────────
    @application.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
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
        from services.vector_store import document_count
        uptime_seconds = int(time.time() - application.config["START_TIME"])
        try:
            doc_count = document_count()
        except Exception:
            doc_count = -1
        with _times_lock:
            times = list(application.config.get("RESPONSE_TIMES", []))
        avg_response_ms = round(sum(times) / len(times) * 1000, 1) if times else 0.0
        return jsonify({
            "status": "ok",
            "model": "llama-3.3-70b-versatile",
            "embedding_model": "all-MiniLM-L6-v2",
            "vector_store_documents": doc_count,
            "uptime_seconds": uptime_seconds,
            "avg_response_ms": avg_response_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200

    # ── Global error handlers ──────────────────────────────────────────────────
    @application.errorhandler(404)
    def not_found(_err):
        return jsonify({"error": "Endpoint not found."}), 404

    @application.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify({"error": "Method not allowed."}), 405

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
    _logger.info("Starting ai-service on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
