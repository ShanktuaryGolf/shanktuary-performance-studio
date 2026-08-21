// High-Precision 3D Geometrically-Dimpled Golf Ball Model

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    this.visualRadius = 0.055; // Refined realistic scale (~1.9 inches)
    
    // 1. Create Geometrically-Dimpled 3D Sphere (392 Authentic Dimples)
    const geometry = this.createDimpledGeometry(this.visualRadius);
    const texture = this.createBallTexture();
    
    // 2. High-Gloss PBR Material with Specular Sheen
    const material = new THREE.MeshStandardMaterial({
      map: texture,
      vertexColors: true,
      roughness: 0.2,
      metalness: 0.05,
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(0, this.visualRadius + 0.02, 0); // Sits resting on the tee pad
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.scene.add(this.mesh);
    
    // 3. Glowing 3D Flight Tracer Ribbon
    this.tracerPoints = [];
    this.tracerGeo = new THREE.BufferGeometry();
    this.tracerMat = new THREE.LineBasicMaterial({
      color: 0x00E5FF,
      linewidth: 4
    });
    this.tracerLine = new THREE.Line(this.tracerGeo, this.tracerMat);
    this.scene.add(this.tracerLine);
    
    // 4. Ground Landing Marker Ring
    const ringGeo = new THREE.RingGeometry(0.4, 0.8, 32);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x00FF66,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85
    });
    this.landingRing = new THREE.Mesh(ringGeo, ringMat);
    this.landingRing.position.set(0, 0.03, 0);
    this.landingRing.visible = false;
    this.scene.add(this.landingRing);
    
    this.particles = [];
    this.trajectory = null;
    this.elapsedTime = 0;
    this.isAnimating = false;
    this.lastBounces = 0;
  }

  createDimpledGeometry(radius) {
    const geometry = new THREE.SphereGeometry(radius, 80, 80);
    const pos = geometry.attributes.position;
    const colors = [];
    
    const N = 392;
    const dimpleCenters = [];
    for (let i = 0; i < N; i++) {
      const z = 1.0 - (2.0 * i) / (N - 1);
      const r = Math.sqrt(Math.max(0.0, 1.0 - z * z));
      const theta = i * Math.PI * (3.0 - Math.sqrt(5.0));
      const x = r * Math.cos(theta);
      const y = r * Math.sin(theta);
      dimpleCenters.push(new THREE.Vector3(x, y, z));
    }
    
    const dimpleAngleThreshold = 0.082;
    const maxDepressionDepth = radius * 0.12;
    
    const v = new THREE.Vector3();
    const vNorm = new THREE.Vector3();
    
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      vNorm.copy(v).normalize();
      
      let minAngle = 999;
      for (let j = 0; j < N; j++) {
        const dot = Math.min(1.0, Math.max(-1.0, vNorm.dot(dimpleCenters[j])));
        const angle = Math.acos(dot);
        if (angle < minAngle) {
          minAngle = angle;
        }
      }
      
      let ao = 1.0;
      if (minAngle < dimpleAngleThreshold) {
        const ratio = minAngle / dimpleAngleThreshold;
        const depth = maxDepressionDepth * Math.pow(Math.cos(ratio * (Math.PI / 2)), 2);
        v.sub(vNorm.multiplyScalar(depth));
        pos.setXYZ(i, v.x, v.y, v.z);
        ao = 0.78 + 0.22 * ratio;
      }
      
      colors.push(ao, ao, ao);
    }
    
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geometry.computeVertexNormals();
    return geometry;
  }

  createBallTexture() {
    const size = 512;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, size, size);
    
    ctx.fillStyle = '#111111';
    ctx.fillRect(size / 2 - 3, 0, 6, size);
    
    ctx.fillStyle = '#e11d48';
    ctx.font = 'bold 44px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('1', size / 2 + 50, size / 2);
    
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
  }

  reset() {
    this.mesh.position.set(0, this.visualRadius + 0.02, 0);
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
      this.landingRing.position.set(finalPoint.x, 0.03, finalPoint.z);
      this.landingRing.visible = true;
    }
  }

  createTurfImpact(x, z) {
    for (let i = 0; i < 8; i++) {
      const pGeo = new THREE.PlaneGeometry(0.14, 0.14);
      pGeo.rotateX(-Math.PI / 2);
      const pMat = new THREE.MeshBasicMaterial({
        color: 0x7da85b,
        transparent: true,
        opacity: 0.8
      });
      const pMesh = new THREE.Mesh(pGeo, pMat);
      pMesh.position.set(x + (Math.random() * 0.3 - 0.15), 0.04, z + (Math.random() * 0.3 - 0.15));
      this.scene.add(pMesh);
      this.particles.push({ mesh: pMesh, life: 0.7, maxLife: 0.7 });
    }
  }

  update(deltaTime) {
    if (this.isAnimating && this.trajectory && this.trajectory.length > 0) {
      this.elapsedTime += deltaTime;
      
      const targetIndex = Math.min(
        Math.floor(this.elapsedTime / 0.01),
        this.trajectory.length - 1
      );
      
      const p = this.trajectory[targetIndex];
      
      this.mesh.position.set(p.x, Math.max(this.visualRadius, p.y), p.z);
      this.mesh.rotation.x -= deltaTime * 18;
      this.mesh.rotation.y += deltaTime * 2;
      
      if (this.tracerPoints.length === 0 || 
          this.tracerPoints[this.tracerPoints.length - 1].distanceTo(this.mesh.position) > 0.3) {
        this.tracerPoints.push(new THREE.Vector3(p.x, Math.max(this.visualRadius, p.y), p.z));
        this.tracerGeo.setFromPoints(this.tracerPoints);
      }
      
      if (p.bounces > this.lastBounces) {
        this.createTurfImpact(p.x, p.z);
        this.lastBounces = p.bounces;
      }
      
      if (targetIndex >= this.trajectory.length - 1) {
        this.isAnimating = false;
      }
    }
    
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
