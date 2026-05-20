"""
Mock Notification/Email Server — simulates sending Emails and SMS.
Logs all notifications to stdout and stores them in memory for the event log.
"""

import logging
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [EMAIL] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock Notification Server", version="2.0.0")

# In-memory message and email store
notifications: dict[str, list] = defaultdict(list)


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    patient_id: str


class SendSMSRequest(BaseModel):
    to: str
    message: str
    patient_id: str


@app.post("/send-email")
async def send_email(request: SendEmailRequest):
    """Simulate sending an Email."""
    sid = f"EM{uuid.uuid4().hex[:24]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "sid": sid,
        "to": request.to,
        "subject": request.subject,
        "message": f"Subject: {request.subject}\n\n{request.body}",
        "patient_id": request.patient_id,
        "timestamp": timestamp,
        "source": "EMAIL",
    }
    notifications[request.patient_id].append(record)

    logger.info(
        f"📧 EMAIL to <{request.to}> | Subject: {request.subject}\n"
        f"   Body: {request.body[:120]}..."
    )
    return {"status": "sent", "sid": sid, "timestamp": timestamp}


@app.post("/send-sms")
async def send_sms(request: SendSMSRequest):
    """Simulate sending an SMS (kept for legacy/fallback)."""
    sid = f"SM{uuid.uuid4().hex[:24]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "sid": sid,
        "to": request.to,
        "message": request.message,
        "patient_id": request.patient_id,
        "timestamp": timestamp,
        "source": "SMS",
    }
    notifications[request.patient_id].append(record)

    logger.info(f"📱 SMS to {request.to}: {request.message[:80]}...")
    return {"status": "sent", "sid": sid, "timestamp": timestamp}


@app.get("/messages/{patient_id}")
async def get_messages(patient_id: str):
    """Retrieve all notifications (Emails and SMS) for a patient (compatibility endpoint)."""
    return {"patient_id": patient_id, "messages": notifications.get(patient_id, [])}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "mock-notifications"}
