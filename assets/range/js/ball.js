// 3D Golf Ball with Real-Time Physical Flight & Ground Interaction

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    this.visualRadius = 0.22; // Yards (visually scaled for driving range perspective)
    
    // Create Golf Ball mesh with dimpled texture & shine
    const geometry = new THREE.SphereGeometry(this.visualRadius, 32, 32);
    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.25,
      metalness: 0.05
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(0, this.visualRadius, 0); // Sits flush on the tee
    this.mesh.castShadow = true;
    this.scene.add(this.mesh);
    
    // Glowing Flight Tracer Ribbon
    this.tracerPoints = [];
    this.tracerGeo = new THREE.BufferGeometry();
    this.tracerMat = new THREE.LineBasicMaterial({
      color: 0x00E5FF,
      linewidth: 4
    });
    this.tracerLine = new THREE.Line(this.tracerGeo, this.tracerMat);
    this.scene.add(this.tracerLine);
    
    // Ground Landing Marker Target
    const ringGeo = new THREE.RingGeometry(0.6, 1.2, 32);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x00FF66,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85
    });
    this.landingRing = new THREE.Mesh(ringGeo, ringMat);
    this.landingRing.position.set(0, 0.04, 0);
    this.landingRing.visible = false;
    this.scene.add(this.landingRing);
    
    // Grass/Dirt Impact Particles
    this.particles = [];
    
    this.trajectory = null;
    this.elapsedTime = 0;
    this.isAnimating = false;
    this.lastBounces = 0;
  }

  reset() {
    this.mesh.position.set(0, this.visualRadius, 0);
    this.tracerPoints = [];
    this.tracerGeo.setFromPoints([]);
    this.landingRing.visible = false;
    this.isAnimating = false;
    this.elapsedTime = 0;
    this.lastBounces = 0;
  }

  launch(trajectoryPoints) {
    this.reset();
    this.trajectory = trajectoryPoints;
    this.isAnimating = true;
    this.elapsedTime = 0;
    this.lastBounces = 0;
    
    if (trajectoryPoints.length > 0) {
      const finalPoint = trajectoryPoints[trajectoryPoints.length - 1];
      this.landingRing.position.set(finalPoint.x, 0.04, finalPoint.z);
      this.landingRing.visible = true;
    }
  }

  createTurfImpact(x, z) {
    // Spawn subtle turf grass/dirt dust on bounce
    for (let i = 0; i < 8; i++) {
      const pGeo = new THREE.PlaneGeometry(0.18, 0.18);
      pGeo.rotateX(-Math.PI / 2);
      const pMat = new THREE.MeshBasicMaterial({
        color: 0x7da85b,
        transparent: true,
        opacity: 0.8
      });
      const pMesh = new THREE.Mesh(pGeo, pMat);
      pMesh.position.set(x + (Math.random() * 0.4 - 0.2), 0.05, z + (Math.random() * 0.4 - 0.2));
      this.scene.add(pMesh);
      this.particles.push({ mesh: pMesh, life: 0.8, maxLife: 0.8 });
    }
  }

  update(deltaTime) {
    if (this.isAnimating && this.trajectory && this.trajectory.length > 0) {
      this.elapsedTime += deltaTime;
      
      // Each trajectory tick represents 0.01 seconds (10ms)
      const targetIndex = Math.min(
        Math.floor(this.elapsedTime / 0.01),
        this.trajectory.length - 1
      );
      
      const p = this.trajectory[targetIndex];
      
      // Position ball so bottom touches ground/turf exactly (y = p.y)
      this.mesh.position.set(p.x, Math.max(this.visualRadius, p.y), p.z);
      
      // Ball rotation around flight axis
      this.mesh.rotation.x -= deltaTime * 12;
      
      // Update Tracer Ribbon (anchored to ball center)
      if (this.tracerPoints.length === 0 || 
          this.tracerPoints[this.tracerPoints.length - 1].distanceTo(this.mesh.position) > 0.4) {
        this.tracerPoints.push(new THREE.Vector3(p.x, Math.max(this.visualRadius, p.y), p.z));
        this.tracerGeo.setFromPoints(this.tracerPoints);
      }
      
      // Trigger turf impact when bounce counter increments
      if (p.bounces > this.lastBounces) {
        this.createTurfImpact(p.x, p.z);
        this.lastBounces = p.bounces;
      }
      
      if (targetIndex >= this.trajectory.length - 1) {
        this.isAnimating = false;
      }
    }
    
    // Update and fade particles
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.life -= deltaTime;
      p.mesh.material.opacity = Math.max(0, p.life / p.maxLife);
      p.mesh.scale.multiplyScalar(1.02);
      if (p.life <= 0) {
        this.scene.remove(p.mesh);
        this.particles.splice(i, 1);
      }
    }
  }
}
