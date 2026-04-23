"""
ai-service — Flask microservice for Tool-70 Whistleblower & Ethics Hotline
Port: 5000
"""

import os
import time
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App factory ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Rate limiter: 30 requests / minute per IP ──────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["30 per minute"],
    storage_uri="memory://",
)

# ── Register middleware ────────────────────────────────────────────────────────
from routes.middleware import sanitise_middleware  # noqa: E402

app.before_request(sanitise_middleware)

# ── Register blueprints ────────────────────────────────────────────────────────
from routes.describe import describe_bp        # noqa: E402
from routes.recommend import recommend_bp      # noqa: E402
from routes.report import report_bp            # noqa: E402

app.register_blueprint(describe_bp)
app.register_blueprint(recommend_bp)
app.register_blueprint(report_bp)

# ── Health endpoint ────────────────────────────────────────────────────────────
_start_time = time.time()


@app.route("/health", methods=["GET"])
def health():
    uptime_seconds = int(time.time() - _start_time)
    return jsonify({
        "status": "ok",
        "model": "llama-3.3-70b-versatile",
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


# ── Global error handlers ──────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(_err):
    return jsonify({"error": "Endpoint not found."}), 404


@app.errorhandler(405)
def method_not_allowed(_err):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(429)
def rate_limit_exceeded(_err):
    return jsonify({"error": "Rate limit exceeded. Try again in a moment."}), 429


@app.errorhandler(500)
def internal_error(_err):
    logger.exception("Unhandled internal error")
    return jsonify({"error": "Internal server error."}), 500


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("AI_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting ai-service on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
