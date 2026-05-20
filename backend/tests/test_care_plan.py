"""
Tests for buildCarePlan activity.

build_care_plan is a pure-logic LLM stub — no HTTP calls — so we test
every diagnosis branch and the structure of the returned CarePlan.
"""

import pytest
from temporalio.testing import ActivityEnvironment

from activities.care_plan import build_care_plan
from shared.models import Patient


def make_patient(diagnosis: str) -> Patient:
    return Patient(
        patient_id="TEST-P-CAREPLAN",
        name="Test Patient",
        phone="+1-555-0000",
        discharge_date="2026-01-01",
        diagnosis=diagnosis,
        care_plan_template="standard_post_discharge",
        email="test@example.com",
    )


class TestBuildCarePlan:

    async def test_returns_care_plan_with_plan_id(self):
        env = ActivityEnvironment()
        patient = make_patient("Post-Surgical Recovery")
        plan = await env.run(build_care_plan, patient)
        assert plan.plan_id.startswith("CP-")
        assert len(plan.plan_id) > 3

    async def test_patient_id_matches(self):
        env = ActivityEnvironment()
        patient = make_patient("General")
        plan = await env.run(build_care_plan, patient)
        assert plan.patient_id == "TEST-P-CAREPLAN"

    async def test_template_used_matches_patient(self):
        env = ActivityEnvironment()
        patient = make_patient("Respiratory")
        plan = await env.run(build_care_plan, patient)
        assert plan.template_used == "standard_post_discharge"

    async def test_cardiac_diagnosis_branch(self):
        env = ActivityEnvironment()
        patient = make_patient("Cardiothoracic Cardiac Surgery")
        plan = await env.run(build_care_plan, patient)
        assert len(plan.personalised_instructions) >= 4
        assert any("blood pressure" in i.lower() or "beta" in i.lower()
                   for i in plan.personalised_instructions)
        assert "hypertension" in plan.risk_factors or "medication_adherence" in plan.risk_factors

    async def test_ortho_diagnosis_branch(self):
        env = ActivityEnvironment()
        patient = make_patient("Knee Replacement Surgery")
        plan = await env.run(build_care_plan, patient)
        assert len(plan.personalised_instructions) >= 4
        assert "DVT" in plan.risk_factors or "fall_risk" in plan.risk_factors

    async def test_pneumonia_diagnosis_branch(self):
        env = ActivityEnvironment()
        patient = make_patient("Pneumonia Respiratory Infection")
        plan = await env.run(build_care_plan, patient)
        assert len(plan.personalised_instructions) >= 4
        assert any("antibiotic" in i.lower() or "spirometer" in i.lower()
                   for i in plan.personalised_instructions)

    async def test_general_default_branch(self):
        env = ActivityEnvironment()
        patient = make_patient("General Post-Surgical")
        plan = await env.run(build_care_plan, patient)
        assert len(plan.personalised_instructions) >= 4
        assert "readmission" in plan.risk_factors or "medication_non_adherence" in plan.risk_factors

    async def test_check_in_days_are_correct(self):
        env = ActivityEnvironment()
        patient = make_patient("General")
        plan = await env.run(build_care_plan, patient)
        assert plan.check_in_days == [1, 7, 30, 90]

    async def test_instructions_are_non_empty_strings(self):
        env = ActivityEnvironment()
        patient = make_patient("Post-Surgical Recovery")
        plan = await env.run(build_care_plan, patient)
        for instruction in plan.personalised_instructions:
            assert isinstance(instruction, str)
            assert len(instruction.strip()) > 0

    async def test_created_at_is_set(self):
        env = ActivityEnvironment()
        patient = make_patient("General")
        plan = await env.run(build_care_plan, patient)
        assert plan.created_at != ""
        # Should be an ISO datetime string
        assert "T" in plan.created_at or "-" in plan.created_at

    async def test_unique_plan_ids_per_call(self):
        """Each call to buildCarePlan must produce a unique plan ID."""
        env = ActivityEnvironment()
        patient = make_patient("General")
        plan1 = await env.run(build_care_plan, patient)
        plan2 = await env.run(build_care_plan, patient)
        assert plan1.plan_id != plan2.plan_id
