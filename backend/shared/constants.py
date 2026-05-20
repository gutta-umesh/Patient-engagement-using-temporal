"""
Constants for the Patient Journey Workflow system.
Single source of truth for all configuration values.
"""

import os

# ─── Temporal Configuration ──────────────────────────────────────────────────
TASK_QUEUE = "patient-journey-queue"
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")

# ─── Check-In Schedule (days post-discharge) ────────────────────────────────
CHECK_IN_DAYS = [1, 7, 30, 90]

# ─── Demo Mode ───────────────────────────────────────────────────────────────
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# In demo mode, each "day" collapses to this many seconds
DEMO_TIMER_SECONDS = int(os.getenv("DEMO_TIMER_SECONDS", "8"))

# Time to wait for survey response before timeout
SURVEY_TIMEOUT_SECONDS = int(os.getenv("SURVEY_TIMEOUT_SECONDS", "30"))

# In production mode, survey timeout would be 24 hours
PRODUCTION_SURVEY_TIMEOUT_SECONDS = 86400  # 24 hours

# ─── Risk Score Thresholds ───────────────────────────────────────────────────
RISK_LOW_MAX = 1       # Score 0-1 → send wellness content
RISK_MODERATE = 2      # Score 2   → schedule callback
RISK_HIGH_MIN = 3      # Score 3+  → escalate to care team

# ─── External Service URLs ───────────────────────────────────────────────────
TWILIO_URL = os.getenv("TWILIO_URL", "http://localhost:8090")
FHIR_URL = os.getenv("FHIR_URL", "http://localhost:8091")

# ─── Activity Timeouts (seconds) ────────────────────────────────────────────
ACTIVITY_START_TO_CLOSE_TIMEOUT = 30

# ─── Signal Names ────────────────────────────────────────────────────────────
SIGNAL_SURVEY_RESPONSE = "survey_response"

# ─── Workflow ID Conventions ─────────────────────────────────────────────────
def parent_workflow_id(patient_id: str) -> str:
    """Generate deterministic parent workflow ID."""
    return patient_id


def child_workflow_id(patient_id: str, day: int) -> str:
    """Generate deterministic child workflow ID."""
    return f"{patient_id}-checkin-day-{day}"
