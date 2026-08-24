// WebSocket Telemetry, Proximity, Real-time Fairway Width Slider & Minimap Radar

import { setTargetDistance } from './environment.js';
import { setFairwayWidth, getFairwayWidth } from './foliage.js';
import { PressureTileRenderer } from './pressure_tiles.js';

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    // 1. DOM Elements
    const btnStudioMenu = document.getElementById('btn-studio-menu');
    const btnSettingsToggle = document.getElementById('btn-settings-toggle');
    const settingsDrawer = document.getElementById('settings-drawer');
    const btnGameModes = document.getElementById('btn-game-modes');
    const gameModesDrawer = document.getElementById('game-modes-drawer');
    const btnCloseGameModes = document.getElementById('btn-close-game-modes');
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
    
    const demoBtn = document.getElementById('btn-demo-shot');
    const replayBtn = document.getElementById('btn-replay-shot');
    const lmStatusText = document.getElementById('lm-status-text');
    const hudClubName = document.getElementById('hud-club-name');

    // Telemetry Left Stack
    const elBallSpeed = document.getElementById('tele-ball-speed');
    const elClubSpeed = document.getElementById('tele-club-speed');
    const elSmash = document.getElementById('tele-smash');
    const elCarry = document.getElementById('tele-carry');
    const elTotal = document.getElementById('tele-total');
    const elLaunch = document.getElementById('tele-launch');
    const elHla = document.getElementById('tele-hla');
    const elClosureRate = document.getElementById('tele-closure-rate');
    const elClubPath = document.getElementById('tele-club-path');
    const elFaceAngle = document.getElementById('tele-face-angle');
    const elAttackAngle = document.getElementById('tele-attack-angle');
    const elDynamicLoft = document.getElementById('tele-dynamic-loft');
    const elBackspin = document.getElementById('tele-backspin');
    const elSidespin = document.getElementById('tele-sidespin');
    const elOffline = document.getElementById('tele-offline');
    const elApex = document.getElementById('tele-apex');
    const elDescent = document.getElementById('tele-descent');
    const elHangTime = document.getElementById('tele-hang-time');

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
    const btnPressureToggle = document.getElementById('btn-pressure-toggle');
    const rangePressureTile = document.getElementById('range-pressure-tile');
    const btnClosePressureTile = document.getElementById('btn-close-pressure-tile');
    const hudPressurePhase = document.getElementById('hud-pressure-phase');
    const hudPctLeft = document.getElementById('hud-pct-left');
    const hudPctRight = document.getElementById('hud-pct-right');
    const hudBarFillLeft = document.getElementById('hud-bar-fill-left');
    const rangeHeatmapCanvas = document.getElementById('range-heatmap-canvas');
    const rangeCopCanvas = document.getElementById('range-cop-canvas');
    const pressureRenderer = new PressureTileRenderer();

    // Radar Minimap
    const minimapCanvas = document.getElementById('minimap-canvas');
    const minimapCtx = minimapCanvas ? minimapCanvas.getContext('2d') : null;

    function togglePressureTile() {
        if (!rangePressureTile) return;
        const isHidden = rangePressureTile.style.display === 'none' || !rangePressureTile.style.display;
        rangePressureTile.style.display = isHidden ? 'flex' : 'none';
        if (btnPressureToggle) {
            btnPressureToggle.classList.toggle('active', isHidden);
        }
    }

    if (btnPressureToggle) btnPressureToggle.addEventListener('click', togglePressureTile);
    if (btnClosePressureTile) btnClosePressureTile.addEventListener('click', () => {
        if (rangePressureTile) rangePressureTile.style.display = 'none';
        if (btnPressureToggle) btnPressureToggle.classList.remove('active');
    });

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
            if (rangeModeTitle) rangeModeTitle.innerText = '⛳ DRIVING RANGE';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'block';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'block';
            if (challengePtsContainer) challengePtsContainer.style.display = 'none';
            if (challengeProxContainer) challengeProxContainer.style.display = 'none';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
        } else if (mode === 'ladder') {
            ladderLevel = 1;
            ladderStreak = 0;
            updateTarget(20);
            if (rangeModeTitle) rangeModeTitle.innerText = '🪜 LADDER CHALLENGE';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'block';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'block';
            if (practiceLastCarry) practiceLastCarry.innerText = 'LEVEL 1';
            if (practiceLastOffline) practiceLastOffline.innerText = '0 STREAK';
            if (challengePtsContainer) challengePtsContainer.style.display = 'none';
            if (challengeProxContainer) challengeProxContainer.style.display = 'none';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
            showBanner('🪜', 'DISTANCE LADDER CHALLENGE', 'Target starts at 20 yds. Hit the green to move back 10-20 yds!');
        } else if (mode === 'challenge') {
            if (rangeModeTitle) rangeModeTitle.innerText = '🎯 TARGET CHALLENGE';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'none';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'none';
            if (challengePtsContainer) challengePtsContainer.style.display = 'block';
            if (challengeProxContainer) challengeProxContainer.style.display = 'block';
            if (targetScoringLegend) targetScoringLegend.style.display = 'flex';
        } else if (mode === 'closest-pin') {
            if (rangeModeTitle) rangeModeTitle.innerText = '📍 CLOSEST TO PIN';
            if (practiceCarryContainer) practiceCarryContainer.style.display = 'none';
            if (practiceOfflineContainer) practiceOfflineContainer.style.display = 'none';
            if (challengePtsContainer) challengePtsContainer.style.display = 'block';
            if (challengeProxContainer) challengeProxContainer.style.display = 'block';
            if (targetScoringLegend) targetScoringLegend.style.display = 'none';
        } else if (mode === 'long-drive') {
            if (rangeModeTitle) rangeModeTitle.innerText = '💥 LONG DRIVE';
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
            if (settingsDrawer && !settingsDrawer.classList.contains('open')) {
                if (gameModesDrawer) gameModesDrawer.classList.remove('open');
                if (btnGameModes) btnGameModes.classList.remove('active');
                settingsDrawer.classList.add('open');
                if (btnSettingsToggle) btnSettingsToggle.classList.add('active');
            }
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
    if (btnGameModes && gameModesDrawer) {
        btnGameModes.addEventListener('click', () => {
            if (settingsDrawer) {
                settingsDrawer.classList.remove('open');
                if (btnSettingsToggle) btnSettingsToggle.classList.remove('active');
            }
            gameModesDrawer.classList.toggle('open');
            btnGameModes.classList.toggle('active', gameModesDrawer.classList.contains('open'));
        });
    }

    if (btnCloseGameModes && gameModesDrawer) {
        btnCloseGameModes.addEventListener('click', () => {
            gameModesDrawer.classList.remove('open');
            if (btnGameModes) btnGameModes.classList.remove('active');
        });
    }

    if (btnSettingsToggle && settingsDrawer) {
        btnSettingsToggle.addEventListener('click', () => {
            if (gameModesDrawer) {
                gameModesDrawer.classList.remove('open');
                if (btnGameModes) btnGameModes.classList.remove('active');
            }
            settingsDrawer.classList.toggle('open');
            btnSettingsToggle.classList.toggle('active', settingsDrawer.classList.contains('open'));
        });
    }

    gameModeCards.forEach(card => {
        card.addEventListener('click', () => {
            const mode = card.getAttribute('data-mode');
            setGameMode(mode);
            if (gameModesDrawer) gameModesDrawer.classList.remove('open');
            if (btnGameModes) btnGameModes.classList.remove('active');
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
            if (btnGameModes) btnGameModes.click();
        } else if (e.key === 's' || e.key === 'S') {
            if (btnSettingsToggle) btnSettingsToggle.click();
        }
    });

    // 5. Telemetry Extraction
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

        const clubPath = parseFloat(ogc.club_path_degrees?.right_handed || raw.club_path || raw.club_path_degrees || 0.0);
        const faceAngle = parseFloat(ogc.club_face_to_path_degrees?.right_handed || raw.face_to_path || raw.face_angle || 0.0);
        const attackAngle = parseFloat(ogc.angle_of_attack_degrees?.right_handed || raw.angle_of_attack_degrees || raw.attack_angle || (vla * 0.3 - 4.5));
        const dynamicLoft = parseFloat(ogc.dynamic_loft_degrees?.right_handed || raw.dynamic_loft_degrees || raw.dynamic_loft || (vla * 0.85));
        const hangTime = parseFloat(ogc.hang_time_seconds || raw.hang_time_seconds || raw.hang_time || (2.0 * Math.sin(vla * Math.PI / 180) * (ballSpeed * 0.44704) / 9.81));
        
        let closureRate = 0.0;
        if (ogc.face_closure_rate_dps !== undefined) closureRate = parseFloat(ogc.face_closure_rate_dps);
        else if (raw.face_closure_rate_dps !== undefined) closureRate = parseFloat(raw.face_closure_rate_dps);
        else if (raw.closure_rate !== undefined) closureRate = parseFloat(raw.closure_rate);
        else closureRate = Math.round(1800 + Math.abs(faceAngle) * 320 + (clubSpeed * 12.5));

        const shotClub = raw.club || ogc.club || "7 Iron";
        const clubColor = raw.club_color || ogc.club_color || null;
        const shotId = raw.shot_number || raw.timestamp || raw.id || `${ballSpeed.toFixed(1)}_${vla.toFixed(1)}_${totalSpin.toFixed(0)}`;

        return {
            shotId,
            club: shotClub,
            clubColor: clubColor,
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

    function updateHUDTelemetry(shotData, simulatedCarry = null, simulatedOffline = null) {
        if (!shotData) return;

        const carryYds = shotData.ogcCarry || simulatedCarry || 0.0;
        const totalYds = shotData.ogcTotal || (carryYds * 1.08);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : (simulatedOffline || 0.0);
        const apexFt = shotData.apexFt || (carryYds * 0.42 * 3.0);

        if (elBallSpeed) elBallSpeed.innerText = (typeof shotData.ballSpeed === 'number') ? shotData.ballSpeed.toFixed(1) : '--';
        if (elClubSpeed) elClubSpeed.innerText = (typeof shotData.clubSpeed === 'number') ? shotData.clubSpeed.toFixed(1) : '--';
        if (elSmash) elSmash.innerText = (typeof shotData.smash === 'number') ? shotData.smash.toFixed(2) : '--';
        if (elCarry) elCarry.innerText = (typeof carryYds === 'number') ? carryYds.toFixed(1) : '--';
        if (elTotal) elTotal.innerText = (typeof totalYds === 'number') ? totalYds.toFixed(1) : '--';
        if (elLaunch) elLaunch.innerText = (typeof shotData.verticalLaunchAngle === 'number') ? shotData.verticalLaunchAngle.toFixed(1) : '--';
        if (elHla) elHla.innerText = (typeof shotData.horizontalLaunchAngle === 'number') ? `${shotData.horizontalLaunchAngle >= 0 ? '+' : ''}${shotData.horizontalLaunchAngle.toFixed(1)}` : '--';
        if (elClosureRate) elClosureRate.innerText = shotData.closureRate ? Math.round(shotData.closureRate) : Math.round(1800 + (shotData.ballSpeed || 100) * 10);
        if (elClubPath) elClubPath.innerText = (typeof shotData.clubPath === 'number') ? `${shotData.clubPath >= 0 ? '+' : ''}${shotData.clubPath.toFixed(1)}°` : '--';
        if (elFaceAngle) elFaceAngle.innerText = (typeof shotData.faceAngle === 'number') ? `${shotData.faceAngle >= 0 ? '+' : ''}${shotData.faceAngle.toFixed(1)}°` : '--';
        if (elAttackAngle) elAttackAngle.innerText = (typeof shotData.attackAngle === 'number') ? `${shotData.attackAngle >= 0 ? '+' : ''}${shotData.attackAngle.toFixed(1)}°` : '--';
        if (elDynamicLoft) elDynamicLoft.innerText = (typeof shotData.dynamicLoft === 'number') ? `${shotData.dynamicLoft.toFixed(1)}°` : '--';
        if (elBackspin) elBackspin.innerText = Math.round(shotData.backspin || shotData.total_spin || 3000);
        if (elSidespin) elSidespin.innerText = Math.round(shotData.sidespin || 0);
        if (elOffline) elOffline.innerText = `${Math.abs(offlineYds).toFixed(1)} ${offlineYds >= 0 ? 'R' : 'L'}`;
        if (elApex) elApex.innerText = Math.round(apexFt);
        if (elDescent) elDescent.innerText = (typeof shotData.descent === 'number') ? `${shotData.descent.toFixed(1)}°` : '46.0°';
        if (elHangTime) elHangTime.innerText = (typeof shotData.hangTime === 'number') ? `${shotData.hangTime.toFixed(1)}` : '--';

        if (hudClubName) {
            hudClubName.innerText = shotData.club || '7 Iron';
            if (shotData.clubColor) hudClubName.style.color = shotData.clubColor;
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

        // Draw on Minimap
        drawMinimap();
    }

    function fireShot(shotData) {
        if (!shotData) return;
        lastShotTelemetry = shotData;
        lastShotId = shotData.shotId;

        const trajectory = physicsEngine.calculateTrajectory(shotData);
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = shotData.ogcCarry || Math.abs(finalPt.z);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : finalPt.x;

        updateHUDTelemetry(shotData, carryYds, offlineYds);

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
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            const demo = generateRealisticShotForDistance(currentTargetYards);
            fireShot(demo);
        });
    }

    if (replayBtn) {
        replayBtn.addEventListener('click', () => {
            if (lastShotTelemetry) fireShot(lastShotTelemetry);
        });
    }

    window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;
        if (e.code === 'Space') {
            e.preventDefault();
            if (demoBtn) demoBtn.click();
        } else if (e.key === 'r' || e.key === 'R') {
            if (replayBtn && lastShotTelemetry) replayBtn.click();
        } else if (e.key === 'p' || e.key === 'P') {
            togglePressureTile();
        }
    });

    // 8. 2D Radar Minimap Renderer
    function drawMinimap() {
        if (!minimapCtx || !minimapCanvas) return;
        const w = minimapCanvas.width;
        const h = minimapCanvas.height;

        minimapCtx.clearRect(0, 0, w, h);

        // Fairway Background
        minimapCtx.fillStyle = '#13211a';
        minimapCtx.fillRect(0, 0, w, h);

        const maxRange = Math.max(380, currentTargetYards + 40);
        const toY = (yds) => h - 15 - (yds / maxRange) * (h - 30);
        const toX = (xYds) => w / 2 + (xYds / 120) * (w / 2);

        // Tree Boundaries (Left & Right Corridor)
        const halfFw = currentFairwayWidth / 2;
        const leftX = toX(-halfFw);
        const rightX = toX(+halfFw);

        minimapCtx.fillStyle = '#0a140e';
        minimapCtx.fillRect(0, 0, leftX, h);
        minimapCtx.fillRect(rightX, 0, w - rightX, h);

        minimapCtx.strokeStyle = '#22c55e';
        minimapCtx.lineWidth = 1;
        minimapCtx.beginPath();
        minimapCtx.moveTo(leftX, 0); minimapCtx.lineTo(leftX, h);
        minimapCtx.moveTo(rightX, 0); minimapCtx.lineTo(rightX, h);
        minimapCtx.stroke();

        // Fairway Dashed Centerline
        minimapCtx.strokeStyle = 'rgba(255,255,255,0.3)';
        minimapCtx.setLineDash([3, 3]);
        minimapCtx.beginPath();
        minimapCtx.moveTo(w / 2, h - 15);
        minimapCtx.lineTo(w / 2, 10);
        minimapCtx.stroke();
        minimapCtx.setLineDash([]);

        // Target Green (Clean Natural Putting Green + Center Pin)
        const tgtY = toY(currentTargetYards);
        const tgtX = w / 2;

        minimapCtx.beginPath();
        minimapCtx.arc(tgtX, tgtY, 10, 0, Math.PI * 2);
        minimapCtx.fillStyle = '#55a338';
        minimapCtx.fill();
        minimapCtx.strokeStyle = 'rgba(255,255,255,0.4)';
        minimapCtx.lineWidth = 1.0;
        minimapCtx.stroke();

        // Pin Hole Center
        minimapCtx.fillStyle = '#ffffff';
        minimapCtx.beginPath();
        minimapCtx.arc(tgtX, tgtY, 1.5, 0, Math.PI * 2);
        minimapCtx.fill();

        // Tee Box
        minimapCtx.fillStyle = '#4ade80';
        minimapCtx.beginPath();
        minimapCtx.arc(w / 2, h - 15, 3.5, 0, Math.PI * 2);
        minimapCtx.fill();

        // Last Shot Landing Marker & Flight Line
        if (lastLandingPt) {
            const landX = toX(lastLandingPt.x);
            const landY = toY(lastLandingPt.z);

            minimapCtx.strokeStyle = '#facc15';
            minimapCtx.lineWidth = 1.5;
            minimapCtx.beginPath();
            minimapCtx.moveTo(w / 2, h - 15);
            minimapCtx.lineTo(landX, landY);
            minimapCtx.stroke();

            minimapCtx.fillStyle = '#facc15';
            minimapCtx.beginPath();
            minimapCtx.arc(landX, landY, 4, 0, Math.PI * 2);
            minimapCtx.fill();
        }
    }

    drawMinimap();

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
            if (lmStatusText) lmStatusText.innerText = 'Nova Connected';
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
                            hudPressurePhase.innerText = (p.phase || 'ADDRESS').toUpperCase();
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

        ws.onclose = () => {
            if (lmStatusText) lmStatusText.innerText = 'Reconnecting...';
            setTimeout(connectWS, 2000);
        };
    }

    // 10. HTTP Fallback Poller
    async function pollShotAPI() {
        try {
            const res = await fetch('/api/shot');
            if (res.ok) {
                const data = await res.json();
                if (data && Object.keys(data).length > 0) {
                    const parsed = extractShotTelemetry(data);
                    if (parsed && parsed.shotId && parsed.shotId !== lastShotId) {
                        fireShot(parsed);
                    }
                }
            }
        } catch (e) {
            // Ignore fetch poll errors
        }
    }
    setInterval(pollShotAPI, 2500);

    connectWS();
}

