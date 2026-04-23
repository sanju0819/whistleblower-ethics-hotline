from flask import Blueprint, request, jsonify
from services.groq_client import describe_complaint

describe_bp = Blueprint("describe", __name__)

# Day 3 update
@describe_bp.post("/describe")
def describe():
    data = request.get_json(silent=True)

    # --- Input Validation ---
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    complaint = data.get("complaint", "").strip()

    if not complaint:
        return jsonify({"error": "Missing 'complaint' field"}), 400

    if len(complaint) < 10:
        return jsonify({"error": "Complaint is too short. Minimum 10 characters required."}), 400

    if len(complaint) > 5000:
        return jsonify({"error": "Complaint is too long. Maximum 5000 characters allowed."}), 400

    # --- Call Groq AI ---
    result = describe_complaint(complaint)

    # --- Return Result ---
    if result.get("is_fallback"):
        return jsonify(result), 503

    return jsonify(result), 200
