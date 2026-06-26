import os
import time
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from enum import Enum

app = FastAPI(
    title="bKash CRM Ticket Sorter",
    description="AI-powered CRM ticket classification service for SUST CSE Carnival 2026 Hackathon",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Enums ──────────────────────────────────────────────────────────────────────

class CaseType(str, Enum):
    wrong_transfer = "wrong_transfer"
    payment_failed = "payment_failed"
    refund_request = "refund_request"
    phishing = "phishing_or_social_engineering"
    other = "other"

class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class Department(str, Enum):
    customer_support = "customer_support"
    dispute_resolution = "dispute_resolution"
    payments_ops = "payments_ops"
    fraud_risk = "fraud_risk"


# ── Schemas ────────────────────────────────────────────────────────────────────

class TicketRequest(BaseModel):
    ticket_id: str
    channel: Optional[str] = None
    locale: Optional[str] = None
    message: str

class TicketResponse(BaseModel):
    ticket_id: str
    case_type: str
    severity: str
    department: str
    agent_summary: str
    human_review_required: bool
    confidence: float


# ── Claude AI Classification ───────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are a CRM ticket classifier for bKash, a digital finance platform in Bangladesh.

Classify customer support tickets into exactly these categories and return ONLY valid JSON.

CASE TYPES:
- wrong_transfer: Money sent to the wrong recipient
- payment_failed: Transaction failed but balance may be deducted
- refund_request: Customer asking for a refund
- phishing_or_social_engineering: Suspicious calls/SMS, someone asking for PIN, OTP, or password
- other: Anything not covered above

SEVERITY:
- low: Minor issues, no financial risk (app bugs, general questions, changed-mind refunds)
- medium: Moderate issues that need attention but not urgent
- high: Financial loss or potential financial impact (wrong transfer, failed payment)
- critical: Security threats, fraud, phishing attempts

DEPARTMENT:
- customer_support: other cases, low severity refund requests
- dispute_resolution: wrong_transfer, contested refund_request
- payments_ops: payment_failed
- fraud_risk: phishing_or_social_engineering

RULES:
- human_review_required must be true if severity is "critical" OR case_type is "phishing_or_social_engineering"
- agent_summary must be 1-2 neutral sentences — NEVER ask for PIN, OTP, password, or card number
- confidence should reflect how certain you are (0.0 to 1.0)

Respond ONLY with this JSON structure, no extra text:
{
  "case_type": "...",
  "severity": "...",
  "department": "...",
  "agent_summary": "...",
  "human_review_required": true/false,
  "confidence": 0.0
}"""


async def classify_with_claude(message: str, locale: str = "en") -> dict:
    """Call Claude API to classify the ticket."""
    if not ANTHROPIC_API_KEY:
        return fallback_classify(message)

    user_prompt = f"Classify this customer support ticket (locale: {locale}):\n\n{message}"

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 512,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data["content"][0]["text"].strip()
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text.strip())


def fallback_classify(message: str) -> dict:
    """Rule-based fallback when no API key is set."""
    msg = message.lower()

    # Phishing detection
    phishing_keywords = ["otp", "pin", "password", "account number", "verification code",
                         "called me", "sms from", "asking for", "share my", "give my"]
    if any(k in msg for k in phishing_keywords):
        return {
            "case_type": "phishing_or_social_engineering",
            "severity": "critical",
            "department": "fraud_risk",
            "agent_summary": "Customer reports a suspicious contact requesting sensitive account credentials. Immediate security review required.",
            "human_review_required": True,
            "confidence": 0.88,
        }

    # Wrong transfer
    transfer_keywords = ["wrong number", "wrong person", "wrong account", "sent to wrong",
                         "mistaken transfer", "wrong recipient"]
    if any(k in msg for k in transfer_keywords):
        return {
            "case_type": "wrong_transfer",
            "severity": "high",
            "department": "dispute_resolution",
            "agent_summary": "Customer reports sending money to an incorrect recipient and is requesting recovery assistance.",
            "human_review_required": True,
            "confidence": 0.90,
        }

    # Payment failed
    failed_keywords = ["payment fail", "transaction fail", "failed", "not received", "deducted but",
                       "balance deducted", "money deducted", "charge but"]
    if any(k in msg for k in failed_keywords):
        return {
            "case_type": "payment_failed",
            "severity": "high",
            "department": "payments_ops",
            "agent_summary": "Customer reports a failed transaction with a possible balance deduction. Payment reconciliation is needed.",
            "human_review_required": False,
            "confidence": 0.85,
        }

    # Refund request
    refund_keywords = ["refund", "money back", "return my", "get back", "revert", "reverse"]
    if any(k in msg for k in refund_keywords):
        return {
            "case_type": "refund_request",
            "severity": "medium",
            "department": "dispute_resolution",
            "agent_summary": "Customer is requesting a refund for a recent transaction.",
            "human_review_required": False,
            "confidence": 0.82,
        }

    # Default
    return {
        "case_type": "other",
        "severity": "low",
        "department": "customer_support",
        "agent_summary": "Customer has submitted a general inquiry that does not match a specific financial incident category.",
        "human_review_required": False,
        "confidence": 0.60,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """Returns service health status."""
    return {
        "status": "ok",
        "service": "bKash CRM Ticket Sorter",
        "version": "1.0.0",
        "ai_enabled": bool(ANTHROPIC_API_KEY),
    }


@app.post("/sort-ticket", response_model=TicketResponse, tags=["Classification"])
async def sort_ticket(ticket: TicketRequest):
    """
    Accepts a CRM ticket and returns structured classification.

    - Identifies case type, severity, and responsible department
    - Generates a brief agent-readable summary
    - Flags phishing or critical cases for human review
    """
    try:
        result = await classify_with_claude(ticket.message, ticket.locale or "en")
    except Exception:
        result = fallback_classify(ticket.message)

    # Safety guard: ensure human_review is set correctly
    if result.get("case_type") == "phishing_or_social_engineering" or result.get("severity") == "critical":
        result["human_review_required"] = True

    # Safety guard: never include sensitive prompts in summary
    forbidden = ["pin", "otp", "password", "card number"]
    summary_lower = result.get("agent_summary", "").lower()
    if any(word in summary_lower for word in forbidden):
        result["agent_summary"] = "Customer has submitted a support request that requires agent review."

    return TicketResponse(
        ticket_id=ticket.ticket_id,
        case_type=result.get("case_type", "other"),
        severity=result.get("severity", "low"),
        department=result.get("department", "customer_support"),
        agent_summary=result.get("agent_summary", "Customer submitted a support ticket."),
        human_review_required=result.get("human_review_required", False),
        confidence=float(result.get("confidence", 0.70)),
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    """Serve the interactive UI."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())