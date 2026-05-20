/**
 * API Client — all HTTP calls to the FastAPI backend.
 */
const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : `http://${window.location.hostname}:8080`;

const api = {
    async enroll(patient) {
        const resp = await fetch(`${API_BASE}/enroll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patient),
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Enrollment failed');
        }
        return resp.json();
    },

    async submitSurvey(workflowId, answers) {
        const resp = await fetch(`${API_BASE}/survey-response/${workflowId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answers }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to submit survey signal');
        }
        return resp.json();
    },

    async submitSurveyText(patientId, checkInId, responseText) {
        const resp = await fetch(`${API_BASE}/api/patients/${patientId}/survey`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ checkInId, response: responseText, runId: "" }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to submit survey signal');
        }
        return resp.json();
    },

    async getStatus(workflowId) {
        const resp = await fetch(`${API_BASE}/status/${workflowId}`);
        if (!resp.ok) return null;
        return resp.json();
    },

    async getEvents(patientId) {
        const resp = await fetch(`${API_BASE}/events/${patientId}`);
        if (!resp.ok) return { events: [] };
        return resp.json();
    },
};

/** Safe element getter — returns a no-op stub when element is missing, preventing null crashes */
function safeEl(id) {
    const el = document.getElementById(id);
    if (el) return el;
    // Return a stub that silently ignores property access
    return new Proxy({}, { get: () => '', set: () => true });
}

window.currentState = { enrolled: false, patientId: null, workflowId: null, currentDay: 0, lastStatus: null, lastShownDay: 0, toastShownForDay: null };
let pollInterval = null;

