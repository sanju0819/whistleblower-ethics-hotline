# ai-service — Tool-70 Whistleblower & Ethics Hotline (AI Microservice)

Flask 3.x Python microservice providing AI-powered analysis of whistleblower reports
via the Groq API (LLaMA-3.3-70b) and RAG over a ChromaDB knowledge base.

Runs on **port 5000**. Consumed by the Java Spring Boot backend on port 8080.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python --version` |
| pip | latest | `pip install --upgrade pip` |
| Groq API key | — | Free at [console.groq.com](https://console.groq.com) |
| Redis | 7+ | Optional locally; required in production for rate limiting |
| Docker + Compose | latest | For containerised deployment |

---

## Setup (Local Development)

```bash
# 1. Clone and enter the ai-service directory
cd ai-service

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env — set GROQ_API_KEY at minimum

# 5. Run the development server
python app.py
```

The service starts on `http://localhost:5000`. Check `GET /health` to confirm it is running.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in real values. **Never commit `.env`.**

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | **Yes** | — | Groq API key from console.groq.com |
| `AI_PORT` | No | `5000` | Port the Flask/Gunicorn server listens on |
| `FLASK_DEBUG` | No | `false` | Set `true` for hot-reload in local dev only |
| `REDIS_URL` | No* | `memory://` | Redis URL for rate-limiter shared state. *Required in production (e.g. `redis://redis:6379`). Without it, each Gunicorn worker has its own counter — rate limits are not enforced correctly across workers. A warning is logged at startup if unset. |
| `CHROMA_PERSIST_DIR` | No | `./chroma_data` | Path where ChromaDB stores its persistent vector data. In Docker this maps to the named volume in `docker-compose.yml`. |

---

## API Reference

All endpoints accept and return `application/json`. Rate limit: **30 requests / minute per IP**.

### `GET /health`

Returns service status, model info, uptime, and vector store document count.

**Response 200:**
```json
{
  "status": "ok",
  "model": "llama-3.3-70b-versatile",
  "embedding_model": "all-MiniLM-L6-v2",
  "vector_store_documents": 10,
  "uptime_seconds": 142,
  "timestamp": "2026-04-24T10:00:00+00:00"
}
```

---

### `POST /describe`

Accepts a whistleblower report text and returns a structured AI description.

**Request:** `{ "text": "My manager has been approving fictitious expense claims." }`

**Response 200:**
```json
{
  "category": "Fraud",
  "severity": "High",
  "summary": "An employee reports their manager approving fraudulent expense claims.",
  "key_entities": ["manager", "Finance Department"],
  "recommended_action": "Initiate an internal audit of expense approvals.",
  "generated_at": "2026-04-24T10:00:00+00:00",
  "is_fallback": false
}
```

---

### `POST /recommend`

Returns 3 prioritised compliance recommendations for a given report.

**Request:** `{ "text": "A colleague is being harassed by a senior manager." }`

**Response 200:**
```json
{
  "recommendations": [
    { "action_type": "Investigation", "description": "...", "priority": "High" },
    { "action_type": "Documentation", "description": "...", "priority": "Medium" },
    { "action_type": "Training", "description": "...", "priority": "Low" }
  ],
  "generated_at": "2026-04-24T10:00:00+00:00",
  "is_fallback": false
}
```

---

### `POST /generate-report`

Generates a formal compliance report document from the submission text.

**Request:** `{ "text": "Safety equipment was not provided on the factory floor." }`

**Response 200:**
```json
{
  "title": "Compliance Report — Workplace Safety Violation",
  "summary": "An employee reports absence of required personal protective equipment.",
  "overview": "The report describes...",
  "key_items": ["PPE not provided", "Requests ignored for 3 months"],
  "recommendations": ["Immediate PPE audit", "Escalate to Health & Safety officer"],
  "generated_at": "2026-04-24T10:00:00+00:00",
  "is_fallback": false
}
```

---

### `POST /query` *(RAG — Retrieval-Augmented Generation)*

Answers natural language questions using the embedded ethics knowledge base
(ChromaDB + DefaultEmbeddingFunction).

**RAG Flow:**
1. Embed the query with ChromaDB's default ONNX embedding function
2. Retrieve top-3 relevant documents from ChromaDB (cosine similarity >= 0.4)
3. Inject retrieved context into the Groq prompt
4. Return structured answer with source attribution

**Request:** `{ "query": "What whistleblower protection laws apply to financial fraud?" }`

**Response 200:**
```json
{
  "answer": "Whistleblowers reporting financial fraud are protected under the Sarbanes-Oxley Act and Dodd-Frank Act...",
  "sources": ["Compliance Handbook — Financial Fraud", "Whistleblower Protection Policy"],
  "confidence": "High",
  "generated_at": "2026-04-24T10:00:00+00:00",
  "is_fallback": false
}
```

**Confidence:** `High` (context directly answers) | `Medium` (partial) | `Low` (general knowledge)  
**Field limits:** `query` max 2000 characters, `text` max 5000 characters.

---

## Running Tests

```bash
pytest tests/ -v
```

All tests mock the Groq API — no live network access required.

---

## Docker

```bash
docker build -t ai-service .
docker run -p 5000:5000 --env-file .env ai-service
```

---

## Project Structure

```
ai-service/
├── app.py                  # Application factory, health endpoint, error handlers
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── .env.example
├── prompts/
│   ├── describe_prompt.txt
│   ├── recommend_prompt.txt
│   ├── report_prompt.txt
│   └── query_prompt.txt
├── routes/
│   ├── describe.py         # POST /describe
│   ├── recommend.py        # POST /recommend
│   ├── report.py           # POST /generate-report
│   ├── query.py            # POST /query  (RAG)
│   ├── middleware.py       # Sanitisation + request correlation IDs
│   └── helpers.py          # load_prompt, sanitise_input, extract_json
├── services/
│   ├── groq_client.py      # Groq API client with retry + Retry-After backoff
│   └── vector_store.py     # ChromaDB collection and default embeddings
└── tests/
    ├── conftest.py          # Shared pytest fixtures
    └── test_endpoints.py   # 20 tests — all Groq calls mocked
```
