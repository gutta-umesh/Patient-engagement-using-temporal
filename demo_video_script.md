# Presentation Script: Temporal Features Walkthrough

This script is structured to show off the backend, highlighting **Temporal’s core features** (Durable Execution, Workflows vs. Activities, Signals, Queries, Child Workflows, and the Event History Audit Trail).

---

### **[Part 1: Introduction — What is Durable Execution?]** (Duration: ~30s)

* **[Visual Cue]** *Open your IDE showing the project root, or have the Temporal Web UI dashboard open on screen.*

* **[Spoken Prompt]** 
  > "Hi everyone. Today I'm going to demonstrate our Post-Discharge Patient Care system. 
  >
  > Instead of writing traditional code with cron jobs, state tables, and polling queues, we built this using **Temporal's Durable Execution** engine. 
  >
  > With Temporal, if a server crashes, if the database drops, or if a network cable is unplugged, our patient journey code doesn't fail. It simply pauses and resumes exactly where it left off, guaranteeing that critical patient care instructions are never lost."

---

### **[Part 2: The Core Concept — Workflows vs. Activities]** (Duration: ~45s)

* **[Visual Cue]** *Highlight the `workflows/` and `activities/` directories in your IDE sidebar.*

* **[Spoken Prompt]** 
  > "The first key Temporal feature is the strict separation between **Workflows** and **Activities**.
  >
  > Workflows are **deterministic orchestrators**. They are not allowed to make direct network calls, generate random numbers, or query local time. Why? Because Temporal tracks a workflow's state by recording its event history. If a worker crashes, Temporal recreates the exact state by **replaying** the history.
  >
  > Activities, on the other hand, are where we isolate **non-deterministic side-effects**. Every network call—like calling our FHIR database or sending an SMS through Twilio—is wrapped in an activity. If an activity fails, Temporal automatically retries it in the background using exponential backoff, without affecting the parent workflow logic."

---

### **[Part 3: Parent & Child Workflows with Durable Sleep]** (Duration: ~1m)

* **[Visual Cue]** *Open [patient_journey.py](file:///Users/umesh/patient/backend/workflows/patient_journey.py) and scroll to the check-in loop (lines 130–144).*

* **[Spoken Prompt]** 
  > "Let's look at two major features here: **Durable Sleep** and **Child Workflows**.
  >
  > In `patient_journey.py`, the parent workflow coordinates a 90-day recovery. To wait between check-ins, we run `await workflow.sleep(...)`. 
  >
  > Unlike a standard Python `time.sleep()`, which hogs server resources and dies if the container restarts, Temporal’s sleep is **durable**. The worker unloads the workflow from memory entirely. The Temporal Server registers a database-backed timer. When it expires, Temporal queues a task, a worker picks it up, and the code seamlessly continues.
  >
  > When the timer wakes up, we execute `CheckInWorkflow` as a **Child Workflow**. Spawning child workflows allows us to modularize complex patient flows and manage separate execution boundaries easily."

---

### **[Part 4: Signals & Queries (Real-time Communication)]** (Duration: ~45s)

* **[Visual Cue]** *Open [check_in.py](file:///Users/umesh/patient/backend/workflows/check_in.py) and scroll to the signal handler (around line 50) and `wait_condition` (lines 103–118).*

* **[Spoken Prompt]**
  > "Another powerful feature is **Signals and Queries**.
  >
  > A **Signal** is a way to send an asynchronous event into a running workflow. Here, we use `workflow.wait_condition` to halt the workflow until the patient replies. When the patient submits their survey, the frontend calls our API, which delivers the `survey_response` signal. This wakes up the workflow instantly, avoiding any resource-heavy database polling.
  >
  > We also use **Queries**—which you can see in `patient_journey.py`. A Query allows the frontend to inspect the internal variables of a running workflow at any moment, safely returning patient state, current care plans, and scores directly from Temporal's active state."

---

### **[Part 5: Activity Retry Policies & Event History]** (Duration: ~45s)

* **[Visual Cue]** *Switch to [check_in.py](file:///Users/umesh/patient/backend/workflows/check_in.py) and highlight `RetryPolicy(maximum_attempts=1)` for the `send_no_response_alert` activity call.*

* **[Spoken Prompt]**
  > "Finally, let's talk about **Retry Policies and Event History**.
  >
  > For integration activities, Temporal retries infinitely by default, assuming downstream services will recover. However, for human alerts—like sending a manager email when a patient misses a survey—we explicitly set a `RetryPolicy` with `maximum_attempts=1`. This prevents sending duplicate spams if there's a slow SMTP connection.
  >
  > If we switch over to the **Temporal Web UI**, we can see the complete, immutable **Event History Audit Trail**. It records every state change, signal, activity schedule, and timer fired event. This gives us full visual debugging and auditing capability out-of-the-box.
  >
  > By utilizing Workflows, Activities, durable Timers, and Signals, we've built a bulletproof clinical system with minimal code. Thank you!"
