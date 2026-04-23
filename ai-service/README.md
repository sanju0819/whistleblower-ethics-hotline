# ai-service — Tool-70 Whistleblower & Ethics Hotline

Flask-based AI microservice. Runs on port **5000**.

## Tech Stack
- Python 3.11, Flask 3.x, Groq API (LLaMA-3.3-70b), flask-limiter

## Setup

```bash
cd ai-service
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in GROQ_API_KEY
python app.py
```

## Environment Variables

| Variable       | Description                          | Default |
|----------------|--------------------------------------|---------|
| `GROQ_API_KEY` | API key from console.groq.com        | —       |
| `AI_PORT`      | Port for the Flask server            | 5000    |
| `FLASK_DEBUG`  | Enable debug mode (`true`/`false`)   | false   |

## API Reference

### `GET /health`
Returns service status and uptime.

**Response:**
```json
{
  "status": "ok",
  "model": "llama-3.3-70b-versatile",
  "uptime_seconds": 120,
  "timestamp": "2026-04-17T10:00:00+00:00"
}
```

---

### `POST /describe`
Generates a structured description of a whistleblower report.

**Request:**
```json
{ "text": "I witnessed my manager approving fake invoices." }
```

**Response:**
```json
{
  "category": "Fraud",
  "severity": "High",
  "summary": "Employee reports manager approving fraudulent invoices.",
  "key_entities": ["Manager", "Finance"],
  "recommended_action": "Initiate an internal audit.",
  "generated_at": "2026-04-17T10:00:00+00:00"
}
```

---

### `POST /recommend`
Returns 3 actionable compliance recommendations.

**Request:**
```json
{ "text": "I witnessed my manager approving fake invoices." }
```

**Response:**
```json
{
  "recommendations": [
    {
      "action_type": "Investigation",
      "description": "Launch a formal internal investigation into the invoicing process.",
      "priority": "High"
    },
    {
      "action_type": "Documentation",
      "description": "Preserve all invoice records and email communications as evidence.",
      "priority": "Medium"
    },
    {
      "action_type": "Policy Review",
      "description": "Review invoice approval policies to close procedural gaps.",
      "priority": "Low"
    }
  ]
}
```

---

### `POST /generate-report`
Generates a formal compliance report document.

**Request:**
```json
{ "text": "I witnessed my manager approving fake invoices." }
```

**Response:**
```json
{
  "title": "Compliance Report — Financial Misconduct",
  "summary": "...",
  "overview": "...",
  "key_items": ["...", "..."],
  "recommendations": ["...", "..."],
  "generated_at": "2026-04-17T10:00:00+00:00"
}
```

## Running Tests

```bash
pytest tests/ -v
```

All tests mock the Groq API — no live network access required.

## Docker

```bash
docker build -t ai-service .
docker run -p 5000:5000 --env-file .env ai-service
```
