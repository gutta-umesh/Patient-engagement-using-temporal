"""
Demo Driver — accelerates time to demonstrate the full patient journey in under 5 minutes.

Compresses "Day 7" to 30 seconds so the entire 90-day journey can be observed quickly.
Automatically sends varied survey responses to showcase all 4 routing paths:

  - Day  1: Low risk     → Wellness content sent
  - Day  7: Moderate     → Nurse callback scheduled
  - Day 30: High risk    → Escalated to care team (Slack webhook)
  - Day 90: No response  → Timeout alert to manager

Usage:
  docker compose --profile demo up --build
"""

import os
import time
import logging
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DEMO-DRIVER] %(message)s",
)
logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://api:8080")
DEMO_TIMER = int(os.getenv("DEMO_TIMER_SECONDS", "2"))

# Pre-configured demo patient
DEMO_PATIENT = {
    "patient_id": "P-DEMO-001",
    "name": "Sarah Johnson",
    "phone": "+1-555-0142",
    "email": "sarah.johnson@example.com",
    "discharge_date": "2026-05-19",
    "diagnosis": "Post-Cardiac Surgery Recovery",
    "care_plan_template": "cardiac_rehabilitation",
}

# Survey responses for each check-in day — showcases all 4 routing paths
SURVEY_SCHEDULE = [
    {
        "day": 1,
        "delay_factor": 1,  # Multiplied by DEMO_TIMER to determine wait
        "response_type": "low_risk",
        "answers": [0, 1, 0, 1],
        "free_text": "Feeling good overall, just some mild discomfort. Recovery seems to be going well.",
        "expected_action": "wellness_content_sent",
    },
    {
        "day": 7,
        "delay_factor": 6,  # (7-1) days compressed
        "response_type": "moderate_risk",
        "answers": [2, 1, 2, 1],
        "free_text": "Feeling tired and have a persistent headache. Some nausea after meals.",
        "expected_action": "callback_scheduled",
    },
    {
        "day": 30,
        "delay_factor": 23,  # (30-7) days compressed
        "response_type": "high_risk",
        "answers": [3, 3, 2, 3],
        "free_text": "Severe chest pain and difficulty breathing. Feeling terrible, worst day so far.",
        "expected_action": "escalated_to_care_team",
    },
    {
        "day": 90,
        "delay_factor": 60,  # (90-30) days compressed
        "response_type": "no_response",
        "answers": None,  # No response — will timeout
        "free_text": None,
        "expected_action": "no_response_alert_sent",
    },
]


