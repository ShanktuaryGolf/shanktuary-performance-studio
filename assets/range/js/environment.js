// Realistic PGA Driving Range Environment with Tour Alignment Rods & Fairway Centerline

let activeTargetGreen = null;
let signContext = null;
let signTexture = null;

export function setupEnvironment(scene, initialTargetYards = 150) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Atmospheric Fog
    scene.background = new THREE.Color(0xa8d8ea);
    scene.fog = new THREE.FogExp2(0xa8d8ea, 0.0012);
    
    // 2. High-Res Fairway Turf with Normal Depth Mapping
    const grassTex = textureLoader.load('/range/textures/gen_fairway_tex.png');
    grassTex.wrapS = THREE.RepeatWrapping;
    grassTex.wrapT = THREE.RepeatWrapping;
    grassTex.repeat.set(25, 50);
    
    const grassNormal = textureLoader.load('/range/textures/gen_fairway_map.png');
    grassNormal.wrapS = THREE.RepeatWrapping;
    grassNormal.wrapT = THREE.RepeatWrapping;
    grassNormal.repeat.set(25, 50);
    
    const terrainGeo = new THREE.PlaneGeometry(350, 750, 64, 64);
    terrainGeo.rotateX(-Math.PI / 2);
    
    const terrainMat = new THREE.MeshStandardMaterial({
        map: grassTex,
        normalMap: grassNormal,
        roughness: 0.85,
        metalness: 0.05
    });
    
    const terrain = new THREE.Mesh(terrainGeo, terrainMat);
    terrain.position.set(0, 0, -250);
    terrain.receiveShadow = true;
    scene.add(terrain);
    
    // 3. Tour Hitting Station (Alignment Rails & Practice Ball Pyramid)
    createTourHittingStation(scene);
    
    // 4. Fairway Centerline & Target Alignment Grid (PGA ShotLink Style)
    createFairwayCenterLine(scene);
    
    // 5. Create Organic Contoured PGA Target Green
    createOrganicTargetGreen(scene, initialTargetYards, textureLoader);
    
    // 6. Background 3D Mountains
    loadBackgroundMountains(scene);
}

function createDimpledBallGeometry(radius, detail = 48) {
    const geometry = new THREE.SphereGeometry(radius, detail, detail);
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
    
    const dimpleAngleThreshold = 0.088;
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
            ao = 0.76 + 0.24 * ratio;
        }
        
        colors.push(ao, ao, ao);
    }
    
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geometry.computeVertexNormals();
    return geometry;
}

