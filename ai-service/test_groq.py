"""
test_groq.py — quick smoke test for the Groq API connection.
Run: python test_groq.py
Requires GROQ_API_KEY to be set in .env or environment.
"""

from dotenv import load_dotenv
load_dotenv()

from services.groq_client import call_groq  # noqa: E402

TEST_PROMPT = (
    "Reply with ONLY this JSON, nothing else: "
    '{\"status\": \"ok\", \"message\": \"Groq connection working\"}'
)

if __name__ == "__main__":
    print("Testing Groq API connection...")
    try:
        response = call_groq(TEST_PROMPT, temperature=0.1, max_tokens=64)
        print("SUCCESS — raw response:")
        print(response)
    except Exception as exc:
        print(f"FAILED — {exc}")
