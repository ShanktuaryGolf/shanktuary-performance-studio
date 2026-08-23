// WebSocket Telemetry, Proximity & Live Nova / OpenGolfCoach Real Shot Handler

import { setTargetDistance } from './environment.js';

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    const telemetryDiv = document.getElementById('telemetry-data');
    const demoBtn = document.getElementById('btn-demo-shot');
    const replayBtn = document.getElementById('btn-replay-shot');
    const statusBadge = document.getElementById('ws-status-badge');
    const targetInput = document.getElementById('target-dist-input');
    const presetBtns = document.querySelectorAll('.preset-btn');
    
    const btnMinus10 = document.getElementById('btn-step-minus-10');
    const btnMinus5 = document.getElementById('btn-step-minus-5');
    const btnPlus5 = document.getElementById('btn-step-plus-5');
    const btnPlus10 = document.getElementById('btn-step-plus-10');
    
    let currentTargetYards = 150;
    let lastShotTelemetry = null;
    let lastShotId = null;
    
    const savedDist = localStorage.getItem('sps_range_target_dist');
    if (savedDist) {
        currentTargetYards = parseInt(savedDist, 10);
        if (targetInput) targetInput.value = currentTargetYards;
        setTargetDistance(currentTargetYards);
    }
    
    function updateTarget(newYards) {
        if (isNaN(newYards) || newYards <= 0) return;
        currentTargetYards = Math.max(30, Math.min(500, Math.round(newYards)));
        if (targetInput && document.activeElement !== targetInput) {
            targetInput.value = currentTargetYards;
        }
        setTargetDistance(currentTargetYards);
        localStorage.setItem('sps_range_target_dist', currentTargetYards);
    }
    
    if (targetInput) {
        targetInput.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val) && val >= 30 && val <= 500) {
                setTargetDistance(val);
                currentTargetYards = val;
                localStorage.setItem('sps_range_target_dist', currentTargetYards);
            }
        });
        
        targetInput.addEventListener('change', (e) => {
            updateTarget(parseFloat(e.target.value));
        });
        
        targetInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                updateTarget(parseFloat(targetInput.value));
                targetInput.blur();
            }
        });
    }
    
    if (btnMinus10) btnMinus10.addEventListener('click', () => updateTarget(currentTargetYards - 10));
    if (btnMinus5) btnMinus5.addEventListener('click', () => updateTarget(currentTargetYards - 5));
    if (btnPlus5) btnPlus5.addEventListener('click', () => updateTarget(currentTargetYards + 5));
    if (btnPlus10) btnPlus10.addEventListener('click', () => updateTarget(currentTargetYards + 10));
    
    presetBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const yds = parseInt(e.target.getAttribute('data-yds'), 10);
            updateTarget(yds);
        });
    });
    
    window.addEventListener('keydown', (e) => {
        if (document.activeElement === targetInput) return;
        if (e.key === 'ArrowLeft') {
            updateTarget(currentTargetYards - 5);
        } else if (e.key === 'ArrowRight') {
            updateTarget(currentTargetYards + 5);
        } else if (e.key === 'ArrowUp') {
            updateTarget(currentTargetYards + 10);
        } else if (e.key === 'ArrowDown') {
            updateTarget(currentTargetYards - 10);
        }
    });

    // Extract exact native OpenLaunch Nova & OpenGolfCoach telemetry
    function extractShotTelemetry(msg) {
        if (!msg) return null;
        
        const raw = msg.data || msg.shot || msg;
        if (!raw || typeof raw !== 'object') return null;
        
        const ogc = raw.open_golf_coach || (raw.shot && raw.shot.open_golf_coach) || {};
        const us = ogc.us_customary_units || raw.us_units || (raw.shot && raw.shot.us_units) || {};
        
        // 1. Ball Speed (MPH)
        let ballSpeed = 0.0;
        if (us.ball_speed_mph !== undefined && us.ball_speed_mph !== null) {
            ballSpeed = parseFloat(us.ball_speed_mph);
        } else if (raw.ball_speed_meters_per_second !== undefined && raw.ball_speed_meters_per_second !== null) {
            ballSpeed = parseFloat(raw.ball_speed_meters_per_second) * 2.236936;
        } else if (raw.ball_speed_mph !== undefined && raw.ball_speed_mph !== null) {
            ballSpeed = parseFloat(raw.ball_speed_mph);
        } else if (raw.ball_speed !== undefined && raw.ball_speed !== null) {
            ballSpeed = parseFloat(raw.ball_speed);
        } else if (raw.ballSpeed !== undefined && raw.ballSpeed !== null) {
            ballSpeed = parseFloat(raw.ballSpeed);
        }
        
        if (isNaN(ballSpeed) || ballSpeed < 5.0) {
            return null; // Ignore invalid / zero shots
        }
        
        // 2. Vertical Launch Angle (Degrees)
        let vla = 14.0;
        if (raw.vertical_launch_angle_degrees !== undefined && raw.vertical_launch_angle_degrees !== null) {
            vla = parseFloat(raw.vertical_launch_angle_degrees);
        } else if (us.vert_launch_angle_deg !== undefined && us.vert_launch_angle_deg !== null) {
            vla = parseFloat(us.vert_launch_angle_deg);
        } else if (raw.launch_angle !== undefined && raw.launch_angle !== null) {
            vla = parseFloat(raw.launch_angle);
        } else if (raw.vla !== undefined && raw.vla !== null) {
            vla = parseFloat(raw.vla);
        } else if (raw.verticalLaunchAngle !== undefined && raw.verticalLaunchAngle !== null) {
            vla = parseFloat(raw.verticalLaunchAngle);
        }
        
        // 3. Horizontal Launch Angle (Degrees)
        let hla = 0.0;
        if (raw.horizontal_launch_angle_degrees !== undefined && raw.horizontal_launch_angle_degrees !== null) {
            hla = parseFloat(raw.horizontal_launch_angle_degrees);
        } else if (us.horiz_launch_angle_deg !== undefined && us.horiz_launch_angle_deg !== null) {
            hla = parseFloat(us.horiz_launch_angle_deg);
        } else if (raw.hla !== undefined && raw.hla !== null) {
            hla = parseFloat(raw.hla);
        } else if (raw.horizontalLaunchAngle !== undefined && raw.horizontalLaunchAngle !== null) {
            hla = parseFloat(raw.horizontalLaunchAngle);
        }
        
        // 4. Total Spin (RPM)
        let totalSpin = 3000.0;
        if (raw.total_spin_rpm !== undefined && raw.total_spin_rpm !== null) {
            totalSpin = parseFloat(raw.total_spin_rpm);
        } else if (ogc.total_spin_rpm !== undefined && ogc.total_spin_rpm !== null) {
            totalSpin = parseFloat(ogc.total_spin_rpm);
        } else if (us.total_spin_rpm !== undefined && us.total_spin_rpm !== null) {
            totalSpin = parseFloat(us.total_spin_rpm);
        } else if (raw.total_spin !== undefined && raw.total_spin !== null) {
            totalSpin = parseFloat(raw.total_spin);
        } else if (raw.spinSpeed !== undefined && raw.spinSpeed !== null) {
            totalSpin = parseFloat(raw.spinSpeed);
        }
        
        // 5. Spin Axis (Degrees)
        let spinAxis = 0.0;
        if (raw.spin_axis_degrees !== undefined && raw.spin_axis_degrees !== null) {
            spinAxis = parseFloat(raw.spin_axis_degrees);
        } else if (ogc.spin_axis_degrees !== undefined && ogc.spin_axis_degrees !== null) {
            spinAxis = parseFloat(ogc.spin_axis_degrees);
        } else if (us.spin_axis_deg !== undefined && us.spin_axis_deg !== null) {
            spinAxis = parseFloat(us.spin_axis_deg);
        } else if (raw.spin_axis !== undefined && raw.spin_axis !== null) {
            spinAxis = parseFloat(raw.spin_axis);
        } else if (raw.spinAxis !== undefined && raw.spinAxis !== null) {
            spinAxis = parseFloat(raw.spinAxis);
        }
        
        // 6. Carry & Offline
        let carryYds = null;
        if (us.carry_distance_yards !== undefined && us.carry_distance_yards !== null) {
            carryYds = parseFloat(us.carry_distance_yards);
        } else if (raw.carry !== undefined && raw.carry !== null) {
            carryYds = parseFloat(raw.carry);
        } else if (ogc.carry_distance_meters !== undefined && ogc.carry_distance_meters !== null) {
            carryYds = parseFloat(ogc.carry_distance_meters) * 1.09361;
        }

        let offlineYds = null;
        if (us.offline_distance_yards !== undefined && us.offline_distance_yards !== null) {
            offlineYds = parseFloat(us.offline_distance_yards);
        } else if (raw.offline !== undefined && raw.offline !== null) {
            offlineYds = parseFloat(raw.offline);
        } else if (ogc.offline_distance_meters !== undefined && ogc.offline_distance_meters !== null) {
            offlineYds = parseFloat(ogc.offline_distance_meters) * 1.09361;
        }
        
        const shotClub = raw.club || ogc.club || "Club";
        const shotId = raw.shot_number || raw.timestamp || raw.id || `${ballSpeed.toFixed(1)}_${vla.toFixed(1)}_${totalSpin.toFixed(0)}`;

        return {
            shotId,
            club: shotClub,
            ballSpeed,
            verticalLaunchAngle: vla,
            horizontalLaunchAngle: hla,
            total_spin: totalSpin,
            spin_axis: spinAxis,
            ogcCarry: carryYds,
            ogcOffline: offlineYds
        };
    }

    function updateHUDTelemetry(shotData, simulatedCarry = null, simulatedOffline = null) {
        if (!shotData || !telemetryDiv) return;
        
        const carryYds = shotData.ogcCarry || simulatedCarry || 0.0;
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : (simulatedOffline || 0.0);
        const offlineDir = offlineYds >= 0 ? "R" : "L";
        
        const dx = offlineYds;
        const dz = carryYds - currentTargetYards;
        const distToPinYds = Math.sqrt(dx * dx + dz * dz);
        const onGreen = distToPinYds <= 10.0;
        
        const pinFeedback = onGreen 
            ? `⛳ GREEN HIT! (${distToPinYds.toFixed(1)} yds to pin)` 
            : `🎯 Pin Delta: ${distToPinYds.toFixed(1)} yds (${dz >= 0 ? '+' : ''}${dz.toFixed(1)}y)`;
        
        telemetryDiv.innerHTML = `Club: ${shotData.club || '7 Iron'}  •  Ball Speed: ${shotData.ballSpeed.toFixed(1)} mph\n` +
                                 `Launch: ${shotData.verticalLaunchAngle.toFixed(1)}° (H: ${shotData.horizontalLaunchAngle >= 0 ? '+' : ''}${shotData.horizontalLaunchAngle.toFixed(1)}°)\n` +
                                 `Spin: ${Math.round(shotData.total_spin)} rpm (Axis: ${shotData.spin_axis.toFixed(1)}°)\n` +
                                 `Carry: ${carryYds.toFixed(1)} yds (${Math.abs(offlineYds).toFixed(1)}y ${offlineDir})\n` +
                                 `${pinFeedback}`;
                                 
        if (replayBtn) {
            replayBtn.style.display = 'inline-block';
        }
    }

    function fireShot(shotData) {
        if (!shotData) return;
        
        console.log('[+] Live Nova Shot Received:', shotData);
        lastShotTelemetry = shotData;
        lastShotId = shotData.shotId;
        
        const trajectory = physicsEngine.calculateTrajectory(shotData);
        
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = shotData.ogcCarry || Math.abs(finalPt.z);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : finalPt.x;
        
        updateHUDTelemetry(shotData, carryYds, offlineYds);
        
        cameraController.setLandingPosition(new THREE.Vector3(finalPt.x, 0.05, finalPt.z));
        ball.launch(trajectory);
    }
    
    function generateRealisticShotForDistance(targetYds) {
        let speed, vla, spin;
        
        if (targetYds <= 80) {
            speed = 52 + (targetYds - 50) * 0.45;
            vla = 30.0 - (targetYds - 50) * 0.1;
            spin = 8200 - (targetYds - 50) * 15;
        } else if (targetYds <= 120) {
            speed = 65 + (targetYds - 80) * 0.55;
            vla = 26.0 - (targetYds - 80) * 0.12;
            spin = 7500 - (targetYds - 80) * 20;
        } else if (targetYds <= 170) {
            speed = 88 + (targetYds - 120) * 0.52;
            vla = 21.0 - (targetYds - 120) * 0.09;
            spin = 6400 - (targetYds - 120) * 25;
        } else if (targetYds <= 220) {
            speed = 114 + (targetYds - 170) * 0.45;
            vla = 16.5 - (targetYds - 170) * 0.06;
            spin = 4800 - (targetYds - 170) * 20;
        } else {
            speed = 138 + (targetYds - 220) * 0.40;
            vla = 13.5 - Math.min(3.0, (targetYds - 220) * 0.03);
            spin = 3200 - Math.min(1000, (targetYds - 220) * 10);
        }
        
        return {
            shotId: `demo_${Date.now()}`,
            club: "Demo Club",
            ballSpeed: speed + (Math.random() * 2.0 - 1.0),
            verticalLaunchAngle: vla + (Math.random() * 1.0 - 0.5),
            horizontalLaunchAngle: (Math.random() * 2.0 - 1.0),
            total_spin: spin + (Math.random() * 200 - 100),
            spin_axis: (Math.random() * 2.0 - 1.0),
            ogcCarry: null,
            ogcOffline: null
        };
    }
    
    // Demo Shot Button
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            const demoShot = generateRealisticShotForDistance(currentTargetYards);
            fireShot(demoShot);
        });
    }
    
    // Replay Last Shot Button
    if (replayBtn) {
        replayBtn.addEventListener('click', () => {
            if (lastShotTelemetry) {
                fireShot(lastShotTelemetry);
            }
        });
    }
    
    window.addEventListener('keydown', (e) => {
        if (document.activeElement === targetInput) return;
        if (e.code === 'Space') {
            if (demoBtn) demoBtn.click();
        } else if (e.key === 'r' || e.key === 'R') {
            if (replayBtn && lastShotTelemetry) replayBtn.click();
        }
    });
    
    // Connect to WebSocket Server on Port 9321
    function connectWS() {
        let wsUrl;
        if (window.location.protocol === 'file:') {
            wsUrl = 'ws://localhost:9321';
        } else {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            wsUrl = `${protocol}//${window.location.host || 'localhost:9321'}`;
        }
        
        console.log('[+] Connecting to WebSocket:', wsUrl);
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('[✓] Connected to Shanktuary WebSocket server');
            if (statusBadge) {
                statusBadge.innerText = '● Live';
                statusBadge.style.color = '#00FF66';
                statusBadge.style.borderColor = '#00FF66';
                statusBadge.style.background = 'rgba(0,255,102,0.15)';
            }
        };
        
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log('[+] Received WebSocket message type:', msg.type);
                
                if (msg.type === 'shot') {
                    const parsed = extractShotTelemetry(msg);
                    if (parsed) {
                        fireShot(parsed);
                    }
                } else if (msg.type === 'init' && msg.data) {
                    console.log('[+] Processing init shot data:', msg.data);
                    const parsed = extractShotTelemetry(msg.data);
                    if (parsed) {
                        lastShotTelemetry = parsed;
                        lastShotId = parsed.shotId;
                        updateHUDTelemetry(parsed);
                    }
                }
            } catch (err) {
                console.error('[!] Error parsing WebSocket message:', err);
            }
        };
        
        ws.onclose = () => {
            console.log('[!] WebSocket disconnected, reconnecting in 2s...');
            if (statusBadge) {
                statusBadge.innerText = '○ Offline (reconnecting)';
                statusBadge.style.color = '#FFD600';
                statusBadge.style.borderColor = '#FFD600';
                statusBadge.style.background = 'rgba(255,214,0,0.15)';
            }
            setTimeout(connectWS, 2000);
        };
    }
    
    // HTTP Fallback Polling in case WebSockets are blocked
    async function pollShotAPI() {
        try {
            const res = await fetch('/api/shot');
            if (res.ok) {
                const data = await res.json();
                if (data && Object.keys(data).length > 0) {
                    const parsed = extractShotTelemetry(data);
                    if (parsed && parsed.shotId && parsed.shotId !== lastShotId) {
                        console.log('[+] HTTP Poll detected new shot:', parsed);
                        fireShot(parsed);
                    }
                }
            }
        } catch (e) {
            // Ignore fetch errors during polling
        }
    }
    setInterval(pollShotAPI, 2500);
    
    connectWS();
}
