import * as THREE from 'three';
import { initRenderer } from './renderer.js';
import { setupEnvironment } from './environment.js';
import { setupFoliage } from './foliage.js';
import { CameraController } from './camera.js';
import { GolfPhysicsEngine } from './physics.js';
import { GolfBall } from './ball.js';
import { setupWebSocketAndUI } from './websocket.js';

async function main() {
    const { scene, camera, renderer } = await initRenderer();
    
    setupEnvironment(scene);
    setupFoliage(scene);
    
    // Initialize Physics and Ball
    const physicsEngine = new GolfPhysicsEngine();
    const ball = new GolfBall(scene);
    
    // Initialize Camera Controller
    const cameraController = new CameraController(camera, renderer.domElement);
    
    // Initialize WebSocket and UI
    setupWebSocketAndUI(scene, physicsEngine, ball, cameraController);
    
    const clock = new THREE.Clock();
    
    function animate() {
        requestAnimationFrame(animate);
        
        const delta = clock.getDelta();
        
        // Update ball animation
        if (ball) {
            ball.update(delta);
            if (cameraController) {
                cameraController.setBallPosition(ball.mesh.position);
            }
        }
        
        // Update camera interpolation
        if (cameraController) {
            cameraController.update(delta);
        }
        
        renderer.renderAsync(scene, camera);
    }
    
    animate();
}

main().catch(console.error);

