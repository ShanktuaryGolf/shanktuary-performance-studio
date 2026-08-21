// Procedural Fairway, Target Greens, Distance Markers & Water Hazard

export function setupEnvironment(scene) {
    // 1. Procedural Tournament Striped Fairway
    const terrainGeometry = new THREE.PlaneGeometry(300, 600, 32, 32);
    terrainGeometry.rotateX(-Math.PI / 2);
    
    // Create striped mowing pattern on canvas
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#2e5d1e';
    ctx.fillRect(0, 0, 512, 512);
    ctx.fillStyle = '#264f19';
    for (let i = 0; i < 512; i += 32) {
        ctx.fillRect(i, 0, 16, 512);
    }
    
    const stripeTexture = new THREE.CanvasTexture(canvas);
    stripeTexture.wrapS = THREE.RepeatWrapping;
    stripeTexture.wrapT = THREE.RepeatWrapping;
    stripeTexture.repeat.set(15, 30);
    
    const terrainMaterial = new THREE.MeshStandardMaterial({
        map: stripeTexture,
        roughness: 0.85,
        metalness: 0.05
    });
    
    const terrain = new THREE.Mesh(terrainGeometry, terrainMaterial);
    terrain.position.set(0, 0, -250); // Centered down range
    terrain.receiveShadow = true;
    scene.add(terrain);
    
    // Tee Box Pad at (0, 0.02, 0)
    const teeGeo = new THREE.BoxGeometry(6, 0.04, 6);
    const teeMat = new THREE.MeshStandardMaterial({ color: 0x1f4414, roughness: 0.9 });
    const teePad = new THREE.Mesh(teeGeo, teeMat);
    teePad.position.set(0, 0.02, 0);
    teePad.receiveShadow = true;
    scene.add(teePad);
    
    // 2. Target Greens at 50, 100, 150, 200, 250, 300 yards
    const distances = [50, 100, 150, 200, 250, 300];
    distances.forEach(yd => {
        createTargetGreen(scene, yd);
    });
    
    // 3. Water Hazard at 175 yards with Stone Bridge
    createWaterHazard(scene, 175);
}

function createTargetGreen(scene, yardage) {
    const zDist = yardage; // In yards down -Z
    
    // Raised circular green
    const greenRadius = 8 + (yardage * 0.02);
    const greenGeo = new THREE.CylinderGeometry(greenRadius, greenRadius + 1.5, 0.15, 32);
    const greenMat = new THREE.MeshStandardMaterial({ 
        color: 0x3d7e26, 
        roughness: 0.7 
    });
    const green = new THREE.Mesh(greenGeo, greenMat);
    green.position.set(0, 0.08, -zDist);
    green.receiveShadow = true;
    scene.add(green);
    
    // White Flagstick with Red Pin Flag
    const poleGeo = new THREE.CylinderGeometry(0.04, 0.04, 3, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.set(0, 1.5, -zDist);
    pole.castShadow = true;
    scene.add(pole);
    
    const flagGeo = new THREE.PlaneGeometry(1.0, 0.6);
    const flagMat = new THREE.MeshStandardMaterial({ color: 0xff1744, side: THREE.DoubleSide });
    const flag = new THREE.Mesh(flagGeo, flagMat);
    flag.position.set(0.5, 2.7, -zDist);
    flag.castShadow = true;
    scene.add(flag);
    
    // Glowing Neon Distance Board on left side
    createDistanceSign(scene, -greenRadius - 5, -zDist, `${yardage} YDS`);
    
    // Sand Bunker around right side
    const bunkerGeo = new THREE.CylinderGeometry(5, 6, 0.08, 16);
    const bunkerMat = new THREE.MeshStandardMaterial({ color: 0xd9c58b, roughness: 1.0 });
    const bunker = new THREE.Mesh(bunkerGeo, bunkerMat);
    bunker.position.set(greenRadius + 3, 0.05, -zDist + 4);
    bunker.receiveShadow = true;
    scene.add(bunker);
}

function createDistanceSign(scene, x, z, text) {
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 256;
    signCanvas.height = 128;
    const sCtx = signCanvas.getContext('2d');
    sCtx.fillStyle = '#101116';
    sCtx.fillRect(0, 0, 256, 128);
    sCtx.strokeStyle = '#00E5FF';
    sCtx.lineWidth = 6;
    sCtx.strokeRect(4, 4, 248, 120);
    sCtx.fillStyle = '#00FF66';
    sCtx.font = 'bold 48px monospace';
    sCtx.textAlign = 'center';
    sCtx.textBaseline = 'middle';
    sCtx.fillText(text, 128, 64);
    
    const texture = new THREE.CanvasTexture(signCanvas);
    const signGeo = new THREE.BoxGeometry(3, 1.5, 0.2);
    const signMat = new THREE.MeshStandardMaterial({ 
        map: texture,
        roughness: 0.3
    });
    const sign = new THREE.Mesh(signGeo, signMat);
    sign.position.set(x, 1.0, z);
    sign.castShadow = true;
    scene.add(sign);
    
    // Sign posts
    const postGeo = new THREE.CylinderGeometry(0.06, 0.06, 1.0);
    const postMat = new THREE.MeshStandardMaterial({ color: 0x333333 });
    const postL = new THREE.Mesh(postGeo, postMat);
    postL.position.set(x - 1, 0.5, z);
    scene.add(postL);
    const postR = new THREE.Mesh(postGeo, postMat);
    postR.position.set(x + 1, 0.5, z);
    scene.add(postR);
}

function createWaterHazard(scene, zDist) {
    // Water pond geometry
    const waterGeo = new THREE.PlaneGeometry(50, 25);
    waterGeo.rotateX(-Math.PI / 2);
    const waterMat = new THREE.MeshStandardMaterial({ 
        color: 0x0066aa, 
        roughness: 0.1,
        metalness: 0.8,
        transparent: true,
        opacity: 0.85
    });
    const water = new THREE.Mesh(waterGeo, waterMat);
    water.position.set(-15, 0.04, -zDist);
    scene.add(water);
    
    // Stone Bridge crossing the hazard
    const bridgeGeo = new THREE.BoxGeometry(6, 0.4, 20);
    const bridgeMat = new THREE.MeshStandardMaterial({ color: 0x6e6e6e, roughness: 0.9 });
    const bridge = new THREE.Mesh(bridgeGeo, bridgeMat);
    bridge.position.set(8, 0.4, -zDist);
    bridge.castShadow = true;
    bridge.receiveShadow = true;
    scene.add(bridge);
}
