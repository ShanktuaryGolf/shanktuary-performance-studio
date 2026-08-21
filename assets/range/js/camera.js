import * as THREE from 'three';

export const CameraModes = {
    GOLFER: 0,
    FOLLOW: 1,
    BROADCAST: 2,
    LANDING: 3,
    BLIMP: 4
};

export class CameraController {
    constructor(camera, domElement) {
        this.camera = camera;
        this.domElement = domElement;
        this.mode = CameraModes.GOLFER;
        
        this.target = new THREE.Vector3(0, 0, -10);
        this.currentPosition = new THREE.Vector3().copy(camera.position);
        this.desiredPosition = new THREE.Vector3().copy(camera.position);
        
        this.ballPosition = new THREE.Vector3();
        this.landingPosition = new THREE.Vector3(0, 0, -100);
        
        this.setupEventListeners();
        this.updateModeUI();
    }
    
    setupEventListeners() {
        window.addEventListener('keydown', (e) => {
            if (e.key === 'v' || e.key === 'V') {
                this.cycleMode();
            }
        });
        
        const btn = document.getElementById('btn-cam-switch');
        if (btn) {
            btn.addEventListener('click', () => {
                this.cycleMode();
            });
        }
    }
    
    cycleMode() {
        this.mode = (this.mode + 1) % 5;
        this.updateModeUI();
    }
    
    setMode(mode) {
        this.mode = mode;
        this.updateModeUI();
    }
    
    updateModeUI() {
        const modeNames = ["Golfer View", "Follow-Cam", "Broadcast Tower", "Target Green", "Top-Down Blimp"];
        const modeLabel = document.getElementById('camera-mode-label');
        if (modeLabel) {
            modeLabel.innerText = "Cam: " + modeNames[this.mode];
        }
    }
    
    setBallPosition(pos) {
        this.ballPosition.copy(pos);
    }
    
    setLandingPosition(pos) {
        this.landingPosition.copy(pos);
    }
    
    update(deltaTime) {
        const lerpFactor = 5.0 * deltaTime; // Smooth damping
        
        switch (this.mode) {
            case CameraModes.GOLFER:
                this.desiredPosition.set(0, 2, 5); // Behind tee
                this.target.set(0, 0, -10); // Look forward
                break;
                
            case CameraModes.FOLLOW:
                this.desiredPosition.set(this.ballPosition.x, this.ballPosition.y + 2, this.ballPosition.z + 5);
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.BROADCAST:
                this.desiredPosition.set(20, 15, -20); 
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.LANDING:
                this.desiredPosition.set(this.landingPosition.x + 5, this.landingPosition.y + 2, this.landingPosition.z + 10);
                this.target.copy(this.landingPosition);
                break;
                
            case CameraModes.BLIMP:
                this.desiredPosition.set(this.ballPosition.x, 50, this.ballPosition.z + 1); // Avoid exact top down gimbal lock
                this.target.copy(this.ballPosition);
                break;
        }
        
        this.currentPosition.lerp(this.desiredPosition, lerpFactor);
        this.camera.position.copy(this.currentPosition);
        this.camera.lookAt(this.target);
    }
}
