# QueueStorm Ticket Sorter

> **SUST CSE Carnival 2026 - Codex Community Hackathon - QueueStorm Warmup**

An AI-powered CRM ticket classification microservice built with **FastAPI**. Reads a customer support message and instantly classifies it by case type, severity, responsible department, and generates an agent-ready summary -- with automatic escalation flags for phishing and critical cases.

---

## Features

| Feature | Details |
|---|---|
| AI Classification | Uses Claude (`claude-sonnet-4-6`) when an API key is present |
| Rule-based Fallback | Works fully offline with keyword-based logic |
| Phishing Detection | Flags OTP/PIN/password solicitation attempts as `critical` |
|  Structured Output | JSON response with type, severity, department, summary, confidence |
|  Interactive UI | Dark-themed web interface to test tickets in the browser |
| Auto Docs | FastAPI auto-generates `/docs` (Swagger) and `/redoc` |

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- (Optional) An Anthropic API key for AI-powered classification

### 1. Clone the repository

```bash
git clone https://github.com/<your-team>/bkash-crm-sorter.git
cd bkash-crm-sorter
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

```bash
# Optional -- without this, the rule-based fallback is used
export ANTHROPIC_API_KEY=sk-ant-...

export PORT=8000   # default
```

On Windows (PowerShell):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:PORT = "8000"
```

### 5. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

---

## API Reference

### `GET /health`

Returns service health status.

**Response**
```json
{
  "status": "ok",
  "service": "QueueStorm Ticket Sorter",
  "version": "1.0.0",
  "ai_enabled": true
}
```

---

### `POST /sort-ticket`

Classifies a customer support ticket.

**Request Body**

```json
{
  "ticket_id": "T-001",
  "channel": "app",
  "locale": "en",
  "message": "I sent 5000 taka to a wrong number this morning, please help me get it back"
}
```

| Field | Type | Required | Values |
|---|---|---|---|
| `ticket_id` | string | | Any string |
| `channel` | string | | `app`, `sms`, `call_center`, `merchant_portal` |
| `locale` | string | | `en`, `bn`, `mixed` |
| `message` | string | | Free-text customer complaint |

**Response**

```json
{
  "ticket_id": "T-001",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT to a wrong number and requests recovery.",
  "human_review_required": true,
  "confidence": 0.88
}
```

**Enums**

`case_type`:
- `wrong_transfer` -- Money sent to wrong recipient
- `payment_failed` -- Transaction failed, balance may be deducted
- `refund_request` -- Customer wants a refund
- `phishing_or_social_engineering` -- Suspicious OTP/PIN solicitation
- `other` -- Anything else

`severity`:
- `low`, `medium`, `high`, `critical`

`department`:
- `customer_support`, `dispute_resolution`, `payments_ops`, `fraud_risk`

`human_review_required` is **always `true`** when:
- `severity == "critical"`, OR
- `case_type == "phishing_or_social_engineering"`

---

## Deploy to Render

This project includes a `render.yaml` for one-click deployment.

### Steps

1. Push this repo to GitHub (must be **public**)
2. Go to [render.com](https://render.com) -> **New -> Web Service**
3. Connect your GitHub account and select this repo
4. Render auto-detects `render.yaml` -- confirm the settings
5. Under **Environment Variables**, add:
   - `ANTHROPIC_API_KEY` -> your key (optional but recommended)
6. Click **Create Web Service**
7. Wait ~2 minutes for the build. Your URL will be `https://<service-name>.onrender.com`

> **Free tier note:** Render free services spin down after 15 minutes of inactivity. The first request after a cold start may take ~20 seconds (within the 30s limit).

### Manual Render Config (if not using `render.yaml`)

| Setting | Value |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Python Version | `3.11` |

---

##  Deploy to Other Platforms

### Railway

```bash
railway login
railway init
railway up
railway variables set ANTHROPIC_API_KEY=sk-ant-...
```

### Fly.io

```bash
fly launch
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t bkash-crm-sorter .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... bkash-crm-sorter
```

---

## Safety Rules

- `agent_summary` will **never** instruct the customer to share PIN, OTP, password, or card number (enforced server-side regardless of AI output)
- Phishing cases are **always** escalated with `human_review_required: true`
- No GPU required -- rule-based fallback ensures the service works without any API keys

---

## Sample Test Cases

```bash
# Wrong transfer
curl -X POST http://localhost:8000/sort-ticket \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"T-001","message":"I sent 3000 to a wrong number"}'

# Phishing
curl -X POST http://localhost:8000/sort-ticket \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"T-003","message":"Someone called asking my OTP, is that bKash?"}'

# Health check
curl http://localhost:8000/health
```

---

## Project Structure

```
bkash-crm-sorter/
+-- main.py              # FastAPI app -- endpoints, schemas, AI + fallback logic
+-- requirements.txt     # Python dependencies
+-- render.yaml          # Render deployment config
+-- Procfile             # Heroku / Railway compatibility
+-- .python-version      # Python 3.11
+-- static/
|   +-- index.html       # Interactive dark-themed web UI
+-- README.md
```

---

##  Architecture

```
POST /sort-ticket
      |
      v
 TicketRequest (Pydantic validation)
      |
      +-- ANTHROPIC_API_KEY set?
      |       +-- YES -> classify_with_claude() -> Claude Sonnet 4.6
      |       +-- NO  -> fallback_classify() [keyword rules]
      |
      v
 Safety guards
   - human_review_required forced true for phishing / critical
   - agent_summary scrubbed for PIN/OTP keywords
      |
      v
 TicketResponse -> JSON
```

---

## Submission Checklist

- [x] `GET /health` endpoint responds within 10 seconds
- [x] `POST /sort-ticket` responds within 30 seconds
- [x] No GPU dependency
- [x] No secrets in repository (uses environment variables)
- [x] `agent_summary` never asks for PIN, OTP, password, or card number
- [x] `human_review_required` is true for phishing and critical cases
- [x] Public GitHub repository with this README
- [x] `render.yaml` for one-click Render deployment
- [x] LLM used: **Claude Sonnet 4.6** (via Anthropic API), with rule-based fallback

---

## Team

- **Team Name:** *Binary Bandits*
- **Deployment Platform:** Render
- **LLM Used:** Yes -- Claude (`claude-sonnet-4-6`) via Anthropic API