async function handleEnroll() {
    const patientId = document.getElementById('enroll-id').value.trim();
    const patientName = document.getElementById('enroll-name').value.trim();
    const phone = document.getElementById('enroll-phone').value.trim();
    const diagnosis = document.getElementById('enroll-diagnosis').value.trim();

    if (!patientId || !patientName || !phone || !diagnosis) {
        showToast('⚠️ Input Required', 'Please enter all patient details before initiating monitoring.', 'warning');
        alert('Please enter the patient details.');
        return;
    }

    const btn = document.getElementById('btn-enroll');
    btn.disabled = true;
    btn.innerHTML = '<span class="status-dot"></span> Orchestrating...';

    addEvent('SYSTEM', `Initiating post-discharge monitoring pipeline for ${patientName}`);

    try {
        const result = await api.enroll({
            patient_id: patientId,
            name: patientName,
            phone,
            discharge_date: new Date().toISOString().split('T')[0],
            diagnosis
        });
        window.currentState = { ...window.currentState, enrolled: true, patientId, workflowId: result.workflow_id, toastShownForDay: null };

        // Save patient into global roster storage
        const newPatient = {
            patientId,
            name: patientName,
            email: phone,
            diagnosis,
            workflowId: result.workflow_id,
            currentDay: 0,
            lastStatus: 'active',
            lastShownDay: 0,
            completed_check_ins: []
        };
        // Deduplicate MRNs
        window.enrolledPatients = (window.enrolledPatients || []).filter(p => p.patientId !== patientId);
        window.enrolledPatients.push(newPatient);
        localStorage.setItem('enrolledPatients', JSON.stringify(window.enrolledPatients));

        if (typeof renderActivePatients === 'function') {
            renderActivePatients();
        }

        // Hide enrollment form, reveal monitoring dashboards and grids via showSection
        showSection('dashboard');

        document.getElementById('patient-name-display').textContent = patientName;
        document.getElementById('mrn-display').textContent = patientId;
        document.getElementById('diagnosis-tag').textContent = diagnosis;

        // Dynamic avatar initials
        const initials = patientName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        document.getElementById('patient-avatar').textContent = initials;

        addEvent('SYSTEM', `Patient journey orchestration started successfully. Workflow ID: ${result.workflow_id}`);

        // Setup initial phone simulator message
        const msgList = document.getElementById('phone-messages');
        msgList.innerHTML = '<div class="phone-msg-bubble"><b>CareFlow System</b><br><br>Welcome to your post-discharge support service. We will send you regular check-in recovery SMS messages.</div>';

        showWaitingState('Awaiting initial Day 1 check-in scheduling...');
        startPolling();
    } catch (err) {
        addEvent('ALERT', `Failed to start orchestration: ${err.message}`);
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            Begin Automated Monitoring
        `;
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        await pollStatus();
        await pollEvents();
    }, 2000);
}

async function pollStatus() {
    const state = window.currentState;
    if (!state.enrolled || !state.workflowId) return;
    try {
        const status = await api.getStatus(state.workflowId);
        if (!status) return;
        state.lastStatus = status;
        updateTimeline(status);

        // Update persistent active patient roster state in local storage
        if (window.enrolledPatients) {
            const p = window.enrolledPatients.find(x => x.patientId === state.patientId);
            if (p) {
                p.currentDay = status.current_day || p.currentDay || 0;
                p.completed_check_ins = status.completed_check_ins || [];

                const latest = (status.completed_check_ins || []).slice(-1)[0];
                if (latest) {
                    // Properly handle no_response: risk_level is null for timed-out check-ins
                    if (latest.status === 'no_response') {
                        p.lastStatus = 'no_response';
                    } else if (latest.action_taken === 'escalated_to_care_team') {
                        p.lastStatus = 'escalated';
                    } else {
                        p.lastStatus = latest.risk_level || 'active';
                    }
                }
                if (status.status === 'completed') {
                    p.lastStatus = 'completed';
                }
                localStorage.setItem('enrolledPatients', JSON.stringify(window.enrolledPatients));
                if (typeof renderActivePatients === 'function') {
                    renderActivePatients();
                }
            }
        }

        const completedDays = (status.completed_check_ins || []).map(ci => ci.day);
        state.currentDay = status.current_day || 0;

        if (status.status === 'completed') {
            document.getElementById('status-text').textContent = 'Monitoring Completed';
            document.querySelector('.status-chip').className = 'status-chip completed';
            clearInterval(pollInterval);
            addEvent('SYSTEM', 'Post-discharge journey orchestration finished successfully. Patient graduated from active monitoring pipeline.');

            showWaitingState('Workflow complete. Patient discharged from care orchestration.');
            disablePhoneSms();
            const planCard = document.getElementById('clinical-plan-card');
            if (planCard) planCard.style.display = 'none';

            // ── Reset enroll button & form so a new patient can be enrolled ──
            setTimeout(() => {
                const btn = document.getElementById('btn-enroll');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                        Begin Automated Monitoring
                    `;
                }
                // Clear form inputs for next patient
                const fieldsToReset = ['enroll-name', 'enroll-id', 'enroll-phone', 'enroll-diagnosis'];
                fieldsToReset.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.value = '';
                });
                addEvent('SYSTEM', '✅ Enrollment form reset — ready to monitor a new patient.');
            }, 3500); // Short delay so user sees the "completed" state first

            return;
        }

        const statusStr = status.status || '';
        const dayMatch = statusStr.match(/check_in_day_(\d+)/);
        if (dayMatch) {
            const activeDay = parseInt(dayMatch[1]);
            if (activeDay !== state.lastShownDay && !completedDays.includes(activeDay)) {
                state.lastShownDay = activeDay;
                state.currentDay = activeDay;
                state.toastShownForDay = null; // Reset toast tracking for new day check-in
                addEvent('SMS', `Check-in SMS delivered for Day ${activeDay}`);
                showSurveyForm(activeDay);
                triggerPhoneSms(activeDay);
            }
        }

        const latestCompleted = (status.completed_check_ins || []).slice(-1)[0];
        if (latestCompleted && latestCompleted.day === state.lastShownDay) {
            showScoreResult(latestCompleted);
            const rl = latestCompleted.risk_level || 'timeout';
            addEvent('AI', `Symptom score evaluation: ${latestCompleted.score ?? 'N/A'} (Risk: ${rl ? rl.toUpperCase() : 'TIMEOUT'})`);
            addEvent('CARE', `Protocol executed: ${latestCompleted.action_taken || 'None'}`);
            addEvent('EHR', `FHIR record entry updated successfully`);
            
            // Explicitly generate ALERT events for critical protocols
            if (latestCompleted.action_taken === 'no_response_alert_sent') {
                addEvent('ALERT', 'noResponseAlert: Manager notification triggered for non-responsive patient.');
            } else if (latestCompleted.action_taken === 'escalated_to_care_team') {
                addEvent('ALERT', 'escalateToCare: Slack webhook fired to care team channel.');
            }

            // Trigger toast alert for timed-out/no response check-in if not already shown
            if (latestCompleted.status === 'no_response' && state.toastShownForDay !== latestCompleted.day) {
                state.toastShownForDay = latestCompleted.day;
                const pName = document.getElementById('patient-name-display').textContent || 'Jane Doe';
                showToast(
                    '⏰ Patient Non-Responsive',
                    `Email has been sent to the care coordinator that patient ${pName} is not responding.`,
                    'danger'
                );
            }

            disablePhoneSms();

            const next = CHECK_IN_DAYS.filter(d => d > latestCompleted.day);
            if (next.length > 0) {
                setTimeout(() => {
                    showWaitingState(`Waiting for Day ${next[0]} check-in window...`);
                }, 3000);
            }
            state.lastShownDay = -1;
        }
    } catch (err) {
        console.error("Error in pollStatus:", err);
    }
}

