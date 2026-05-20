"""
Shared test fixtures for the Patient Journey test suite.

Provides:
  - PATIENT_FIXTURE       : a standard Patient dataclass instance
  - CARE_PLAN_FIXTURE     : a standard CarePlan dataclass instance
  - SURVEY_LOW / MED / HIGH : SurveyResponse instances for each risk tier
  - activity_env          : Temporal ActivityEnvironment (pytest fixture)
"""

import pytest
from temporalio.testing import ActivityEnvironment

from shared.models import (
    Patient,
    CarePlan,
    CheckInInput,
    SurveyResponse,
    EHROutcome,
)


# ── Reusable data objects ─────────────────────────────────────────────────────

PATIENT = Patient(
    patient_id="TEST-P-001",
    name="Jane Test",
    phone="+1-555-0001",
    discharge_date="2026-01-01",
    diagnosis="Post-Surgical Recovery",
    care_plan_template="standard_post_discharge",
    email="jane.test@example.com",
)

CARE_PLAN = CarePlan(
    patient_id="TEST-P-001",
    plan_id="CP-test001",
    template_used="standard_post_discharge",
    personalised_instructions=[
        "Follow up with primary care physician within 7 days",
        "Take all prescribed medications as directed",
    ],
    check_in_days=[1, 7, 30, 90],
    risk_factors=["readmission", "medication_non_adherence"],
)

SURVEY_LOW      = SurveyResponse(answers=[0, 1, 0, 0])  # max=1 → low
SURVEY_MODERATE = SurveyResponse(answers=[2, 1, 1, 0])  # max=2 → moderate
SURVEY_HIGH     = SurveyResponse(answers=[3, 2, 1, 1])  # max=3 → high

CHECK_IN_INPUT_DAY1 = CheckInInput(
    patient=PATIENT,
    day=1,
    care_plan=CARE_PLAN,
    demo_mode=True,
)


# ── Pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def activity_env() -> ActivityEnvironment:
    """Temporal ActivityEnvironment — lets activities run outside a real worker."""
    return ActivityEnvironment()
