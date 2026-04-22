import os
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

from routes.describe import describe_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(describe_bp)


@app.get("/")
def home():
    return jsonify({
        "message": "Whistleblower AI Service",
        "status": "running",
        "version": "1.0.0"
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": "llama-3.3-70b-versatile",
        "port": 5000
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