function createGolfBallTexture() {
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
    
    // Putting Alignment Arrow Stamp: ◄—— PRACTICE ——►
    ctx.fillStyle = '#0f172a';
    ctx.font = 'bold 22px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('◄—— PRACTICE ——►', size / 2, size / 2 - 32);
    
    // Tournament Player Number (Red '1' in tour style)
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

function createTourHittingStation(scene) {
    const stationGroup = new THREE.Group();
    
    // Two Sleek Wooden / Composite Guide Rails flanking the ball (matching dr.jpg)
    const railGeo = new THREE.BoxGeometry(0.12, 0.06, 2.4);
    const railMat = new THREE.MeshStandardMaterial({
        color: 0x4a5d43, // Deep olive/slate guide rail
        roughness: 0.7,
        metalness: 0.1
    });
    
    const leftRail = new THREE.Mesh(railGeo, railMat);
    leftRail.position.set(-0.85, 0.03, 0);
    leftRail.castShadow = true;
    leftRail.receiveShadow = true;
    stationGroup.add(leftRail);
    
    const rightRail = new THREE.Mesh(railGeo, railMat);
    rightRail.position.set(0.85, 0.03, 0);
    rightRail.castShadow = true;
    rightRail.receiveShadow = true;
    stationGroup.add(rightRail);
    
    // Tour Practice Ball Pyramid (4-Tier Stacking with authentic Close-Packing Geometry)
    const ballRadius = 0.043; // Standard golf ball radius ~42.7mm
    const ballDiameter = ballRadius * 2;
    const pyramidX = 1.15;
    const pyramidZ = 0.40;
    const trayY = 0.012;
    
    // 1. Tour Pyramid Tray (Matte Slate / Dark Metal Base)
    const trayWidth = ballDiameter * 4 + 0.035;
    const trayGeo = new THREE.BoxGeometry(trayWidth, 0.02, trayWidth);
    const trayMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        roughness: 0.8,
        metalness: 0.2
    });
    const tray = new THREE.Mesh(trayGeo, trayMat);
    tray.position.set(pyramidX, trayY, pyramidZ);
    tray.receiveShadow = true;
    tray.castShadow = true;
    stationGroup.add(tray);
    
    // Tray Beveled Inner Lip / Rim
    const rimGeo = new THREE.BoxGeometry(trayWidth + 0.015, 0.028, trayWidth + 0.015);
    const rimMat = new THREE.MeshStandardMaterial({
        color: 0x0f172a,
        roughness: 0.7,
        metalness: 0.3
    });
    const rim = new THREE.Mesh(rimGeo, rimMat);
    rim.position.set(pyramidX, trayY + 0.004, pyramidZ);
    stationGroup.add(rim);
    
    // 2. High-Detail Dimpled Golf Ball Geometry & Material
    const ballGeo = createDimpledBallGeometry(ballRadius, 48);
    const ballTex = createGolfBallTexture();
    const ballMat = new THREE.MeshStandardMaterial({
        map: ballTex,
        vertexColors: true,
        roughness: 0.18,
        metalness: 0.05
    });
    
    // 3. Compute Close-Packed Stacking Coordinates (4x4 -> 3x3 -> 2x2 -> 1x1 = 30 balls)
    const ballTransforms = [];
    const layers = [4, 3, 2, 1];
    const verticalStep = ballDiameter * 0.7071; // Close-packing vertical delta
    
    layers.forEach((gridSize, layerIndex) => {
        const layerY = trayY + 0.014 + ballRadius + layerIndex * verticalStep;
        for (let i = 0; i < gridSize; i++) {
            for (let j = 0; j < gridSize; j++) {
                const posX = pyramidX + (i - (gridSize - 1) / 2) * ballDiameter;
                const posZ = pyramidZ + (j - (gridSize - 1) / 2) * ballDiameter;
                ballTransforms.push({ x: posX, y: layerY, z: posZ });
            }
        }
    });
    
    // 4. Instanced Mesh for all Balls (1 Single GPU Draw Call with Random Organic Rotations)
    const instancedBalls = new THREE.InstancedMesh(ballGeo, ballMat, ballTransforms.length);
    instancedBalls.castShadow = true;
    instancedBalls.receiveShadow = true;
    
    const dummy = new THREE.Object3D();
    ballTransforms.forEach((pos, idx) => {
        dummy.position.set(pos.x, pos.y, pos.z);
        // Realistic random 3D orientation for alignment stamps and numbers
        dummy.rotation.set(
            Math.random() * Math.PI * 2,
            Math.random() * Math.PI * 2,
            Math.random() * Math.PI * 2
        );
        dummy.updateMatrix();
        instancedBalls.setMatrixAt(idx, dummy.matrix);
    });
    
    instancedBalls.instanceMatrix.needsUpdate = true;
    stationGroup.add(instancedBalls);
    
    scene.add(stationGroup);
}

