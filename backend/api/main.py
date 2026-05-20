"""
FastAPI Signal API — HTTP interface for the Patient Journey system.

Endpoints:
  POST /enroll                          — Start a new patient journey
  POST /api/patients/{patientId}/survey — Survey signal (spec format)
  POST /survey-response/{id}            — Survey signal (legacy numeric format)
  GET  /status/{workflow_id}            — Query workflow status
  GET  /events/{patient_id}             — Get event log from mock services
  GET  /health                          — Health check
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.service import RPCError
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared.temporal_client import get_temporal_client
from shared.constants import (
    TASK_QUEUE,
    SIGNAL_SURVEY_RESPONSE,
    FHIR_URL,
    TWILIO_URL,
)
from shared.models import Patient, SurveyResponse
from shared.constants import parent_workflow_id, child_workflow_id
from workflows.patient_journey import PatientJourneyWorkflow

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [API] %(message)s")
logger = logging.getLogger(__name__)

# ─── Global Temporal client ──────────────────────────────────────────────────
temporal_client: Optional[Client] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global temporal_client
    logger.info("Connecting to Temporal server...")
    temporal_client = await get_temporal_client()
    logger.info("Temporal client connected.")
    yield


app = FastAPI(
    title="Patient Journey API",
    description="HTTP interface for the Temporal-based post-discharge patient journey system.",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ─────────────────────────────────────────────────
class EnrollRequest(BaseModel):
    patient_id: str
    name: str
    phone: str = "+1-555-0100"
    discharge_date: str = "2026-05-19"
    diagnosis: str = "General Post-Surgical"
    care_plan_template: str = "standard_post_discharge"
    email: str = ""


class SurveyRequest(BaseModel):
    """Legacy numeric survey — each answer is 0-3."""
    answers: list[int]


class SurveySignalRequest(BaseModel):
    """
    Spec-compliant survey signal.
    POST /api/patients/{patientId}/survey
    Body: { "checkInId": "checkin-d7", "response": "free text...", "runId": "..." }
    """
    checkInId: str                # e.g. "checkin-d7" or "checkin-d1"
    response: str                 # Free-text patient response
    runId: str = ""               # Optional workflow run ID


class EnrollResponse(BaseModel):
    workflow_id: str
    status: str
    message: str


# ─── Endpoints ───────────────────────────────────────────────────────────────
@app.post("/enroll", response_model=EnrollResponse)
async def enroll_patient(request: EnrollRequest):
    """Start a new patient journey workflow."""
    wf_id = parent_workflow_id(request.patient_id)
    logger.info(f"Enrolling patient {request.patient_id} → workflow {wf_id}")

    # Generate email if not provided
    email_val = request.email
    if not email_val:
        if "@" in request.phone:
            email_val = request.phone
        else:
            email_val = f"{request.name.lower().replace(' ', '')}@example.com"

    try:
        await temporal_client.start_workflow(
            PatientJourneyWorkflow.run,
            Patient(
                patient_id=request.patient_id,
                name=request.name,
                phone=request.phone,
                discharge_date=request.discharge_date,
                diagnosis=request.diagnosis,
                care_plan_template=request.care_plan_template,
                email=email_val,
            ),
            id=wf_id,
            task_queue=TASK_QUEUE,
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        return EnrollResponse(
            workflow_id=wf_id,
            status="started",
            message=f"Patient journey started for {request.name}",
        )
    except WorkflowAlreadyStartedError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Journey already exists for patient {request.patient_id}",
        )
    except Exception as e:
        if "already started" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Journey already exists for patient {request.patient_id}",
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/patients/{patient_id}/survey")
async def submit_patient_survey(patient_id: str, request: SurveySignalRequest):
    """
    Spec-compliant survey endpoint.
    POST /api/patients/{patientId}/survey
    Body: { "checkInId": "checkin-d7", "response": "Feeling fatigued...", "runId": "..." }

    Converts checkInId to the child workflow ID and sends a survey signal.
    Free-text responses are converted to numeric scores using keyword analysis.
    """
    # Parse day from checkInId (e.g. "checkin-d7" → 7)
    check_in_id = request.checkInId
    try:
        day = int(check_in_id.replace("checkin-d", "").replace("checkin-day-", ""))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid checkInId format: {check_in_id}. Expected 'checkin-d<day>' (e.g. checkin-d7)",
        )

    child_wf_id = child_workflow_id(patient_id, day)
    logger.info(
        f"Survey signal for patient {patient_id}, Day {day}: "
        f"'{request.response[:80]}...' → {child_wf_id}"
    )

    # Convert free-text to numeric scores using keyword analysis
    text_lower = request.response.lower()
    high_keywords = ["severe", "emergency", "chest pain", "bleeding", "terrible", "worst", "crisis"]
    mod_keywords = ["tired", "fatigue", "headache", "nausea", "worried", "sore", "swollen"]
    low_keywords = ["good", "fine", "better", "great", "improving", "well", "okay"]

    high_count = sum(1 for kw in high_keywords if kw in text_lower)
    mod_count = sum(1 for kw in mod_keywords if kw in text_lower)

    if high_count >= 1:
        answers = [3, 3, 2, 2]  # Max 3 -> Category 4/4 (Critical)
    elif mod_count >= 1:
        answers = [2, 1, 1, 1]  # Max 2 -> Category 3/4 (Moderate)
    elif any(kw in text_lower for kw in low_keywords):
        answers = [0, 0, 0, 0]  # Max 0 -> Category 1/4 (Minimal/Safe)
    else:
        answers = [0, 1, 0, 0]  # Max 1 -> Category 2/4 (Low)

    try:
        handle = temporal_client.get_workflow_handle(child_wf_id)
        await handle.signal(
            SIGNAL_SURVEY_RESPONSE,
            SurveyResponse(answers=answers),
        )
        return {
            "status": "signal_sent",
            "patient_id": patient_id,
            "check_in_id": check_in_id,
            "day": day,
            "workflow_id": child_wf_id,
            "derived_scores": answers,
        }
    except RPCError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Check-in workflow not found: {child_wf_id}. "
                   f"The Day {day} check-in may not have started yet.",
        )


@app.post("/survey-response/{workflow_id}")
async def submit_survey_response(workflow_id: str, request: SurveyRequest):
    """Send a survey response signal to a check-in child workflow (legacy numeric format)."""
    logger.info(f"Sending survey signal to {workflow_id}: {request.answers}")

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal(
            SIGNAL_SURVEY_RESPONSE,
            SurveyResponse(answers=request.answers),
        )
        return {"status": "signal_sent", "workflow_id": workflow_id}
    except RPCError as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@app.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Query the current status of a patient journey workflow."""
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        status = await handle.query(PatientJourneyWorkflow.get_status)
        return {"workflow_id": workflow_id, **status}
    except RPCError as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@app.get("/events/{patient_id}")
async def get_events(patient_id: str):
    """Get event logs from mock services for a patient."""
    events = []
    async with httpx.AsyncClient() as client:
        try:
            # Get outcomes from mock FHIR
            resp = await client.get(f"{FHIR_URL}/outcomes/{patient_id}")
            if resp.status_code == 200:
                events.extend(resp.json().get("outcomes", []))
        except Exception:
            pass

        try:
            # Get SMS logs from mock Twilio
            resp = await client.get(f"{TWILIO_URL}/messages/{patient_id}")
            if resp.status_code == 200:
                events.extend(resp.json().get("messages", []))
        except Exception:
            pass

    # Sort by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))
    return {"patient_id": patient_id, "events": events}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "patient-journey-api"}
