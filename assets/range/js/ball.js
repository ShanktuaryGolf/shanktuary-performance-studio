// 3D Golf Ball with Real Turf Pitch Mark / Divot Indentations

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    this.visualRadius = 0.055;
    
    // 1. 3D Geometrically-Dimpled Golf Ball (392 Dimples)
    const geometry = this.createDimpledGeometry(this.visualRadius);
    const texture = this.createBallTexture();
    
    const material = new THREE.MeshStandardMaterial({
      map: texture,
      vertexColors: true,
      roughness: 0.2,
      metalness: 0.05,
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(0, this.visualRadius + 0.02, 0);
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.scene.add(this.mesh);
    
    // 2. High-Visibility 3D Glowing Tracer Ribbon
    this.maxTracerSegments = 500;
    this.tracerGeo = new THREE.BufferGeometry();
    this.tracerPositions = new Float32Array(this.maxTracerSegments * 6 * 3);
    this.tracerColors = new Float32Array(this.maxTracerSegments * 6 * 3);
    
    this.tracerGeo.setAttribute('position', new THREE.BufferAttribute(this.tracerPositions, 3));
    this.tracerGeo.setAttribute('color', new THREE.BufferAttribute(this.tracerColors, 3));
    
    this.tracerMat = new THREE.MeshBasicMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.9
    });
    
    this.tracerMesh = new THREE.Mesh(this.tracerGeo, this.tracerMat);
    this.tracerMesh.frustumCulled = false;
    this.scene.add(this.tracerMesh);
    
    this.tracerPath = [];
    this.ribbonWidth = 0.12;
    
    // 3. Ground Landing Target Ring
    const ringGeo = new THREE.RingGeometry(0.5, 1.0, 32);
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
    
    // 4. Session Divots & Pitch Marks
    this.divots = [];
    this.particles = [];
    
    this.trajectory = null;
    this.elapsedTime = 0;
    this.isAnimating = false;
    this.isAtRest = false;
    this.restTimer = 0;
    this.lastBounces = 0;
    
    this.onResetCallback = null;
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
    
    // Crisp glossy white cover
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, size, size);
    
    // Equator seam line (faint)
    ctx.strokeStyle = 'rgba(210, 220, 230, 0.4)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, size / 2);
    ctx.lineTo(size, size / 2);
    ctx.stroke();
    
    // Tour Putting Alignment Stamp: ◄—— PRO V1 ——►
    ctx.fillStyle = '#0f172a';
    ctx.font = 'bold 22px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('◄—— PRO V1 ——►', size / 2, size / 2 - 32);
    
    // Tournament Player Number
    ctx.fillStyle = '#dc2626';
    ctx.font = 'bold 38px sans-serif';
    ctx.fillText('1', size / 2, size / 2 + 28);
    
    // Secondary alignment dots
    ctx.fillStyle = '#0f172a';
    ctx.beginPath();
    ctx.arc(size / 2 - 42, size / 2 + 28, 3.5, 0, Math.PI * 2);
    ctx.arc(size / 2 + 42, size / 2 + 28, 3.5, 0, Math.PI * 2);
    ctx.fill();
    
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
  }

  reset() {
    this.mesh.position.set(0, this.visualRadius + 0.02, 0);
    this.tracerPath = [];
    this.tracerPositions.fill(0);
    this.tracerColors.fill(0);
    this.tracerGeo.attributes.position.needsUpdate = true;
    this.tracerGeo.attributes.color.needsUpdate = true;
    this.tracerGeo.setDrawRange(0, 0);
    
    this.landingRing.visible = false;
    this.isAnimating = false;
    this.isAtRest = false;
    this.restTimer = 0;
    this.elapsedTime = 0;
    this.lastBounces = 0;
  }

  launch(trajectoryPoints) {
    this.reset();
    this.trajectory = trajectoryPoints;
    this.isAnimating = true;
    this.isAtRest = false;
    this.restTimer = 0;
    this.elapsedTime = 0;
    this.lastBounces = 0;
    
    if (trajectoryPoints.length > 0) {
      const finalPoint = trajectoryPoints[trajectoryPoints.length - 1];
      this.landingRing.position.set(finalPoint.x, 0.03, finalPoint.z);
      this.landingRing.visible = true;
    }
  }

  updateTracerRibbon(newPos) {
    if (this.tracerPath.length === 0 || 
        this.tracerPath[this.tracerPath.length - 1].distanceTo(newPos) > 0.3) {
      this.tracerPath.push(newPos.clone());
    }
    
    const count = this.tracerPath.length;
    if (count < 2) return;
    
    let vIdx = 0;
    const halfWidth = this.ribbonWidth;
    
    for (let i = 0; i < count - 1; i++) {
      if (i >= this.maxTracerSegments - 1) break;
      
      const p1 = this.tracerPath[i];
      const p2 = this.tracerPath[i + 1];
      
      const dir = new THREE.Vector3().subVectors(p2, p1).normalize();
      const up = new THREE.Vector3(0, 1, 0);
      const side = new THREE.Vector3().crossVectors(dir, up).normalize().multiplyScalar(halfWidth);
      
      const v0 = new THREE.Vector3().subVectors(p1, side);
      const v1 = new THREE.Vector3().addVectors(p1, side);
      const v2 = new THREE.Vector3().subVectors(p2, side);
      const v3 = new THREE.Vector3().addVectors(p2, side);
      
      const t1 = i / count;
      const t2 = (i + 1) / count;
      
      const r1 = 0.0, g1 = 0.90 + 0.10 * t1, b1 = 1.0 - 0.60 * t1;
      const r2 = 0.0, g2 = 0.90 + 0.10 * t2, b2 = 1.0 - 0.60 * t2;
      
      this.setVertex(vIdx++, v0, r1, g1, b1);
      this.setVertex(vIdx++, v1, r1, g1, b1);
      this.setVertex(vIdx++, v2, r2, g2, b2);
      
      this.setVertex(vIdx++, v1, r1, g1, b1);
      this.setVertex(vIdx++, v3, r2, g2, b2);
      this.setVertex(vIdx++, v2, r2, g2, b2);
    }
    
    this.tracerGeo.attributes.position.needsUpdate = true;
    this.tracerGeo.attributes.color.needsUpdate = true;
    this.tracerGeo.setDrawRange(0, vIdx);
  }

  setVertex(idx, pos, r, g, b) {
    const pArray = this.tracerPositions;
    const cArray = this.tracerColors;
    
    pArray[idx * 3] = pos.x;
    pArray[idx * 3 + 1] = pos.y;
    pArray[idx * 3 + 2] = pos.z;
    
    cArray[idx * 3] = r;
    cArray[idx * 3 + 1] = g;
    cArray[idx * 3 + 2] = b;
  }

  createTurfDivot(x, z) {
    // 1. Realistic Soil Divot & Pitch Mark Decal
    const divotGeo = new THREE.CircleGeometry(0.24, 24);
    divotGeo.rotateX(-Math.PI / 2);
    
    // Create dark organic soil texture with displacement lip
    const dCanvas = document.createElement('canvas');
    dCanvas.width = 128;
    dCanvas.height = 128;
    const dCtx = dCanvas.getContext('2d');
    
    const grad = dCtx.createRadialGradient(64, 64, 4, 64, 64, 60);
    grad.addColorStop(0, '#2d1808'); // Dark soil crater center
    grad.addColorStop(0.5, '#422812'); // Earth
    grad.addColorStop(0.85, '#2e591b'); // Bruised grass rim
    grad.addColorStop(1.0, 'rgba(0,0,0,0)');
    
    dCtx.fillStyle = grad;
    dCtx.fillRect(0, 0, 128, 128);
    
    const dTex = new THREE.CanvasTexture(dCanvas);
    const divotMat = new THREE.MeshBasicMaterial({
      map: dTex,
      transparent: true,
      opacity: 0.95,
      depthWrite: false
    });
    
    const divotMesh = new THREE.Mesh(divotGeo, divotMat);
    divotMesh.position.set(x, 0.022, z);
    divotMesh.scale.set(1.0, 1.0, 1.4); // Stretched in direction of impact
    this.scene.add(divotMesh);
    
    this.divots.push(divotMesh);
    if (this.divots.length > 20) {
      const old = this.divots.shift();
      this.scene.remove(old);
    }
    
    // 2. Flying Turf / Dirt Particle Spray
    for (let i = 0; i < 10; i++) {
      const pGeo = new THREE.PlaneGeometry(0.12, 0.12);
      pGeo.rotateX(-Math.PI / 2);
      const pMat = new THREE.MeshBasicMaterial({
        color: (i % 2 === 0) ? 0x3d2314 : 0x6e964b,
        transparent: true,
        opacity: 0.85
      });
      const pMesh = new THREE.Mesh(pGeo, pMat);
      pMesh.position.set(x + (Math.random() * 0.4 - 0.2), 0.04, z + (Math.random() * 0.4 - 0.2));
      this.scene.add(pMesh);
      this.particles.push({ mesh: pMesh, life: 0.8, maxLife: 0.8 });
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
      const ballPos = new THREE.Vector3(p.x, Math.max(this.visualRadius, p.y), p.z);
      
      this.mesh.position.copy(ballPos);
      this.mesh.rotation.x -= deltaTime * 18;
      this.mesh.rotation.y += deltaTime * 2;
      
      this.updateTracerRibbon(ballPos);
      
      // On First Ground Impact: Create Turf Pitch Mark / Divot
      if (p.bounces > this.lastBounces) {
        this.createTurfDivot(p.x, p.z);
        this.lastBounces = p.bounces;
      }
      
      if (targetIndex >= this.trajectory.length - 1) {
        this.isAnimating = false;
        this.isAtRest = true;
        this.restTimer = 0;
      }
    } else if (this.isAtRest) {
      this.restTimer += deltaTime;
      if (this.restTimer >= 3.0) {
        this.isAtRest = false;
        // Return ball to Tee Box ready for next swing, but keep tracer & landing marker visible
        this.mesh.position.set(0, this.visualRadius + 0.02, 0);
        this.elapsedTime = 0;
        if (typeof this.onResetCallback === 'function') {
          this.onResetCallback();
        }
      }
    }
    
    // Update particle lifespans
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
