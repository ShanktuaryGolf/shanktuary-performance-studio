// Studio composition only. The existing range controller owns game transitions,
// telemetry, scoring and persistence. Selecting a card never starts a run.
const $ = id => document.getElementById(id);
const icons = {
    home: '<path d="m3 13 13-10 13 10M6 12v16h8v-9h5v9h7V12"/>',
    club: '<path d="m24 3-9 22M16 25C3 19 1 24 5 28h9l4-8"/>',
    table: '<rect x="4" y="4" width="24" height="24" rx="2"/><path d="M4 12h24M4 20h24M13 12v16"/>',
    numbers: '<path d="M25 5H8l10 11L8 27h17"/>',
    target: '<circle cx="16" cy="16" r="11"/><circle cx="16" cy="16" r="6"/><path d="M16 1v8m0 14v8M1 16h8m14 0h8"/>',
    flag: '<path d="M6 29V3c8-7 12 8 20 0v14c-8 7-12-8-20 0"/>',
    dispersion: '<circle cx="8" cy="19" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="25" cy="19" r="3"/><circle cx="16" cy="28" r="2"/>',
    bag: '<path d="m9 10-3 18h20l-3-18ZM11 10V6a5 5 0 0 1 10 0v4M11 16h10"/>',
    sliders: '<path d="M3 7h26M3 16h26M3 25h26"/><circle cx="10" cy="7" r="3"/><circle cx="23" cy="16" r="3"/><circle cx="14" cy="25" r="3"/>',
    lab: '<path d="M11 3h10M13 3v11L5 28h22L19 14V3M10 20h12"/>',
    settings: '<circle cx="16" cy="16" r="5"/><path d="m13 3 6 0 1 4 4 2 4-1 3 5-3 3v4l3 3-3 5-4-1-4 2-1 3h-6l-1-3-4-2-4 1-3-5 3-3v-4l-3-3 3-5 4 1 4-2Z" transform="translate(0 -2) scale(.95)"/>',
    garage: '<path d="M3 29V11L16 3l13 8v18M8 29V15h16v14M8 21h16M8 26h16"/>',
    camera: '<rect x="3" y="7" width="18" height="18" rx="2"/><path d="m21 13 8-5v16l-8-5"/>',
    tower: '<rect x="11" y="3" width="10" height="7" rx="1"/><path d="m21 5 5-2v7l-5-2M16 10 7 29m9-19 9 19M10 22h12M12 17h8"/>',
    person: '<circle cx="16" cy="9" r="6"/><path d="M4 29v-5a12 9 0 0 1 24 0v5Z"/>',
    play: '<path d="m8 3 21 13L8 29Z"/>',
    stop: '<rect x="6" y="6" width="20" height="20" rx="2" fill="currentColor" stroke="none"/>',
};
export function rangeIcon(name) {
    return `<svg class="range-icon" viewBox="0 0 32 32" aria-hidden="true">${icons[name] || icons.club}</svg>`;
}
const summaries = {
    practice: 'Hit freely with full shot feedback',
    challenge: 'Score by hitting the target rings',
    target_practice: 'Dial into a single target',
    ladder: 'Hit a series of increasing distances',
    'closest-pin': 'Get closest to the target',
    'long-drive': 'Maximize your distance',
    grid: 'Practice with a standard target grid',
    grid_custom: 'Build your own target layout',
    combine: 'A multi-club performance test',
};

