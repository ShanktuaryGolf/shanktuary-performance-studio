// Multi-Mode 3D Camera System

export const CameraModes = {
    GOLFER: 0,
    FOLLOW: 1,
    BROADCAST: 2,
    LANDING: 3,
    BLIMP: 4
};

export class CameraController {
    constructor(camera) {
        this.camera = camera;
        this.mode = CameraModes.GOLFER;
        
        this.target = new THREE.Vector3(0, 1.5, -40);
        this.currentPosition = new THREE.Vector3(0, 2.5, 6);
        this.desiredPosition = new THREE.Vector3(0, 2.5, 6);
        
        this.ballPosition = new THREE.Vector3(0, 0.25, 0);
        this.landingPosition = new THREE.Vector3(0, 0.05, -150);
        
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
            modeLabel.innerText = "🎥 Cam: " + modeNames[this.mode] + " [V]";
        }
    }
    
    setBallPosition(pos) {
        this.ballPosition.copy(pos);
    }
    
    setLandingPosition(pos) {
        this.landingPosition.copy(pos);
    }
    
    update(deltaTime) {
        const lerpFactor = Math.min(1.0, 4.0 * deltaTime);
        
        switch (this.mode) {
            case CameraModes.GOLFER:
                this.desiredPosition.set(0, 2.5, 6);
                this.target.set(0, 1.5, -40);
                break;
                
            case CameraModes.FOLLOW:
                this.desiredPosition.set(this.ballPosition.x, this.ballPosition.y + 3, this.ballPosition.z + 8);
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.BROADCAST:
                this.desiredPosition.set(35, 18, -30);
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.LANDING:
                this.desiredPosition.set(this.landingPosition.x + 5, this.landingPosition.y + 3, this.landingPosition.z + 15);
                this.target.copy(this.landingPosition);
                break;
                
            case CameraModes.BLIMP:
                this.desiredPosition.set(this.ballPosition.x, 70, this.ballPosition.z + 10);
                this.target.copy(this.ballPosition);
                break;
        }
        
        this.currentPosition.lerp(this.desiredPosition, lerpFactor);
        this.camera.position.copy(this.currentPosition);
        this.camera.lookAt(this.target);
    }
}
