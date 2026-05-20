"""
Email Activity — simulates sending an email notification to the patient.
Sends a request to the mock email/notification service.
"""

import httpx
from temporalio import activity
from pydantic import BaseModel

from shared.constants import TWILIO_URL

class SMSRequest(BaseModel):
    to: str
    subject: str
    body: str
    patient_id: str

@activity.defn(name="sendSMSReminder")
async def send_sms_reminder(request: SMSRequest) -> dict:
    """Send an SMS via the mock notification service (running at TWILIO_URL)."""
    activity.logger.info(
        f"[SMS] Sending check-in SMS to <{request.to}> with subject: '{request.subject}'"
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TWILIO_URL}/send-sms",
            json={
                "to": request.to,
                "message": f"Subject: {request.subject}\n\n{request.body}",
                "patient_id": request.patient_id,
            },
        )
        result = response.json()
    activity.logger.info(
        f"[Email] Email sent successfully: SID={result.get('sid', 'N/A')} "
        f"| Subject={request.subject}"
    )
    return result