function mount(id, target) {
    const node = $(id), parent = $(target);
    if (node && parent) parent.appendChild(node);
}
function initialize() {
    if (!$('range-picker')) return null;
    document.querySelectorAll('[data-range-icon]').forEach(el => { el.innerHTML = rangeIcon(el.dataset.rangeIcon); });
    mount('three-canvas', 'range-scene');
    mount('dist-readout', 'range-scene-controls');
    mount('club-chip', 'range-scene-controls');
    mount('nav', 'range-nav-mount');
    mount('lm-status-indicator', 'range-connection-slot');
    mount('game-modes-drawer', 'range-picker-mount');
    mount('metric-strip', 'range-metrics-mount');
    mount('btn-strip-config', 'range-metrics-mount');
    mount('shot-list', 'range-session-rail');
    mount('right-rail', 'range-session-rail');
    const details = {};
    const cards = [...document.querySelectorAll('.game-mode-card')];
    let actions = {}, selectedMode = 'practice', currentMode = 'practice', hasStarted = false;
    let ready = false, busy = false;
    function selectMode(mode) {
        selectedMode = mode;
        cards.forEach(card => {
            const selected = card.dataset.mode === mode;
            card.classList.toggle('active', selected);
            card.setAttribute('aria-pressed', String(selected));
        });
        $('range-selection-detail').textContent = details[mode] || '';
    }
    cards.forEach(card => {
        const description = card.querySelector('.game-mode-desc');
        details[card.dataset.mode] = description.textContent;
        description.textContent = summaries[card.dataset.mode];
        card.title = details[card.dataset.mode];
        card.addEventListener('click', () => selectMode(card.dataset.mode));
    });
    function showPicker() {
        document.body.dataset.rangeView = 'picker';
        $('range-picker').hidden = false;
        $('range-workspace').hidden = true;
        $('range-page-title').textContent = '3D Range';
        $('range-page-subtitle').textContent = 'Practice mode selection';
        $('range-resume').hidden = !hasStarted;
        selectMode(currentMode);
    }
    function showWorkspace(mode = currentMode) {
        hasStarted = true;
        currentMode = mode;
        document.body.dataset.rangeView = 'workspace';
        document.body.dataset.rangeMode = mode;
        $('range-picker').hidden = true;
        $('range-workspace').hidden = false;
        $('range-page-title').textContent = mode === 'combine' ? '3D Range & Combine' : '3D Range';
        $('range-page-subtitle').textContent = mode === 'combine' ? 'Practice in 3D · Multi-club combine' : `Practice in 3D · ${cards.find(c => c.dataset.mode === mode)?.querySelector('.game-mode-title').textContent || 'Free Practice'}`;
        $('range-practice-tab').setAttribute('aria-selected', String(mode !== 'combine'));
        $('range-combine-tab').setAttribute('aria-selected', String(mode === 'combine'));
        window.dispatchEvent(new Event('resize'));
    }
    async function start(mode) {
        if (!ready || busy) return;
        busy = true;
        $('range-start-mode').disabled = true;
        try {
            await actions.startMode?.(mode);
            showWorkspace(mode);
        } finally {
            busy = false;
            $('range-start-mode').disabled = !ready;
        }
    }
    $('range-start-mode').addEventListener('click', () => start(selectedMode));
    $('range-resume').addEventListener('click', () => showWorkspace());
    $('range-nav-range').addEventListener('click', showPicker);
    $('range-practice-tab').addEventListener('click', () => start('practice'));
    $('range-combine-tab').addEventListener('click', () => start('combine'));
    $('range-start-combine').addEventListener('click', () => actions.combine?.('start'));
    $('range-end-combine').addEventListener('click', () => actions.combine?.('end'));
    $('range-nav-numbers').addEventListener('click', () => { showWorkspace(); actions.metrics?.(); });
    $('range-nav-bag').addEventListener('click', () => { showWorkspace(); actions.bag?.(); });
    $('range-nav-dispersion').addEventListener('click', () => { showWorkspace(); actions.dispersion?.(); });
    $('range-nav-setup').addEventListener('click', () => actions.settings?.());
    document.querySelectorAll('[data-desktop-workspace]').forEach(button => {
        button.title = `Open ${button.dataset.desktopWorkspace} in the desktop app`;
        button.addEventListener('click', () => {
            $('range-desktop-message').textContent = `${button.dataset.desktopWorkspace} is a desktop workspace. Return to Shanktuary Performance Studio and choose ${button.dataset.desktopWorkspace} in its sidebar. Your range session stays open here.`;
            $('range-desktop-notice').hidden = false;
        });
    });
    $('range-dismiss-notice').addEventListener('click', () => { $('range-desktop-notice').hidden = true; });
    $('range-retry-renderer').addEventListener('click', () => window.location.reload());
    document.querySelectorAll('[data-range-camera]').forEach(button => {
        button.addEventListener('click', () => actions.camera?.(Number(button.dataset.rangeCamera)));
    });
    $('range-extra-camera').addEventListener('change', event => {
        if (event.target.value !== '') actions.camera?.(Number(event.target.value));
    });
    selectMode('practice');
    return {
        showPicker, showWorkspace,
        bind(callbacks) { actions = callbacks; ready = true; $('range-start-mode').disabled = false; },
        setEngine(available) {
            $('range-engine-label').textContent = available ? 'Live range · WebGL' : '3D graphics unavailable';
            $('range-renderer-error').hidden = available;
            $('range-picker-note').textContent = available ? 'Illustrated mode previews · Live shots appear after you start' : '3D graphics unavailable in this browser · Mode controls and live telemetry remain available';
        },
        setCamera(mode) {
            document.querySelectorAll('[data-range-camera]').forEach(button => {
                button.setAttribute('aria-pressed', String(Number(button.dataset.rangeCamera) === mode));
            });
            $('range-extra-camera').value = mode > 2 ? String(mode) : '';
        },
        setPressureLive(live) {
            const el = $('range-source-status');
            el.dataset.live = String(live);
            el.querySelector('em').textContent = live ? 'Pressure data received' : 'Awaiting pressure data';
        },
    };
}
export const studioShell = initialize();
