"""
Discharge / Re-enroll Activity — Graduation step at end of PatientJourneyWorkflow.

Marks the patient as discharged from active orchestration in the mock EHR
and logs the final journey summary as a FHIR Observation.

Mock behaviour: logs with patient ID and inserts into mock FHIR server.
"""

import httpx
from temporalio import activity

from shared.constants import FHIR_URL


@activity.defn(name="dischargeOrEnroll")
async def discharge_or_enroll(patient_id: str, status: str = "completed", care_plan_id: str = "", total_check_ins: int = 0) -> dict:
    """
    Graduation activity — called at the end of PatientJourneyWorkflow.

    Marks the patient as discharged from active care orchestration in the
    mock EHR and writes a final FHIR summary Observation.

    Args:
        patient_id:      The patient's MRN / system ID.
        status:          "completed" for a full graduation, or "re_enrolled"
                         if the patient needs another cycle.
        care_plan_id:    ID of the care plan that was followed.
        total_check_ins: Number of check-ins completed during the journey.

    Mock: logs discharge event with patient ID and POSTs to mock FHIR server.
    """
    activity.logger.info(
        f"[DISCHARGE] 🎓 Graduating patient {patient_id} from active orchestration. "
        f"Status: {status} | Care plan: {care_plan_id} | Check-ins: {total_check_ins}"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FHIR_URL}/log-outcome",
            json={
                "patient_id": patient_id,
                "day": 90,
                "event_type": "journey_graduation",
                "details": {
                    "status": status,
                    "care_plan_id": care_plan_id,
                    "total_check_ins": total_check_ins,
                    "graduation_action": "discharged_from_orchestration"
                    if status == "completed"
                    else "re_enrolled_for_next_cycle",
                },
            },
        )
        result = response.json()

    activity.logger.info(
        f"[DISCHARGE] ✅ Patient {patient_id} successfully graduated. "
        f"EHR record ID: {result.get('id', 'N/A')}"
    )
    return {
        "patient_id": patient_id,
        "status": status,
        "graduation_record_id": result.get("id", ""),
        "care_plan_id": care_plan_id,
        "total_check_ins": total_check_ins,
    }