async function pollEvents() {
    const state = window.currentState;
    if (!state.enrolled || !state.patientId) return;
    try {
        const data = await api.getEvents(state.patientId);
        processApiEvents(data.events || []);
    } catch (err) { }
}

function triggerPhoneSms(day) {
    const msgList = document.getElementById('phone-messages');

    // Check if SMS already showing to prevent duplicates
    if (msgList.querySelector(`[data-sms-day="${day}"]`)) return;

    const smsBubble = document.createElement('div');
    smsBubble.className = 'phone-msg-bubble';
    smsBubble.setAttribute('data-sms-day', day);
    smsBubble.innerHTML = `<b>CareFlow SMS: Day ${day} Recovery Check-In</b><br><br>Hi! It is Day ${day} since your discharge. Please complete your recovery check-in survey below.`;
    msgList.appendChild(smsBubble);
    msgList.scrollTop = msgList.scrollHeight;

    // Enable patient simulated click reply buttons
    // The clinical sliders will be used instead.
}

function disablePhoneSms() {
    // Quick reply buttons are removed, handled by slider locking
}

function applyPreset(name, mrn, phone, diagnosis) {
    const uniqueMrn = mrn + '-' + Math.floor(1000 + Math.random() * 9000);
    document.getElementById('enroll-name').value = name;
    document.getElementById('enroll-id').value = uniqueMrn;
    document.getElementById('enroll-phone').value = phone;
    document.getElementById('enroll-diagnosis').value = diagnosis;
    addEvent('SYSTEM', `Preset template applied for patient ${name} (${uniqueMrn})`);
}

function selectRosterPatient(name, mrn, email, diagnosis) {
    applyPreset(name, mrn, email, diagnosis);
    showSection('enroll');
}

window.enrolledPatients = JSON.parse(localStorage.getItem('enrolledPatients') || '[]');

function selectActivePatient(patientId) {
    const patients = window.enrolledPatients || [];
    const p = patients.find(x => x.patientId === patientId);
    if (p) {
        // Clear any existing poll intervals to prevent overlap
        if (pollInterval) clearInterval(pollInterval);

        window.currentState = {
            enrolled: true,
            patientId: p.patientId,
            workflowId: p.workflowId,
            currentDay: p.currentDay || 0,
            lastStatus: p.lastStatus || null,
            lastShownDay: p.lastShownDay || 0,
            toastShownForDay: null
        };

        document.getElementById('patient-name-display').textContent = p.name;
        document.getElementById('mrn-display').textContent = p.patientId;
        document.getElementById('diagnosis-tag').textContent = p.diagnosis;

        const initials = p.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        document.getElementById('patient-avatar').textContent = initials;

        // Clear events and load logs for this patient if desired, or keep audit trail
        clearEvents();
        addEvent('SYSTEM', `Loaded telemetry log trail for active patient: ${p.name}`);

        // Load timeline
        updateTimeline({
            completed_check_ins: p.completed_check_ins || [],
            current_day: p.currentDay || 0,
            status: p.lastStatus === 'completed' ? 'completed' : 'active'
        });

        // Set phone mockups or surveys if active
        if (p.lastStatus === 'no_response' || p.lastStatus === 'timeout') {
            showWaitingState('Patient did not respond within 762 hours. Non-Responsive protocol active.');
        } else if (p.lastStatus === 'escalated') {
            showWaitingState('High risk detected. Care coordinator team paged.');
        } else {
            showWaitingState('Awaiting symptom check-in event...');
        }

        // Start polling
        startPolling();
        showSection('dashboard');

        addEvent('SYSTEM', `Post-discharge orchestration tracking loaded for ${p.name}`);
    }
}

