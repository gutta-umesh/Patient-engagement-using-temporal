"""
EHR Activities — logging outcomes to the mock FHIR server.
"""

import httpx
from temporalio import activity

from shared.constants import FHIR_URL
from shared.models import EHROutcome


@activity.defn(name="logOutcomeToEHR")
async def log_outcome_to_ehr(outcome: EHROutcome) -> dict:
    """Log a check-in outcome to the mock FHIR/EHR server."""
    activity.logger.info(
        f"[EHR] Logging {outcome.event_type} for patient {outcome.patient_id} (Day {outcome.day})"
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FHIR_URL}/log-outcome",
            json={
                "patient_id": outcome.patient_id,
                "day": outcome.day,
                "event_type": outcome.event_type,
                "details": outcome.details,
            },
        )
        result = response.json()
    activity.logger.info(f"[EHR] Outcome logged successfully: {result.get('id', 'N/A')}")
    return result
