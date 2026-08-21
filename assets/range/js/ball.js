// 3D Golf Ball with Flight Tracer Trail

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    
    // Create Golf Ball mesh (scaled for good visibility at distance)
    const geometry = new THREE.SphereGeometry(0.25, 24, 24);
    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.2,
      metalness: 0.1
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(0, 0.25, 0); // On the tee
    this.mesh.castShadow = true;
    this.scene.add(this.mesh);
    
    // Flight Tracer Line
    this.tracerPoints = [];
    this.tracerGeo = new THREE.BufferGeometry();
    this.tracerMat = new THREE.LineBasicMaterial({
      color: 0x00E5FF,
      linewidth: 3
    });
    this.tracerLine = new THREE.Line(this.tracerGeo, this.tracerMat);
    this.scene.add(this.tracerLine);
    
    // Landing Ring Target Marker
    const ringGeo = new THREE.RingGeometry(0.8, 1.2, 32);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x00FF66,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8
    });
    this.landingRing = new THREE.Mesh(ringGeo, ringMat);
    this.landingRing.position.set(0, 0.05, 0);
    this.landingRing.visible = false;
    this.scene.add(this.landingRing);
    
    this.trajectory = null;
    this.currentIndex = 0;
    this.isAnimating = false;
  }

  reset() {
    this.mesh.position.set(0, 0.25, 0);
    this.tracerPoints = [];
    this.tracerGeo.setFromPoints([]);
    this.landingRing.visible = false;
    this.isAnimating = false;
  }

  launch(trajectoryPoints) {
    this.reset();
    this.trajectory = trajectoryPoints;
    this.currentIndex = 0;
    this.isAnimating = true;
    
    if (trajectoryPoints.length > 0) {
      const finalPoint = trajectoryPoints[trajectoryPoints.length - 1];
      this.landingRing.position.set(finalPoint.x, 0.06, finalPoint.z);
      this.landingRing.visible = true;
    }
  }

  update(deltaTime) {
    if (this.isAnimating && this.trajectory) {
      // Step forward along trajectory
      const steps = Math.max(1, Math.floor(deltaTime * 60));
      this.currentIndex = Math.min(this.currentIndex + steps, this.trajectory.length - 1);
      
      const p = this.trajectory[this.currentIndex];
      this.mesh.position.set(p.x, p.y + 0.25, p.z);
      
      // Update Tracer Line
      this.tracerPoints.push(new THREE.Vector3(p.x, p.y + 0.25, p.z));
      this.tracerGeo.setFromPoints(this.tracerPoints);
      
      if (this.currentIndex >= this.trajectory.length - 1) {
        this.isAnimating = false;
      }
    }
  }
}
