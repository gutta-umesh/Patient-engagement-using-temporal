"""
CheckInWorkflow — Child Workflow for a single post-discharge check-in.

Sequence:
  1. sendSMSReminder — Twilio stub sends message with survey link
  2. waitForSignal("surveyResponse") with timeout (72h prod / configurable demo)
  3. scoreSymptoms — LLM scores free-text response for risk (0-3 scale)
  4. Branch:
       Score 0-1: sendWellnessContent
       Score 2:   scheduleCallBack
       Score 3:   escalateToCare
       Timeout:   noResponseAlert
  5. logOutcomeToEHR — FHIR Observation POST to mock server
"""

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared.constants import (
        DEMO_MODE,
        DEMO_TIMER_SECONDS,
        SURVEY_TIMEOUT_SECONDS,
        PRODUCTION_SURVEY_TIMEOUT_SECONDS,
        SIGNAL_SURVEY_RESPONSE,
        ACTIVITY_START_TO_CLOSE_TIMEOUT,
    )
    from shared.models import (
        CheckInInput,
        CheckInResult,
        SurveyResponse,
        EHROutcome,
    )
    from activities.sms import send_sms_reminder, SMSRequest
    from activities.scoring import score_symptoms
    from activities.care import send_wellness_content, schedule_callback, escalate_to_care_team
    from activities.notifications import send_no_response_alert
    from activities.ehr import log_outcome_to_ehr


@workflow.defn(name="CheckInWorkflow")
class CheckInWorkflow:
    """
    Child workflow for a single check-in interaction.

    Uses the Signal-vs-Timeout race pattern:
    - wait_condition(timeout) races a signal against a durable timer
    - If the signal arrives first → process the survey
    - If the timer fires first → handle as no-response
    """

    def __init__(self) -> None:
        self._survey_response: Optional[SurveyResponse] = None

    @workflow.signal(name=SIGNAL_SURVEY_RESPONSE)
    async def handle_survey_response(self, response: SurveyResponse) -> None:
        """Signal handler — stores the response and lets the main loop react."""
        self._survey_response = response
        workflow.logger.info(
            f"[SIGNAL] Survey response received: {response.answers}"
        )

    @workflow.run
    async def run(self, input: CheckInInput) -> CheckInResult:
        workflow.logger.info(f"[CHECK-IN] Initiating Day {input.day} check-in SMS for patient {input.patient.patient_id}")

        # ── Build personalised message with care plan context ─────────────
        care_tips = ""
        if input.care_plan and input.care_plan.personalised_instructions:
            # Include first 2 care plan instructions as reminders
            tips = input.care_plan.personalised_instructions[:2]
            care_tips = "\n\n💡 Recovery Tips:\n- " + "\n- ".join(tips)

        sms_subject = f"🏥 CareFlow: Day {input.day} Recovery Check-In"
        sms_body = (
            f"Hi {input.patient.name},\n\n"
            f"It has been {input.day} day(s) since your discharge. We want to check in on "
            f"how you are recovering.\n\n"
            f"Please reply to this SMS with your symptoms on a scale of 0-3 (Pain, Fatigue, Mood, Sleep). "
            f"https://careflow.health/survey/{input.patient.patient_id}/day-{input.day}"
            f"{care_tips}\n\n"
            f"Best regards,\n"
            f"Your CareFlow Coordination Team"
        )

        # Use patient email or fallback to auto-generated one
        recipient_email = input.patient.email or f"{input.patient.name.lower().replace(' ', '')}@example.com"

        await workflow.execute_activity(
            send_sms_reminder,
            SMSRequest(
                to=recipient_email,
                subject=sms_subject,
                body=sms_body,
                patient_id=input.patient.patient_id,
            ),
            start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
        )

        # ── Step 2: Race — wait for signal OR timeout ────────────────────
        timeout = SURVEY_TIMEOUT_SECONDS if input.demo_mode else PRODUCTION_SURVEY_TIMEOUT_SECONDS
        workflow.logger.info(
            f"[CHECK-IN] Waiting up to {timeout}s for survey response..."
        )

        import asyncio
        try:
            await workflow.wait_condition(
                lambda: self._survey_response is not None,
                timeout=timedelta(seconds=timeout),
            )
            signal_received = True
        except asyncio.TimeoutError:
            signal_received = False

        # ── Step 3: Process based on outcome ─────────────────────────────
        if signal_received and self._survey_response:
            # Survey was received — score it
            score_result = await workflow.execute_activity(
                score_symptoms,
                self._survey_response,
                start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
            )

            # ── Step 1: Send the initial check-in SMS ─────────────────────────────
            action_taken = ""
            if score_result.recommendation == "wellness_content":
                recipient_email = input.patient.email or f"{input.patient.name.lower().replace(' ', '')}@example.com"
                await workflow.execute_activity(
                    send_wellness_content,
                    args=[input.patient.patient_id, recipient_email],
                    start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
                )
                action_taken = "wellness_content_sent"

            elif score_result.recommendation == "schedule_callback":
                await workflow.execute_activity(
                    schedule_callback,
                    args=[input.patient.patient_id, input.patient.phone],
                    start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
                )
                action_taken = "callback_scheduled"

            elif score_result.recommendation == "escalate":
                await workflow.execute_activity(
                    escalate_to_care_team,
                    args=[input.patient.patient_id, score_result.score],
                    start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
                )
                action_taken = "escalated_to_care_team"

            result = CheckInResult(
                patient_id=input.patient.patient_id,
                day=input.day,
                status="completed",
                survey_received=True,
                score=score_result.score,
                risk_level=score_result.risk_level,
                action_taken=action_taken,
                completed_at=workflow.now().isoformat(),
            )
        else:
            # Timeout — no response received
            await workflow.execute_activity(
                send_no_response_alert,
                args=[input.patient.patient_id, input.day],
                start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            result = CheckInResult(
                patient_id=input.patient.patient_id,
                day=input.day,
                status="no_response",
                survey_received=False,
                action_taken="no_response_alert_sent",
                completed_at=workflow.now().isoformat(),
            )

        # ── Step 5: Log outcome to EHR (FHIR Observation POST) ──────────
        await workflow.execute_activity(
            log_outcome_to_ehr,
            EHROutcome(
                patient_id=input.patient.patient_id,
                day=input.day,
                event_type="check_in_result",
                details={
                    "status": result.status,
                    "score": result.score,
                    "risk_level": result.risk_level,
                    "action_taken": result.action_taken,
                },
            ),
            start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
        )

        workflow.logger.info(
            f"[CHECK-IN] Day {input.day} complete — "
            f"status={result.status}, action={result.action_taken}"
        )
        return result
