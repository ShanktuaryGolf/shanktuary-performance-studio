// WebSocket Telemetry, Proximity, Real-time Fairway Width Slider & Minimap Radar

import { setTargetDistance } from './environment.js';
import { setFairwayWidth, getFairwayWidth } from './foliage.js';
import { PressureTileRenderer } from './pressure_tiles.js';
import { ShotHistory, isSmashClamped } from './shot_history.js';
import { drawDispersion } from './dispersion.js';
import { WIDGET_REGISTRY } from './widgets.js';
import {
    METRICS, MIN_STRIP, MAX_STRIP, DEFAULT_STRIP,
    loadStripLayout, saveStripLayout, readMetric,
} from './metrics.js';
import { fetchBag, groupClubs, pillLabel, clubSubtitle } from './club_picker.js';

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    // 0. HUD scale wrapper
    // ------------------------------------------------------------------
    // Every HUD panel is moved into #hud-scale so the overlay can be zoomed
    // for projector viewing without touching the 3D canvas. Done here rather
    // than in the markup so the panels keep their existing source order and
    // the diff stays reviewable.
    //
    // Built FIRST, before any element lookups below, because reparenting after
    // a ResizeObserver or canvas measurement would invalidate it.
    const HUD_SCALE_KEY = 'sps_range_hud_scale';
    const HUD_SCALE_MIN = 80;
    const HUD_SCALE_MAX = 200;

    (function buildHudScaleWrapper() {
        if (document.getElementById('hud-scale')) return;
        const ids = [
            'nav', 'dist-readout', 'shot-list', 'club-chip',
            'metric-strip', 'btn-strip-config', 'strip-menu',
            'all-metrics', 'right-rail', 'widget-menu', 'ladder-banner',
            'practice-carry-container', 'practice-offline-container',
            'target-scoring-legend', 'target-dist-badge-container',
        ];
        const wrap = document.createElement('div');
        wrap.id = 'hud-scale';
        // Insert directly after the canvas so stacking order is unchanged.
        const canvas = document.getElementById('three-canvas');
        if (canvas && canvas.parentNode) {
            canvas.parentNode.insertBefore(wrap, canvas.nextSibling);
        } else {
            document.body.appendChild(wrap);
        }
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) wrap.appendChild(el);
        }
    })();

    const hudScaleEl = document.getElementById('hud-scale');
    const hudScaleSlider = document.getElementById('hud-scale-slider');
    const hudScaleReadout = document.getElementById('hud-scale-readout');
    const hudScaleChips = document.querySelectorAll('.preset-chip[data-hud-scale]');

    function clampHudScale(pct) {
        const n = Math.round(Number(pct) || 100);
        return Math.min(HUD_SCALE_MAX, Math.max(HUD_SCALE_MIN, n));
    }

    /**
     * Largest scale at which the HUD still fits the viewport.
     *
     * The side panels are fixed-width, so on a narrow window a big scale would
     * push the metric strip under the rail. These are the unscaled pixel costs
     * the layout actually needs; dividing the viewport by them gives the
     * largest zoom that still leaves the strip a usable gap between the shot
     * list and the rail.
     */
    function maxUsableHudScale() {
        // shot list (18 + 216 + 16 gutter) + rail (292 + 18 + 12 gutter)
        // + a minimum readable strip width.
        const SIDES_W = (18 + 216 + 16) + (292 + 18 + 12);
        const MIN_STRIP_W = 300;
        // nav + strip + the gaps above and below it
        const NEEDED_H = 56 + 8 + 80 + 18 + 24;
        const byW = (window.innerWidth / (SIDES_W + MIN_STRIP_W)) * 100;
        const byH = (window.innerHeight / NEEDED_H) * 100;

        // Strip cells: the strip's left/right offsets are CSS pixels, so at zoom
        // z they consume SIDES_W*z screen px, leaving the strip
        //     cssWidth = vw/z - SIDES_W
        // and each of n cells cssWidth/n. Requiring that to stay above the
        // floor gives  z <= vw / (n*MIN + SIDES_W).
        //
        // Measured with 10 metrics at 1568px: clean at 140%, clipping by 150%
        // -- this formula caps at 143%.
        const n = Math.max(1, stripLayout.length);
        const MIN_CELL_CSS_W = 52;
        const byCells = (window.innerWidth / (n * MIN_CELL_CSS_W + SIDES_W)) * 100;

        return clampHudScale(Math.min(byW, byH, byCells));
    }

    function applyHudScale(pct, { persist = true } = {}) {
        const want = clampHudScale(pct);
        const max = maxUsableHudScale();
        const used = Math.min(want, max);
        if (hudScaleEl) hudScaleEl.style.zoom = used === 100 ? '' : String(used / 100);
        if (hudScaleSlider) hudScaleSlider.value = String(want);
        if (hudScaleReadout) {
            // Show the requested value, and flag when the viewport is limiting it
            // rather than silently ignoring the user's setting.
            hudScaleReadout.textContent = used < want
                ? `${want}% (fits ${used}%)`
                : `${want}%`;
            hudScaleReadout.title = used < want
                ? 'Window is too small for the requested size; showing the largest that fits.'
                : '';
        }
        hudScaleChips.forEach(ch => {
            ch.classList.toggle('active',
                Number(ch.getAttribute('data-hud-scale')) === want);
        });
        if (persist) {
            try { localStorage.setItem(HUD_SCALE_KEY, String(want)); } catch {}
        }
        // Canvas-backed widgets measure their own box, so they must redraw.
        requestAnimationFrame(() => {
            if (typeof drawMinimap === 'function') drawMinimap();
            if (typeof refreshDynamicWidgets === 'function') refreshDynamicWidgets();
        });
    }

    let hudScalePct = 100;
    try {
        const saved = localStorage.getItem(HUD_SCALE_KEY);
        if (saved !== null) hudScalePct = clampHudScale(saved);
    } catch {}

    if (hudScaleSlider) {
        hudScaleSlider.addEventListener('input', () => applyHudScale(hudScaleSlider.value));
    }
    hudScaleChips.forEach(ch => {
        ch.addEventListener('click', () => applyHudScale(ch.getAttribute('data-hud-scale')));
    });
    window.addEventListener('resize', () => applyHudScale(hudScaleSlider ? hudScaleSlider.value : hudScalePct, { persist: false }));

    // 1. DOM Elements
    const btnStudioMenu = document.getElementById('nav-logo');
    const settingsDrawer = document.getElementById('settings-drawer');
    const btnCloseSettings = document.getElementById('btn-close-settings');
    const gameModesDrawer = document.getElementById('game-modes-drawer');
    const btnCloseGameModes = document.getElementById('btn-close-game-modes');
    const drawerScrim = document.getElementById('drawer-scrim');
    const gameModeCards = document.querySelectorAll('.game-mode-card');

    const rangeModeTitle = document.getElementById('range-mode-title');
    const practiceCarryContainer = document.getElementById('practice-carry-container');
    const practiceOfflineContainer = document.getElementById('practice-offline-container');
    const practiceLastCarry = document.getElementById('practice-last-carry');
    const practiceLastOffline = document.getElementById('practice-last-offline');
    const challengePtsContainer = document.getElementById('challenge-pts-container');
    const challengeProxContainer = document.getElementById('challenge-prox-container');
    const targetScoringLegend = document.getElementById('target-scoring-legend');

    const ladderBanner = document.getElementById('ladder-banner');
    const ladderBannerTitle = document.getElementById('ladder-banner-title');
    const ladderBannerSub = document.getElementById('ladder-banner-sub');
    const ladderBannerIcon = document.getElementById('ladder-banner-icon');
    let bannerTimer = null;

    function showBanner(icon, title, sub, duration = 3500) {
        if (!ladderBanner) return;
        if (ladderBannerIcon) ladderBannerIcon.innerText = icon;
        if (ladderBannerTitle) ladderBannerTitle.innerText = title;
        if (ladderBannerSub) ladderBannerSub.innerText = sub;
        ladderBanner.classList.add('show');
        if (bannerTimer) clearTimeout(bannerTimer);
        bannerTimer = setTimeout(() => {
            ladderBanner.classList.remove('show');
        }, duration);
    }
    
    const slDemoBtn = document.getElementById('sl-demo-btn');
    const lmStatusText = document.getElementById('lm-status-text');
    const lmStatusPill = document.getElementById('lm-status-indicator');

    function setLmStatus(text, online) {
        if (lmStatusText) lmStatusText.innerText = text;
        if (lmStatusPill) lmStatusPill.classList.toggle('offline', !online);
    }
    const hudClubName = document.getElementById('hud-club-name');

    // Bottom strip is rendered from a user-configurable layout (metrics.js).
    // The All Metrics panel keeps its static elements and always shows
    // everything, so the strip choice never hides a metric outright.
    const metricStrip = document.getElementById('metric-strip');
    const btnStripConfig = document.getElementById('btn-strip-config');
    const stripMenu = document.getElementById('strip-menu');
    const smList = document.getElementById('sm-list');
    const smHint = document.getElementById('sm-hint');
    const smReset = document.getElementById('sm-reset');

    let stripLayout = loadStripLayout();
    // key -> {value, unit} nodes for the currently rendered cells
    const stripCells = new Map();

    // All Metrics panel (static)
    const elClubSpeed = document.getElementById('tele-club-speed');
    const elSpinAxis = document.getElementById('tele-spin-axis');
    const elHla = document.getElementById('tele-hla');
    const elClosureRate = document.getElementById('tele-closure-rate');
    const elClubPath = document.getElementById('tele-club-path');
    const elFaceAngle = document.getElementById('tele-face-angle');
    const elAttackAngle = document.getElementById('tele-attack-angle');
    const elDynamicLoft = document.getElementById('tele-dynamic-loft');
    const elBackspin = document.getElementById('tele-backspin');
    const elSidespin = document.getElementById('tele-sidespin');
    const elDescent = document.getElementById('tele-descent');
    const elHangTime = document.getElementById('tele-hang-time');

    // Shot list rail
    const slBody = document.getElementById('sl-body');
    const slSortBtn = document.getElementById('sl-sort-btn');
    const clubChipSub = document.getElementById('club-chip-sub');
    const dispersionFilterEl = document.getElementById('dispersion-filter');
    const dsCarry = document.getElementById('ds-carry');
    const dsCarrySd = document.getElementById('ds-carry-sd');
    const dsOffline = document.getElementById('ds-offline');

    // Nav tabs / All Metrics panel
    const allMetricsPanel = document.getElementById('all-metrics');
    const btnCloseAllMetrics = document.getElementById('btn-close-all-metrics');
    const tabMetrics = document.getElementById('tab-metrics');
    const tabModes = document.getElementById('tab-modes');
    const tabSettings = document.getElementById('tab-settings');
    const navTabs = document.querySelectorAll('.nav-tab');

    const shotHistory = new ShotHistory();
    let shotListSort = 'recent';
    let selectedShotSeq = null;

    // Top Challenge & Practice Pill
    const elTargetPts = document.getElementById('target-pts-val');
    const elTargetDistBadge = document.getElementById('target-dist-badge');
    const elPinProx = document.getElementById('pin-proximity-badge');

    // Fairway Width Controls
    const fwSlider = document.getElementById('fairway-width-slider');
    const fwReadout = document.getElementById('fairway-width-readout');
    const fwStepMinus10 = document.getElementById('fw-step-minus-10');
    const fwStepMinus5 = document.getElementById('fw-step-minus-5');
    const fwStepPlus5 = document.getElementById('fw-step-plus-5');
    const fwStepPlus10 = document.getElementById('fw-step-plus-10');
    const fwPresetChips = document.querySelectorAll('.preset-chip[data-fw]');

    // Target Distance Controls
    const tgtSlider = document.getElementById('target-dist-slider');
    const tgtReadout = document.getElementById('target-dist-readout');
    const tgtCustomInput = document.getElementById('target-custom-input');
    const btnSetCustomTarget = document.getElementById('btn-set-custom-target');
    const targetBadgeContainer = document.getElementById('target-dist-badge-container');
    const tgtStepMinus10 = document.getElementById('tgt-step-minus-10');
    const tgtStepMinus5 = document.getElementById('tgt-step-minus-5');
    const tgtStepPlus5 = document.getElementById('tgt-step-plus-5');
    const tgtStepPlus10 = document.getElementById('tgt-step-plus-10');
    const tgtPresetChips = document.querySelectorAll('.preset-chip[data-tgt]');

    // Swing Lab Pressure Tile Elements
    const rangePressureTile = document.getElementById('range-pressure-tile');
    const btnClosePressureTile = document.getElementById('btn-close-pressure-tile');
    const hudPressurePhase = document.getElementById('hud-pressure-phase');
    const hudPctLeft = document.getElementById('hud-pct-left');
    const hudPctRight = document.getElementById('hud-pct-right');
    const hudBarFillLeft = document.getElementById('hud-bar-fill-left');
    const rangeHeatmapCanvas = document.getElementById('range-heatmap-canvas');
    const rangeCopCanvas = document.getElementById('range-cop-canvas');
    const pressureRenderer = new PressureTileRenderer();

    // Dispersion plot canvas (sized from CSS; see dispersion.js)
    const minimapCanvas = document.getElementById('minimap-canvas');

    // Pressure is a rail widget. The tile's own close control goes through the
    // widget manager -- otherwise the picker's "Added" state and the rail-full
    // count drift out of sync with what's on screen. (addWidget/removeWidget
    // are hoisted function declarations.)
    function togglePressureTile() {
        if (!rangePressureTile) return;
        const isHidden = rangePressureTile.style.display === 'none' || !rangePressureTile.style.display;
        if (isHidden) addWidget('pressure');
        else removeWidget('pressure');
    }

    if (btnClosePressureTile) btnClosePressureTile.addEventListener('click', () => removeWidget('pressure'));

    let currentTargetYards = 150;
    let currentRangeMode = localStorage.getItem('sps_range_game_mode') || 'practice';
    let totalChallengeScore = 0;
    let bestPinProx = 999.0;
    let bestLongDrive = 0.0;
    let ladderLevel = 1;
    let ladderStreak = 0;
    let lastShotTelemetry = null;
    let lastShotId = null;
    let lastLandingPt = null;

    // 2. Game Mode Selection Logic
    function setGameMode(mode) {
        currentRangeMode = mode;
        localStorage.setItem('sps_range_game_mode', mode);

        gameModeCards.forEach(card => {
            const m = card.getAttribute('data-mode');
            const isActive = (m === mode);
            card.classList.toggle('active', isActive);
            const tag = card.querySelector('.game-mode-tag');
            if (tag) tag.style.display = isActive ? 'inline-block' : 'none';
        });

        // Reset stats for new game session
        totalChallengeScore = 0;
        bestPinProx = 999.0;
        bestLongDrive = 0.0;
        if (elTargetPts) elTargetPts.innerText = '0';
        if (elPinProx) elPinProx.innerText = '--';

        if (mode === 'practice') {
            if (rangeModeTitle) rangeModeTitle.innerText = 'Free Practice';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'block';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'block';
            if (challengePtsContainer) challengePtsContainer.style.display = 'none';
            if (challengeProxContainer) challengeProxContainer.style.display = 'none';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
        } else if (mode === 'ladder') {
            ladderLevel = 1;
            ladderStreak = 0;
            updateTarget(20);
            if (rangeModeTitle) rangeModeTitle.innerText = 'Distance Ladder';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'block';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'block';
            if (practiceLastCarry) practiceLastCarry.innerText = 'LEVEL 1';
            if (practiceLastOffline) practiceLastOffline.innerText = '0 STREAK';
            if (challengePtsContainer) challengePtsContainer.style.display = 'none';
            if (challengeProxContainer) challengeProxContainer.style.display = 'none';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
            showBanner('🪜', 'DISTANCE LADDER CHALLENGE', 'Target starts at 20 yds. Hit the green to move back 10-20 yds!');
        } else if (mode === 'challenge') {
            if (rangeModeTitle) rangeModeTitle.innerText = 'Target Challenge';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'none';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'none';
            if (challengePtsContainer) challengePtsContainer.style.display = 'block';
            if (challengeProxContainer) challengeProxContainer.style.display = 'block';
            if (targetScoringLegend) targetScoringLegend.style.display = 'flex';
        } else if (mode === 'closest-pin') {
            if (rangeModeTitle) rangeModeTitle.innerText = 'Closest to Pin';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'none';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'none';
            if (challengePtsContainer) challengePtsContainer.style.display = 'block';
            if (challengeProxContainer) challengeProxContainer.style.display = 'block';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
        } else if (mode === 'long-drive') {
            if (rangeModeTitle) rangeModeTitle.innerText = 'Long Drive';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'block';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'block';
            if (challengePtsContainer) challengePtsContainer.style.display = 'none';
            if (challengeProxContainer) challengeProxContainer.style.display = 'none';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
        }
    }

    // Initialize Default Mode
    setGameMode(currentRangeMode);

    // 3. Initialize Fairway Width from Storage
    let currentFairwayWidth = getFairwayWidth();
    if (fwSlider) fwSlider.value = currentFairwayWidth;
    if (fwReadout) fwReadout.innerText = `${currentFairwayWidth} yds`;

    function updateFairwayWidth(yards) {
        if (isNaN(yards)) return;
        currentFairwayWidth = Math.max(30, Math.min(120, Math.round(yards)));
        setFairwayWidth(currentFairwayWidth);
        if (fwSlider) fwSlider.value = currentFairwayWidth;
        if (fwReadout) fwReadout.innerText = `${currentFairwayWidth} yds`;
        
        fwPresetChips.forEach(chip => {
            const val = parseInt(chip.getAttribute('data-fw'), 10);
            chip.classList.toggle('active', val === currentFairwayWidth);
        });

        drawMinimap();
    }

    if (fwSlider) {
        fwSlider.addEventListener('input', (e) => updateFairwayWidth(parseFloat(e.target.value)));
    }
    if (fwStepMinus10) fwStepMinus10.addEventListener('click', () => updateFairwayWidth(currentFairwayWidth - 10));
    if (fwStepMinus5) fwStepMinus5.addEventListener('click', () => updateFairwayWidth(currentFairwayWidth - 5));
    if (fwStepPlus5) fwStepPlus5.addEventListener('click', () => updateFairwayWidth(currentFairwayWidth + 5));
    if (fwStepPlus10) fwStepPlus10.addEventListener('click', () => updateFairwayWidth(currentFairwayWidth + 10));

    fwPresetChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            const fwVal = parseInt(e.target.getAttribute('data-fw'), 10);
            updateFairwayWidth(fwVal);
        });
    });

    // 4. Initialize Target Distance from Storage
    const savedDist = localStorage.getItem('sps_range_target_dist');
    if (savedDist) {
        currentTargetYards = parseInt(savedDist, 10);
    }
    if (tgtSlider) tgtSlider.value = currentTargetYards;
    if (tgtCustomInput) tgtCustomInput.value = currentTargetYards;
    if (tgtReadout) tgtReadout.innerText = `${currentTargetYards} yds`;
    if (elTargetDistBadge) elTargetDistBadge.innerText = `${currentTargetYards}`;
    setTargetDistance(currentTargetYards);

    function updateTarget(newYards) {
        if (isNaN(newYards) || newYards <= 0) return;
        currentTargetYards = Math.max(20, Math.min(500, Math.round(newYards)));
        setTargetDistance(currentTargetYards);
        
        if (tgtSlider) tgtSlider.value = currentTargetYards;
        if (tgtCustomInput) tgtCustomInput.value = currentTargetYards;
        if (tgtReadout) tgtReadout.innerText = `${currentTargetYards} yds`;
        if (elTargetDistBadge) elTargetDistBadge.innerText = `${currentTargetYards}`;
        
        tgtPresetChips.forEach(chip => {
            const val = parseInt(chip.getAttribute('data-tgt'), 10);
            chip.classList.toggle('active', val === currentTargetYards);
        });

        localStorage.setItem('sps_range_target_dist', currentTargetYards);
        drawMinimap();
    }

    if (tgtSlider) {
        tgtSlider.addEventListener('input', (e) => updateTarget(parseFloat(e.target.value)));
    }
    if (btnSetCustomTarget && tgtCustomInput) {
        btnSetCustomTarget.addEventListener('click', () => {
            const val = parseFloat(tgtCustomInput.value);
            if (!isNaN(val) && val > 0) updateTarget(val);
        });
        tgtCustomInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = parseFloat(tgtCustomInput.value);
                if (!isNaN(val) && val > 0) updateTarget(val);
            }
        });
    }
    if (targetBadgeContainer) {
        targetBadgeContainer.addEventListener('click', () => {
            setDrawer('settings');
            if (tgtCustomInput) {
                tgtCustomInput.focus();
                tgtCustomInput.select();
            }
        });
    }

    if (tgtStepMinus10) tgtStepMinus10.addEventListener('click', () => updateTarget(currentTargetYards - 10));
    if (tgtStepMinus5) tgtStepMinus5.addEventListener('click', () => updateTarget(currentTargetYards - 5));
    if (tgtStepPlus5) tgtStepPlus5.addEventListener('click', () => updateTarget(currentTargetYards + 5));
    if (tgtStepPlus10) tgtStepPlus10.addEventListener('click', () => updateTarget(currentTargetYards + 10));

    tgtPresetChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            const yds = parseInt(e.target.getAttribute('data-tgt'), 10);
            updateTarget(yds);
        });
    });

    // 5. Drawer and Menu Actions
    //
    // Modes and Settings are both nav-tab drawers anchored under the top bar.
    // One helper owns "open exactly one of them" so the pair can never both be
    // open and a tab's active state can never drift from its drawer.
    function setDrawer(which) {
        const drawers = [
            { el: gameModesDrawer, tab: tabModes, key: 'modes' },
            { el: settingsDrawer, tab: tabSettings, key: 'settings' },
        ];
        let anyOpen = false;
        for (const d of drawers) {
            if (!d.el) continue;
            const open = d.key === which;
            d.el.classList.toggle('open', open);
            if (d.tab) d.tab.classList.toggle('active', open);
            if (open) anyOpen = true;
        }
        // These are centred modals, so they need a scrim behind them.
        if (drawerScrim) drawerScrim.classList.toggle('open', anyOpen);
    }

    function toggleDrawer(key) {
        const el = key === 'modes' ? gameModesDrawer : settingsDrawer;
        if (!el) return;
        setDrawer(el.classList.contains('open') ? null : key);
    }

    if (drawerScrim) {
        drawerScrim.addEventListener('click', () => setDrawer(null));
    }
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') setDrawer(null);
    });

    if (btnCloseGameModes) {
        btnCloseGameModes.addEventListener('click', () => setDrawer(null));
    }
    if (btnCloseSettings) {
        btnCloseSettings.addEventListener('click', () => setDrawer(null));
    }

    gameModeCards.forEach(card => {
        card.addEventListener('click', () => {
            const mode = card.getAttribute('data-mode');
            setGameMode(mode);
            setDrawer(null);
        });
    });

    if (btnStudioMenu) {
        btnStudioMenu.addEventListener('click', () => {
            window.location.href = '/';
        });
    }

    window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.key === 'g' || e.key === 'G') {
            toggleDrawer('modes');
        } else if (e.key === 's' || e.key === 'S') {
            toggleDrawer('settings');
        }
    });

    // 5. Telemetry Extraction
    // Handedness: Nova sends per-hand dicts {right_handed, left_handed}.
    // Enable lefty mode with ?lefty=1 (persisted) or localStorage sps_lefty=1.
    const IS_LEFTY = (() => {
        try {
            const qp = new URLSearchParams(window.location.search).get('lefty');
            if (qp !== null) {
                const v = qp === '1' || qp === 'true';
                localStorage.setItem('sps_lefty', v ? '1' : '0');
                return v;
            }
            return localStorage.getItem('sps_lefty') === '1';
        } catch (e) { return false; }
    })();
    function handed(val, fallback = 0.0) {
        if (val && typeof val === 'object') {
            const v = IS_LEFTY ? (val.left_handed ?? val.right_handed) : val.right_handed;
            return v ?? fallback;
        }
        return val ?? fallback;
    }

    function extractShotTelemetry(msg) {
        if (!msg) return null;
        const raw = msg.data || msg.shot || msg;
        if (!raw || typeof raw !== 'object') return null;

        const ogc = raw.open_golf_coach || (raw.shot && raw.shot.open_golf_coach) || {};
        const us = ogc.us_customary_units || raw.us_units || (raw.shot && raw.shot.us_units) || {};

        // Ball Speed (MPH)
        let ballSpeed = 0.0;
        if (us.ball_speed_mph !== undefined && us.ball_speed_mph !== null) {
            ballSpeed = parseFloat(us.ball_speed_mph);
        } else if (raw.ball_speed_meters_per_second !== undefined && raw.ball_speed_meters_per_second !== null) {
            ballSpeed = parseFloat(raw.ball_speed_meters_per_second) * 2.236936;
        } else if (raw.ball_speed_mph !== undefined && raw.ball_speed_mph !== null) {
            ballSpeed = parseFloat(raw.ball_speed_mph);
        } else if (raw.ball_speed !== undefined && raw.ball_speed !== null) {
            ballSpeed = parseFloat(raw.ball_speed);
        }

        if (isNaN(ballSpeed) || ballSpeed < 5.0) return null;

        // Launch Angles & Spin
        const vla = parseFloat(raw.vertical_launch_angle_degrees || us.vert_launch_angle_deg || raw.launch_angle || 14.0);
        const hla = parseFloat(raw.horizontal_launch_angle_degrees || us.horiz_launch_angle_deg || raw.hla || 0.0);
        const totalSpin = parseFloat(raw.total_spin_rpm || ogc.total_spin_rpm || us.total_spin_rpm || raw.total_spin || 3000.0);
        const spinAxis = parseFloat(raw.spin_axis_degrees || ogc.spin_axis_degrees || us.spin_axis_deg || raw.spin_axis || 0.0);
        const sidespin = parseFloat(ogc.sidespin_rpm || raw.sidespin_rpm || raw.sidespin || (Math.sin(spinAxis * Math.PI / 180) * totalSpin));
        const backspin = parseFloat(ogc.backspin_rpm || raw.backspin_rpm || raw.backspin || (Math.cos(spinAxis * Math.PI / 180) * totalSpin));
        const descent = parseFloat(ogc.descent_angle_degrees || raw.descent_angle_degrees || raw.descent_angle || 45.0);

        let carryYds = null;
        if (us.carry_distance_yards !== undefined && us.carry_distance_yards !== null) carryYds = parseFloat(us.carry_distance_yards);
        else if (raw.carry !== undefined && raw.carry !== null) carryYds = parseFloat(raw.carry);

        let totalYds = null;
        if (us.total_distance_yards !== undefined && us.total_distance_yards !== null) totalYds = parseFloat(us.total_distance_yards);
        else if (raw.total !== undefined && raw.total !== null) totalYds = parseFloat(raw.total);

        let offlineYds = null;
        if (us.offline_distance_yards !== undefined && us.offline_distance_yards !== null) offlineYds = parseFloat(us.offline_distance_yards);
        else if (raw.offline !== undefined && raw.offline !== null) offlineYds = parseFloat(raw.offline);

        let apexFt = null;
        if (us.peak_height_yards !== undefined && us.peak_height_yards !== null) apexFt = parseFloat(us.peak_height_yards) * 3.0;
        else if (raw.apex !== undefined && raw.apex !== null) apexFt = parseFloat(raw.apex) * 3.0;

        // Club Analytics & Advanced Telemetry
        const smash = parseFloat(ogc.smash_factor || raw.smash_factor || raw.smash || 1.35);
        let clubSpeed = 0.0;
        if (us.club_speed_mph !== undefined && us.club_speed_mph !== null) {
            clubSpeed = parseFloat(us.club_speed_mph);
        } else if (raw.club_speed_mph !== undefined && raw.club_speed_mph !== null) {
            clubSpeed = parseFloat(raw.club_speed_mph);
        } else if (raw.club_speed !== undefined && raw.club_speed !== null) {
            clubSpeed = parseFloat(raw.club_speed);
        } else {
            clubSpeed = ballSpeed / Math.max(1.0, smash);
        }

        const clubPath = parseFloat(handed(ogc.club_path_degrees, null) ?? raw.club_path ?? raw.club_path_degrees ?? 0.0);
        const faceAngle = parseFloat(handed(ogc.club_face_to_path_degrees, null) ?? raw.face_to_path ?? raw.face_angle ?? 0.0);
        const attackAngle = parseFloat(handed(ogc.angle_of_attack_degrees, null) ?? raw.angle_of_attack_degrees ?? raw.attack_angle ?? (vla * 0.3 - 4.5));
        const dynamicLoft = parseFloat(handed(ogc.dynamic_loft_degrees, null) ?? raw.dynamic_loft_degrees ?? raw.dynamic_loft ?? (vla * 0.85));
        const hangTime = parseFloat(ogc.hang_time_seconds || raw.hang_time_seconds || raw.hang_time || (2.0 * Math.sin(vla * Math.PI / 180) * (ballSpeed * 0.44704) / 9.81));
        
        let closureRate = 0.0;
        if (ogc.face_closure_rate_dps !== undefined) closureRate = parseFloat(ogc.face_closure_rate_dps);
        else if (raw.face_closure_rate_dps !== undefined) closureRate = parseFloat(raw.face_closure_rate_dps);
        else if (raw.closure_rate !== undefined) closureRate = parseFloat(raw.closure_rate);
        else closureRate = Math.round(1800 + Math.abs(faceAngle) * 320 + (clubSpeed * 12.5));

        // Which values the payload did NOT contain, and we filled in with a
        // model or a constant. The UI tags these so a derived number is never
        // presented as something the Nova measured. Keep this in sync with the
        // fallbacks above -- an untagged estimate is a lie to the user.
        const has = (v) => v !== undefined && v !== null;
        const derived = {
            clubSpeed: !(has(us.club_speed_mph) || has(raw.club_speed_mph) || has(raw.club_speed)),
            attackAngle: !(has(handed(ogc.angle_of_attack_degrees, null))
                           || has(raw.angle_of_attack_degrees) || has(raw.attack_angle)),
            dynamicLoft: !(has(handed(ogc.dynamic_loft_degrees, null))
                           || has(raw.dynamic_loft_degrees) || has(raw.dynamic_loft)),
            hangTime: !(has(ogc.hang_time_seconds) || has(raw.hang_time_seconds) || has(raw.hang_time)),
            closureRate: !(has(ogc.face_closure_rate_dps)
                           || has(raw.face_closure_rate_dps) || has(raw.closure_rate)),
            descent: !(has(ogc.descent_angle_degrees)
                       || has(raw.descent_angle_degrees) || has(raw.descent_angle)),
            backspin: !(has(ogc.backspin_rpm) || has(raw.backspin_rpm) || has(raw.backspin)),
            sidespin: !(has(ogc.sidespin_rpm) || has(raw.sidespin_rpm) || has(raw.sidespin)),
            total: !has(totalYds),
            apex: !has(apexFt),
        };

        const shotClub = raw.club || ogc.club || "7 Iron";
        const clubColor = raw.club_color || ogc.club_color || null;
        const shotId = raw.shot_number || raw.timestamp || raw.id || `${ballSpeed.toFixed(1)}_${vla.toFixed(1)}_${totalSpin.toFixed(0)}`;

        return {
            shotId,
            club: shotClub,
            clubColor: clubColor,
            derived,
            ballSpeed,
            clubSpeed,
            smash,
            closureRate,
            clubPath,
            faceAngle,
            attackAngle,
            dynamicLoft,
            hangTime,
            verticalLaunchAngle: vla,
            horizontalLaunchAngle: hla,
            total_spin: totalSpin,
            spin_axis: spinAxis,
            sidespin,
            backspin,
            descent,
            ogcCarry: carryYds,
            ogcTotal: totalYds,
            ogcOffline: offlineYds,
            apexFt
        };
    }

    // ------------------------------------------------------------------
    // Bottom strip: build cells from the saved layout, then paint values.
    // ------------------------------------------------------------------
    function buildStrip() {
        if (!metricStrip) return;
        metricStrip.innerHTML = '';
        stripCells.clear();

        for (const key of stripLayout) {
            const def = METRICS[key];
            if (!def) continue;

            const cell = document.createElement('div');
            cell.className = 'ms-cell';
            cell.dataset.metric = key;

            const label = document.createElement('div');
            label.className = 'ms-label';
            label.textContent = def.label;
            label.dataset.full = def.label;
            label.dataset.short = def.short || def.label;

            const value = document.createElement('div');
            value.className = 'ms-value' + (def.accent ? ' accent' : '');
            value.textContent = '\u2014\u2014';

            const unit = document.createElement('div');
            unit.className = 'ms-unit';
            unit.textContent = def.unit || '';

            cell.appendChild(label);
            cell.appendChild(value);
            cell.appendChild(unit);
            metricStrip.appendChild(cell);

            stripCells.set(key, { cell, label, value, unit });
        }
        fitStripLabels();
        // Repaint immediately so a layout change doesn't blank the strip until
        // the next shot arrives.
        if (lastShotTelemetry) {
            const t = lastShotTelemetry;
            const carryYds = t.ogcCarry || 0.0;
            paintStrip(t, {
                carryYds,
                totalYds: t.ogcTotal || (carryYds * 1.08),
                offlineYds: t.ogcOffline !== null ? t.ogcOffline : 0.0,
                apexFt: t.apexFt || (carryYds * 0.42 * 3.0),
                smashClamped: isSmashClamped(t.smash),
            });
        }
    }

    /**
     * Fit strip labels to their cell.
     *
     * Two-stage degradation, because font shrinking alone bottoms out: first
     * try the full label, then the metric's short form. The EST tag is never
     * dropped -- it is the marker saying a value was derived rather than
     * measured, so a label losing characters is strictly better than a value
     * silently looking measured.
     */
    function fitStripLabels() {
        for (const { cell, label } of stripCells.values()) {
            if (!label || !label.dataset.full) continue;
            const tag = label.querySelector('.est-tag');
            const setText = (t) => {
                label.textContent = t;
                if (tag) label.appendChild(tag);
            };
            const overflowing = () => label.scrollWidth > label.clientWidth + 1;

            if (cell) cell.classList.remove('tight');
            setText(label.dataset.full);
            if (!overflowing()) continue;

            setText(label.dataset.short);
            if (!overflowing()) continue;

            // Still tight: drop the unit row, which is the least important line
            // (the label already implies it) and buys the label its width.
            if (cell) cell.classList.add('tight');
            if (!overflowing()) continue;

            // Last resort: truncate the short label, but never the EST tag --
            // losing characters is fine, losing the "derived, not measured"
            // marker is not.
            let text = label.dataset.short;
            while (text.length > 2 && overflowing()) {
                text = text.slice(0, -1);
                setText(text + '\u2026');
            }
        }
    }

    if (metricStrip && typeof ResizeObserver !== 'undefined') {
        let stripRaf = null;
        const ro = new ResizeObserver(() => {
            if (stripRaf) cancelAnimationFrame(stripRaf);
            stripRaf = requestAnimationFrame(() => { stripRaf = null; fitStripLabels(); });
        });
        ro.observe(metricStrip);
    }

    function paintStrip(telemetry, ctx) {
        for (const [key, nodes] of stripCells.entries()) {
            const r = readMetric(key, telemetry, ctx);
            if (!r) continue;

            if (r.html) nodes.value.innerHTML = r.html;
            else nodes.value.textContent = r.text;

            nodes.value.classList.toggle('muted', !!r.muted);
            nodes.value.title = r.title || '';
            nodes.unit.textContent = r.unit || '';

            // EST tag: the value came from a model/constant, not the Nova.
            const hasTag = !!nodes.label.querySelector('.est-tag');
            if (r.est && !hasTag) {
                const tag = document.createElement('span');
                tag.className = 'est-tag';
                tag.textContent = 'EST';
                tag.title = 'Derived from a model, not measured by the launch monitor.';
                nodes.label.appendChild(tag);
            } else if (!r.est && hasTag) {
                nodes.label.querySelector('.est-tag').remove();
            }
        }
        // An EST tag changes label width, so re-fit after painting.
        fitStripLabels();
    }

    function renderStripMenu() {
        if (!smList) return;
        smList.innerHTML = '';
        const atMin = stripLayout.length <= MIN_STRIP;
        const atMax = stripLayout.length >= MAX_STRIP;

        if (smHint) {
            smHint.textContent = `${stripLayout.length} of ${MAX_STRIP} selected`
                + (atMax ? ' \u2014 strip is full' : (atMin ? ` \u2014 minimum ${MIN_STRIP}` : ''));
            smHint.classList.toggle('warn', atMin || atMax);
        }

        for (const [key, def] of Object.entries(METRICS)) {
            const idx = stripLayout.indexOf(key);
            const on = idx !== -1;
            // Can't drop below the minimum or add past the maximum.
            const locked = (on && atMin) || (!on && atMax);

            const item = document.createElement('div');
            item.className = 'sm-item' + (on ? ' on' : '') + (locked ? ' locked' : '');
            item.dataset.metric = key;
            item.innerHTML = `<span class="sm-box">${on ? '\u2713' : ''}</span>`
                + `<span class="sm-name">${def.label}</span>`
                + `<span class="sm-unit">${def.unit || ''}</span>`
                + `<span class="sm-order">${on ? idx + 1 : ''}</span>`;
            if (locked) {
                item.title = on
                    ? `At least ${MIN_STRIP} metrics must stay on the strip`
                    : `The strip holds at most ${MAX_STRIP} metrics`;
            } else {
                item.addEventListener('click', () => toggleStripMetric(key));
            }
            smList.appendChild(item);
        }
    }

    function toggleStripMetric(key) {
        const idx = stripLayout.indexOf(key);
        if (idx === -1) {
            if (stripLayout.length >= MAX_STRIP) return;
            stripLayout.push(key);           // appended in selection order
        } else {
            if (stripLayout.length <= MIN_STRIP) return;
            stripLayout.splice(idx, 1);
        }
        saveStripLayout(stripLayout);
        buildStrip();
        renderStripMenu();
        // Metric count feeds the scale ceiling, so re-evaluate it.
        applyHudScale(hudScaleSlider ? hudScaleSlider.value : 100, { persist: false });
    }

    if (btnStripConfig) {
        btnStripConfig.addEventListener('click', (e) => {
            e.stopPropagation();
            if (stripMenu.classList.contains('open')) {
                stripMenu.classList.remove('open');
            } else {
                renderStripMenu();
                stripMenu.classList.add('open');
            }
        });
    }
    if (smReset) {
        smReset.addEventListener('click', (e) => {
            e.stopPropagation();
            stripLayout = [...DEFAULT_STRIP];
            saveStripLayout(stripLayout);
            buildStrip();
            renderStripMenu();
        });
    }
    document.addEventListener('click', (e) => {
        if (!stripMenu || !stripMenu.classList.contains('open')) return;
        if (stripMenu.contains(e.target)) return;
        if (btnStripConfig && btnStripConfig.contains(e.target)) return;
        stripMenu.classList.remove('open');
    }, true);
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && stripMenu) stripMenu.classList.remove('open');
    });

    buildStrip();

    // ------------------------------------------------------------------
    // Club picker: pick the club for the next shot from My Bag.
    // ------------------------------------------------------------------
    // The Nova reports a club on every shot, but it is only ever the club the
    // desktop app currently has selected -- the monitor cannot detect what you
    // actually swung. Picking here overrides that label for subsequent shots so
    // the shot list and per-club dispersion group correctly.
    const clubChip = document.getElementById('club-chip');
    const clubSheet = document.getElementById('club-sheet');
    const csBody = document.getElementById('cs-body');
    const csClose = document.getElementById('cs-close');
    const csClear = document.getElementById('cs-clear');
    const csNote = document.getElementById('cs-note');
    const clubChipSubEl = document.getElementById('club-chip-sub');

    let bagClubs = [];
    let bagError = null;
    let manualClub = null;   // {name, ...} when the user has chosen; null = auto

    function applyClubChip() {
        if (manualClub) {
            if (hudClubName) hudClubName.innerText = manualClub.name;
            if (clubChipSubEl) {
                const sub = clubSubtitle(manualClub);
                clubChipSubEl.innerText = sub || 'Selected from My Bag';
            }
            if (clubChip) clubChip.classList.add('manual');
        } else if (clubChip) {
            clubChip.classList.remove('manual');
        }
        if (csClear) csClear.classList.toggle('active', !manualClub);
    }

    function renderClubSheet() {
        if (!csBody) return;

        if (bagError) {
            csBody.innerHTML = `<div class="cs-error">Couldn't load My Bag (${bagError}).<br><br>`
                + 'Clubs will keep coming from the launch monitor. Start the desktop app '
                + 'and reopen this panel to try again.</div>';
            return;
        }
        if (bagClubs.length === 0) {
            csBody.innerHTML = '<div class="cs-loading">My Bag is empty.<br><br>'
                + 'Add clubs in the desktop app (My Bag) and reopen this panel.</div>';
            return;
        }

        const frag = document.createDocumentFragment();
        for (const g of groupClubs(bagClubs)) {
            const label = document.createElement('div');
            label.className = 'cs-group-label';
            label.textContent = g.label;
            frag.appendChild(label);

            const row = document.createElement('div');
            row.className = 'cs-pills';
            for (const club of g.clubs) {
                const pill = document.createElement('button');
                pill.type = 'button';
                pill.className = 'cs-pill'
                    + (manualClub && manualClub.name === club.name ? ' selected' : '');
                pill.textContent = pillLabel(club);
                pill.dataset.club = club.name;
                const sub = clubSubtitle(club);
                pill.title = sub ? `${club.name} \u2014 ${sub}` : club.name;
                pill.addEventListener('click', () => selectClub(club));
                row.appendChild(pill);
            }
            frag.appendChild(row);
        }
        csBody.innerHTML = '';
        csBody.appendChild(frag);
    }

    function selectClub(club) {
        manualClub = club;
        applyClubChip();
        renderClubSheet();
        closeClubSheet();
    }

    function clearManualClub() {
        manualClub = null;
        applyClubChip();
        renderClubSheet();
        // Fall back to whatever the last shot reported.
        if (lastShotTelemetry && hudClubName) {
            hudClubName.innerText = lastShotTelemetry.club || '--';
        }
    }

    async function openClubSheet() {
        if (!clubSheet) return;
        clubSheet.classList.add('open');
        if (csNote) {
            csNote.textContent = 'Applies to your next shot. Shots already hit keep '
                               + 'the club they were recorded with.';
        }
        // Re-fetch each time: the desktop app can edit the bag while this is open.
        if (csBody) csBody.innerHTML = '<div class="cs-loading">Loading My Bag\u2026</div>';
        const res = await fetchBag();
        bagClubs = res.clubs;
        bagError = res.error;
        renderClubSheet();
        applyClubChip();
    }

    function closeClubSheet() {
        if (clubSheet) clubSheet.classList.remove('open');
    }

    if (clubChip) clubChip.addEventListener('click', openClubSheet);
    if (csClose) csClose.addEventListener('click', closeClubSheet);
    if (csClear) {
        csClear.addEventListener('click', () => {
            clearManualClub();
            closeClubSheet();
        });
    }
    if (clubSheet) {
        // Click the scrim (not the panel) to dismiss.
        clubSheet.addEventListener('click', (e) => {
            if (e.target === clubSheet) closeClubSheet();
        });
    }
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeClubSheet();
    });

    // ------------------------------------------------------------------
    // Cinematic shot view: hide the HUD during ball flight.
    // ------------------------------------------------------------------
    // Driven by a body class so it's pure CSS transform/opacity -- no reflow,
    // and the 3D canvas is never touched.
    //
    // Restoring is the part that has to be bulletproof: a HUD stuck off-screen
    // makes the app look broken and there is no way for the user to recover it.
    // So there are three independent ways back:
    //   1. the ball reports it has come to rest (normal path),
    //   2. an absolute timeout that fires regardless of ball state,
    //   3. any user interaction (key press or click).
    const CINEMATIC_KEY = 'sps_range_cinematic';
    const CINEMATIC_SETTLE_MS = 900;    // linger after the ball rests
    const CINEMATIC_MAX_MS = 22000;     // hard ceiling -- never hide longer

    const cinematicToggle = document.getElementById('cinematic-toggle');
    let cinematicEnabled = localStorage.getItem(CINEMATIC_KEY) !== '0';
    let cinematicActive = false;
    let cinematicPoll = null;
    let cinematicMaxTimer = null;
    let cinematicSettleTimer = null;

    if (cinematicToggle) {
        cinematicToggle.checked = cinematicEnabled;
        cinematicToggle.addEventListener('change', () => {
            cinematicEnabled = cinematicToggle.checked;
            try { localStorage.setItem(CINEMATIC_KEY, cinematicEnabled ? '1' : '0'); } catch {}
            if (!cinematicEnabled) exitCinematic();
        });
    }

    function clearCinematicTimers() {
        if (cinematicPoll !== null) { clearInterval(cinematicPoll); cinematicPoll = null; }
        if (cinematicMaxTimer !== null) { clearTimeout(cinematicMaxTimer); cinematicMaxTimer = null; }
        if (cinematicSettleTimer !== null) { clearTimeout(cinematicSettleTimer); cinematicSettleTimer = null; }
    }

    function exitCinematic() {
        clearCinematicTimers();
        if (!cinematicActive) {
            document.body.classList.remove('cinematic');
            return;
        }
        cinematicActive = false;
        document.body.classList.remove('cinematic');
    }

    function enterCinematic() {
        if (!cinematicEnabled) return;
        // Never hide the HUD while a modal/menu is open -- the user is mid-task
        // and would watch their own panel slide away underneath them.
        if (document.querySelector('#club-sheet.open, #widget-menu.open, #strip-menu.open')) return;
        if (settingsDrawer && settingsDrawer.classList.contains('open')) return;
        if (gameModesDrawer && gameModesDrawer.classList.contains('open')) return;

        clearCinematicTimers();
        cinematicActive = true;
        document.body.classList.add('cinematic');

        // (1) normal path: watch for the ball to finish flying.
        cinematicPoll = setInterval(() => {
            const flying = ball && (ball.isAnimating || ball.isAtRest);
            if (!flying) return;
            if (ball.isAnimating) return;          // still in the air
            // At rest: linger briefly so the landing reads, then restore.
            if (cinematicSettleTimer === null) {
                cinematicSettleTimer = setTimeout(exitCinematic, CINEMATIC_SETTLE_MS);
            }
        }, 120);

        // (2) hard ceiling, independent of ball state.
        cinematicMaxTimer = setTimeout(exitCinematic, CINEMATIC_MAX_MS);
    }

    // (3) any interaction brings the HUD straight back.
    window.addEventListener('keydown', () => { if (cinematicActive) exitCinematic(); });
    document.addEventListener('pointerdown', () => { if (cinematicActive) exitCinematic(); }, true);

    function updateHUDTelemetry(shotData, simulatedCarry = null, simulatedOffline = null) {
        if (!shotData) return;

        const carryYds = shotData.ogcCarry || simulatedCarry || 0.0;
        const totalYds = shotData.ogcTotal || (carryYds * 1.08);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : (simulatedOffline || 0.0);
        const apexFt = shotData.apexFt || (carryYds * 0.42 * 3.0);

        // --- bottom strip (configurable) ---
        // Rendered from the saved layout so adding/removing a metric is a data
        // change, not a code change. Smash clamping is resolved here because the
        // detector lives alongside the OGC constants.
        const stripCtx = {
            carryYds, totalYds, offlineYds, apexFt,
            smashClamped: isSmashClamped(shotData.smash),
        };
        paintStrip(shotData, stripCtx);

        // --- All Metrics panel (static, always complete) ---
        if (elClubSpeed) elClubSpeed.innerText = (typeof shotData.clubSpeed === 'number') ? shotData.clubSpeed.toFixed(1) : '--';
        if (elSpinAxis) elSpinAxis.innerText = (typeof shotData.spin_axis === 'number') ? `${shotData.spin_axis >= 0 ? '+' : ''}${shotData.spin_axis.toFixed(1)}` : '--';
        if (elHla) elHla.innerText = (typeof shotData.horizontalLaunchAngle === 'number') ? `${shotData.horizontalLaunchAngle >= 0 ? '+' : ''}${shotData.horizontalLaunchAngle.toFixed(1)}` : '--';
        if (elClosureRate) elClosureRate.innerText = shotData.closureRate ? Math.round(shotData.closureRate) : '--';
        if (elClubPath) elClubPath.innerText = (typeof shotData.clubPath === 'number') ? `${shotData.clubPath >= 0 ? '+' : ''}${shotData.clubPath.toFixed(1)}°` : '--';
        if (elFaceAngle) elFaceAngle.innerText = (typeof shotData.faceAngle === 'number') ? `${shotData.faceAngle >= 0 ? '+' : ''}${shotData.faceAngle.toFixed(1)}°` : '--';
        if (elAttackAngle) elAttackAngle.innerText = (typeof shotData.attackAngle === 'number') ? `${shotData.attackAngle >= 0 ? '+' : ''}${shotData.attackAngle.toFixed(1)}°` : '--';
        if (elDynamicLoft) elDynamicLoft.innerText = (typeof shotData.dynamicLoft === 'number') ? `${shotData.dynamicLoft.toFixed(1)}°` : '--';
        if (elBackspin) elBackspin.innerText = Math.round(shotData.backspin || shotData.total_spin || 0);
        if (elSidespin) elSidespin.innerText = Math.round(shotData.sidespin || 0);
        if (elDescent) elDescent.innerText = (typeof shotData.descent === 'number') ? `${shotData.descent.toFixed(1)}°` : '--';
        if (elHangTime) elHangTime.innerText = (typeof shotData.hangTime === 'number') ? `${shotData.hangTime.toFixed(1)}` : '--';

        if (hudClubName) {
            hudClubName.innerText = shotData.club || '--';
            if (shotData.clubColor) hudClubName.style.color = shotData.clubColor;
        }
        if (clubChipSub) {
            if (manualClub) {
                // Keep the bag spec visible; the chip's ring already signals
                // that this club was chosen rather than reported.
                const sub = clubSubtitle(manualClub);
                clubChipSub.innerText = sub || 'Selected from My Bag';
            } else {
                const n = shotHistory.shots.filter(s => s.club === (shotData.club || '').trim()).length;
                clubChipSub.innerText = n > 0
                    ? `${n} shot${n === 1 ? '' : 's'} this session`
                    : 'Awaiting shot';
            }
        }

        // 1. Update Free Practice Status
        if (practiceLastCarry) practiceLastCarry.innerText = `${carryYds.toFixed(1)} yds`;
        if (practiceLastOffline) practiceLastOffline.innerText = `${Math.abs(offlineYds).toFixed(1)} ${offlineYds >= 0 ? 'R' : 'L'}`;

        // 2. Calculate Proximity to Target & Game Scores
        const dx = offlineYds;
        const dz = carryYds - currentTargetYards;
        const pinDeltaYds = Math.sqrt(dx * dx + dz * dz);
        const pinDeltaFt = pinDeltaYds * 3.0;

        let points = 0;
        if (pinDeltaYds <= 4.0) points = 5;      // Bullseye
        else if (pinDeltaYds <= 9.0) points = 3; // Mid Ring
        else if (pinDeltaYds <= 16.0) points = 1;// Outer Green

        if (currentRangeMode === 'challenge') {
            totalChallengeScore += points;
            if (elTargetPts) elTargetPts.innerText = totalChallengeScore;
            if (elPinProx) elPinProx.innerText = pinDeltaFt < 100 ? `${pinDeltaFt.toFixed(1)} ft` : `${pinDeltaYds.toFixed(0)} yds`;
        } else if (currentRangeMode === 'ladder') {
            const targetGreenRadiusYds = currentTargetYards <= 40 ? 6.0 : (currentTargetYards <= 100 ? 10.0 : 14.0);
            const isGreenHit = pinDeltaYds <= targetGreenRadiusYds;

            if (isGreenHit) {
                ladderLevel++;
                ladderStreak++;
                // Random increment between 10 and 20 yards
                const inc = Math.floor(Math.random() * 11) + 10;
                const nextDist = Math.min(500, currentTargetYards + inc);
                showBanner('🎉', `LADDER LEVEL ${ladderLevel}! (+${inc}y)`, `Great Shot (${pinDeltaFt.toFixed(1)} ft)! Moving from ${currentTargetYards}y ➔ ${nextDist}y`);
                updateTarget(nextDist);
                if (practiceLastCarry) practiceLastCarry.innerText = `LEVEL ${ladderLevel}`;
                if (practiceLastOffline) practiceLastOffline.innerText = `${ladderStreak} STREAK`;
            } else {
                ladderStreak = 0;
                showBanner('⚠️', `MISSED GREEN (${pinDeltaFt.toFixed(1)} ft away)`, `Target remains at ${currentTargetYards} yds. Try again!`);
                if (practiceLastCarry) practiceLastCarry.innerText = `LEVEL ${ladderLevel}`;
                if (practiceLastOffline) practiceLastOffline.innerText = `0 STREAK`;
            }
        } else if (currentRangeMode === 'closest-pin') {
            if (pinDeltaFt < bestPinProx) bestPinProx = pinDeltaFt;
            if (elTargetPts) elTargetPts.innerText = `${bestPinProx.toFixed(1)} ft`;
            if (elPinProx) elPinProx.innerText = `${pinDeltaFt.toFixed(1)} ft`;
        } else if (currentRangeMode === 'long-drive') {
            const isFairway = Math.abs(offlineYds) <= (currentFairwayWidth / 2);
            if (isFairway && carryYds > bestLongDrive) bestLongDrive = carryYds;
            if (practiceLastCarry) practiceLastCarry.innerText = `${carryYds.toFixed(1)} yds`;
            if (practiceLastOffline) practiceLastOffline.innerText = isFairway ? 'FAIRWAY' : 'ROUGH';
        }

        lastLandingPt = { x: offlineYds, z: carryYds };

        // Redraw the dispersion plot with the new shot
        drawMinimap();
        refreshDynamicWidgets();
    }

    function renderShotList() {
        if (!slBody) return;

        if (shotHistory.count === 0) {
            slBody.innerHTML = '<div class="sl-empty" id="sl-empty">No shots yet.<br>Hit a ball, or use <b>▶ Demo</b> above.</div>';
            return;
        }

        const fmtOffline = (v) => `${Math.abs(v).toFixed(1)} ${v >= 0 ? 'R' : 'L'}`;
        const groups = shotHistory.grouped(shotListSort);
        const frag = document.createDocumentFragment();

        for (const g of groups) {
            const head = document.createElement('div');
            head.className = 'sl-group';
            const name = document.createElement('span');
            name.textContent = g.club;
            const caret = document.createElement('span');
            caret.className = 'caret';
            // Count reflects measured shots; demo shots are called out separately
            // so the group header never implies more real data than exists.
            caret.textContent = g.demoCount
                ? `${g.measuredCount}+${g.demoCount}d`
                : `${g.count}`;
            if (g.demoCount) {
                caret.title = `${g.measuredCount} measured, ${g.demoCount} demo (excluded from AVG)`;
            }
            head.appendChild(name);
            head.appendChild(caret);
            frag.appendChild(head);

            const avg = document.createElement('div');
            avg.className = 'sl-row avg';
            // A demo-only group has no measured shots to average.
            avg.innerHTML = '<span class="n">AVG</span>'
                + `<span class="c">${g.avgCarry === null ? '--' : g.avgCarry.toFixed(1)}</span>`
                + `<span class="o">${g.avgOffline === null ? '--' : fmtOffline(g.avgOffline)}</span>`;
            frag.appendChild(avg);

            for (const s of g.shots) {
                const row = document.createElement('div');
                row.className = 'sl-row'
                    + (s.seq === selectedShotSeq ? ' selected' : '')
                    + (s.isDemo ? ' demo' : '');
                row.dataset.seq = String(s.seq);
                row.innerHTML = `<span class="n">${String(s.seq).padStart(2, '0')}</span>`
                    + `<span class="c">${s.carry.toFixed(1)}</span>`
                    + `<span class="o">${fmtOffline(s.offline)}</span>`
                    + `<button class="sl-replay" data-replay="${s.seq}" `
                    + `title="Replay this shot" aria-label="Replay shot ${s.seq}">\u21ba</button>`;
                row.title = s.isDemo
                    ? 'Demo shot (not measured) \u2014 click to replay'
                    : 'Click to replay this shot';
                frag.appendChild(row);
            }
        }

        slBody.innerHTML = '';
        slBody.appendChild(frag);
    }

    if (slBody) {
        slBody.addEventListener('click', (e) => {
            const row = e.target.closest('.sl-row');
            if (!row || row.classList.contains('avg') || !row.dataset.seq) return;
            const entry = shotHistory.find(parseInt(row.dataset.seq, 10));
            if (!entry) return;
            // Row click and the row's ↺ button do the same thing; the button is
            // the visible affordance for what the whole row already did.
            replayShot(entry);
        });
    }

    if (slSortBtn) {
        slSortBtn.addEventListener('click', () => {
            shotListSort = shotListSort === 'recent' ? 'carry' : 'recent';
            slSortBtn.textContent = (shotListSort === 'recent' ? 'Recent' : 'Carry') + ' ▾';
            renderShotList();
        });
    }

    // All Metrics panel: everything the 8-cell strip doesn't show.
    function setAllMetricsOpen(open) {
        if (!allMetricsPanel) return;
        allMetricsPanel.classList.toggle('open', open);
        if (tabMetrics) tabMetrics.classList.toggle('active', open);
    }
    if (tabMetrics) {
        tabMetrics.addEventListener('click', () => {
            setAllMetricsOpen(!allMetricsPanel.classList.contains('open'));
        });
    }
    if (btnCloseAllMetrics) {
        btnCloseAllMetrics.addEventListener('click', () => setAllMetricsOpen(false));
    }
    if (tabModes && gameModesDrawer) {
        tabModes.addEventListener('click', () => toggleDrawer('modes'));
    }
    if (tabSettings && settingsDrawer) {
        tabSettings.addEventListener('click', () => toggleDrawer('settings'));
    }

    function fireShot(shotData, opts = {}) {
        if (!shotData) return;
        const record = opts.record !== false;

        // A manual pick overrides the monitor's club label for NEW shots only.
        // The Nova reports whichever club the desktop app has selected, not what
        // was actually swung, so the user's choice is the better signal. Replays
        // keep the club they were recorded with.
        if (record && manualClub && manualClub.name) {
            shotData = { ...shotData, club: manualClub.name };
        }

        lastShotTelemetry = shotData;
        lastShotId = shotData.shotId;

        const trajectory = physicsEngine.calculateTrajectory(shotData);
        const finalPt = trajectory[trajectory.length - 1];
        // Carry = first ground contact, NOT the post-roll final point —
        // falling back to finalPt.z inflated carry by the bounce/roll-out.
        let carryPt = finalPt;
        for (let i = 0; i < trajectory.length; i++) {
            if (trajectory[i].bounces > 0) {
                carryPt = trajectory[i];
                break;
            }
        }
        const carryYds = shotData.ogcCarry || Math.abs(carryPt.z);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : finalPt.x;

        if (record) {
            const entry = shotHistory.add(shotData, carryYds, offlineYds, opts.demo === true);
            if (entry) {
                selectedShotSeq = entry.seq;
                autoFollowDispersionClub(entry.club);
            }
        }

        updateHUDTelemetry(shotData, carryYds, offlineYds);
        renderShotList();

        // Clear the HUD for the flight. Only for genuinely new shots: a replay
        // is triggered by clicking the shot list, and hiding the list you just
        // clicked would be hostile.
        if (record) enterCinematic();

        cameraController.setLandingPosition(new THREE.Vector3(finalPt.x, 0.05, finalPt.z));
        ball.launch(trajectory, shotData.clubColor);
    }

    // 6. Realistic Shot Generator for Demo Shots
    function generateRealisticShotForDistance(targetYds) {
        let speed, vla, spin;
        if (targetYds <= 80) {
            speed = 54 + (targetYds - 50) * 0.45;
            vla = 30.0 - (targetYds - 50) * 0.1;
            spin = 8200 - (targetYds - 50) * 15;
        } else if (targetYds <= 130) {
            speed = 68 + (targetYds - 80) * 0.55;
            vla = 25.0 - (targetYds - 80) * 0.10;
            spin = 7200 - (targetYds - 80) * 20;
        } else if (targetYds <= 180) {
            speed = 92 + (targetYds - 130) * 0.48;
            vla = 20.5 - (targetYds - 130) * 0.08;
            spin = 6200 - (targetYds - 130) * 22;
        } else if (targetYds <= 240) {
            speed = 118 + (targetYds - 180) * 0.42;
            vla = 16.0 - (targetYds - 180) * 0.05;
            spin = 4600 - (targetYds - 180) * 18;
        } else {
            speed = 142 + (targetYds - 240) * 0.38;
            vla = 13.0 - Math.min(2.5, (targetYds - 240) * 0.03);
            spin = 3100 - Math.min(800, (targetYds - 240) * 10);
        }

        const demoHla = (Math.random() * 1.6 - 0.8);
        const demoClubPath = demoHla * 0.8 + (Math.random() * 0.6 - 0.3);
        const demoFaceAngle = demoHla * 0.5 + (Math.random() * 0.4 - 0.2);
        const demoSmash = 1.38 + Math.random() * 0.08;
        const demoClubSpeed = speed / demoSmash;
        const demoAttack = vla * 0.3 - 4.5;
        const demoDynLoft = vla * 0.85;
        const demoHangTime = (2.0 * Math.sin(vla * Math.PI / 180) * (speed * 0.44704) / 9.81);
        const demoClosure = Math.round(1800 + Math.abs(demoFaceAngle) * 320 + (demoClubSpeed * 12.5));

        return {
            shotId: `demo_${Date.now()}`,
            club: "7 Iron",
            clubColor: "#00E5FF",
            ballSpeed: speed + (Math.random() * 2.0 - 1.0),
            clubSpeed: demoClubSpeed,
            smash: demoSmash,
            closureRate: demoClosure,
            clubPath: demoClubPath,
            faceAngle: demoFaceAngle,
            attackAngle: demoAttack,
            dynamicLoft: demoDynLoft,
            hangTime: demoHangTime,
            verticalLaunchAngle: vla + (Math.random() * 0.8 - 0.4),
            horizontalLaunchAngle: demoHla,
            total_spin: spin + (Math.random() * 200 - 100),
            spin_axis: (Math.random() * 2.0 - 1.0),
            sidespin: (Math.random() * 120 - 60),
            backspin: spin,
            descent: 46.0 + Math.random() * 2.0,
            ogcCarry: null,
            ogcTotal: null,
            ogcOffline: null,
            apexFt: null
        };
    }

    // 7. Event Listeners
    //
    // Demo and replay are plain functions, not button proxies. The toolbar
    // buttons that used to own them are gone (demo moved into the shot list
    // header, replay lives on each shot row), so a keybind that called
    // someButton.click() would have silently gone inert.
    function fireDemoShot() {
        const demo = generateRealisticShotForDistance(currentTargetYards);
        // demo:true tags it as synthetic so it is excluded from averages,
        // dispersion sigma and trend stats.
        fireShot(demo, { demo: true });
    }

    /** Replay a recorded shot without appending a duplicate to history. */
    function replayShot(entry) {
        if (!entry) return;
        selectedShotSeq = entry.seq;
        renderShotList();
        drawMinimap();
        refreshDynamicWidgets();
        fireShot(entry.telemetry, { record: false });
    }

    /** Replay whatever row is selected, else the most recent shot. */
    function replaySelectedShot() {
        const entry = shotHistory.find(selectedShotSeq)
            || shotHistory.shots[shotHistory.shots.length - 1];
        replayShot(entry || null);
    }

    if (slDemoBtn) slDemoBtn.addEventListener('click', fireDemoShot);

    window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.code === 'Space') {
            e.preventDefault();
            fireDemoShot();
        } else if (e.key === 'r' || e.key === 'R') {
            replaySelectedShot();
        } else if (e.key === 'p' || e.key === 'P') {
            togglePressureTile();
        }
    });

    // 8. 2D Radar Minimap Renderer
    // Club filter for the dispersion plot: null = all clubs, else club name.
    // Defaults to the club you're currently hitting -- a carry sigma pooled
    // across a wedge and a driver describes nothing, so per-club is the only
    // view where the spread stats mean anything.
    let dispersionClub = null;
    let dispersionPinned = false;   // true once the user picks a club by hand

    function dispersionShots() {
        // Measured shots only: a demo shot is fabricated telemetry and would
        // distort the sigma ellipse and offline bias it is drawn from.
        const all = shotHistory.measured;
        if (!dispersionClub) return all;
        return all.filter(s => s.club === dispersionClub);
    }

    function drawMinimap() {
        if (!minimapCanvas) return;
        // Skip while the widget is hidden: a display:none canvas measures 0x0
        // and would clobber the backing store with an empty draw.
        if (!minimapCanvas.getClientRects().length) return;
        const shots = dispersionShots();
        const res = drawDispersion(minimapCanvas, shots, selectedShotSeq, currentTargetYards);

        if (dispersionFilterEl) {
            dispersionFilterEl.innerText = (dispersionClub || 'All clubs') + ' \u25be';
        }

        const st = res && res.stats;
        const fmtBias = (v) => `${Math.abs(v).toFixed(1)} ${v >= 0 ? 'R' : 'L'}`;
        if (dsCarry) dsCarry.innerText = st ? st.carryMean.toFixed(1) : '--';
        // A standard deviation needs a sample; below 3 shots it is noise, so
        // show it as unavailable rather than printing a meaningless number.
        if (dsCarrySd) dsCarrySd.innerText = (st && st.count >= 3) ? `\u00b1${st.carryStd.toFixed(1)}` : '--';
        if (dsOffline) dsOffline.innerText = st ? fmtBias(st.offlineMean) : '--';
    }

    if (dispersionFilterEl) {
        dispersionFilterEl.addEventListener('click', () => {
            // Cycle: each club seen this session -> All clubs -> back to first.
            const clubs = [...new Set(shotHistory.shots.map(s => s.club))];
            if (clubs.length === 0) return;
            const idx = dispersionClub === null ? -1 : clubs.indexOf(dispersionClub);
            dispersionClub = (idx + 1 >= clubs.length) ? null : clubs[idx + 1];
            dispersionPinned = true;
            drawMinimap();
        });
    }

    /** Follow the club being hit until the user picks one explicitly. */
    function autoFollowDispersionClub(club) {
        if (dispersionPinned || !club) return;
        dispersionClub = club;
    }

    window.addEventListener('resize', () => drawMinimap());

    // The dispersion canvas is sized by flexbox, so its pixel height changes
    // whenever another widget is shown/hidden and the rail re-shares space.
    // That reflow fires no window resize event, so observe the element itself
    // or the plot renders into a stale backing store.
    if (typeof ResizeObserver !== 'undefined' && minimapCanvas) {
        let rafId = null;
        const ro = new ResizeObserver(() => {
            if (rafId !== null) return;          // coalesce bursts into one redraw
            rafId = requestAnimationFrame(() => {
                rafId = null;
                drawMinimap();
            });
        });
        ro.observe(minimapCanvas);
    }

    drawMinimap();

    // ------------------------------------------------------------------
    // Rail widget manager ("+ Add Widget")
    // ------------------------------------------------------------------
    // Widgets share the rail height equally, so past a point each slice is too
    // short to read. Cap the count rather than letting the user shrink the rail
    // into unusable slivers.
    const MAX_RAIL_WIDGETS = 4;

    const rightRail = document.getElementById('right-rail');
    const addWidgetBtn = document.getElementById('add-widget');
    const widgetMenu = document.getElementById('widget-menu');
    const wmList = document.getElementById('wm-list');

    // key -> {el, def, canvas?, host?, ro?}
    const activeWidgets = new Map();

    function isWidgetActive(key) {
        const def = WIDGET_REGISTRY[key];
        if (!def) return false;
        if (def.fixed) {
            const el = document.getElementById(def.element);
            return !!el && getComputedStyle(el).display !== 'none';
        }
        return activeWidgets.has(key);
    }

    function activeWidgetCount() {
        return Object.keys(WIDGET_REGISTRY).filter(isWidgetActive).length;
    }

    /** Redraw one dynamic widget from current session state. */
    function refreshWidget(key) {
        const rec = activeWidgets.get(key);
        if (!rec) return;
        const ctx = {
            // Widgets plot statistics, so they see measured shots only.
            shots: shotHistory.measured,
            history: shotHistory,
            selectedSeq: selectedShotSeq,
            targetYards: currentTargetYards,
        };
        try {
            if (rec.def.kind === 'canvas' && rec.canvas) rec.def.draw(rec.canvas, ctx);
            else if (rec.def.kind === 'dom' && rec.host) rec.def.render(rec.host, ctx);
        } catch (err) {
            console.warn(`[!] widget "${key}" failed to render`, err);
        }
    }

    function refreshDynamicWidgets() {
        for (const key of activeWidgets.keys()) refreshWidget(key);
    }

    function addWidget(key) {
        const def = WIDGET_REGISTRY[key];
        if (!def || isWidgetActive(key)) return;
        if (activeWidgetCount() >= MAX_RAIL_WIDGETS) return;

        if (def.fixed) {
            // Already in the markup -- just reveal it.
            const el = document.getElementById(def.element);
            if (el) el.style.display = 'flex';
            if (key === 'dispersion') {
                // Canvas was 0x0 while hidden; redraw once it has a box.
                requestAnimationFrame(() => drawMinimap());
            }
            renderWidgetMenu();
            updateAddButtonState();
            return;
        }

        const el = document.createElement('div');
        el.className = 'widget glass';
        el.dataset.widget = key;

        const head = document.createElement('div');
        head.className = 'widget-head';
        const title = document.createElement('div');
        title.className = 'widget-title';
        title.textContent = def.title;
        const close = document.createElement('button');
        close.className = 'widget-close';
        close.type = 'button';
        close.textContent = '\u2715';
        close.title = 'Remove widget';
        close.addEventListener('click', () => removeWidget(key));
        head.appendChild(title);
        head.appendChild(close);
        el.appendChild(head);

        const rec = { el, def };

        if (def.kind === 'canvas') {
            const canvas = document.createElement('canvas');
            canvas.className = 'widget-canvas';
            el.appendChild(canvas);
            rec.canvas = canvas;
            // Flex reflow fires no window resize, so watch the element itself
            // or the plot draws into a stale backing store.
            if (typeof ResizeObserver !== 'undefined') {
                let raf = null;
                rec.ro = new ResizeObserver(() => {
                    if (raf !== null) return;
                    raf = requestAnimationFrame(() => { raf = null; refreshWidget(key); });
                });
                rec.ro.observe(canvas);
            }
        } else {
            const host = document.createElement('div');
            host.className = 'widget-body';
            el.appendChild(host);
            rec.host = host;
        }

        rightRail.insertBefore(el, addWidgetBtn);
        activeWidgets.set(key, rec);
        refreshWidget(key);
        renderWidgetMenu();
        updateAddButtonState();
    }

    function removeWidget(key) {
        const def = WIDGET_REGISTRY[key];
        if (!def) return;

        if (def.fixed) {
            const el = document.getElementById(def.element);
            if (el) el.style.display = 'none';
        } else {
            const rec = activeWidgets.get(key);
            if (rec) {
                if (rec.ro) rec.ro.disconnect();
                rec.el.remove();
                activeWidgets.delete(key);
            }
        }
        renderWidgetMenu();
        updateAddButtonState();
    }

    function updateAddButtonState() {
        if (!addWidgetBtn) return;
        const full = activeWidgetCount() >= MAX_RAIL_WIDGETS;
        addWidgetBtn.classList.toggle('disabled', full);
        addWidgetBtn.title = full
            ? `Rail is full (${MAX_RAIL_WIDGETS} widgets max) \u2014 remove one first`
            : 'Add a widget to the rail';
    }

    function renderWidgetMenu() {
        if (!wmList) return;
        const full = activeWidgetCount() >= MAX_RAIL_WIDGETS;
        wmList.innerHTML = '';
        for (const [key, def] of Object.entries(WIDGET_REGISTRY)) {
            const on = isWidgetActive(key);
            const blocked = !on && full;
            const item = document.createElement('div');
            item.className = 'wm-item' + (on || blocked ? ' added' : '');
            item.dataset.widget = key;
            item.innerHTML = `<div class="wm-title"><span>${def.title}</span>`
                + `<span class="tag">${on ? 'Added' : (blocked ? 'Rail full' : '')}</span></div>`
                + `<div class="wm-desc">${def.desc}</div>`;
            if (!on && !blocked) {
                item.addEventListener('click', () => {
                    addWidget(key);
                    closeWidgetMenu();
                });
            }
            wmList.appendChild(item);
        }
    }

    function openWidgetMenu() {
        if (!widgetMenu) return;
        renderWidgetMenu();
        widgetMenu.classList.add('open');
    }
    function closeWidgetMenu() {
        if (widgetMenu) widgetMenu.classList.remove('open');
    }

    if (addWidgetBtn) {
        addWidgetBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (addWidgetBtn.classList.contains('disabled')) return;
            if (widgetMenu.classList.contains('open')) closeWidgetMenu();
            else openWidgetMenu();
        });
    }
    document.addEventListener('click', (e) => {
        if (!widgetMenu || !widgetMenu.classList.contains('open')) return;
        if (widgetMenu.contains(e.target)) return;
        if (addWidgetBtn && addWidgetBtn.contains(e.target)) return;
        closeWidgetMenu();
    }, true);   // capture phase: runs before the button's own handler, so a
                // click on the button never opens-then-immediately-closes
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeWidgetMenu();
    });

    updateAddButtonState();
    renderWidgetMenu();

    // Apply the saved HUD scale now that every panel and widget exists, so the
    // canvas-backed widgets redraw at the right size on first paint.
    applyHudScale(hudScalePct, { persist: false });

    const btnCloseDispersion = document.getElementById('btn-close-dispersion');
    if (btnCloseDispersion) {
        btnCloseDispersion.addEventListener('click', (e) => {
            e.stopPropagation();   // don't trip the club-filter cycle
            removeWidget('dispersion');
        });
    }

    // 9. WebSocket Connection (Port 9321)
    function connectWS() {
        let wsUrl;
        if (window.location.protocol === 'file:') {
            wsUrl = 'ws://localhost:9321';
        } else {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            wsUrl = `${protocol}//${window.location.host || 'localhost:9321'}`;
        }

        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('[✓] Connected to Shanktuary WebSocket server');
            if (lmStatusText) setLmStatus('Nova Connected', true);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'shot') {
                    const parsed = extractShotTelemetry(msg);
                    if (parsed) fireShot(parsed);
                } else if (msg.type === 'pressure' && msg.data) {
                    const p = msg.data;
                    pressureRenderer.pushSample(p);
                    if (rangePressureTile && rangePressureTile.style.display !== 'none') {
                        if (hudPressurePhase) {
                            hudPressurePhase.innerText = (p.phase || 'ADDRESS')
                                .toUpperCase().replace(/_/g, ' ');
                        }
                        if (hudPctLeft) hudPctLeft.innerText = `${Math.round(p.pct_left || 50)}% L`;
                        if (hudPctRight) hudPctRight.innerText = `${Math.round(p.pct_right || 50)}% R`;
                        if (hudBarFillLeft) hudBarFillLeft.style.width = `${p.pct_left || 50}%`;
                        if (rangeHeatmapCanvas) pressureRenderer.renderHeatmap(rangeHeatmapCanvas, p);
                        if (rangeCopCanvas) pressureRenderer.renderCOPDot(rangeCopCanvas, p);
                    }
                } else if (msg.type === 'init' && msg.data) {
                    const parsed = extractShotTelemetry(msg.data);
                    if (parsed) {
                        lastShotTelemetry = parsed;
                        lastShotId = parsed.shotId;
                        updateHUDTelemetry(parsed);
                    }
                }
            } catch (err) {
                console.error('[!] WebSocket JSON parse error:', err);
            }
        };

        ws.onerror = (e) => console.warn('[!] Range WebSocket error', e);

        ws.onclose = () => {
            if (lmStatusText) setLmStatus('Reconnecting...', false);
            setTimeout(connectWS, 2000);
        };
    }

    // 10. HTTP Fallback Poller
    // First successful poll only ESTABLISHES the baseline shotId — it must
    // never fire. Otherwise a page load (or OBS scene switch) replays the
    // previous session's stored shot as if it were just hit.
    let pollBaselined = false;
    async function pollShotAPI() {
        try {
            const res = await fetch('/api/shot');
            if (res.ok) {
                const data = await res.json();
                if (data && Object.keys(data).length > 0) {
                    const parsed = extractShotTelemetry(data);
                    if (parsed && parsed.shotId) {
                        if (!pollBaselined) {
                            pollBaselined = true;
                            if (lastShotId === null || lastShotId === undefined) {
                                lastShotId = parsed.shotId;
                            }
                            return;
                        }
                        if (parsed.shotId !== lastShotId) {
                            fireShot(parsed);
                        }
                    }
                } else {
                    // Empty response still proves the server is reachable —
                    // safe to treat subsequent changes as fresh shots.
                    pollBaselined = true;
                }
            }
        } catch (e) {
            // Ignore fetch poll errors
        }
    }
    setInterval(pollShotAPI, 2500);

    connectWS();
}

