"""
Care Plan Activity — LLM-powered care plan personalisation.
In production this would call an LLM service; the mock returns a canned plan.
"""

import uuid
from datetime import datetime, timezone

from temporalio import activity

from shared.models import Patient, CarePlan
from shared.constants import CHECK_IN_DAYS


@activity.defn(name="buildCarePlan")
async def build_care_plan(patient: Patient) -> CarePlan:
    """
    Build a personalised care plan using an LLM stub.
    
    In production: sends patient history + template to an LLM to generate
    a personalised post-discharge care plan.
    Mock: returns a realistic-looking care plan based on the diagnosis.
    """
    activity.logger.info(
        f"[LLM] Building personalised care plan for {patient.patient_id} "
        f"(diagnosis: {patient.diagnosis}, template: {patient.care_plan_template})"
    )

    # ── Mock LLM personalisation based on diagnosis ──────────────────────
    diagnosis_lower = patient.diagnosis.lower()

    if "cardiac" in diagnosis_lower or "heart" in diagnosis_lower:
        instructions = [
            "Monitor blood pressure twice daily (morning and evening)",
            "Take prescribed beta-blockers with food",
            "Limit sodium intake to < 2000mg/day",
            "Walk 15 minutes daily, increasing by 5 min each week",
            "Report any chest pain, shortness of breath, or swelling immediately",
            "Attend cardiac rehabilitation sessions as scheduled",
        ]
        risk_factors = ["hypertension", "post-surgical_complications", "medication_adherence"]
    elif "ortho" in diagnosis_lower or "knee" in diagnosis_lower or "hip" in diagnosis_lower:
        instructions = [
            "Perform prescribed physical therapy exercises 3x daily",
            "Keep surgical site clean and dry",
            "Use ice packs for 20 min every 2 hours for first 48 hours",
            "Take pain medication as prescribed — do not exceed dosage",
            "Use assistive device (walker/crutches) for all mobility",
            "Elevate affected limb when resting",
        ]
        risk_factors = ["fall_risk", "wound_infection", "DVT"]
    elif "pneumonia" in diagnosis_lower or "respiratory" in diagnosis_lower:
        instructions = [
            "Complete full course of prescribed antibiotics",
            "Use incentive spirometer 10 times every hour while awake",
            "Monitor temperature twice daily",
            "Stay well-hydrated — minimum 8 glasses of water daily",
            "Report any fever > 101°F, worsening cough, or difficulty breathing",
            "Avoid smoking and secondhand smoke exposure",
        ]
        risk_factors = ["reinfection", "dehydration", "oxygen_desaturation"]
    else:
        instructions = [
            "Follow up with primary care physician within 7 days",
            "Take all prescribed medications as directed",
            "Monitor temperature and report fever > 101°F",
            "Keep surgical site/wounds clean and dry",
            "Gradually increase activity level as tolerated",
            "Maintain adequate hydration and nutrition",
        ]
        risk_factors = ["readmission", "medication_non_adherence", "wound_complications"]

    plan = CarePlan(
        patient_id=patient.patient_id,
        plan_id=f"CP-{uuid.uuid4().hex[:8]}",
        template_used=patient.care_plan_template,
        personalised_instructions=instructions,
        check_in_days=CHECK_IN_DAYS,
        risk_factors=risk_factors,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    activity.logger.info(
        f"[LLM] Care plan generated: {plan.plan_id} | "
        f"{len(instructions)} instructions | "
        f"Risk factors: {', '.join(risk_factors)}"
    )
    return plan
