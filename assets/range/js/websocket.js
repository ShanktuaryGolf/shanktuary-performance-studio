// WebSocket Telemetry, Proximity & Custom Yardage HUD Controller

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
    
    // Load saved distance from localStorage
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
    
    // Direct numerical input listener
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
                targetInput.blur(); // Remove focus
            }
        });
    }
    
    // Stepper Buttons (-10, -5, +5, +10)
    if (btnMinus10) btnMinus10.addEventListener('click', () => updateTarget(currentTargetYards - 10));
    if (btnMinus5) btnMinus5.addEventListener('click', () => updateTarget(currentTargetYards - 5));
    if (btnPlus5) btnPlus5.addEventListener('click', () => updateTarget(currentTargetYards + 5));
    if (btnPlus10) btnPlus10.addEventListener('click', () => updateTarget(currentTargetYards + 10));
    
    // Quick Preset Buttons
    presetBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const yds = parseInt(e.target.getAttribute('data-yds'), 10);
            updateTarget(yds);
        });
    });
    
    // Arrow Key Stepping (when not typing in the input box)
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

    function fireShot(shotData) {
        const trajectory = physicsEngine.calculateTrajectory(shotData);
        
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = Math.abs(finalPt.z);
        const offlineYds = finalPt.x;
        const offlineDir = finalPt.x >= 0 ? "R" : "L";
        
        // Calculate Proximity to Target Pin
        const dx = finalPt.x;
        const dz = carryYds - currentTargetYards;
        const distToPinYds = Math.sqrt(dx * dx + dz * dz);
        const onGreen = distToPinYds <= 10.0;
        
        const pinFeedback = onGreen 
            ? `⛳ GREEN HIT! (${distToPinYds.toFixed(1)} yds to pin)` 
            : `🎯 Pin Delta: ${distToPinYds.toFixed(1)} yds (${dz >= 0 ? '+' : ''}${dz.toFixed(1)}y)`;
        
        if (telemetryDiv) {
            telemetryDiv.innerHTML = `Ball Speed: ${(shotData.ballSpeed || shotData.ball_speed_mph || 150).toFixed(1)} mph\n` +
                                     `Launch Ang: ${(shotData.verticalLaunchAngle || shotData.vertical_launch_angle_degrees || 12).toFixed(1)}°\n` +
                                     `Total Spin: ${Math.round(shotData.total_spin || shotData.total_spin_rpm || 2500)} rpm\n` +
                                     `Carry: ${carryYds.toFixed(1)} yds (${Math.abs(offlineYds).toFixed(1)}y ${offlineDir})\n` +
                                     `${pinFeedback}`;
        }
        
        cameraController.setLandingPosition(new THREE.Vector3(finalPt.x, 0.05, finalPt.z));
        ball.launch(trajectory);
    }
    
    // Demo Shot Button
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            const targetSpeed = Math.sqrt(currentTargetYards) * 12.8;
            const demoShot = {
                ballSpeed: targetSpeed + (Math.random() * 6 - 3),
                verticalLaunchAngle: 13.0 + (Math.random() * 2 - 1),
                horizontalLaunchAngle: (Math.random() * 2.5 - 1.25),
                total_spin: 2500 + (Math.random() * 300 - 150),
                spin_axis: (Math.random() * 3 - 1.5)
            };
            fireShot(demoShot);
        });
    }
    
    window.addEventListener('keydown', (e) => {
        if (document.activeElement === targetInput) return;
        if (e.code === 'Space') {
            if (demoBtn) demoBtn.click();
        }
    });
    
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
                if (msg.type === 'shot' && msg.data) {
                    fireShot(msg.data);
                } else if (msg.type === 'init' && msg.data) {
                    fireShot(msg.data);
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
