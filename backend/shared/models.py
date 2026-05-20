"""
Pydantic models shared across all services.
These are the data contracts for workflows, activities, and the API.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Patient:
    """Patient enrollment data passed to start the journey."""
    patient_id: str
    name: str
    phone: str
    discharge_date: str          # ISO format
    diagnosis: str = "General Post-Surgical"
    ehr_id: str = ""             # Populated after enrollPatient activity
    care_plan_template: str = "standard_post_discharge"
    email: str = ""


@dataclass
class CarePlan:
    """Personalised care plan returned by the buildCarePlan activity."""
    patient_id: str
    plan_id: str = ""
    template_used: str = ""
    personalised_instructions: list[str] = field(default_factory=list)
    check_in_days: list[int] = field(default_factory=lambda: [1, 7, 30, 90])
    risk_factors: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class SurveyResponse:
    """Survey response received via Temporal Signal (numeric scores)."""
    answers: list[int]           # Each answer is 0-3
    submitted_at: str = ""       # ISO timestamp


@dataclass
class SurveySignal:
    """
    Survey signal matching the spec endpoint format.
    POST /api/patients/{patientId}/survey
    Body: { "checkInId": "checkin-d7", "response": "free text", "runId": "..." }
    """
    check_in_id: str             # e.g. "checkin-d7"
    response: str                # Free-text patient response
    run_id: str = ""             # Workflow run ID


@dataclass
class SymptomScore:
    """Result of the AI symptom scoring activity."""
    score: int                   # 0-3
    risk_level: str              # "low", "moderate", "high"
    recommendation: str          # "wellness_content", "schedule_callback", "escalate"
    reasoning: str = ""          # LLM explanation of scoring


@dataclass
class EnrollmentResult:
    """Result of enrolling a patient in the mock EHR."""
    ehr_id: str
    fhir_resource_type: str = "Patient"
    status: str = "active"


@dataclass
class CheckInInput:
    """Input passed from parent to child workflow."""
    patient: Patient
    day: int
    care_plan: CarePlan = field(default_factory=lambda: CarePlan(patient_id=""))
    demo_mode: bool = False


@dataclass
class CheckInResult:
    """Result returned from each CheckInWorkflow child."""
    patient_id: str
    day: int
    status: str                  # "completed", "no_response"
    survey_received: bool = False
    score: Optional[int] = None
    risk_level: Optional[str] = None
    action_taken: Optional[str] = None
    completed_at: str = ""


@dataclass
class JourneyResult:
    """Final result of the entire PatientJourneyWorkflow."""
    patient_id: str
    status: str                  # "completed"
    ehr_id: str = ""
    care_plan_id: str = ""
    check_in_results: list[CheckInResult] = field(default_factory=list)
    total_check_ins: int = 0
    completed_at: str = ""


@dataclass
class EmailRequest:
    """Request to send an Email via mock email service."""
    to: str
    subject: str
    body: str
    patient_id: str


@dataclass
class EHROutcome:
    """Outcome record to log to the mock FHIR server."""
    patient_id: str
    day: int
    event_type: str              # "check_in_result", "enrollment", "journey_complete"
    details: dict = field(default_factory=dict)
