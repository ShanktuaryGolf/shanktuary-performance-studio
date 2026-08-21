// Photorealistic 3D Golf Ball with Procedural Dimple Normal Map & Realistic PGA Scale

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    this.visualRadius = 0.065; // True-to-life realistic scale (~2.3 inches)
    
    // 1. Generate High-Res 1024x1024 Dimple Normal Map
    const dimpleNormalMap = this.createDimpleNormalMap();
    const ballAlbedoMap = this.createBallAlbedoMap();
    
    // 2. Photorealistic Dimpled MeshPhysicalMaterial
    const geometry = new THREE.SphereGeometry(this.visualRadius, 64, 64);
    const material = new THREE.MeshPhysicalMaterial({
      map: ballAlbedoMap,
      normalMap: dimpleNormalMap,
      normalScale: new THREE.Vector2(1.2, 1.2),
      roughness: 0.22,
      metalness: 0.02,
      clearcoat: 1.0, // High-gloss outer urethane cover
      clearcoatRoughness: 0.1,
      reflectivity: 0.9
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.position.set(0, this.visualRadius + 0.025, 0); // Resting on tee pad
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
    
    // 4. Ground Landing Target Marker
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
    
    // Turf impact dust particles
    this.particles = [];
    
    this.trajectory = null;
    this.elapsedTime = 0;
    this.isAnimating = false;
    this.lastBounces = 0;
  }

  createDimpleNormalMap() {
    const size = 1024;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    
    // Base normal flat vector (0, 0, 1) -> RGB (128, 128, 255)
    ctx.fillStyle = 'rgb(128, 128, 255)';
    ctx.fillRect(0, 0, size, size);
    
    const imgData = ctx.getImageData(0, 0, size, size);
    const data = imgData.data;
    
    const dimpleRadius = 14;
    const spacingX = 32;
    const spacingY = 28;
    
    // Staggered hexagonal dimple grid pattern
    for (let y = 0; y < size; y += spacingY) {
      const offsetX = (Math.floor(y / spacingY) % 2) * (spacingX / 2);
      for (let x = -spacingX; x < size + spacingX; x += spacingX) {
        const cx = x + offsetX;
        const cy = y;
        
        // Draw concave spherical dimple normal perturbation
        for (let dy = -dimpleRadius; dy <= dimpleRadius; dy++) {
          for (let dx = -dimpleRadius; dx <= dimpleRadius; dx++) {
            const distSq = dx * dx + dy * dy;
            if (distSq < dimpleRadius * dimpleRadius) {
              const px = (cx + dx + size) % size;
              const py = (cy + dy + size) % size;
              const idx = (py * size + px) * 4;
              
              const dist = Math.sqrt(distSq);
              const depth = Math.cos((dist / dimpleRadius) * (Math.PI / 2));
              
              // Perturbed normal vector (Nx, Ny, Nz)
              const nx = -(dx / dimpleRadius) * depth * 0.8;
              const ny = -(dy / dimpleRadius) * depth * 0.8;
              const nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
              
              // Map [-1, 1] to [0, 255]
              data[idx] = Math.floor((nx * 0.5 + 0.5) * 255);
              data[idx + 1] = Math.floor((ny * 0.5 + 0.5) * 255);
              data[idx + 2] = Math.floor((nz * 0.5 + 0.5) * 255);
            }
          }
        }
      }
    }
    
    ctx.putImageData(imgData, 0, 0);
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(4, 2);
    return texture;
  }

  createBallAlbedoMap() {
    const size = 512;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    
    // Pure White Golf Ball Urethane Cover
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, size, size);
    
    // Alignment Stripe & Brand Number "1"
    ctx.fillStyle = '#101116';
    ctx.fillRect(size / 2 - 2, 0, 4, size); // Black alignment line
    
    ctx.fillStyle = '#dc2626';
    ctx.font = 'bold 36px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('1', size / 2 + 60, size / 2);
    
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
  }

  reset() {
    this.mesh.position.set(0, this.visualRadius + 0.025, 0);
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
      const pGeo = new THREE.PlaneGeometry(0.15, 0.15);
      pGeo.rotateX(-Math.PI / 2);
      const pMat = new THREE.MeshBasicMaterial({
        color: 0x6e964b,
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
      
      // Position ball with bottom resting flush on ground
      this.mesh.position.set(p.x, Math.max(this.visualRadius, p.y), p.z);
      
      // Rotate ball based on forward speed
      this.mesh.rotation.x -= deltaTime * 20;
      
      // Update flight tracer ribbon
      if (this.tracerPoints.length === 0 || 
          this.tracerPoints[this.tracerPoints.length - 1].distanceTo(this.mesh.position) > 0.3) {
        this.tracerPoints.push(new THREE.Vector3(p.x, Math.max(this.visualRadius, p.y), p.z));
        this.tracerGeo.setFromPoints(this.tracerPoints);
      }
      
      // Trigger turf bounce impact
      if (p.bounces > this.lastBounces) {
        this.createTurfImpact(p.x, p.z);
        this.lastBounces = p.bounces;
      }
      
      if (targetIndex >= this.trajectory.length - 1) {
        this.isAnimating = false;
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
