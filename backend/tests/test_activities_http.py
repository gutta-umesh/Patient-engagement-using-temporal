"""
Tests for HTTP-calling activities: enroll_patient, log_outcome_to_ehr,
send_sms_reminder, send_wellness_content, schedule_callback,
escalate_to_care_team, send_no_response_alert, discharge_or_enroll.

All external HTTP calls are intercepted with `respx` so tests are fully
offline and deterministic.
"""

import pytest
import respx
import httpx
from temporalio.testing import ActivityEnvironment

from activities.enrollment import enroll_patient
from activities.ehr import log_outcome_to_ehr
from activities.sms import send_sms_reminder, SMSRequest
from activities.care import send_wellness_content, schedule_callback, escalate_to_care_team
from activities.discharge import discharge_or_enroll
from shared.models import Patient, EHROutcome
from tests.conftest import PATIENT


FHIR_BASE  = "http://localhost:8091"
TWILIO_BASE = "http://localhost:8090"


# ── enroll_patient ────────────────────────────────────────────────────────────

class TestEnrollPatient:

    @respx.mock
    async def test_returns_ehr_id(self):
        respx.post(f"{FHIR_BASE}/Patient").mock(
            return_value=httpx.Response(200, json={"id": "FHIR-abc12345"})
        )
        env = ActivityEnvironment()
        result = await env.run(enroll_patient, PATIENT)
        assert result.ehr_id == "FHIR-abc12345"
        assert result.fhir_resource_type == "Patient"
        assert result.status == "active"

    @respx.mock
    async def test_sends_correct_patient_fields(self):
        """Verify the FHIR POST body contains the right patient data."""
        route = respx.post(f"{FHIR_BASE}/Patient").mock(
            return_value=httpx.Response(200, json={"id": "FHIR-xyz"})
        )
        env = ActivityEnvironment()
        await env.run(enroll_patient, PATIENT)

        sent = route.calls[0].request
        import json
        body = json.loads(sent.content)
        assert body["identifier"] == PATIENT.patient_id
        assert body["name"] == PATIENT.name

    @respx.mock
    async def test_handles_missing_id_gracefully(self):
        """FHIR response without 'id' → ehr_id should be empty string."""
        respx.post(f"{FHIR_BASE}/Patient").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        env = ActivityEnvironment()
        result = await env.run(enroll_patient, PATIENT)
        assert result.ehr_id == ""


# ── log_outcome_to_ehr ────────────────────────────────────────────────────────

class TestLogOutcomeToEHR:

    @respx.mock
    async def test_logs_outcome_successfully(self):
        respx.post(f"{FHIR_BASE}/log-outcome").mock(
            return_value=httpx.Response(200, json={"id": "OBS-001", "status": "logged"})
        )
        env = ActivityEnvironment()
        outcome = EHROutcome(
            patient_id="TEST-P-001",
            day=7,
            event_type="check_in_result",
            details={"score": 2, "risk_level": "moderate"},
        )
        result = await env.run(log_outcome_to_ehr, outcome)
        assert result["id"] == "OBS-001"

    @respx.mock
    async def test_sends_correct_body(self):
        route = respx.post(f"{FHIR_BASE}/log-outcome").mock(
            return_value=httpx.Response(200, json={"id": "OBS-002"})
        )
        env = ActivityEnvironment()
        outcome = EHROutcome(
            patient_id="TEST-P-001",
            day=30,
            event_type="journey_graduation",
            details={"status": "completed"},
        )
        await env.run(log_outcome_to_ehr, outcome)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["patient_id"] == "TEST-P-001"
        assert body["day"] == 30
        assert body["event_type"] == "journey_graduation"


# ── send_sms_reminder ─────────────────────────────────────────────────────────

class TestSendSMSReminder:

    @respx.mock
    async def test_sends_sms_successfully(self):
        respx.post(f"{TWILIO_BASE}/send-sms").mock(
            return_value=httpx.Response(200, json={"status": "sent", "sid": "SM123"})
        )
        env = ActivityEnvironment()
        req = SMSRequest(
            to="patient@example.com",
            subject="Day 1 Check-In",
            body="Hi! Please complete your survey.",
            patient_id="TEST-P-001",
        )
        result = await env.run(send_sms_reminder, req)
        assert result["status"] == "sent"

    @respx.mock
    async def test_message_contains_subject_and_body(self):
        route = respx.post(f"{TWILIO_BASE}/send-sms").mock(
            return_value=httpx.Response(200, json={"sid": "SM456"})
        )
        env = ActivityEnvironment()
        req = SMSRequest(
            to="test@example.com",
            subject="Day 7 Recovery",
            body="How are you feeling?",
            patient_id="TEST-P-001",
        )
        await env.run(send_sms_reminder, req)

        import json
        body = json.loads(route.calls[0].request.content)
        assert "Day 7 Recovery" in body["message"]
        assert "How are you feeling?" in body["message"]
        assert body["patient_id"] == "TEST-P-001"


