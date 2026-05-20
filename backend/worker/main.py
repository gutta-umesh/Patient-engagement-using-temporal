"""
Temporal Worker — registers all workflows and activities on the task queue.

This is the single entrypoint for the worker service.
"""

import asyncio
import logging

from temporalio.worker import Worker

from shared.temporal_client import get_temporal_client
from shared.constants import TASK_QUEUE

# Workflows
from workflows.patient_journey import PatientJourneyWorkflow
from workflows.check_in import CheckInWorkflow

# Activities
from activities.enrollment import enroll_patient
from activities.care_plan import build_care_plan
from activities.sms import send_sms_reminder
from activities.scoring import score_symptoms, score_free_text
from activities.ehr import log_outcome_to_ehr
from activities.care import send_wellness_content, schedule_callback, escalate_to_care_team
from activities.notifications import send_no_response_alert
from activities.discharge import discharge_or_enroll


logging.basicConfig(level=logging.INFO, format="%(asctime)s [WORKER] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    logger.info("Connecting to Temporal server...")
    client = await get_temporal_client()

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            PatientJourneyWorkflow,
            CheckInWorkflow,
        ],
        activities=[
            # Enrollment & care plan
            enroll_patient,
            build_care_plan,
            # SMS
            send_sms_reminder,
            # AI/LLM scoring
            score_symptoms,
            score_free_text,
            # Care routing
            send_wellness_content,
            schedule_callback,
            escalate_to_care_team,
            # Notifications
            send_no_response_alert,
            # EHR
            log_outcome_to_ehr,
            # Graduation
            discharge_or_enroll,
        ],
    )

    logger.info("Worker is running. Waiting for tasks...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