function createFairwayCenterLine(scene) {
    const centerGroup = new THREE.Group();
    
    // Crisp Solid/Dashed White Centerline (matching dr.jpg)
    const centerLineGeo = new THREE.PlaneGeometry(0.4, 400);
    centerLineGeo.rotateX(-Math.PI / 2);
    
    const centerLineMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.85,
        depthWrite: false
    });
    
    const centerLine = new THREE.Mesh(centerLineGeo, centerLineMat);
    centerLine.position.set(0, 0.015, -200);
    centerGroup.add(centerLine);
    
    // Lateral Corridor Reference Guidelines (+/- 10 yards, +/- 20 yards)
    const corridorMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.18,
        depthWrite: false
    });
    
    [-20, -10, 10, 20].forEach(xOffset => {
        const lineGeo = new THREE.PlaneGeometry(0.12, 400);
        lineGeo.rotateX(-Math.PI / 2);
        const lineMesh = new THREE.Mesh(lineGeo, corridorMat);
        lineMesh.position.set(xOffset, 0.014, -200);
        centerGroup.add(lineMesh);
    });
    
    // 50-Yard Interval Cross Arcs across the range (50, 100, 150, 200, 250, 300, 350)
    const intervalDistances = [50, 100, 150, 200, 250, 300, 350];
    intervalDistances.forEach(dist => {
        const crossGeo = new THREE.PlaneGeometry(50, 0.25);
        crossGeo.rotateX(-Math.PI / 2);
        const crossMat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.25,
            depthWrite: false
        });
        const crossMesh = new THREE.Mesh(crossGeo, crossMat);
        crossMesh.position.set(0, 0.014, -dist);
        centerGroup.add(crossMesh);
    });
    
    scene.add(centerGroup);
}

