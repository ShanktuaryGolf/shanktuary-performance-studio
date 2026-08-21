// WebSocket Telemetry, Proximity & Live Nova / OpenGolfCoach Shot Handler

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

    // Unpack all possible shapes from Nova, OpenGolfCoach, and Performance Studio
    function extractShotTelemetry(msg) {
        if (!msg) return null;
        
        const raw = msg.data || msg;
        const shotObj = raw.shot || raw;
        const us = shotObj.us_units || raw.us_units || shotObj;
        
        const ballSpeed = parseFloat(
            us.ball_speed_mph || us.ballSpeed || us.ball_speed || shotObj.ballSpeed || raw.ballSpeed || 0
        );
        
        if (ballSpeed <= 5.0) {
            return null; // Not a valid shot
        }
        
        const vla = parseFloat(
            us.vert_launch_angle_deg || us.vertical_launch_angle_degrees || us.verticalLaunchAngle || us.vla || 12.0
        );
        
        const hla = parseFloat(
            us.horiz_launch_angle_deg || us.horizontal_launch_angle_degrees || us.horizontalLaunchAngle || us.hla || 0.0
        );
        
        const totalSpin = parseFloat(
            us.total_spin_rpm || us.total_spin || us.spinSpeed || us.spin_rate || 2500.0
        );
        
        const spinAxis = parseFloat(
            us.spin_axis_deg || us.spin_axis_degrees || us.spin_axis || us.spinAxis || 0.0
        );
        
        const clubSpeed = parseFloat(
            us.club_speed_mph || us.club_speed || us.clubSpeed || 0.0
        );
        
        return {
            ballSpeed,
            verticalLaunchAngle: vla,
            horizontalLaunchAngle: hla,
            total_spin: totalSpin,
            spin_axis: spinAxis,
            clubSpeed
        };
    }

    function fireShot(shotData) {
        if (!shotData) return;
        
        console.log('[+] Launching live shot in 3D Driving Range:', shotData);
        
        const trajectory = physicsEngine.calculateTrajectory(shotData);
        
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = Math.abs(finalPt.z);
        const offlineYds = finalPt.x;
        const offlineDir = finalPt.x >= 0 ? "R" : "L";
        
        const dx = finalPt.x;
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
        
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('[+] Connected to Shanktuary WebSocket server');
        };
        
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log('[+] Received WebSocket message:', msg.type);
                
                if (msg.type === 'shot' || msg.type === 'init') {
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
            setTimeout(connectWS, 2000);
        };
    }
    
    connectWS();
}
