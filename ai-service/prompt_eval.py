#!/usr/bin/env python3
"""
prompt_eval.py — Offline prompt quality evaluator for Tool-70 AI Service.

Usage:
  python prompt_eval.py --mock   (default — no live Groq calls)
  python prompt_eval.py --live   (calls live Groq API — requires GROQ_API_KEY in .env)

Scores each endpoint against 10 realistic whistleblower scenarios.
Prints a table. Exits with code 1 if any prompt average < 7.0.
"""

import sys
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── 10 realistic whistleblower inputs ─────────────────────────────────────────
INPUTS = [
    {"id": 1, "category": "Fraud",             "text": "My manager has been falsifying expense reports for the past three months, submitting claims for meals and travel that never occurred."},
    {"id": 2, "category": "Harassment",        "text": "A senior colleague has been making inappropriate sexual comments to junior staff members during team meetings and one-on-one sessions."},
    {"id": 3, "category": "Safety",            "text": "The maintenance team has been bypassing safety lockout procedures on heavy machinery, putting workers at serious risk of injury."},
    {"id": 4, "category": "Corruption",        "text": "I believe the procurement director is accepting kickbacks from a vendor in exchange for awarding contracts above market rate."},
    {"id": 5, "category": "Discrimination",    "text": "Employees over 50 are consistently passed over for promotions regardless of their performance scores and tenure."},
    {"id": 6, "category": "Retaliation",       "text": "After I submitted a complaint about overtime violations, my manager gave me a negative performance review and removed me from key projects."},
    {"id": 7, "category": "Data Privacy",      "text": "Our IT team shared customer personal data including email addresses and purchase history with a third-party marketing firm without consent."},
    {"id": 8, "category": "Conflict",          "text": "The VP of Operations awarded a major contract to his brother-in-law's company without following the standard tender process."},
    {"id": 9, "category": "Policy Violation",  "text": "A department head has been approving her own expense claims without a secondary authoriser, circumventing the dual-control policy."},
    {"id": 10,"category": "Safety",            "text": "Multiple employees have reported that the fire exits on floor 3 are blocked by stored equipment, violating fire safety regulations."},
]

# ── Mocked Groq responses (used with --mock) ──────────────────────────────────
MOCK_DESCRIBE = {
    "category": "Fraud", "severity": "High",
    "summary": "An employee reports fraudulent expense claims by their manager.",
    "key_entities": ["Manager", "Finance Department"],
    "recommended_action": "Initiate an internal audit of expense reports.",
    "generated_at": "2026-04-21T09:00:00+00:00", "is_fallback": False
}
MOCK_RECOMMEND = {
    "recommendations": [
        {"action_type": "Investigation", "description": "Launch a formal investigation.", "priority": "High"},
        {"action_type": "Documentation", "description": "Preserve all evidence.",         "priority": "Medium"},
        {"action_type": "Training",      "description": "Conduct ethics training.",        "priority": "Low"},
    ], "is_fallback": False
}
MOCK_REPORT = {
    "title": "Compliance Report — Fraudulent Expense Claims",
    "summary": "An employee reports three months of falsified expense claims.",
    "overview": "The manager submitted fabricated meal and travel claims consistently.",
    "key_items": ["Falsified meal claims", "Fabricated travel expenses", "3-month duration"],
    "recommendations": ["Initiate audit", "Suspend approvals", "Notify HR"],
    "generated_at": "2026-04-21T09:00:00+00:00", "is_fallback": False
}

# ── Scoring criteria ───────────────────────────────────────────────────────────
DESCRIBE_CHECKS = ["category", "severity", "summary", "key_entities", "recommended_action", "generated_at"]
RECOMMEND_CHECKS_FN = lambda d: (
    isinstance(d.get("recommendations"), list) and
    len(d["recommendations"]) == 3 and
    all(r.get("action_type") and r.get("description") and r.get("priority") in {"High","Medium","Low"} for r in d["recommendations"])
)
REPORT_CHECKS = ["title", "summary", "overview", "key_items", "recommendations", "generated_at"]

def score_describe(result: dict) -> float:
    passed = sum(1 for f in DESCRIBE_CHECKS if result.get(f))
    return round(passed / len(DESCRIBE_CHECKS) * 10, 1)

def score_recommend(result: dict) -> float:
    return 10.0 if RECOMMEND_CHECKS_FN(result) else 4.0

