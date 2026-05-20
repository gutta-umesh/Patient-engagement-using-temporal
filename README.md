# 🏥 Patient Journey Orchestrator

A Temporal-based post-discharge patient monitoring system that demonstrates workflow orchestration, durable timers, signal handling, and parent-child workflow patterns.

## Architecture

```
Frontend (3000) → FastAPI API (8080) → Temporal Server (7233) → Worker
                                                                  ↓
                                                    Mock Twilio (8090) + Mock FHIR (8091)
```

## Quick Start

```bash
# Start all services (interactive — use the frontend dashboard)
docker compose up --build

# Or include the auto-running demo driver
docker compose --profile demo up --build
```

## Service Ports

| Service | Port | URL |
|---------|------|-----|
| **Frontend Dashboard** | 3000 | http://localhost:3000 |
| **FastAPI API** | 8080 | http://localhost:8080/docs |
| **Temporal UI** | 8233 | http://localhost:8233 |
| **Mock Twilio** | 8090 | http://localhost:8090 |
| **Mock FHIR** | 8091 | http://localhost:8091 |

## How to Demo

### Option 1: Interactive (via Frontend Dashboard)
1. Open http://localhost:3000
2. Click a patient preset or fill in the enrollment form
3. Click **"Begin Automated Monitoring"** to enroll the patient
4. The workflow will: enroll the patient in EHR → build a personalised care plan → start check-ins
5. Fill in survey responses at each check-in or use the phone simulator
6. Watch the timeline, event log, and routing logic update in real-time

### Option 2: Automated (via Demo Driver)
```bash
docker compose --profile demo up --build
```
The demo driver automatically sends varied survey responses to showcase all 4 routing paths:
- Day 1: Low risk → Wellness content sent via SMS
- Day 7: Moderate → Nurse callback scheduled
- Day 30: High risk → Escalated via Slack webhook
- Day 90: No response → Timeout alert to manager

## Workflow Sequence

### Parent Workflow: `PatientJourneyWorkflow`
```
Input: {patientId, name, phone, diagnosis, carePlanTemplate, checkInDays: [1, 7, 30, 90]}

1. enrollPatient      → POST to mock FHIR /Patient → returns canned FHIR resource
2. buildCarePlan      → LLM stub personalises care plan from template + diagnosis
3. Loop over checkInDays:
   └── workflow.sleep(durable timer) → execute child CheckInWorkflow
```

### Child Workflow: `CheckInWorkflow`
```
1. sendSMSReminder    → Twilio stub sends SMS with survey link + care plan tips
2. waitForSignal("surveyResponse") with timeout (72h prod / configurable demo)
3. scoreSymptoms      → LLM stub scores response (PHQ-2 style, 0-3 scale)
4. Branch:
   ├── Score 0-1: sendWellnessContent  → SMS wellness tips
   ├── Score 2:   scheduleCallBack     → POST to mock-scheduler
   ├── Score 3:   escalateToCare       → Slack webhook (logged)
   └── Timeout:   noResponseAlert      → Manager notification
5. logOutcomeToEHR    → POST FHIR Observation to mock server
```

## Activities

| Activity | What it does | Mock |
|----------|-------------|------|
| `enrollPatient` | POST to mock FHIR /Patient | Returns canned FHIR patient resource |
| `buildCarePlan` | LLM fills care plan template | Returns diagnosis-specific JSON plan |
| `sendSMSReminder` | Calls Twilio REST stub | Logs message to stdout |
| `scoreSymptoms` | LLM sentiment + PHQ-2 style scoring | Keyword-based 0-3 score |
| `sendWellnessContent` | SMS wellness tips to patient | Sends via mock Twilio |
| `scheduleCallBack` | Creates appointment in mock scheduling system | POST to mock FHIR |
| `escalateToCare` | Fires Slack webhook to care team channel | Logs alert payload |
| `noResponseAlert` | Sends manager notification | Logs with patient ID |
| `logOutcomeToEHR` | POST FHIR Observation resource | Inserts into mock FHIR server |

## API Endpoints

### Enrollment
```
POST /enroll
Body: { "patient_id": "P-1001", "name": "John Doe", "phone": "+1-555-0100",
        "diagnosis": "Post-Cardiac Surgery", "care_plan_template": "cardiac_rehabilitation" }
```

### Survey Signal (Spec Format)
```
POST /api/patients/{patientId}/survey
Body: { "checkInId": "checkin-d7", "response": "Feeling fatigued, mild headache", "runId": "..." }
```

### Survey Signal (Legacy Numeric)
```
POST /survey-response/{workflowId}
Body: { "answers": [2, 1, 1, 1] }
```

### Status Query
```
GET /status/{workflowId}
```

## Project Structure

```
patient/
├── docker-compose.yml
├── backend/
│   ├── shared/          # Models, constants, Temporal client
│   ├── workflows/       # Parent + Child workflows
│   ├── activities/      # All side-effectful operations (9 activities)
│   ├── worker/          # Temporal worker entrypoint
│   ├── api/             # FastAPI signal & enrollment endpoints
│   ├── mocks/           # Mock Twilio + FHIR servers
│   └── demo/            # Automated demo driver
└── frontend/
    ├── index.html       # Dashboard UI
    ├── css/styles.css   # Design system
    └── js/              # App, API, timeline, checkin, eventlog, explainer
```

## Temporal Concepts Demonstrated

| Concept | Where |
|---------|-------|
| Parent-Child Workflows | `PatientJourneyWorkflow` → `CheckInWorkflow` |
| Durable Timers | `workflow.sleep()` between check-in days |
| Signals | `survey_response` signal to child workflows |
| Signal-vs-Timeout Race | `wait_condition(timeout=...)` in CheckInWorkflow |
| Activity Isolation | All I/O in `activities/` — workflows are pure |
| Workflow Queries | `get_status` query for frontend polling |
| Deterministic Workflow IDs | `patient-journey-{id}-checkin-day-{day}` |

## Docker Compose Services

| Service | Description |
|---------|-------------|
| `temporal-server` | Temporal orchestration engine |
| `temporal-ui` | Temporal web UI (port 8233) |
| `postgres` | PostgreSQL for Temporal persistence |
| `worker` | Temporal worker processing workflows + activities |
| `api-server` | FastAPI HTTP interface for signals + enrollment |
| `mock-fhir-server` | Mock FHIR EHR (HAPI FHIR lite) |
| `mock-twilio` | Mock Twilio SMS webhook logger |
| `demo-driver` | Optional automated demo (use `--profile demo`) |
