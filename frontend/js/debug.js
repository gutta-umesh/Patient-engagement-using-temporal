window.addEventListener('error', function(e) {
    const el = document.createElement('div');
    el.style.background = 'red';
    el.style.color = 'white';
    el.style.padding = '10px';
    el.style.zIndex = '9999';
    el.textContent = "JS ERROR: " + e.message + " at " + e.filename + ":" + e.lineno;
    document.body.prepend(el);
});
window.addEventListener('unhandledrejection', function(e) {
    const el = document.createElement('div');
    el.style.background = 'orange';
    el.style.color = 'white';
    el.style.padding = '10px';
    el.style.zIndex = '9999';
    el.textContent = "PROMISE REJECTION: " + (e.reason && e.reason.message ? e.reason.message : e.reason);
    document.body.prepend(el);
});