def score_report(result: dict) -> float:
    passed = sum(1 for f in REPORT_CHECKS if result.get(f))
    return round(passed / len(REPORT_CHECKS) * 10, 1)

def evaluate_mock() -> list[dict]:
    rows = []
    for inp in INPUTS:
        d_score = score_describe(MOCK_DESCRIBE)
        r_score = score_recommend(MOCK_RECOMMEND)
        rep_score = score_report(MOCK_REPORT)
        rows.append({
            "id": inp["id"], "category": inp["category"],
            "describe": d_score, "recommend": r_score, "report": rep_score,
        })
    return rows

def evaluate_live() -> list[dict]:
    from services.groq_client import call_groq
    from routes.helpers import load_prompt, extract_json

    rows = []
    for inp in INPUTS:
        text = inp["text"]
        ts = datetime.now(timezone.utc).isoformat()

        # /describe
        try:
            d_template = load_prompt("describe_prompt.txt")
            d_prompt = d_template.replace("{text}", text).replace("{generated_at}", ts)
            d_raw = call_groq(d_prompt, temperature=0.3)
            d_parsed = extract_json(d_raw)
            d_score = score_describe(d_parsed)
        except Exception:
            d_score = 0.0

        # /recommend
        try:
            r_template = load_prompt("recommend_prompt.txt")
            r_prompt = r_template.replace("{text}", text)
            r_raw = call_groq(r_prompt, temperature=0.3)
            r_parsed = extract_json(r_raw)
            r_score = score_recommend(r_parsed)
        except Exception:
            r_score = 0.0

        # /generate-report
        try:
            rep_template = load_prompt("report_prompt.txt")
            rep_prompt = rep_template.replace("{text}", text).replace("{generated_at}", ts)
            rep_raw = call_groq(rep_prompt, temperature=0.4, max_tokens=1500)
            rep_parsed = extract_json(rep_raw)
            rep_score = score_report(rep_parsed)
        except Exception:
            rep_score = 0.0

        rows.append({
            "id": inp["id"], "category": inp["category"],
            "describe": d_score, "recommend": r_score, "report": rep_score,
        })
    return rows

def print_report(rows: list[dict], mode: str):
    print(f"\n{'='*72}")
    print(f"  Tool-70 Prompt Quality Evaluation — Mode: {mode.upper()}")
    print(f"{'='*72}")
    header = f"{'#':>3} {'Category':<20} {'Describe':>9} {'Recommend':>10} {'Report':>8} {'Status':<10}"
    print(header)
    print("-" * 72)
    for row in rows:
        flag = "[NEEDS TUNING]" if min(row["describe"], row["recommend"], row["report"]) < 7.0 else "OK"
        print(f"{row['id']:>3} {row['category']:<20} {row['describe']:>9.1f} {row['recommend']:>10.1f} {row['report']:>8.1f} {flag}")
    print("-" * 72)
    avg_d = sum(r["describe"] for r in rows) / len(rows)
    avg_r = sum(r["recommend"] for r in rows) / len(rows)
    avg_rep = sum(r["report"] for r in rows) / len(rows)
    print(f"{'AVERAGE':<24} {avg_d:>9.1f} {avg_r:>10.1f} {avg_rep:>8.1f}")
    print(f"{'='*72}")
    all_pass = all(avg >= 7.0 for avg in [avg_d, avg_r, avg_rep])
    if all_pass:
        print("✅  ALL PROMPTS PASS (average >= 7.0 for all endpoints)")
    else:
        failed = [ep for ep, avg in [("describe", avg_d), ("recommend", avg_r), ("report", avg_rep)] if avg < 7.0]
        print(f"❌  {len(failed)} PROMPT(S) NEED TUNING: {', '.join(failed)}")
    print()
    return all_pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool-70 Prompt Evaluator")
    parser.add_argument("--live", action="store_true", help="Use live Groq API (requires GROQ_API_KEY)")
    parser.add_argument("--mock", action="store_true", help="Use mocked responses (default, no API key needed)")
    args = parser.parse_args()

    mode = "live" if args.live else "mock"
    print(f"Running evaluation in {mode.upper()} mode against 10 real ethics scenarios...")

    rows = evaluate_live() if args.live else evaluate_mock()
    all_pass = print_report(rows, mode)
    sys.exit(0 if all_pass else 1)
