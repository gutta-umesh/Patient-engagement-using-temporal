"""
Notification Activities — alerts for timeouts and system events.
"""

import os
import smtplib
from email.message import EmailMessage

from temporalio import activity

# Mock fallback for demonstration if no SMTP is configured
import httpx
from shared.constants import TWILIO_URL

@activity.defn(name="noResponseAlert")
async def send_no_response_alert(patient_id: str, day: int) -> dict:
    """Alert the care team that a patient did not respond to a check-in via SMS."""
    activity.logger.info(
        f"[ALERT] ⏰ No response from patient {patient_id} for Day {day} SMS check-in. Sending alert Email."
    )
    
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    
    recipient = "guttaumesh123@gmail.com"
    subject = f"⏰ URGENT ALERT: No Response from Patient {patient_id} (Day {day})"
    
    body = (
        f"Dear Dr Gutta Umesh, Care coordinator,\n\n"
        f"ALERT: Patient {patient_id} has not responded to their scheduled "
        f"Day {day} post-discharge SMS check-in.\n\n"
        f"The 1-minute response window has expired without any reply from the patient.\n\n"
        f"Please initiate manual follow-up or phone call outreach immediately.\n\n"
        f"Best regards,\n"
        f"CareFlow Automated System"
    )

    if not smtp_username or not smtp_password or smtp_username == "your_email@gmail.com":
        activity.logger.warning("SMTP credentials not configured. Falling back to mock notification service.")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{TWILIO_URL}/send-email",
                    json={
                        "to": recipient,
                        "subject": subject,
                        "body": body,
                        "patient_id": patient_id,
                    },
                )
                return response.json()
            except Exception as e:
                activity.logger.error(f"Failed to reach mock email server: {e}")
                return {"status": "error", "error": str(e)}
            
    # Real SMTP Delivery
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = smtp_username
        msg['To'] = recipient

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        activity.logger.info(f"Real SMTP Email successfully sent to {recipient}")
        from datetime import datetime
        return {"status": "sent_via_smtp", "to": recipient, "timestamp": datetime.now().isoformat()}
        
    except Exception as e:
        activity.logger.error(f"Failed to send SMTP email: {e}")
        raise