def wait_for_api():
    """Wait until the API server is healthy."""
    logger.info(f"Waiting for API server at {API_URL}...")
    for attempt in range(60):
        try:
            resp = requests.get(f"{API_URL}/health", timeout=3)
            if resp.status_code == 200:
                logger.info("✅ API server is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    logger.error("❌ API server did not become ready in time")
    return False


def enroll_patient():
    """Enroll the demo patient."""
    logger.info(f"📋 Enrolling patient: {DEMO_PATIENT['name']} ({DEMO_PATIENT['patient_id']})")
    try:
        resp = requests.post(f"{API_URL}/enroll", json=DEMO_PATIENT, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"✅ Patient enrolled — Workflow: {result['workflow_id']}")
            return result["workflow_id"]
        elif resp.status_code == 409:
            # Already enrolled — derive workflow ID
            wf_id = DEMO_PATIENT['patient_id']
            logger.info(f"⚠️  Patient already enrolled — using existing workflow: {wf_id}")
            return wf_id
        else:
            logger.error(f"❌ Enrollment failed: {resp.status_code} — {resp.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Enrollment error: {e}")
        return None


def submit_survey_response(patient_id: str, day: int, answers: list[int]):
    """Submit a survey response via the numeric endpoint."""
    child_wf_id = f"{patient_id}-checkin-day-{day}"
    logger.info(f"📝 Submitting survey for Day {day}: answers={answers} → {child_wf_id}")

    try:
        resp = requests.post(
            f"{API_URL}/survey-response/{child_wf_id}",
            json={"answers": answers},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"✅ Survey signal delivered for Day {day}")
            return True
        else:
            logger.warning(f"⚠️  Survey signal failed: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Survey submission error: {e}")
        return False


def submit_free_text_survey(patient_id: str, day: int, text: str):
    """Submit a free-text survey via the spec-compliant endpoint."""
    logger.info(f"📝 Submitting free-text survey for Day {day}: '{text[:60]}...'")

    try:
        resp = requests.post(
            f"{API_URL}/api/patients/{patient_id}/survey",
            json={
                "checkInId": f"checkin-d{day}",
                "response": text,
                "runId": "",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            logger.info(
                f"✅ Free-text survey signal delivered for Day {day} "
                f"(derived scores: {result.get('derived_scores')})"
            )
            return True
        else:
            logger.warning(f"⚠️  Free-text survey failed: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Free-text survey error: {e}")
        return False


def check_status(workflow_id: str):
    """Query and log current workflow status."""
    try:
        resp = requests.get(f"{API_URL}/status/{workflow_id}", timeout=10)
        if resp.status_code == 200:
            status = resp.json()
            logger.info(
                f"📊 Status: {status.get('status')} | "
                f"Day: {status.get('current_day')} | "
                f"EHR: {status.get('ehr_id', 'N/A')} | "
                f"Check-ins completed: {len(status.get('completed_check_ins', []))}"
            )
            return status
    except Exception:
        pass
    return None


def run_demo():
    """
    Run the complete demo journey.
    Demonstrates all 4 routing paths with compressed timers.
    """
    logger.info("=" * 70)
    logger.info("🏥 CareFlow Demo Driver — Patient Journey Orchestration")
    logger.info("=" * 70)
    logger.info(f"   Timer compression: 1 day = {DEMO_TIMER}s")
    logger.info(f"   Patient: {DEMO_PATIENT['name']} ({DEMO_PATIENT['patient_id']})")
    logger.info(f"   Diagnosis: {DEMO_PATIENT['diagnosis']}")
    logger.info("=" * 70)

    # Wait for API
    if not wait_for_api():
        return

    # Enroll patient
    workflow_id = enroll_patient()
    if not workflow_id:
        return

    # Wait for enrollment + care plan activities to complete
    logger.info("⏳ Waiting for enrollment and care plan generation...")
    time.sleep(5)
    check_status(workflow_id)

    # Process each scheduled check-in
    for schedule in SURVEY_SCHEDULE:
        day = schedule["day"]
        delay = schedule["delay_factor"] * DEMO_TIMER

        logger.info("")
        logger.info(f"{'─' * 60}")
        logger.info(f"📅 Day {day} — {schedule['response_type'].upper()}")
        logger.info(f"   Waiting {delay}s for check-in to become active...")
        logger.info(f"{'─' * 60}")

        # Wait for the workflow timer to fire and the check-in to start
        time.sleep(delay)

        # Additional buffer for activity execution
        time.sleep(3)

        if schedule["answers"] is not None:
            # Submit survey response — alternate between numeric and free-text
            if schedule["free_text"] and day in [7, 30]:
                # Use spec-compliant free-text endpoint for Days 7 & 30
                submit_free_text_survey(
                    DEMO_PATIENT["patient_id"],
                    day,
                    schedule["free_text"],
                )
            else:
                # Use numeric endpoint for Day 1
                submit_survey_response(
                    DEMO_PATIENT["patient_id"],
                    day,
                    schedule["answers"],
                )
        else:
            logger.info(f"⏰ Day {day}: No response — waiting for timeout...")

        # Wait for scoring + routing to complete
        time.sleep(5)

        # Check status after this check-in
        status = check_status(workflow_id)
        if status:
            check_ins = status.get("completed_check_ins", [])
            for ci in check_ins:
                if ci["day"] == day:
                    action = ci.get("action_taken", "N/A")
                    expected = schedule["expected_action"]
                    match = "✅" if action == expected else "❌"
                    logger.info(
                        f"   {match} Day {day}: action={action} "
                        f"(expected: {expected})"
                    )

    # Final status
    logger.info("")
    logger.info("=" * 70)
    logger.info("🏁 Demo Complete — Full Patient Journey Orchestrated!")
    logger.info("=" * 70)
    final = check_status(workflow_id)
    if final:
        logger.info(f"   Final status: {final.get('status')}")
        logger.info(f"   Total check-ins: {len(final.get('completed_check_ins', []))}")
        for ci in final.get("completed_check_ins", []):
            icon = {"low": "🟢", "moderate": "🟡", "high": "🔴"}.get(
                ci.get("risk_level"), "⚪"
            )
            logger.info(
                f"   {icon} Day {ci['day']}: "
                f"{ci['status']} | score={ci.get('score', 'N/A')} | "
                f"action={ci.get('action_taken', 'N/A')}"
            )


if __name__ == "__main__":
    run_demo()
