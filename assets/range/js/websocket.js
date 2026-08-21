// WebSocket Telemetry, Proximity & Live Nova / OpenGolfCoach Real Shot Handler

import { setTargetDistance } from './environment.js';

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    const telemetryDiv = document.getElementById('telemetry-data');
    const demoBtn = document.getElementById('btn-demo-shot');
    const targetInput = document.getElementById('target-dist-input');
    const presetBtns = document.querySelectorAll('.preset-btn');
    
    const btnMinus10 = document.getElementById('btn-step-minus-10');
    const btnMinus5 = document.getElementById('btn-step-minus-5');
    const btnPlus5 = document.getElementById('btn-step-plus-5');
    const btnPlus10 = document.getElementById('btn-step-plus-10');
    
    let currentTargetYards = 150;
    
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
        const ogc = raw.open_golf_coach || (raw.shot && raw.shot.open_golf_coach) || {};
        const us = ogc.us_customary_units || raw.us_units || (raw.shot && raw.shot.us_units) || {};
        
        // 1. Ball Speed (MPH)
        let ballSpeed = 0.0;
        if (us.ball_speed_mph) {
            ballSpeed = parseFloat(us.ball_speed_mph);
        } else if (raw.ball_speed_meters_per_second) {
            ballSpeed = parseFloat(raw.ball_speed_meters_per_second) * 2.236936;
        } else if (raw.ball_speed_mph) {
            ballSpeed = parseFloat(raw.ball_speed_mph);
        } else if (raw.ballSpeed) {
            ballSpeed = parseFloat(raw.ballSpeed);
        }
        
        if (isNaN(ballSpeed) || ballSpeed < 5.0) {
            return null; // Ignore invalid / zero shots
        }
        
        // 2. Vertical Launch Angle (Degrees)
        let vla = 14.0;
        if (raw.vertical_launch_angle_degrees !== undefined) {
            vla = parseFloat(raw.vertical_launch_angle_degrees);
        } else if (us.vert_launch_angle_deg !== undefined) {
            vla = parseFloat(us.vert_launch_angle_deg);
        } else if (raw.vla !== undefined) {
            vla = parseFloat(raw.vla);
        } else if (raw.verticalLaunchAngle !== undefined) {
            vla = parseFloat(raw.verticalLaunchAngle);
        }
        
        // 3. Horizontal Launch Angle (Degrees)
        let hla = 0.0;
        if (raw.horizontal_launch_angle_degrees !== undefined) {
            hla = parseFloat(raw.horizontal_launch_angle_degrees);
        } else if (us.horiz_launch_angle_deg !== undefined) {
            hla = parseFloat(us.horiz_launch_angle_deg);
        } else if (raw.hla !== undefined) {
            hla = parseFloat(raw.hla);
        } else if (raw.horizontalLaunchAngle !== undefined) {
            hla = parseFloat(raw.horizontalLaunchAngle);
        }
        
        // 4. Total Spin (RPM)
        let totalSpin = 3000.0;
        if (raw.total_spin_rpm !== undefined) {
            totalSpin = parseFloat(raw.total_spin_rpm);
        } else if (ogc.total_spin_rpm !== undefined) {
            totalSpin = parseFloat(ogc.total_spin_rpm);
        } else if (us.total_spin_rpm !== undefined) {
            totalSpin = parseFloat(us.total_spin_rpm);
        } else if (raw.total_spin !== undefined) {
            totalSpin = parseFloat(raw.total_spin);
        } else if (raw.spinSpeed !== undefined) {
            totalSpin = parseFloat(raw.spinSpeed);
        }
        
        // 5. Spin Axis (Degrees)
        let spinAxis = 0.0;
        if (raw.spin_axis_degrees !== undefined) {
            spinAxis = parseFloat(raw.spin_axis_degrees);
        } else if (ogc.spin_axis_degrees !== undefined) {
            spinAxis = parseFloat(ogc.spin_axis_degrees);
        } else if (us.spin_axis_deg !== undefined) {
            spinAxis = parseFloat(us.spin_axis_deg);
        } else if (raw.spin_axis !== undefined) {
            spinAxis = parseFloat(raw.spin_axis);
        } else if (raw.spinAxis !== undefined) {
            spinAxis = parseFloat(raw.spinAxis);
        }
        
        return {
            ballSpeed,
            verticalLaunchAngle: vla,
            horizontalLaunchAngle: hla,
            total_spin: totalSpin,
            spin_axis: spinAxis,
            ogcCarry: us.carry_distance_yards ? parseFloat(us.carry_distance_yards) : null,
            ogcOffline: us.offline_distance_yards ? parseFloat(us.offline_distance_yards) : null
        };
    }

    function fireShot(shotData) {
        if (!shotData) return;
        
        console.log('[+] Live Nova Shot Received:', shotData);
        
        const trajectory = physicsEngine.calculateTrajectory(shotData);
        
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = shotData.ogcCarry || Math.abs(finalPt.z);
        const offlineYds = shotData.ogcOffline !== null ? shotData.ogcOffline : finalPt.x;
        const offlineDir = offlineYds >= 0 ? "R" : "L";
        
        const dx = offlineYds;
        const dz = carryYds - currentTargetYards;
        const distToPinYds = Math.sqrt(dx * dx + dz * dz);
        const onGreen = distToPinYds <= 10.0;
        
        const pinFeedback = onGreen 
            ? `⛳ GREEN HIT! (${distToPinYds.toFixed(1)} yds to pin)` 
            : `🎯 Pin Delta: ${distToPinYds.toFixed(1)} yds (${dz >= 0 ? '+' : ''}${dz.toFixed(1)}y)`;
        
        if (telemetryDiv) {
            telemetryDiv.innerHTML = `Ball Speed: ${shotData.ballSpeed.toFixed(1)} mph\n` +
                                     `Launch Ang: ${shotData.verticalLaunchAngle.toFixed(1)}°\n` +
                                     `Total Spin: ${Math.round(shotData.total_spin)} rpm\n` +
                                     `Carry: ${carryYds.toFixed(1)} yds (${Math.abs(offlineYds).toFixed(1)}y ${offlineDir})\n` +
                                     `${pinFeedback}`;
        }
        
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
            ballSpeed: speed + (Math.random() * 2.0 - 1.0),
            verticalLaunchAngle: vla + (Math.random() * 1.0 - 0.5),
            horizontalLaunchAngle: (Math.random() * 2.0 - 1.0),
            total_spin: spin + (Math.random() * 200 - 100),
            spin_axis: (Math.random() * 2.0 - 1.0)
        };
    }
    
    // Demo Shot Button
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            const demoShot = generateRealisticShotForDistance(currentTargetYards);
            fireShot(demoShot);
        });
    }
    
    window.addEventListener('keydown', (e) => {
        if (document.activeElement === targetInput) return;
        if (e.code === 'Space') {
            if (demoBtn) demoBtn.click();
        }
    });
    
    // Connect to WebSocket Server on Port 9321
    function connectWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host || 'localhost:9321'}`;
        
        console.log('[+] Connecting to WebSocket:', wsUrl);
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('[✓] Connected to Shanktuary WebSocket server');
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
                }
            } catch (err) {
                console.error('[!] Error parsing WebSocket message:', err);
            }
        };
        
        ws.onclose = () => {
            console.log('[!] WebSocket disconnected, reconnecting in 2s...');
            setTimeout(connectWS, 2000);
        };
    }
    
    connectWS();
}
