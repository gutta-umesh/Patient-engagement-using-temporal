"""
Mock FHIR/EHR Server — simulates an Electronic Health Record system.

Endpoints:
  POST /Patient           — Enroll a patient (returns canned FHIR Patient resource)
  POST /log-outcome       — Log a clinical outcome (FHIR Observation)
  POST /schedule-callback — Schedule a nurse/care team callback
  GET  /outcomes/{id}     — Retrieve all outcomes for a patient
  GET  /Patient/{id}      — Retrieve a patient record
  GET  /health            — Health check
"""

import logging
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [FHIR] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock FHIR/EHR Server", version="1.0.0")

# In-memory stores
patients: dict[str, dict] = {}
outcomes: dict[str, list] = defaultdict(list)
callbacks: dict[str, list] = defaultdict(list)


# ─── Request Models ──────────────────────────────────────────────────────────
class CreatePatientRequest(BaseModel):
    resourceType: str = "Patient"
    identifier: str
    name: str
    phone: str = ""
    diagnosis: str = ""
    discharge_date: str = ""


class LogOutcomeRequest(BaseModel):
    patient_id: str
    day: int
    event_type: str
    details: dict = {}


class ScheduleCallbackRequest(BaseModel):
    patient_id: str
    phone: Optional[str] = ""
    reason: str
    priority: str = "routine"


# ─── Endpoints ───────────────────────────────────────────────────────────────
@app.post("/Patient")
async def create_patient(request: CreatePatientRequest):
    """
    Enroll a patient — returns a canned FHIR Patient resource.
    Simulates POST to a real FHIR R4 /Patient endpoint.
    """
    ehr_id = f"FHIR-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    fhir_resource = {
        "resourceType": "Patient",
        "id": ehr_id,
        "meta": {
            "versionId": "1",
            "lastUpdated": timestamp,
        },
        "identifier": [
            {
                "system": "urn:careflow:mrn",
                "value": request.identifier,
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "text": request.name,
            }
        ],
        "telecom": [
            {
                "system": "phone",
                "value": request.phone,
                "use": "mobile",
            }
        ],
        "managingOrganization": {
            "reference": "Organization/careflow-hospital",
            "display": "CareFlow General Hospital",
        },
        # Extra fields for our system
        "diagnosis": request.diagnosis,
        "discharge_date": request.discharge_date,
        "timestamp": timestamp,
    }

    patients[request.identifier] = fhir_resource
    logger.info(
        f"🏥 Patient enrolled: {request.name} (MRN: {request.identifier}) → EHR ID: {ehr_id}"
    )
    return fhir_resource


@app.get("/Patient/{patient_id}")
async def get_patient(patient_id: str):
    """Retrieve a patient record by identifier."""
    if patient_id in patients:
        return patients[patient_id]
    return {"error": "Patient not found", "patient_id": patient_id}


@app.post("/log-outcome")
async def log_outcome(request: LogOutcomeRequest):
    """
    Log a clinical outcome — simulates POST of a FHIR Observation resource.
    """
    record_id = f"OBS-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "resourceType": "Observation",
        "id": record_id,
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "urn:careflow:observation-type",
                    "code": request.event_type,
                    "display": request.event_type.replace("_", " ").title(),
                }
            ]
        },
        "subject": {
            "reference": f"Patient/{request.patient_id}",
        },
        "effectiveDateTime": timestamp,
        "patient_id": request.patient_id,
        "day": request.day,
        "event_type": request.event_type,
        "details": request.details,
        "timestamp": timestamp,
        "source": "EHR",
    }
    outcomes[request.patient_id].append(record)

    logger.info(
        f"📋 Observation logged: {request.event_type} for patient "
        f"{request.patient_id} (Day {request.day})"
    )
    return {"status": "logged", "id": record_id, "timestamp": timestamp}


@app.post("/schedule-callback")
async def schedule_callback_endpoint(request: ScheduleCallbackRequest):
    """Schedule a nurse/care team callback."""
    callback_id = f"CB-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "callback_id": callback_id,
        "patient_id": request.patient_id,
        "phone": request.phone,
        "reason": request.reason,
        "priority": request.priority,
        "timestamp": timestamp,
        "source": "EHR",
    }
    callbacks[request.patient_id].append(record)

    icon = "🚨" if request.priority == "urgent" else "☎️"
    logger.info(f"{icon} Callback scheduled: {request.reason[:60]}...")
    return {"status": "scheduled", "callback_id": callback_id, "timestamp": timestamp}


@app.get("/outcomes/{patient_id}")
async def get_outcomes(patient_id: str):
    """Retrieve all outcomes for a patient."""
    return {
        "patient_id": patient_id,
        "outcomes": outcomes.get(patient_id, []),
        "callbacks": callbacks.get(patient_id, []),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "mock-fhir"}
