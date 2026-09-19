// 3D Golf Ball with Real Turf Pitch Mark / Divot Indentations

export class GolfBall {
  constructor(scene) {
    this.scene = scene;
    this.visualRadius = 0.055;
    
    // 1. 3D Geometrically-Dimpled Golf Ball (392 Dimples)
    // Deliberately untextured. This previously carried a painted
    // CanvasTexture (PRO V1 stamp + seam), which rendered as grey/striped
    // garbage whenever its WebGL upload failed -- see getDivotAssets() for
    // the underlying canvas-upload issue. The per-vertex AO baked into the
    // dimpled geometry already sells the dimple look, and a plain cover is
    // the preferred look here, so there is nothing to upload at all.
    const geometry = this.createDimpledGeometry(this.visualRadius);
    
    const material = new THREE.MeshStandardMaterial({
      color: 0xf8fafc,
      vertexColors: true,
      roughness: 0.25,
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
      opacity: 0.85,
      // Sits above the same turf plane as the divots; bias it in depth and
      // draw it last so it reads on top of whatever decals it overlaps.
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2
    });
    this.landingRing = new THREE.Mesh(ringGeo, ringMat);
    this.landingRing.position.set(0, 0.03, 0);
    this.landingRing.renderOrder = 30;
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
    // Fired the instant flight ends (ball reaches its final trajectory
    // point), before the 3s tee-return delay. Lets callers queue a shot
    // that arrived mid-flight instead of yanking the current one out from
    // under itself via launch()'s immediate reset().
    this.onFlightEndCallback = null;
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

  launch(trajectoryPoints, customColorHex = null) {
    this.reset();
    this.trajectory = trajectoryPoints;
    this.isAnimating = true;
    this.isAtRest = false;
    this.restTimer = 0;
    this.elapsedTime = 0;
    this.lastBounces = 0;
    
    const baseColor = new THREE.Color(customColorHex || '#00E5FF');
    this.tracerBaseR = baseColor.r !== undefined ? baseColor.r : 0.0;
    this.tracerBaseG = baseColor.g !== undefined ? baseColor.g : 0.9;
    this.tracerBaseB = baseColor.b !== undefined ? baseColor.b : 1.0;

    if (trajectoryPoints.length > 0) {
      const finalPoint = trajectoryPoints[trajectoryPoints.length - 1];
      this.landingRing.position.set(finalPoint.x, 0.03, finalPoint.z);
      if (this.landingRing.material) {
        this.landingRing.material.color.set(baseColor);
      }
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
      
      const br = this.tracerBaseR !== undefined ? this.tracerBaseR : 0.0;
      const bg = this.tracerBaseG !== undefined ? this.tracerBaseG : 0.9;
      const bb = this.tracerBaseB !== undefined ? this.tracerBaseB : 1.0;

      const r1 = Math.min(1.0, br * (0.8 + 0.2 * t1));
      const g1 = Math.min(1.0, bg * (0.8 + 0.2 * t1));
      const b1 = Math.min(1.0, bb * (0.8 + 0.2 * t1));

      const r2 = Math.min(1.0, br * (0.8 + 0.2 * t2));
      const g2 = Math.min(1.0, bg * (0.8 + 0.2 * t2));
      const b2 = Math.min(1.0, bb * (0.8 + 0.2 * t2));
      
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

  /**
   * Divot decal resources, built once and shared by every divot mesh.
   *
   * These used to be created per landing: a fresh <canvas> + CanvasTexture
   * for each divot, forever. Firefox only keeps a bounded number of 2D
   * canvas backing surfaces alive and discards older ones under pressure,
   * after which uploading from them fails with
   *   "WebGL warning: texSubImage: Failed to map source surface for upload"
   * and the texture samples uninitialized GPU memory -- the shredded
   * turf/confetti pattern on the green. Every divot is visually identical,
   * so one shared texture removes the churn entirely.
   */
  getDivotAssets() {
    if (this._divotAssets) return this._divotAssets;

    const divotGeo = new THREE.CircleGeometry(0.24, 24);
    divotGeo.rotateX(-Math.PI / 2);

    const dCanvas = document.createElement('canvas');
    dCanvas.width = 128;
    dCanvas.height = 128;
    // CPU-backed surface so the WebGL upload can't fail (see environment.js).
    const dCtx = dCanvas.getContext('2d', { willReadFrequently: true });

    const grad = dCtx.createRadialGradient(64, 64, 4, 64, 64, 60);
    grad.addColorStop(0, '#2d1808'); // Dark soil crater center
    grad.addColorStop(0.5, '#422812'); // Earth
    grad.addColorStop(0.85, '#2e591b'); // Bruised grass rim
    grad.addColorStop(1.0, 'rgba(0,0,0,0)');

    dCtx.fillStyle = grad;
    dCtx.fillRect(0, 0, 128, 128);

    const dTex = new THREE.CanvasTexture(dCanvas);
    dTex.colorSpace = THREE.SRGBColorSpace;

    const divotMat = new THREE.MeshBasicMaterial({
      map: dTex,
      transparent: true,
      opacity: 0.95,
      depthWrite: false,
      // Ground decals sit a hair above a large turf plane. polygonOffset
      // biases them in depth without moving them geometrically.
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1
    });

    this._divotAssets = { divotGeo, divotMat, dTex };
    return this._divotAssets;
  }

  createTurfDivot(x, z) {
    // 1. Realistic Soil Divot & Pitch Mark Decal (shared geometry/material)
    const { divotGeo, divotMat } = this.getDivotAssets();

    const divotMesh = new THREE.Mesh(divotGeo, divotMat);
    // Small per-divot height stagger: shots cluster around the same pin, so
    // these transparent decals overlap constantly and identical Y values
    // make coplanar quads fight. Range 0.0235..0.0273 stays clear of
    // cupRim (0.022) and landingRing (0.03).
    this.divotSeq = (this.divotSeq || 0) + 1;
    const slot = this.divotSeq % 20;
    divotMesh.position.set(x, 0.0235 + (slot * 0.0002), z);
    divotMesh.renderOrder = 2 + slot;
    divotMesh.scale.set(1.0, 1.0, 1.4); // Stretched in direction of impact
    this.scene.add(divotMesh);
    
    this.divots.push(divotMesh);
    if (this.divots.length > 20) {
      const old = this.divots.shift();
      this.scene.remove(old);
      // NOTE: geometry/material/texture are SHARED with every other divot --
      // disposing them here would blank the divots still on the green.
      // Removing the mesh from the scene is the whole cleanup.
    }
    
    // 2. Flying Turf / Dirt Particle Spray
    // Geometry is shared (identical quad); each particle keeps its own
    // material because they fade independently via material.opacity.
    if (!this._particleGeo) {
      this._particleGeo = new THREE.PlaneGeometry(0.12, 0.12);
      this._particleGeo.rotateX(-Math.PI / 2);
    }
    for (let i = 0; i < 10; i++) {
      const pMat = new THREE.MeshBasicMaterial({
        color: (i % 2 === 0) ? 0x3d2314 : 0x6e964b,
        transparent: true,
        opacity: 0.85
      });
      const pMesh = new THREE.Mesh(this._particleGeo, pMat);
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
        if (typeof this.onFlightEndCallback === 'function') {
          // Deferred: the callback typically starts the NEXT shot, and
          // launch() re-enters this object's state. Calling it inline would
          // mutate trajectory/isAnimating in the middle of the frame we are
          // still executing, wedging the ball permanently in isAnimating.
          const cb = this.onFlightEndCallback;
          setTimeout(() => cb(), 0);
        }
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
        // Dispose the per-particle material only. The geometry is shared by
        // every particle (see createTurfDivot) -- disposing it here would
        // break all future sprays.
        if (p.mesh.material) p.mesh.material.dispose();
        this.particles.splice(i, 1);
      }
    }
  }
}
