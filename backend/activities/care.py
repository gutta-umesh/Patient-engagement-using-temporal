"""
Care Team Activities — wellness content, callbacks, and escalation.

Activities:
  - sendWellnessContent: Score 0-1 → SMS wellness tips
  - scheduleCallBack: Score 2 → POST to mock-scheduler/FHIR
  - escalateToCare: Score 3 → Fire Slack webhook to care team channel
"""

import json
import httpx
from temporalio import activity

from shared.constants import TWILIO_URL, FHIR_URL


@activity.defn(name="sendWellnessContent")
async def send_wellness_content(patient_id: str, email: str) -> dict:
    """Send wellness/educational content to the patient via Email."""
    activity.logger.info(f"[CARE] Sending wellness content Email to {email}")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TWILIO_URL}/send-email",
            json={
                "to": email,
                "subject": "🌿 CareFlow: Your Recovery Wellness Tips",
                "body": "Great news! Your post-discharge recovery is on track.\n\n"
                        "Here are some key wellness tips to help you recover:\n"
                        "- Stay well-hydrated throughout the day\n"
                        "- Take short, gentle walks as tolerated\n"
                        "- Ensure you get plenty of rest\n"
                        "- Follow your personalized care instructions closely.\n\n"
                        "Keep up the great work!",
                "patient_id": patient_id,
            },
        )
        result = response.json()
    activity.logger.info(f"[CARE] Wellness content Email sent to {email}")
    return result


@activity.defn(name="scheduleCallBack")
async def schedule_callback(patient_id: str, phone: str) -> dict:
    """
    Schedule a nurse callback via the mock scheduling system.
    Creates an appointment in the mock FHIR scheduler.
    """
    activity.logger.info(f"[CARE] Scheduling nurse callback for patient {patient_id}")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FHIR_URL}/schedule-callback",
            json={
                "patient_id": patient_id,
                "phone": phone,
                "reason": "Moderate symptom score — nurse follow-up needed within 24 hours",
                "priority": "routine",
            },
        )
        result = response.json()
    activity.logger.info(f"[CARE] Callback scheduled: {result.get('callback_id', 'N/A')}")
    return result


@activity.defn(name="escalateToCare")
async def escalate_to_care_team(patient_id: str, score: int) -> dict:
    """
    Escalate to care team for high-risk patients.
    Fires a Slack webhook to the care team channel (mocked via logging).
    Also creates an urgent callback in the scheduling system.
    """
    # ── Build Slack webhook payload ──────────────────────────────────────
    slack_payload = {
        "channel": "#care-team-alerts",
        "username": "CareFlow Alert Bot",
        "icon_emoji": ":rotating_light:",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 HIGH RISK PATIENT ALERT",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Patient ID:*\n{patient_id}"},
                    {"type": "mrkdwn", "text": f"*Symptom Score:*\n{score}/3 (Critical)"},
                    {"type": "mrkdwn", "text": "*Priority:*\nURGENT — Immediate Review"},
                    {"type": "mrkdwn", "text": "*Source:*\nAutomated CareFlow Assessment"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Patient reported severe symptoms during post-discharge check-in. "
                            "Immediate care coordinator review and intervention required.",
                },
            },
        ],
    }

    # ── Log the Slack alert payload (mock webhook fire) ──────────────────
    activity.logger.info(
        f"[SLACK] 🚨 ESCALATION — Firing Slack webhook to #care-team-alerts "
        f"for patient {patient_id} (score: {score})"
    )
    activity.logger.info(
        f"[SLACK] Webhook payload: {json.dumps(slack_payload, indent=2)}"
    )

    # ── Also create urgent callback in scheduling system ─────────────────
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FHIR_URL}/schedule-callback",
            json={
                "patient_id": patient_id,
                "phone": "",
                "reason": f"CRITICAL — Symptom score {score}/3 — "
                          f"Immediate care team review and intervention required",
                "priority": "urgent",
            },
        )
        result = response.json()

    activity.logger.info(
        f"[CARE] Urgent escalation created: {result.get('callback_id', 'N/A')}"
    )
    return {**result, "slack_alert_sent": True, "slack_channel": "#care-team-alerts"}
