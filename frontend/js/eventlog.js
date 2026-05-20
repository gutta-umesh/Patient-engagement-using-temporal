const events = [];
let currentLogFilter = 'ALL';

function filterEvents(filter) {
    currentLogFilter = filter;
    
    // Update button styling
    const allBtn = document.getElementById('tab-all');
    const alertBtn = document.getElementById('tab-alerts');
    
    if (filter === 'ALL') {
        allBtn.style.background = 'var(--accent)';
        allBtn.style.color = 'white';
        alertBtn.style.background = 'transparent';
        alertBtn.style.color = 'var(--text-secondary)';
    } else {
        alertBtn.style.background = 'rgba(239, 68, 68, 0.2)';
        alertBtn.style.color = 'var(--danger)';
        allBtn.style.background = 'transparent';
        allBtn.style.color = 'var(--text-secondary)';
    }
    
    renderEvents();
}

function addEvent(source, message) {
    const now = new Date();
    events.push({ time: now.toLocaleTimeString('en-US', { hour12: false }), source, message, timestamp: now });
    renderEvents();
}

function renderEvents() {
    const log = document.getElementById('event-log');
    const count = document.getElementById('event-count');
    
    let filteredEvents = events;
    if (currentLogFilter === 'ALERT') {
        filteredEvents = events.filter(e => {
            const src = e.source.toUpperCase();
            const msg = e.message.toLowerCase();
            return src === 'ALERT' || msg.includes('alert') || msg.includes('escalat') || msg.includes('timeout') || msg.includes('failed');
        });
    }
    
    if (filteredEvents.length === 0) { 
        log.innerHTML = `<div class="audit-empty">${currentLogFilter === 'ALERT' ? 'No alerts recorded yet' : 'No activity recorded yet'}</div>`; 
        count.textContent = '0 entries'; 
        return; 
    }
    
    count.textContent = `${filteredEvents.length} entries`;
    const visible = filteredEvents.slice(-50);
    log.innerHTML = visible.map(e => `<div class="event-item"><span class="event-time">${e.time}</span><span class="event-badge ${e.source.toLowerCase()}">${e.source}</span><span class="event-message">${e.message}</span></div>`).join('');
    log.scrollTop = log.scrollHeight;
}

function clearEvents() { events.length = 0; renderEvents(); }

let lastEventCount = 0;
function processApiEvents(apiEvents) {
    if (!apiEvents || apiEvents.length <= lastEventCount) return;
    apiEvents.slice(lastEventCount).forEach(e => {
        const src = e.source || 'SYSTEM';
        let msg = e.event_type ? `${e.event_type}: ${JSON.stringify(e.details || {})}` : (e.message ? e.message : JSON.stringify(e));
        addEvent(src, msg);
    });
    lastEventCount = apiEvents.length;
}