async function quickEnrollPreset(name, baseMrn, email, diagnosis) {
    const uniqueMrn = baseMrn + '-' + Math.floor(1000 + Math.random() * 9000);
    addEvent('SYSTEM', `Quick enrolling preset patient: ${name} (${uniqueMrn})`);

    try {
        const result = await api.enroll({
            patient_id: uniqueMrn,
            name: name,
            phone: email,
            discharge_date: new Date().toISOString().split('T')[0],
            diagnosis: diagnosis
        });

        window.currentState = { ...window.currentState, enrolled: true, patientId: uniqueMrn, workflowId: result.workflow_id };

        const newPatient = {
            patientId: uniqueMrn,
            name: name,
            email: email,
            diagnosis: diagnosis,
            workflowId: result.workflow_id,
            currentDay: 0,
            lastStatus: 'active',
            lastShownDay: 0,
            completed_check_ins: []
        };
        window.enrolledPatients = (window.enrolledPatients || []).filter(p => p.patientId !== uniqueMrn);
        window.enrolledPatients.push(newPatient);
        localStorage.setItem('enrolledPatients', JSON.stringify(window.enrolledPatients));

        if (typeof renderActivePatients === 'function') renderActivePatients();

        showSection('dashboard');

        document.getElementById('patient-name-display').textContent = name;
        document.getElementById('mrn-display').textContent = uniqueMrn;
        document.getElementById('diagnosis-tag').textContent = diagnosis;

        const initials = name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        document.getElementById('patient-avatar').textContent = initials;

        addEvent('SYSTEM', `Patient journey orchestration started successfully. Workflow ID: ${result.workflow_id}`);

        const msgList = document.getElementById('phone-messages');
        msgList.innerHTML = '<div class="phone-msg-bubble"><b>CareFlow System</b><br><br>Welcome to your post-discharge support service. We will send you regular check-in recovery SMS messages.</div>';

        showWaitingState('Awaiting initial Day 1 check-in scheduling...');
        startPolling();
    } catch (err) {
        addEvent('ALERT', `Failed to enroll preset patient: ${err.message}`);
        alert(`Enrollment failed: ${err.message}`);
    }
}

