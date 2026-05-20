"""
PatientJourneyWorkflow — Parent Workflow orchestrating the full post-discharge journey.

Sequence:
  1. enrollPatient — creates patient record in mock EHR
  2. buildCarePlan — LLM personalises the care plan from template + patient history
  3. Loop over checkInDays, scheduling a child CheckInWorkflow with durable timer delay

This workflow contains ZERO side effects — all I/O is delegated to activities
and child workflows.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared.constants import (
        CHECK_IN_DAYS,
        DEMO_MODE,
        DEMO_TIMER_SECONDS,
        TASK_QUEUE,
        ACTIVITY_START_TO_CLOSE_TIMEOUT,
    )
    from shared.models import (
        Patient,
        CarePlan,
        EnrollmentResult,
        CheckInInput,
        CheckInResult,
        JourneyResult,
    )
    from workflows.check_in import CheckInWorkflow
    from activities.enrollment import enroll_patient
    from activities.care_plan import build_care_plan
    from activities.discharge import discharge_or_enroll


@workflow.defn(name="PatientJourneyWorkflow")
class PatientJourneyWorkflow:
    """
    Parent workflow — orchestrates the complete post-discharge patient journey.

    Responsibilities:
    1. Enroll patient in EHR (enrollPatient activity)
    2. Build personalised care plan (buildCarePlan activity via LLM stub)
    3. Loop through CHECK_IN_DAYS sequentially
    4. Sleep (durable timer) until each check-in day
    5. Execute CheckInWorkflow as a child for each check-in
    6. Collect and return all results
    """

    def __init__(self) -> None:
        self._check_in_results: list[CheckInResult] = []
        self._current_day: int = 0
        self._status: str = "started"
        self._ehr_id: str = ""
        self._care_plan: CarePlan | None = None

    @workflow.query
    def get_status(self) -> dict:
        """Query handler — returns current journey state for the frontend."""
        return {
            "status": self._status,
            "current_day": self._current_day,
            "ehr_id": self._ehr_id,
            "care_plan": {
                "plan_id": self._care_plan.plan_id if self._care_plan else "",
                "template_used": self._care_plan.template_used if self._care_plan else "",
                "instructions": self._care_plan.personalised_instructions if self._care_plan else [],
                "risk_factors": self._care_plan.risk_factors if self._care_plan else [],
            },
            "completed_check_ins": [
                {
                    "day": r.day,
                    "status": r.status,
                    "score": r.score,
                    "risk_level": r.risk_level,
                    "action_taken": r.action_taken,
                    "completed_at": r.completed_at,
                }
                for r in self._check_in_results
            ],
        }

    @workflow.run
    async def run(self, patient: Patient) -> JourneyResult:
        demo_mode = DEMO_MODE
        workflow.logger.info(
            f"[JOURNEY] Starting patient journey for {patient.name} "
            f"(ID: {patient.patient_id}) | demo_mode={demo_mode}"
        )

        # ── Step 1: Enroll patient in EHR ────────────────────────────────
        self._status = "enrolling"
        workflow.logger.info(
            f"[JOURNEY] Step 1: Enrolling patient {patient.patient_id} in EHR"
        )
        enrollment = await workflow.execute_activity(
            enroll_patient,
            patient,
            start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
        )
        self._ehr_id = enrollment.ehr_id
        patient.ehr_id = enrollment.ehr_id
        workflow.logger.info(
            f"[JOURNEY] Patient enrolled — EHR ID: {enrollment.ehr_id}"
        )

        # ── Step 2: Build personalised care plan (LLM stub) ──────────────
        self._status = "building_care_plan"
        workflow.logger.info(
            f"[JOURNEY] Step 2: Building care plan (template: {patient.care_plan_template})"
        )
        care_plan = await workflow.execute_activity(
            build_care_plan,
            patient,
            start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
        )
        self._care_plan = care_plan
        workflow.logger.info(
            f"[JOURNEY] Care plan ready: {care_plan.plan_id} | "
            f"{len(care_plan.personalised_instructions)} instructions | "
            f"Risk factors: {care_plan.risk_factors}"
        )

        # ── Step 3: Loop through check-in days ───────────────────────────
        previous_day = 0

        for day in CHECK_IN_DAYS:
            # ── Durable timer: sleep until this check-in day ─────────────
            days_to_wait = day - previous_day
            if demo_mode:
                sleep_seconds = days_to_wait * DEMO_TIMER_SECONDS
            else:
                sleep_seconds = days_to_wait * 86400  # Real days

            workflow.logger.info(
                f"[JOURNEY] Sleeping {sleep_seconds}s until Day {day} "
                f"({'demo' if demo_mode else 'production'} mode)"
            )
            await workflow.sleep(timedelta(seconds=sleep_seconds))

            # ── Execute child workflow for this check-in ─────────────────
            self._current_day = day
            self._status = f"check_in_day_{day}"

            workflow.logger.info(f"[JOURNEY] Executing CheckInWorkflow for Day {day}")

            from shared.constants import child_workflow_id

            result = await workflow.execute_child_workflow(
                CheckInWorkflow.run,
                CheckInInput(
                    patient=patient,
                    day=day,
                    care_plan=care_plan,
                    demo_mode=demo_mode,
                ),
                id=child_workflow_id(patient.patient_id, day),
                task_queue=workflow.info().task_queue,
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

            # ── Record result and break if non-responsive ─────────────────
            self._check_in_results.append(result)
            workflow.logger.info(
                f"[JOURNEY] Day {day} result: {result.status} | action: {result.action_taken}"
            )
            
            if result.status == "no_response":
                workflow.logger.info(f"[JOURNEY] Patient went non-responsive on Day {day}. Halting automated pipeline.")
                break

            previous_day = day

        # ── Graduation: dischargeOrEnroll ────────────────────────────────
        self._status = "graduating"
        workflow.logger.info(
            f"[JOURNEY] Step 4 (Graduation): Discharging patient {patient.patient_id} "
            f"from active orchestration."
        )
        await workflow.execute_activity(
            discharge_or_enroll,
            args=[
                patient.patient_id,
                "completed",
                care_plan.plan_id,
                len(self._check_in_results),
            ],
            start_to_close_timeout=timedelta(seconds=ACTIVITY_START_TO_CLOSE_TIMEOUT),
        )

        # ── Journey complete ─────────────────────────────────────────────
        self._status = "completed"
        workflow.logger.info(
            f"[JOURNEY] Patient journey completed for {patient.patient_id}. "
            f"Total check-ins: {len(self._check_in_results)}"
        )

        return JourneyResult(
            patient_id=patient.patient_id,
            status="completed",
            ehr_id=self._ehr_id,
            care_plan_id=care_plan.plan_id,
            check_in_results=self._check_in_results,
            total_check_ins=len(self._check_in_results),
            completed_at=workflow.now().isoformat(),
        )
