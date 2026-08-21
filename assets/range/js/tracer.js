import * as THREE from 'three';

export class FlightTracer {
  constructor(scene) {
    this.scene = scene;
    
    const material = new THREE.LineBasicMaterial({
      color: 0xff0000,
      linewidth: 3,
      transparent: true,
      opacity: 0.8
    });
    
    this.geometry = new THREE.BufferGeometry();
    this.points = [];
    this.line = new THREE.Line(this.geometry, material);
    
    this.scene.add(this.line);
    
    // Target ring
    const ringGeo = new THREE.RingGeometry(0.5, 0.6, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00ff00, side: THREE.DoubleSide });
    this.targetRing = new THREE.Mesh(ringGeo, ringMat);
    this.targetRing.rotation.x = Math.PI / 2; // Flat on ground
    this.targetRing.visible = false;
    this.scene.add(this.targetRing);
  }

  addPoint(pos) {
    this.points.push(new THREE.Vector3(pos.x, pos.y, pos.z));
    this.geometry.setFromPoints(this.points);
  }

  reset() {
    this.points = [];
    this.geometry.setFromPoints(this.points);
    this.targetRing.visible = false;
  }
  
  showLandingTarget(pos) {
    this.targetRing.position.set(pos.x, 0.01, pos.z);
    this.targetRing.visible = true;
  }
}