# ── send_wellness_content ─────────────────────────────────────────────────────

class TestSendWellnessContent:

    @respx.mock
    async def test_sends_wellness_email(self):
        respx.post(f"{TWILIO_BASE}/send-email").mock(
            return_value=httpx.Response(200, json={"status": "sent", "sid": "EM001"})
        )
        env = ActivityEnvironment()
        result = await env.run(send_wellness_content, "TEST-P-001", "test@example.com")
        assert result["status"] == "sent"

    @respx.mock
    async def test_wellness_email_body_content(self):
        route = respx.post(f"{TWILIO_BASE}/send-email").mock(
            return_value=httpx.Response(200, json={"status": "sent"})
        )
        env = ActivityEnvironment()
        await env.run(send_wellness_content, "TEST-P-001", "test@example.com")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["to"] == "test@example.com"
        assert body["patient_id"] == "TEST-P-001"
        assert "wellness" in body["subject"].lower() or "recovery" in body["subject"].lower()


# ── schedule_callback ─────────────────────────────────────────────────────────

class TestScheduleCallback:

    @respx.mock
    async def test_schedules_callback_successfully(self):
        respx.post(f"{FHIR_BASE}/schedule-callback").mock(
            return_value=httpx.Response(200, json={"callback_id": "CB-001", "status": "scheduled"})
        )
        env = ActivityEnvironment()
        result = await env.run(schedule_callback, "TEST-P-001", "+1-555-0001")
        assert result["callback_id"] == "CB-001"

    @respx.mock
    async def test_callback_priority_is_routine(self):
        route = respx.post(f"{FHIR_BASE}/schedule-callback").mock(
            return_value=httpx.Response(200, json={"callback_id": "CB-002"})
        )
        env = ActivityEnvironment()
        await env.run(schedule_callback, "TEST-P-001", "+1-555-0001")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["priority"] == "routine"
        assert body["patient_id"] == "TEST-P-001"


# ── escalate_to_care_team ─────────────────────────────────────────────────────

class TestEscalateToCareTeam:

    @respx.mock
    async def test_escalation_marks_slack_sent(self):
        respx.post(f"{FHIR_BASE}/schedule-callback").mock(
            return_value=httpx.Response(200, json={"callback_id": "CB-URGENT"})
        )
        env = ActivityEnvironment()
        result = await env.run(escalate_to_care_team, "TEST-P-001", 3)
        assert result["slack_alert_sent"] is True
        assert result["slack_channel"] == "#care-team-alerts"

    @respx.mock
    async def test_escalation_priority_is_urgent(self):
        route = respx.post(f"{FHIR_BASE}/schedule-callback").mock(
            return_value=httpx.Response(200, json={"callback_id": "CB-URGENT"})
        )
        env = ActivityEnvironment()
        await env.run(escalate_to_care_team, "TEST-P-001", 3)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["priority"] == "urgent"


# ── discharge_or_enroll ───────────────────────────────────────────────────────

class TestDischargeOrEnroll:

    @respx.mock
    async def test_discharge_returns_patient_id(self):
        respx.post(f"{FHIR_BASE}/log-outcome").mock(
            return_value=httpx.Response(200, json={"id": "GRAD-001", "status": "logged"})
        )
        env = ActivityEnvironment()
        result = await env.run(
            discharge_or_enroll, "TEST-P-001", "completed", "CP-test001", 4
        )
        assert result["patient_id"] == "TEST-P-001"
        assert result["status"] == "completed"
        assert result["total_check_ins"] == 4
        assert result["graduation_record_id"] == "GRAD-001"

    @respx.mock
    async def test_discharge_sends_graduation_event_type(self):
        route = respx.post(f"{FHIR_BASE}/log-outcome").mock(
            return_value=httpx.Response(200, json={"id": "GRAD-002"})
        )
        env = ActivityEnvironment()
        await env.run(discharge_or_enroll, "TEST-P-001", "completed", "CP-abc", 3)

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["event_type"] == "journey_graduation"
        assert body["details"]["status"] == "completed"
        assert body["details"]["total_check_ins"] == 3

    @respx.mock
    async def test_discharge_action_label_correct(self):
        respx.post(f"{FHIR_BASE}/log-outcome").mock(
            return_value=httpx.Response(200, json={"id": "GRAD-003"})
        )
        env = ActivityEnvironment()
        result = await env.run(
            discharge_or_enroll, "TEST-P-001", "completed", "CP-001", 4
        )
        assert result["care_plan_id"] == "CP-001"
