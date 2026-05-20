const CHECK_IN_DAYS = [1, 7, 30, 90];

function updateTimeline(status) {
    if (!status) return;
    const completedDays = (status.completed_check_ins || []).map(ci => ci.day);
    const currentDay = status.current_day || 0;

    // Collect all triggered risk routes from completed check-ins
    const triggeredRoutes = [];

    CHECK_IN_DAYS.forEach((day) => {
        const item = document.getElementById(`timeline-day-${day}`);
        const node = item.querySelector('.tl-node');
        const resultEl = document.getElementById(`result-day-${day}`);
        const connector = item.querySelector('.tl-connector');
        node.className = 'tl-node';

        const checkIn = (status.completed_check_ins || []).find(ci => ci.day === day);
        if (checkIn) {
            const rl = checkIn.risk_level || (checkIn.status === 'no_response' ? 'timeout' : '');
            if (rl === 'high') node.classList.add('danger');
            else if (rl === 'moderate') node.classList.add('warning');
            else if (rl === 'timeout' || checkIn.status === 'no_response') node.classList.add('timeout');
            else node.classList.add('completed');
            if (connector) connector.classList.add('filled');
            resultEl.innerHTML = createResultTag(checkIn);
            if (rl) triggeredRoutes.push(rl);
        } else if (currentDay === day || (currentDay > 0 && !completedDays.includes(day) && isNextDay(day, completedDays))) {
            node.classList.add('active');
            resultEl.innerHTML = '<span style="color:var(--accent);font-size:.75rem">In progress...</span>';
        } else {
            node.classList.add('pending');
            resultEl.innerHTML = '';
        }
    });

    // Highlight all triggered routes — latest is primary active
    highlightAllRoutes(triggeredRoutes);

    // Update patient card stats
    const completed = status.completed_check_ins || [];
    document.getElementById('completed-count').textContent = `${completed.length} / 4`;
    document.getElementById('current-day-display').textContent = currentDay > 0 ? `Day ${currentDay}` : '—';
    const latest = completed.slice(-1)[0];
    if (latest) {
        const riskEl = document.getElementById('risk-display');
        riskEl.textContent = latest.risk_level ? latest.risk_level.charAt(0).toUpperCase() + latest.risk_level.slice(1) : (latest.status === 'no_response' ? 'Non-Responsive' : '—');
    }
}

function isNextDay(day, completedDays) {
    const i = CHECK_IN_DAYS.indexOf(day);
    if (i === 0) return completedDays.length === 0;
    return completedDays.includes(CHECK_IN_DAYS[i - 1]);
}

function createResultTag(ci) {
    if (ci.status === 'no_response') return '<span class="result-tag timeout">Non-Responsive</span>';
    const l = ci.risk_level || 'low';
    const labels = { low: 'Low Risk', moderate: 'Moderate', high: 'High Risk' };
    const actions = { wellness_content_sent: 'Wellness sent', callback_scheduled: 'Callback scheduled', escalated_to_care_team: 'Escalated' };
    return `<span class="result-tag ${l}">${labels[l] || l}</span><div style="font-size:.7rem;color:var(--text3);margin-top:3px">${actions[ci.action_taken] || ci.action_taken || ''}</div>`;
}

function highlightAllRoutes(triggeredRoutes) {
    const map = { low: 'route-low', moderate: 'route-moderate', high: 'route-high', timeout: 'route-timeout' };

    // Clear all highlights first
    document.querySelectorAll('.pathway-item').forEach(r => {
        r.classList.remove('active');
        r.classList.remove('triggered');
        const b = r.querySelector('.pw-badge');
        if (b) { b.style.display = 'none'; b.textContent = 'ACTIVE'; }
    });

    if (triggeredRoutes.length === 0) return;

    // The latest route is the primary "active" one
    const latestRoute = triggeredRoutes[triggeredRoutes.length - 1];

    // Mark all previously triggered routes with a "triggered" class
    const seen = new Set();
    triggeredRoutes.forEach((rl, index) => {
        if (seen.has(rl)) return;
        seen.add(rl);
        const id = map[rl];
        if (!id) return;
        const el = document.getElementById(id);
        if (!el) return;

        if (rl === latestRoute && index === triggeredRoutes.length - 1) {
            // Latest route — full active highlight
            el.classList.add('active');
            const badge = el.querySelector('.pw-badge');
            if (badge) { badge.style.display = 'block'; badge.textContent = 'ACTIVE'; }
        } else {
            // Previously triggered route — secondary highlight
            el.classList.add('triggered');
            const badge = el.querySelector('.pw-badge');
            if (badge) { badge.style.display = 'block'; badge.textContent = 'TRIGGERED'; }
        }
    });

    // Also ensure the latest gets active if it was also seen earlier
    const latestId = map[latestRoute];
    if (latestId) {
        const latestEl = document.getElementById(latestId);
        if (latestEl && !latestEl.classList.contains('active')) {
            latestEl.classList.remove('triggered');
            latestEl.classList.add('active');
            const badge = latestEl.querySelector('.pw-badge');
            if (badge) { badge.style.display = 'block'; badge.textContent = 'ACTIVE'; }
        }
    }
}

// Legacy single-route highlight (kept for compatibility)
function highlightRoute(riskLevel) {
    highlightAllRoutes(riskLevel ? [riskLevel] : []);
}
