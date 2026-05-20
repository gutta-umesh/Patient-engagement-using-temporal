"""
Patient Enrollment Activity — registers the patient in the mock EHR (FHIR server).
POST /Patient to the mock FHIR server, returns a canned FHIR patient resource.
"""

import httpx
from temporalio import activity

from shared.constants import FHIR_URL
from shared.models import Patient, EnrollmentResult


@activity.defn(name="enrollPatient")
async def enroll_patient(patient: Patient) -> EnrollmentResult:
    """
    Enroll a patient in the EHR system.
    POST to mock FHIR /Patient — returns a canned FHIR patient resource.
    """
    activity.logger.info(
        f"[EHR] Enrolling patient {patient.patient_id} ({patient.name}) in EHR"
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FHIR_URL}/Patient",
            json={
                "resourceType": "Patient",
                "identifier": patient.patient_id,
                "name": patient.name,
                "phone": patient.phone,
                "diagnosis": patient.diagnosis,
                "discharge_date": patient.discharge_date,
            },
        )
        result = response.json()

    ehr_id = result.get("id", "")
    activity.logger.info(
        f"[EHR] Patient enrolled successfully — EHR ID: {ehr_id}"
    )
    return EnrollmentResult(
        ehr_id=ehr_id,
        fhir_resource_type="Patient",
        status="active",
    )