async function addNewPatient() {
    const nameInput = document.getElementById('new-patient-name');
    const idInput = document.getElementById('new-patient-id');
    const emailInput = document.getElementById('new-patient-email');
    const diagnosisInput = document.getElementById('new-patient-diagnosis');
    const btn = document.getElementById('btn-add-patient');

    const patientName = nameInput.value.trim();
    const patientId = idInput.value.trim() || `P-${Math.floor(1000 + Math.random() * 9000)}`;
    const email = emailInput.value.trim() || `${patientName.toLowerCase().replace(/\s+/g, '')}@example.com`;
    const diagnosis = diagnosisInput.value.trim() || 'General Post-Surgical Recovery';

    if (!patientName) {
        alert('Please enter a patient name.');
        nameInput.focus();
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="status-dot"></span> Enrolling...';
    addEvent('SYSTEM', `Enrolling new custom patient: ${patientName} (${patientId})`);

    try {
        const result = await api.enroll({
            patient_id: patientId,
            name: patientName,
            phone: email,
            discharge_date: new Date().toISOString().split('T')[0],
            diagnosis: diagnosis
        });

        window.currentState = { ...window.currentState, enrolled: true, patientId: patientId, workflowId: result.workflow_id };

        const newPatient = {
            patientId: patientId,
            name: patientName,
            email: email,
            diagnosis: diagnosis,
            workflowId: result.workflow_id,
            currentDay: 0,
            lastStatus: 'active',
            lastShownDay: 0,
            completed_check_ins: []
        };
        window.enrolledPatients = (window.enrolledPatients || []).filter(p => p.patientId !== patientId);
        window.enrolledPatients.push(newPatient);
        localStorage.setItem('enrolledPatients', JSON.stringify(window.enrolledPatients));

        if (typeof renderActivePatients === 'function') renderActivePatients();

        showSection('dashboard');

        document.getElementById('patient-name-display').textContent = patientName;
        document.getElementById('mrn-display').textContent = patientId;
        document.getElementById('diagnosis-tag').textContent = diagnosis;

        const initials = patientName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        document.getElementById('patient-avatar').textContent = initials;

        addEvent('SYSTEM', `Patient journey orchestration started for ${patientName}. Workflow: ${result.workflow_id}`);

        const msgList = document.getElementById('phone-messages');
        msgList.innerHTML = '<div class="phone-msg-bubble"><b>CareFlow System</b><br><br>Welcome to your post-discharge support service. We will send you regular check-in recovery SMS messages.</div>';

        showWaitingState('Awaiting initial Day 1 check-in scheduling...');
        startPolling();

        // Clear the form for next use
        nameInput.value = '';
        idInput.value = '';
        emailInput.value = '';
        diagnosisInput.value = '';
    } catch (err) {
        addEvent('ALERT', `Failed to enroll patient: ${err.message}`);
        alert(`Enrollment failed: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            Enroll & Start Monitoring
        `;
    }
}

function renderActivePatients() {
    const container = document.getElementById('active-patients-list');
    if (!container) return;

    const list = window.enrolledPatients || [];

    const activeCardWrapper = container.closest('.enroll-card');

    if (list.length === 0) {
        if (activeCardWrapper) {
            activeCardWrapper.style.display = 'none';
        }
        return;
    } else {
        if (activeCardWrapper) {
            activeCardWrapper.style.display = 'block';
        }
    }

    container.innerHTML = list.map(p => {
        let riskColor = '#5eff7e';
        let riskBg = 'rgba(94, 255, 126, 0.12)';
        let riskLabel = 'ACTIVE';

        if (p.lastStatus === 'no_response' || p.lastStatus === 'timeout') {
            riskColor = '#ff5e5e';
            riskBg = 'rgba(255, 94, 94, 0.12)';
            riskLabel = 'TIMEOUT';
        } else if (p.lastStatus === 'escalated' || p.lastStatus === 'high') {
            riskColor = '#ff5e5e';
            riskBg = 'rgba(255, 94, 94, 0.12)';
            riskLabel = 'CRITICAL';
        } else if (p.lastStatus === 'moderate') {
            riskColor = '#ffb35e';
            riskBg = 'rgba(255, 179, 94, 0.12)';
            riskLabel = 'MODERATE';
        } else if (p.lastStatus === 'completed') {
            riskColor = '#5eff7e';
            riskBg = 'rgba(94, 255, 126, 0.12)';
            riskLabel = 'COMPLETED';
        }

        return `
            <div class="preset-card active-patient-card" onclick="selectActivePatient('${p.patientId}')" style="background: rgba(94,126,255,0.04); border: 1px solid rgba(94,126,255,0.12); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(0,0,0,0.15); width: 100%; box-sizing: border-box;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <span style="font-weight:700; font-size:1.1rem; color:var(--text-primary);">${p.name}</span>
                    <span class="badge" style="background:${riskBg}; color:${riskColor}; border:1px solid ${riskColor}33; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:12px;">${riskLabel}</span>
                </div>
                <p style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:4px;"><strong>MRN:</strong> ${p.patientId}</p>
                <p style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:4px;"><strong>Email:</strong> ${p.email}</p>
                <p style="font-size:0.85rem; color:var(--text-secondary);"><strong>Diagnosis:</strong> ${p.diagnosis}</p>
            </div>
        `;
    }).join('');
}

function clearAllData() {
    if (confirm("Are you sure you want to clear all active monitoring pipelines and reset the CareFlow system?")) {
        localStorage.clear();
        window.enrolledPatients = [];
        resetSession();
        renderActivePatients();
        addEvent('SYSTEM', 'Platform data cleared successfully. System state reset.');
    }
}

function showSection(name) {
    // Update active state in sidebar
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));

    const enrollSec = document.getElementById('enroll-section');
    const dashboardGrid = document.getElementById('dashboard-grid');
    const patientCard = document.getElementById('patient-card');
    const pathwayContainer = document.getElementById('pathway-flow-container');
    const auditContainer = document.getElementById('audit-log-container');
    const patientsSec = document.getElementById('patients-section');

    if (name === 'enroll') {
        const navEnroll = document.getElementById('nav-enroll');
        if (navEnroll) navEnroll.classList.add('active');
        enrollSec.style.display = 'flex';
        dashboardGrid.style.display = 'none';
        if (patientCard) patientCard.style.display = 'none';
        if (pathwayContainer) pathwayContainer.style.display = 'none';
        if (auditContainer) auditContainer.style.display = 'none';
        if (patientsSec) patientsSec.style.display = 'none';
    } else if (name === 'dashboard') {
        const navDashboard = document.getElementById('nav-dashboard');
        if (navDashboard) navDashboard.classList.add('active');
        if (window.currentState && window.currentState.enrolled) {
            enrollSec.style.display = 'none';
            dashboardGrid.style.display = 'grid';
            if (patientCard) patientCard.style.display = 'block';
            if (pathwayContainer) pathwayContainer.style.display = 'block';
            if (auditContainer) auditContainer.style.display = 'block';
            if (patientsSec) patientsSec.style.display = 'none';
        } else {
            if (window.enrolledPatients && window.enrolledPatients.length > 0) {
                selectActivePatient(window.enrolledPatients[0].patientId);
                return;
            }
            addEvent('ALERT', 'No active patient is currently enrolled. Please enroll a patient first.');
            alert('No active patient is currently enrolled. Please enroll a patient first.');
            showSection('enroll');
        }
    } else if (name === 'patients') {
        const navPatients = document.getElementById('nav-patients');
        if (navPatients) navPatients.classList.add('active');
        enrollSec.style.display = 'none';
        dashboardGrid.style.display = 'none';
        if (patientCard) patientCard.style.display = 'none';
        if (pathwayContainer) pathwayContainer.style.display = 'none';
        if (auditContainer) auditContainer.style.display = 'none';
        if (patientsSec) patientsSec.style.display = 'block';
    }
}

