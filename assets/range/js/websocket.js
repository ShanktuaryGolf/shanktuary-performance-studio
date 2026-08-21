import * as THREE from 'three';

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    let ws;
    let tracerLine = null;
    
    // Connect Demo Shot button
    const demoBtn = document.getElementById('btn-demo-shot');
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            handleShotPayload({
                ballSpeed: 165,
                verticalLaunchAngle: 12.5,
                horizontalLaunchAngle: -1.0,
                total_spin: 2500,
                spin_axis: -2.0,
                carry: 285.5,
                apex: 35.2,
                shot_name: 'Demo Drive',
                rank: 'A'
            });
        });
    }
    
    // Ensure camera UI starts correctly
    if (cameraController) cameraController.updateModeUI();
    
    function connect() {
        ws = new WebSocket('ws://localhost:9321');
        
        ws.onopen = () => {
            console.log('Connected to telemetry server');
        };
        
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'shot' || msg.type === 'init') {
                    if (msg.data && msg.data.ball_speed) {
                        // Map snake_case to expected camelCase
                        const payload = {
                            ballSpeed: msg.data.ball_speed,
                            verticalLaunchAngle: msg.data.launch_angle,
                            horizontalLaunchAngle: msg.data.horizontal_angle || 0,
                            total_spin: msg.data.spin_rate || 2500,
                            spin_axis: msg.data.spin_axis || 0,
                            carry: msg.data.carry,
                            apex: msg.data.apex || 0,
                            shot_name: msg.data.shot_name || 'Live Shot',
                            rank: msg.data.rank || 'N/A'
                        };
                        handleShotPayload(payload);
                    }
                }
            } catch (e) {
                console.error('Error parsing telemetry:', e);
            }
        };
        
        ws.onclose = () => {
            setTimeout(connect, 1000); // Reconnect automatically
        };
    }
    
    function handleShotPayload(shot) {
        // Update HUD
        const telemetryData = document.getElementById('telemetry-data');
        if (telemetryData) {
            telemetryData.innerHTML = `
Name: ${shot.shot_name} (Rank: ${shot.rank})
Ball Speed: ${shot.ballSpeed.toFixed(1)} mph
Launch Angle: ${shot.verticalLaunchAngle.toFixed(1)}° (V) / ${shot.horizontalLaunchAngle.toFixed(1)}° (H)
Spin: ${shot.total_spin} rpm (Axis: ${shot.spin_axis.toFixed(1)}°)
Carry: ${shot.carry.toFixed(1)} yds
Apex: ${shot.apex.toFixed(1)} yds
            `.trim();
        }
        
        // Calculate trajectory
        const trajectory = physicsEngine.calculateTrajectory(shot);
        
        // Launch ball
        if (ball) {
            ball.launch(trajectory);
        }
        
        // Update camera landing target
        if (cameraController && trajectory.length > 0) {
            cameraController.setLandingPosition(trajectory[trajectory.length - 1]);
        }
        
        // Create tracer ribbon
        if (tracerLine) {
            scene.remove(tracerLine);
            tracerLine.geometry.dispose();
            tracerLine.material.dispose();
        }
        
        const points = trajectory.map(p => new THREE.Vector3(p.x, p.y, p.z));
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const material = new THREE.LineBasicMaterial({
            color: 0xffffff,
            linewidth: 2,
            transparent: true,
            opacity: 0.5
        });
        
        tracerLine = new THREE.Line(geometry, material);
        scene.add(tracerLine);
    }
    
    connect();
}
