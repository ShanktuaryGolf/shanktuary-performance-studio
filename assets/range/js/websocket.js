// WebSocket Telemetry & HUD Controller

export function setupWebSocketAndUI(scene, physicsEngine, ball, cameraController) {
    const telemetryDiv = document.getElementById('telemetry-data');
    const demoBtn = document.getElementById('btn-demo-shot');
    
    function fireShot(shotData) {
        const trajectory = physicsEngine.calculateTrajectory(shotData);
        
        // Calculate final stats
        const finalPt = trajectory[trajectory.length - 1];
        const carryYds = Math.abs(finalPt.z).toFixed(1);
        const offlineYds = finalPt.x.toFixed(1);
        const offlineDir = finalPt.x >= 0 ? "R" : "L";
        
        if (telemetryDiv) {
            telemetryDiv.innerHTML = `Ball Speed: ${(shotData.ballSpeed || shotData.ball_speed_mph || 150).toFixed(1)} mph\n` +
                                     `Launch Ang: ${(shotData.verticalLaunchAngle || shotData.vertical_launch_angle_degrees || 12).toFixed(1)}°\n` +
                                     `Total Spin: ${Math.round(shotData.total_spin || shotData.total_spin_rpm || 2500)} rpm\n` +
                                     `Carry: ${carryYds} yds\n` +
                                     `Offline: ${Math.abs(offlineYds)} yds ${offlineDir}`;
        }
        
        cameraController.setLandingPosition(new THREE.Vector3(finalPt.x, 0.05, finalPt.z));
        ball.launch(trajectory);
    }
    
    // Demo Shot Button
    if (demoBtn) {
        demoBtn.addEventListener('click', () => {
            const demoShot = {
                ballSpeed: 155.0 + (Math.random() * 10 - 5),
                verticalLaunchAngle: 12.5 + (Math.random() * 2 - 1),
                horizontalLaunchAngle: (Math.random() * 3 - 1.5),
                total_spin: 2400 + (Math.random() * 400 - 200),
                spin_axis: (Math.random() * 4 - 2)
            };
            fireShot(demoShot);
        });
    }
    
    // Spacebar hotkey for demo shot
    window.addEventListener('keydown', (e) => {
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
            setTimeout(connectWS, 2000); // Auto-reconnect after 2s
        };
    }
    
    connectWS();
}