function resetSession() {
    if (pollInterval) clearInterval(pollInterval);
    window.currentState = { enrolled: false, patientId: null, workflowId: null, currentDay: 0, lastStatus: null, lastShownDay: 0 };

    showSection('enroll');

    const btn = document.getElementById('btn-enroll');
    btn.disabled = false;
    btn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        Begin Automated Monitoring
    `;

    document.getElementById('phone-messages').innerHTML = '<div class="phone-msg-bubble">System ready. Awaiting check-in SMS...</div>';

    clearEvents();
    addEvent('SYSTEM', 'Monitoring dashboard reset. Awaiting next enrollment simulation.');
}

const selectedScores = { pain: null, fatigue: null, mood: null, sleep: null };
let surveyLocked = false;

function selectScore(btn) {
    const question = btn.parentElement.dataset.question;
    btn.parentElement.querySelectorAll('.scale-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    selectedScores[question] = parseInt(btn.dataset.value);

    // Risk category is determined by the WORST (max) single symptom score
    const maxScore = Math.max(...Object.values(selectedScores).map(v => v ?? 0));
    const category = maxScore + 1; // 0→1, 1→2, 2→3, 3→4
    const catColors = ['#10b981', '#f59e0b', '#f97316', '#ef4444'];
    const catLabels = ['Minimal', 'Low Risk', 'Moderate', 'Critical'];
    const dots = '●'.repeat(category) + '○'.repeat(4 - category);
    const liveScoreEl = document.getElementById('live-total-score');
    if (liveScoreEl) liveScoreEl.innerHTML = `Risk Category: <span style="font-weight:900; color:${catColors[maxScore]};">${category}/4 ${dots}</span> — ${catLabels[maxScore]}`;
}

function showSurveyForm(day) {
    surveyLocked = false;

    // Enable and clear inputs
    const phoneInput = document.getElementById('phone-sms-input');
    const phoneBtn = document.getElementById('btn-submit-phone');
    const freeInput = document.getElementById('free-text-input');
    const freeBtn = document.getElementById('btn-submit-free-text');

    if (phoneInput) {
        phoneInput.disabled = false;
        phoneInput.value = '';
    }
    if (phoneBtn) phoneBtn.disabled = false;
    if (freeInput) {
        freeInput.disabled = false;
        freeInput.value = '';
    }
    if (freeBtn) freeBtn.disabled = false;

    safeEl('survey-form').style.display = 'block';
    safeEl('waiting-state').style.display = 'none';
    safeEl('score-result').style.display = 'none';
    safeEl('countdown').style.display = 'flex';

    // Sync countdown with the actual backend SURVEY_TIMEOUT_SECONDS (60s)
    // Subtract a small buffer (3s) to account for polling delay + workflow startup
    startCountdown(25);
}

function hideSurveyForm() {
    clearInterval(countdownInterval);
    safeEl('survey-form').style.display = 'none';
}

async function submitPhoneSms() {
    const input = document.getElementById('phone-sms-input');
    if (!input) return;
    const val = input.value.trim();
    if (!val) return;
    await simulatePatientSurvey(val);
}

async function submitFreeTextSurvey() {
    const input = document.getElementById('free-text-input');
    if (!input) return;
    const val = input.value.trim();
    if (!val) {
        alert('Please enter a symptom response message.');
        return;
    }
    await simulatePatientSurvey(val);
}

async function simulatePatientSurvey(responseText) {
    if (!window.currentState || !window.currentState.enrolled) return;
    if (surveyLocked) {
        addEvent('ALERT', 'Survey already submitted for this check-in.');
        showPhoneError('Survey already submitted.');
        return;
    }

    const state = window.currentState;
    const checkInId = `checkin-d${state.currentDay}`;

    // Disable inputs
    const phoneInput = document.getElementById('phone-sms-input');
    const phoneBtn = document.getElementById('btn-submit-phone');
    const freeInput = document.getElementById('free-text-input');
    const freeBtn = document.getElementById('btn-submit-free-text');

    if (phoneInput) phoneInput.disabled = true;
    if (phoneBtn) phoneBtn.disabled = true;
    if (freeInput) freeInput.disabled = true;
    if (freeBtn) freeBtn.disabled = true;

    addEvent('SIGNAL', `Simulating SMS check-in response: "${responseText}"`);

    try {
        await api.submitSurveyText(state.patientId, checkInId, responseText);
        addEvent('SIGNAL', `Survey response submitted successfully to ${checkInId}`);

        surveyLocked = true;
        hideSurveyForm();
        safeEl('countdown').style.display = 'none';

        // Add visual reply bubble on patient phone
        const msgList = document.getElementById('phone-messages');
        const replyBubble = document.createElement('div');
        replyBubble.className = 'phone-msg-bubble';
        replyBubble.style.alignSelf = 'flex-end';
        replyBubble.style.background = '#10b981';
        replyBubble.style.color = '#fff';
        replyBubble.innerHTML = `<b>Reply:</b><br>${responseText}`;
        msgList.appendChild(replyBubble);
        msgList.scrollTop = msgList.scrollHeight;

        // Clear the text areas
        if (phoneInput) phoneInput.value = '';
        if (freeInput) freeInput.value = '';

    } catch (err) {
        addEvent('ALERT', `Delivery of survey signal failed: ${err.message}`);
        showPhoneError(`Failed: ${err.message}`);
    } finally {
        if (phoneInput) phoneInput.disabled = false;
        if (phoneBtn) phoneBtn.disabled = false;
        if (freeInput) freeInput.disabled = false;
        if (freeBtn) freeBtn.disabled = false;
    }
}

function showPhoneError(message) {
    const msgList = document.getElementById('phone-messages');
    const errorBubble = document.createElement('div');
    errorBubble.className = 'phone-msg-bubble';
    errorBubble.style.background = 'rgba(239, 68, 68, 0.3)';
    errorBubble.style.borderColor = 'var(--danger)';
    errorBubble.style.color = '#ff8888';
    errorBubble.style.fontSize = '0.72rem';
    errorBubble.innerHTML = `⚠️ ${message}`;
    msgList.appendChild(errorBubble);
    msgList.scrollTop = msgList.scrollHeight;
}


function showScoreResult(checkIn) {
    safeEl('survey-form').style.display = 'none';
    safeEl('waiting-state').style.display = 'none';
    safeEl('countdown').style.display = 'none';

    const msgList = document.getElementById('phone-messages');
    const resultBubble = document.createElement('div');
    resultBubble.className = 'phone-msg-bubble';
    resultBubble.style.color = '#111827'; // Dark text for legibility

    if (checkIn.status === 'no_response') {
        resultBubble.style.color = '#ffffff'; // White text for legibility on dark background
        resultBubble.style.background = 'rgba(239, 68, 68, 0.1)';
        resultBubble.style.borderColor = 'var(--danger)';
        resultBubble.innerHTML = `<b>⏰ System Alert: Patient Non-Responsive</b><br><br>The assessment window expired. An email has been successfully sent to the care coordinator (guttaumesh123@gmail.com) that the patient is not responding.`;
    } else {
        // Risk Category: score (0-3 max symptom) maps to category 1-4
        // 0→1/4 Minimal, 1→2/4 Low, 2→3/4 Moderate, 3→4/4 Critical
        const score = checkIn.score ?? 0;
        const category = score + 1;
        const dots = '●'.repeat(category) + '○'.repeat(4 - category);
        const catBgColors = { low: '#dcfce7', moderate: '#fef9c3', high: '#fee2e2' };
        const catDotColors = { low: '#16a34a', moderate: '#ca8a04', high: '#dc2626' };
        const riskLabels = { low: 'Low Risk', moderate: 'Moderate Risk', high: 'Critical Risk' };
        const actionLabels = {
            wellness_content_sent: 'Wellness resources dispatched.',
            callback_scheduled: 'Nurse Callback Scheduled (24h).',
            escalated_to_care_team: 'Escalated to On-Call Care Team.',
        };

        resultBubble.style.background = catBgColors[checkIn.risk_level] || '#fff';
        resultBubble.style.color = '#111827';
        resultBubble.innerHTML =
            `<b>✅ Check-in Processed</b><br><br>` +
            `<b>Risk Category:</b> <span style="font-weight:900; color:${catDotColors[checkIn.risk_level] || '#555'};">${category}/4 ${dots}</span><br><br>` +
            `<b>Risk:</b> ${riskLabels[checkIn.risk_level] || checkIn.risk_level}<br>` +
            `<b>Action:</b> ${actionLabels[checkIn.action_taken] || checkIn.action_taken}`;
    }

    msgList.appendChild(resultBubble);
    msgList.scrollTop = msgList.scrollHeight;
}

function showWaitingState(message) {
    safeEl('survey-form').style.display = 'none';
    safeEl('score-result').style.display = 'none';
    safeEl('countdown').style.display = 'none';
    safeEl('waiting-state').style.display = 'flex';
    safeEl('waiting-message').textContent = message || 'Waiting for next check-in...';
}

let countdownInterval = null, countdownRemaining = 0;

function startCountdown(s) {
    clearInterval(countdownInterval);
    countdownRemaining = s;
    surveyLocked = false;
    updateCountdownDisplay();

    countdownInterval = setInterval(() => {
        countdownRemaining--;
        updateCountdownDisplay();

        if (countdownRemaining <= 5 && countdownRemaining > 0) {
            // Flash warning when time is running low
            const cdEl = document.getElementById('countdown');
            if (cdEl) cdEl.style.animation = 'pulse 0.5s infinite';
        }

        if (countdownRemaining <= 0) {
            clearInterval(countdownInterval);
            onCountdownExpired();
        }
    }, 1000);
}

function onCountdownExpired() {
    // CRITICAL: Lock the survey immediately so no late submissions happen
    surveyLocked = true;

    // Disable all submission inputs and buttons
    const phoneInput = document.getElementById('phone-sms-input');
    const phoneBtn = document.getElementById('btn-submit-phone');
    const freeInput = document.getElementById('free-text-input');
    const freeBtn = document.getElementById('btn-submit-free-text');

    if (phoneInput) phoneInput.disabled = true;
    if (phoneBtn) phoneBtn.disabled = true;
    if (freeInput) freeInput.disabled = true;
    if (freeBtn) freeBtn.disabled = true;

    // Update countdown display to show expired state
    const cdValue = document.getElementById('countdown-value');
    if (cdValue) cdValue.textContent = 'EXPIRED';
    const cdEl = document.getElementById('countdown');
    if (cdEl) cdEl.style.animation = 'none';

    // Show expired message on phone
    showPhoneError('Survey response window expired. Workflow will mark as non-responsive.');

    addEvent('ALERT', '⏰ Survey response window expired! Check-in will be marked as non-responsive.');

    const state = window.currentState;
    if (state.toastShownForDay !== state.currentDay) {
        state.toastShownForDay = state.currentDay;
        const pName = document.getElementById('patient-name-display').textContent || 'Jane Doe';
        showToast(
            '⏰ Patient Non-Responsive',
            `Email has been sent to the care coordinator that patient ${pName} is not responding.`,
            'danger'
        );
    }
}

function updateCountdownDisplay() {
    const el = document.getElementById('countdown-value');
    if (!el) return;

    if (countdownRemaining <= 0) {
        el.textContent = 'EXPIRED';
    } else if (countdownRemaining <= 5) {
        el.textContent = `⚠️ ${countdownRemaining}s — RESPOND NOW!`;
    } else {
        el.textContent = `${countdownRemaining}s remaining`;
    }
}

function showToast(title, message, type = 'accent') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // SVG icon matching the type
    let iconSvg = '';
    if (type === 'danger') {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    } else if (type === 'success') {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
    } else if (type === 'warning') {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    } else {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
    }

    toast.innerHTML = `
        <div class="toast-icon">${iconSvg}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.classList.add('toast-out'); setTimeout(() => this.parentElement.remove(), 350)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
    `;

    container.appendChild(toast);

    // Auto close after 7 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('toast-out');
            setTimeout(() => toast.remove(), 350);
        }
    }, 7000);
}

