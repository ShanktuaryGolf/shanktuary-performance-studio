// Multi-Mode 3D Camera System with Up-Close Golf Ball Framing

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
        const savedMode = parseInt(localStorage.getItem('sps_range_camera_mode') || '0', 10);
        this.mode = (savedMode >= 0 && savedMode <= 4) ? savedMode : CameraModes.GOLFER;
        
        this.target = new THREE.Vector3(0, 1.10, -70);
        this.currentPosition = new THREE.Vector3(0, 1.75, 4.6);
        this.desiredPosition = new THREE.Vector3(0, 1.75, 4.6);
        
        this.ballPosition = new THREE.Vector3(0, 0.085, 0);
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
        try {
            localStorage.setItem('sps_range_camera_mode', this.mode.toString());
        } catch (e) {}
        this.updateModeUI();
    }
    
    setMode(mode) {
        this.mode = mode;
        try {
            localStorage.setItem('sps_range_camera_mode', this.mode.toString());
        } catch (e) {}
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
        const lerpFactor = Math.min(1.0, 5.0 * deltaTime);
        
        switch (this.mode) {
            case CameraModes.GOLFER:
                this.desiredPosition.set(0, 1.75, 4.6); // Elevated and pulled back for natural golfer perspective
                this.target.set(0, 1.10, -70);
                break;
                
            case CameraModes.FOLLOW:
                this.desiredPosition.set(this.ballPosition.x, this.ballPosition.y + 0.8, this.ballPosition.z + 2.5);
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.BROADCAST:
                this.desiredPosition.set(25, 12, -20);
                this.target.copy(this.ballPosition);
                break;
                
            case CameraModes.LANDING:
                this.desiredPosition.set(this.landingPosition.x + 3, this.landingPosition.y + 2, this.landingPosition.z + 10);
                this.target.copy(this.landingPosition);
                break;
                
            case CameraModes.BLIMP:
                this.desiredPosition.set(this.ballPosition.x, 50, this.ballPosition.z + 6);
                this.target.copy(this.ballPosition);
                break;
        }
        
        this.currentPosition.lerp(this.desiredPosition, lerpFactor);
        this.camera.position.copy(this.currentPosition);
        this.camera.lookAt(this.target);
    }
}
