"""
Workflow integration tests using Temporal's time-skipping test environment.

WorkflowEnvironment.start_time_skipping() runs workflows in-process with
durable timers fast-forwarded instantly — no real Temporal server needed.

Tests cover:
  - CheckInWorkflow: signal-received path (all 3 risk tiers)
  - CheckInWorkflow: timeout / no-response path
  - PatientJourneyWorkflow: full happy-path with mocked activities
"""

import pytest
import respx
import httpx
from datetime import timedelta
from typing import Optional
from unittest.mock import AsyncMock, patch

from temporalio import activity
from temporalio.testing import WorkflowEnvironment, ActivityEnvironment
from temporalio.worker import Worker

from workflows.check_in import CheckInWorkflow
from workflows.patient_journey import PatientJourneyWorkflow
from shared.models import (
    Patient, CarePlan, CheckInInput, CheckInResult,
    SurveyResponse, EnrollmentResult, JourneyResult,
)
from shared.constants import SIGNAL_SURVEY_RESPONSE
from tests.conftest import PATIENT, CARE_PLAN, SURVEY_LOW, SURVEY_MODERATE, SURVEY_HIGH


# ── Stub activities (used in workflow integration tests) ──────────────────────
# These replace real activities with simple in-process stubs so workflow
# tests run instantly without any HTTP infrastructure.

@activity.defn(name="sendSMSReminder")
async def stub_send_sms(req) -> dict:
    return {"status": "sent", "sid": "SM-stub"}

@activity.defn(name="scoreSymptoms")
async def stub_score_symptoms(resp: SurveyResponse):
    from shared.models import SymptomScore
    max_s = max(resp.answers) if resp.answers else 0
    if max_s <= 1:
        return SymptomScore(score=max_s, risk_level="low",
                            recommendation="wellness_content", reasoning="stub")
    elif max_s == 2:
        return SymptomScore(score=2, risk_level="moderate",
                            recommendation="schedule_callback", reasoning="stub")
    else:
        return SymptomScore(score=3, risk_level="high",
                            recommendation="escalate", reasoning="stub")

@activity.defn(name="sendWellnessContent")
async def stub_send_wellness(patient_id: str, email: str) -> dict:
    return {"status": "sent"}

@activity.defn(name="scheduleCallBack")
async def stub_schedule_callback(patient_id: str, phone: str) -> dict:
    return {"callback_id": "CB-stub"}

@activity.defn(name="escalateToCare")
async def stub_escalate(patient_id: str, score: int) -> dict:
    return {"slack_alert_sent": True}

@activity.defn(name="noResponseAlert")
async def stub_no_response_alert(patient_id: str, day: int) -> dict:
    return {"status": "logged"}

@activity.defn(name="logOutcomeToEHR")
async def stub_log_ehr(outcome) -> dict:
    return {"id": "OBS-stub"}

@activity.defn(name="enrollPatient")
async def stub_enroll(patient: Patient) -> EnrollmentResult:
    return EnrollmentResult(ehr_id="FHIR-stub-001", status="active")

@activity.defn(name="buildCarePlan")
async def stub_build_care_plan(patient: Patient) -> CarePlan:
    return CARE_PLAN

@activity.defn(name="dischargeOrEnroll")
async def stub_discharge(patient_id: str, status: str, care_plan_id: str, total: int) -> dict:
    return {"patient_id": patient_id, "status": status, "graduation_record_id": "GRAD-stub"}



# All stub activities registered together for easy reuse
ALL_STUB_ACTIVITIES = [
    stub_send_sms,
    stub_score_symptoms,
    stub_send_wellness,
    stub_schedule_callback,
    stub_escalate,
    stub_no_response_alert,
    stub_log_ehr,
    stub_enroll,
    stub_build_care_plan,
    stub_discharge,
]


# ── CheckInWorkflow tests ─────────────────────────────────────────────────────

