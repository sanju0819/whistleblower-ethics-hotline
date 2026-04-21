from flask import Flask, request, jsonify
from services.ai_service import generate_description

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"message": "AI Service Running 🚀"})

@app.route("/describe", methods=["POST"])
def describe():
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    user_input = data["text"]

    result = generate_description(user_input)

    return jsonify({"description": result})

if __name__ == "__main__":
    app.run(port=5000, debug=True)