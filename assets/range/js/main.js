// Main Driving Range Application Entrypoint

import { initRenderer } from './renderer.js';
import { setupEnvironment } from './environment.js';
import { setupFoliage } from './foliage.js';
import { CameraController, CameraModes } from './camera.js';
import { GolfPhysicsEngine } from './physics.js';
import { GolfBall } from './ball.js';
import { setupWebSocketAndUI } from './websocket.js';

function start() {
    console.log('[+] Initializing 3D Driving Range...');
    
    const { scene, camera, renderer } = initRenderer();
    
    // Setup Environment & Foliage
    setupEnvironment(scene);
    setupFoliage(scene);
    
    // Physics, Ball & Camera
    const physicsEngine = new GolfPhysicsEngine();
    const ball = new GolfBall(scene);
    const cameraController = new CameraController(camera);
    
    // 3-Second Auto-Reset: Return camera to Golfer View at Tee Box
    ball.onResetCallback = () => {
        console.log('[+] Shot complete: Returning camera & ball to Tee Box');
        cameraController.setMode(CameraModes.GOLFER);
    };
    
    // WebSocket & UI Controls
    setupWebSocketAndUI(scene, physicsEngine, ball, cameraController);
    
    const clock = new THREE.Clock();
    
    // Render Loop
    function animate() {
        requestAnimationFrame(animate);
        
        const delta = Math.min(clock.getDelta(), 0.1);
        
        ball.update(delta);
        cameraController.setBallPosition(ball.mesh.position);
        cameraController.update(delta);
        
        renderer.render(scene, camera);
    }
    
    animate();
    console.log('[✓] 3D Driving Range is running!');
}

window.addEventListener('DOMContentLoaded', start);
