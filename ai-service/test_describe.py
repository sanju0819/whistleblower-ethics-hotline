"""
Day 3 — Manual test script for /describe endpoint.

Run this AFTER starting the Flask server:
    python app.py

Then in another terminal:
    python test_describe.py
"""
# Day 3 update
import requests
import json

BASE_URL = "http://localhost:5000"

test_cases = [
    {
        "name": "Test 1 — Financial Fraud",
        "payload": {"complaint": "My manager has been asking me to approve fake vendor invoices worth around 2 lakhs every month. The vendor does not seem to exist and the payments are going to an unknown account."}
    },
    {
        "name": "Test 2 — Workplace Harassment",
        "payload": {"complaint": "My senior colleague makes inappropriate jokes about my gender in team meetings. When I asked him to stop he told me to not be so sensitive. HR has not taken any action even after I reported it 3 weeks ago."}
    },
    {
        "name": "Test 3 — Safety Violation",
        "payload": {"complaint": "The fire exits on the 3rd floor of our office building have been blocked with storage boxes for the past month. Nobody seems to be fixing this despite multiple complaints to the facilities team."}
    },
    {
        "name": "Test 4 — Data Breach",
        "payload": {"complaint": "I noticed a colleague copying customer personal data including phone numbers and addresses to a personal USB drive. When I asked what it was for he said it was none of my business."}
    },
    {
        "name": "Test 5 — Conflict of Interest",
        "payload": {"complaint": "Our procurement head is awarding contracts to a company that his wife owns. The bids from other vendors are being rejected without proper explanation."}
    },
]

validation_cases = [
    {"name": "Empty complaint", "payload": {"complaint": ""}},
    {"name": "Missing complaint field", "payload": {"other": "value"}},
    {"name": "Too short complaint", "payload": {"complaint": "short"}},
]

print("=" * 60)
print("RUNNING 5 MAIN TEST CASES")
print("=" * 60)

pass_count = 0
fail_count = 0

for tc in test_cases:
    print(f"\n{tc['name']}")
    print(f"Input: {tc['payload']['complaint'][:80]}...")
    try:
        r = requests.post(f"{BASE_URL}/describe", json=tc["payload"], timeout=15)
        data = r.json()
        print(f"Status: {r.status_code}")
        print(f"Output:\n{json.dumps(data, indent=2)}")

        # Checks
        required_keys = ["title", "description", "category", "severity", "severity_reason", "suggested_department", "generated_at"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"FAIL — Missing keys: {missing}")
            fail_count += 1
        else:
            print("PASS — All required keys present")
            pass_count += 1
    except Exception as e:
        print(f"ERROR — {e}")
        fail_count += 1
    print("-" * 60)

print("\n" + "=" * 60)
print("RUNNING VALIDATION TEST CASES")
print("=" * 60)

for tc in validation_cases:
    print(f"\n{tc['name']}")
    try:
        r = requests.post(f"{BASE_URL}/describe", json=tc["payload"], timeout=10)
        print(f"Status: {r.status_code} — Expected: 400")
        if r.status_code == 400:
            print("PASS — Correctly rejected bad input")
        else:
            print("FAIL — Should have returned 400")
    except Exception as e:
        print(f"ERROR — {e}")
    print("-" * 60)

print(f"\nSUMMARY: {pass_count}/5 main tests passed, {fail_count} failed")
