function toggleCard(card) {
    const was = card.classList.contains('expanded');
    document.querySelectorAll('.arch-card').forEach(c => c.classList.remove('expanded'));
    if (!was) card.classList.add('expanded');
}

function toggleArchSection() {
    const grid = document.getElementById('explainer-grid');
    const arrow = document.getElementById('arch-arrow');
    if (grid.style.display === 'none') { grid.style.display = 'grid'; arrow.classList.add('open'); }
    else { grid.style.display = 'none'; arrow.classList.remove('open'); }
}