function createOrganicTargetGreen(scene, yardage, textureLoader) {
    const greenGroup = new THREE.Group();
    
    // 1. Organic Teardrop / Kidney Green Shape
    const shape = new THREE.Shape();
    const w = 12;
    const l = 16;
    
    shape.moveTo(0, l);
    shape.bezierCurveTo(w * 0.9, l * 0.9, w * 1.1, l * 0.2, w * 0.8, -l * 0.4);
    shape.bezierCurveTo(w * 0.5, -l * 0.9, -w * 0.5, -l * 0.9, -w * 0.8, -l * 0.4);
    shape.bezierCurveTo(-w * 1.1, l * 0.2, -w * 0.9, l * 0.9, 0, l);
    
    // Outer Fringe Collar (Second Cut Grass)
    const fringeShape = new THREE.Shape();
    const fw = w + 2.5;
    const fl = l + 2.5;
    fringeShape.moveTo(0, fl);
    fringeShape.bezierCurveTo(fw * 0.9, fl * 0.9, fw * 1.1, fl * 0.2, fw * 0.8, -fl * 0.4);
    fringeShape.bezierCurveTo(fw * 0.5, -fl * 0.9, -fw * 0.5, -fl * 0.9, -fw * 0.8, -fl * 0.4);
    fringeShape.bezierCurveTo(-fw * 1.1, fl * 0.2, -fw * 0.9, fl * 0.9, 0, fl);
    
    const fringeGeo = new THREE.ShapeGeometry(fringeShape);
    fringeGeo.rotateX(-Math.PI / 2);
    
    const fringeMat = new THREE.MeshStandardMaterial({
        color: 0x275e1a,
        roughness: 0.85
    });
    const fringeMesh = new THREE.Mesh(fringeGeo, fringeMat);
    fringeMesh.position.set(0, 0.016, 0);
    fringeMesh.receiveShadow = true;
    greenGroup.add(fringeMesh);
    
    // Manicured Putting Surface (Pristine Bentgrass with Mower Stripes)
    const greenGeo = new THREE.ShapeGeometry(shape);
    greenGeo.rotateX(-Math.PI / 2);
    
    const greenCanvas = document.createElement('canvas');
    greenCanvas.width = 512;
    greenCanvas.height = 512;
    const gCtx = greenCanvas.getContext('2d');
    gCtx.fillStyle = '#4a992d';
    gCtx.fillRect(0, 0, 512, 512);
    gCtx.fillStyle = '#428c27';
    for (let i = 0; i < 512; i += 32) {
        gCtx.fillRect(i, 0, 16, 512);
    }
    const greenTex = new THREE.CanvasTexture(greenCanvas);
    greenTex.wrapS = THREE.RepeatWrapping;
    greenTex.wrapT = THREE.RepeatWrapping;
    greenTex.repeat.set(4, 4);
    
    const greenMat = new THREE.MeshStandardMaterial({
        map: greenTex,
        roughness: 0.65,
        metalness: 0.05
    });
    const greenMesh = new THREE.Mesh(greenGeo, greenMat);
    greenMesh.position.set(0, 0.018, 0);
    greenMesh.receiveShadow = true;
    greenGroup.add(greenMesh);
    
    // 2. Center Cup Hole with White Plastic Liner
    const cupRimGeo = new THREE.RingGeometry(0.22, 0.28, 32);
    cupRimGeo.rotateX(-Math.PI / 2);
    const cupRimMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const cupRim = new THREE.Mesh(cupRimGeo, cupRimMat);
    cupRim.position.set(0, 0.022, 0);
    greenGroup.add(cupRim);
    
    const cupInteriorGeo = new THREE.CircleGeometry(0.22, 32);
    cupInteriorGeo.rotateX(-Math.PI / 2);
    const cupInteriorMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
    const cupInterior = new THREE.Mesh(cupInteriorGeo, cupInteriorMat);
    cupInterior.position.set(0, 0.021, 0);
    greenGroup.add(cupInterior);
    
    // 3. Pin Flagstick (Fiberglass Striped Stick)
    const poleGeo = new THREE.CylinderGeometry(0.035, 0.035, 3.2, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xfafafa, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.set(0, 1.6, 0);
    pole.castShadow = true;
    greenGroup.add(pole);
    
    // High-Vis Red Tournament Pin Flag
    const flagGeo = new THREE.PlaneGeometry(1.2, 0.75);
    const flagMat = new THREE.MeshStandardMaterial({ 
        color: 0xef4444, 
        side: THREE.DoubleSide,
        roughness: 0.4
    });
    const flag = new THREE.Mesh(flagGeo, flagMat);
    flag.position.set(0.6, 2.9, 0);
    flag.castShadow = true;
    greenGroup.add(flag);
    
    // 4. Dynamic Yardage Sign Board (Offset Left)
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 256;
    signCanvas.height = 128;
    signContext = signCanvas.getContext('2d');
    signTexture = new THREE.CanvasTexture(signCanvas);
    
    const signGeo = new THREE.BoxGeometry(3.6, 2.0, 0.2);
    const signMat = new THREE.MeshStandardMaterial({ 
        map: signTexture,
        roughness: 0.3
    });
    const signMesh = new THREE.Mesh(signGeo, signMat);
    signMesh.position.set(-w - 6, 1.2, 0);
    signMesh.castShadow = true;
    greenGroup.add(signMesh);
    
    const postGeo = new THREE.CylinderGeometry(0.06, 0.06, 1.2);
    const postMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const post = new THREE.Mesh(postGeo, postMat);
    post.position.set(-w - 6, 0.6, 0);
    greenGroup.add(post);
    
    // Set position down range
    greenGroup.position.set(0, 0, -yardage);
    scene.add(greenGroup);
    
    activeTargetGreen = greenGroup;
    updateSignText(yardage);
}

function updateSignText(yardage) {
    if (!signContext || !signTexture) return;
    
    signContext.fillStyle = '#101116';
    signContext.fillRect(0, 0, 256, 128);
    signContext.strokeStyle = '#00E5FF';
    signContext.lineWidth = 6;
    signContext.strokeRect(4, 4, 248, 120);
    
    signContext.fillStyle = '#00FF66';
    signContext.font = 'bold 50px monospace';
    signContext.textAlign = 'center';
    signContext.textBaseline = 'middle';
    signContext.fillText(`${Math.round(yardage)} YDS`, 128, 64);
    
    signTexture.needsUpdate = true;
}

export function setTargetDistance(yards) {
    if (activeTargetGreen) {
        activeTargetGreen.position.z = -yards;
        updateSignText(yards);
    }
}

function loadBackgroundMountains(scene) {
    if (typeof THREE.GLTFLoader === 'function') {
        const loader = new THREE.GLTFLoader();
        loader.load('/range/models/rangeMtns.glb', (gltf) => {
            const mountains = gltf.scene;
            mountains.position.set(0, -5, -450);
            mountains.scale.set(15, 15, 15);
            
            mountains.traverse((child) => {
                if (child.isMesh) {
                    child.material = new THREE.MeshStandardMaterial({
                        color: 0x5a7580,
                        roughness: 0.95,
                        metalness: 0.05
                    });
                }
            });
            
            scene.add(mountains);
        }, undefined, (err) => {
            console.warn('[!] Mountain GLB fallback:', err);
        });
    }
}