class TestCheckInWorkflow:
    """Tests for the child CheckInWorkflow using time-skipping environment."""

    async def _run_check_in(self, env: WorkflowEnvironment, survey: Optional[SurveyResponse],
                             day: int = 1) -> CheckInResult:
        """Helper: runs CheckInWorkflow, optionally sending a signal."""
        async with Worker(
            env.client,
            task_queue="test-tq",
            workflows=[CheckInWorkflow],
            activities=ALL_STUB_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                CheckInWorkflow.run,
                CheckInInput(patient=PATIENT, day=day, care_plan=CARE_PLAN, demo_mode=True),
                id=f"test-checkin-d{day}",
                task_queue="test-tq",
            )
            if survey:
                # Small delay then send signal
                import asyncio
                await asyncio.sleep(0.1)
                await handle.signal(SIGNAL_SURVEY_RESPONSE, survey)

            return await handle.result()

    async def test_low_risk_path(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, SURVEY_LOW, day=1)
        assert result.status == "completed"
        assert result.survey_received is True
        assert result.action_taken == "wellness_content_sent"

    async def test_moderate_risk_path(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, SURVEY_MODERATE, day=7)
        assert result.status == "completed"
        assert result.survey_received is True
        assert result.action_taken == "callback_scheduled"

    async def test_high_risk_path(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, SURVEY_HIGH, day=30)
        assert result.status == "completed"
        assert result.survey_received is True
        assert result.action_taken == "escalated_to_care_team"

    async def test_timeout_no_response_path(self):
        """No signal sent → timeout → no_response_alert fired."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, survey=None, day=90)
        assert result.status == "no_response"
        assert result.survey_received is False
        assert result.action_taken == "no_response_alert_sent"

    async def test_result_includes_patient_id_and_day(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, SURVEY_LOW, day=7)
        assert result.patient_id == PATIENT.patient_id
        assert result.day == 7

    async def test_result_includes_completed_at_timestamp(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            result = await self._run_check_in(env, SURVEY_LOW, day=1)
        assert result.completed_at != ""


# ── PatientJourneyWorkflow tests ──────────────────────────────────────────────

class TestPatientJourneyWorkflow:
    """
    Tests for the parent workflow.
    Uses a stripped-down check-in schedule (single day) to keep tests fast.
    Activities are fully stubbed.
    """

    async def test_full_happy_path_completes(self):
        """Parent workflow completes after all check-ins and graduation."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tq",
                workflows=[PatientJourneyWorkflow, CheckInWorkflow],
                activities=ALL_STUB_ACTIVITIES,
            ):
                handle = await env.client.start_workflow(
                    PatientJourneyWorkflow.run,
                    PATIENT,
                    id="test-journey-001",
                    task_queue="test-tq",
                )
                result: JourneyResult = await handle.result()

        assert result.status == "completed"
        assert result.patient_id == PATIENT.patient_id
        assert result.ehr_id == "FHIR-stub-001"
        assert result.care_plan_id == CARE_PLAN.plan_id

    async def test_journey_runs_all_check_in_days(self):
        """Verify all 4 check-in days (1, 7, 30, 90) are executed."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tq",
                workflows=[PatientJourneyWorkflow, CheckInWorkflow],
                activities=ALL_STUB_ACTIVITIES,
            ):
                handle = await env.client.start_workflow(
                    PatientJourneyWorkflow.run,
                    PATIENT,
                    id="test-journey-002",
                    task_queue="test-tq",
                )
                result: JourneyResult = await handle.result()

        assert result.total_check_ins == 4
        completed_days = [ci.day for ci in result.check_in_results]
        assert sorted(completed_days) == [1, 7, 30, 90]

    async def test_get_status_query_reflects_state(self):
        """Query handler returns meaningful state during execution."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tq",
                workflows=[PatientJourneyWorkflow, CheckInWorkflow],
                activities=ALL_STUB_ACTIVITIES,
            ):
                handle = await env.client.start_workflow(
                    PatientJourneyWorkflow.run,
                    PATIENT,
                    id="test-journey-003",
                    task_queue="test-tq",
                )
                # Let it finish, then query the final state
                await handle.result()
                status = await handle.query(PatientJourneyWorkflow.get_status)

        assert status["status"] == "completed"
        assert status["ehr_id"] == "FHIR-stub-001"
        assert len(status["completed_check_ins"]) == 4

    async def test_journey_result_has_completed_at(self):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tq",
                workflows=[PatientJourneyWorkflow, CheckInWorkflow],
                activities=ALL_STUB_ACTIVITIES,
            ):
                handle = await env.client.start_workflow(
                    PatientJourneyWorkflow.run,
                    PATIENT,
                    id="test-journey-004",
                    task_queue="test-tq",
                )
                result: JourneyResult = await handle.result()

        assert result.completed_at != ""
