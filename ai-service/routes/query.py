"""
routes/query.py
POST /query — RAG-based question answering over the ethics knowledge base.

RAG Flow:
  1. Validate and sanitise the incoming query (middleware handles sanitisation).
  2. Generate an embedding for the query (ChromaDB DefaultEmbeddingFunction).
  3. Retrieve the top-3 most relevant documents from ChromaDB (score >= MIN_RELEVANCE_SCORE).
  4. Inject retrieved context + query into the Groq prompt.
  5. Parse and return the structured JSON response.

Response shape:
{
  "answer":       "...",
  "sources":      ["Source Label 1", "Source Label 2"],
  "confidence":   "High | Medium | Low",
  "generated_at": "ISO-8601 timestamp",
  "is_fallback":  false
}
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g

from services.groq_client import call_groq
from services.vector_store import similarity_search
from routes.helpers import load_prompt, sanitise_input, extract_json

logger = logging.getLogger(__name__)

query_bp = Blueprint("query", __name__)

# Fallback returned when the AI service or vector store is unavailable
_FALLBACK_RESPONSE = {
    "answer": "The query service is temporarily unavailable. Please try again shortly.",
    "sources": [],
    "confidence": "Low",
    "generated_at": None,
    "is_fallback": True,
}

# Maximum characters accepted in a single query
_MAX_QUERY_LENGTH = 2000


@query_bp.route("/query", methods=["POST"])
def query():
    """
    POST /query
    Body: { "query": "<natural language question>" }
    """
    # ── 1. Validate request body ───────────────────────────────────────────────
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    raw_query = body.get("query", "")
    if not raw_query or not raw_query.strip():
        return jsonify({"error": "Field 'query' is required and must not be empty."}), 400

    if len(raw_query) > _MAX_QUERY_LENGTH:
        return jsonify(
            {"error": f"Field 'query' must not exceed {_MAX_QUERY_LENGTH} characters."}
        ), 400

    # ── 2. Sanitise input ──────────────────────────────────────────────────────
    # Fix #10: Use middleware-cleaned value if available.
    if getattr(g, "sanitised", False):
        clean_query = g.clean_fields.get("query", raw_query.strip())
    else:
        try:
            clean_query = sanitise_input(raw_query)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    generated_at = datetime.now(timezone.utc).isoformat()

    # ── 3. Retrieve relevant context from ChromaDB ────────────────────────────
    # Fix #14: similarity_search already filters by MIN_RELEVANCE_SCORE.
    try:
        search_results = similarity_search(clean_query, top_k=3)
    except Exception as exc:
        logger.error("Vector search failed for /query: %s", exc)
        search_results = []

    # ── 4. Build context block and source list ─────────────────────────────────
    if search_results:
        context_lines = []
        for idx, result in enumerate(search_results, start=1):
            source = result.get("source", "Unknown Source")
            text = result.get("text", "")
            score = result.get("score", 0.0)
            context_lines.append(
                f"[{idx}] Source: {source} (relevance: {score:.2f})\n{text}"
            )
        context_block = "\n\n".join(context_lines)
        sources = [r.get("source", "Unknown Source") for r in search_results]
    else:
        context_block = "No relevant documents found in the knowledge base."
        sources = []

    # ── 5. Format source list for prompt injection ─────────────────────────────
    if sources:
        source_list_str = ", ".join(f'"{s}"' for s in sources)
    else:
        source_list_str = ""

    # ── 6. Build and send prompt to Groq ──────────────────────────────────────
    # Fix #2: Use str.replace() for user-controlled fields to avoid KeyError when
    # the query contains curly braces (e.g. "What is {this}?").
    try:
        template = load_prompt("query_prompt.txt")
        prompt = (
            template
            .replace("{context}", context_block)
            .replace("{query}", clean_query)
            .replace("{source_list}", source_list_str)
            .replace("{generated_at}", generated_at)
        )
    except Exception as exc:
        logger.error("Failed to load query prompt: %s", exc)
        fallback = dict(_FALLBACK_RESPONSE)
        fallback["generated_at"] = generated_at
        return jsonify(fallback), 200

    try:
        raw_response = call_groq(prompt, temperature=0.3, max_tokens=1024)
    except Exception as exc:
        logger.error("Groq call failed for /query: %s", exc)
        fallback = dict(_FALLBACK_RESPONSE)
        fallback["generated_at"] = generated_at
        return jsonify(fallback), 200

    # ── 7. Parse and enrich the response ──────────────────────────────────────
    try:
        parsed = extract_json(raw_response)
    except ValueError as exc:
        logger.error(
            "JSON parse failed for /query: %s | raw: %s", exc, raw_response[:300]
        )
        fallback = dict(_FALLBACK_RESPONSE)
        fallback["generated_at"] = generated_at
        return jsonify(fallback), 200

    # Fix #7: Always overwrite sources with ground-truth ChromaDB results.
    # LLM-generated sources may be hallucinated and must never appear in the response.
    parsed["sources"] = sources
    parsed.setdefault("generated_at", generated_at)
    parsed.setdefault("is_fallback", False)

    # Normalise confidence field
    valid_confidences = {"High", "Medium", "Low"}
    raw_conf = str(parsed.get("confidence", "")).strip().capitalize()
    if raw_conf not in valid_confidences:
        parsed["confidence"] = "Medium" if search_results else "Low"
    else:
        parsed["confidence"] = raw_conf

    logger.info(
        "/query answered with confidence=%s, sources=%d",
        parsed["confidence"],
        len(sources),
    )
    return jsonify(parsed), 200
