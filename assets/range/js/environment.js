// Professional 3D Driving Range Environment (Clean Target Greens, No Sand Traps, Background Mountains)

export function setupEnvironment(scene) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Volumetric Atmospheric Fog
    scene.background = new THREE.Color(0xa8d8ea); // Soft morning sky
    scene.fog = new THREE.FogExp2(0xa8d8ea, 0.0012);
    
    // 2. High-Res Fairway Turf with Normal Mapping
    const grassTex = textureLoader.load('/range/textures/gen_fairway_tex.png');
    grassTex.wrapS = THREE.RepeatWrapping;
    grassTex.wrapT = THREE.RepeatWrapping;
    grassTex.repeat.set(25, 50);
    
    const grassNormal = textureLoader.load('/range/textures/gen_fairway_map.png');
    grassNormal.wrapS = THREE.RepeatWrapping;
    grassNormal.wrapT = THREE.RepeatWrapping;
    grassNormal.repeat.set(25, 50);
    
    const terrainGeo = new THREE.PlaneGeometry(350, 700, 64, 64);
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
    
    // 3. Tee Box Hitting Pad
    const teeGeo = new THREE.BoxGeometry(8, 0.05, 6);
    const teeMat = new THREE.MeshStandardMaterial({ 
        color: 0x1f4a14, 
        roughness: 0.9 
    });
    const teePad = new THREE.Mesh(teeGeo, teeMat);
    teePad.position.set(0, 0.025, 0);
    teePad.receiveShadow = true;
    scene.add(teePad);
    
    // Tee Divider Markers
    const markerGeo = new THREE.SphereGeometry(0.12, 16, 16);
    const markerMat = new THREE.MeshStandardMaterial({ color: 0x00E5FF, roughness: 0.3 });
    const markerL = new THREE.Mesh(markerGeo, markerMat);
    markerL.position.set(-2.5, 0.12, 0);
    scene.add(markerL);
    const markerR = new THREE.Mesh(markerGeo, markerMat);
    markerR.position.set(2.5, 0.12, 0);
    scene.add(markerR);
    
    // 4. Clean PGA Target Greens (No Sand Traps)
    const targets = [
        { yd: 50, radius: 7, color: 0x4CAF50 },
        { yd: 100, radius: 9, color: 0x2196F3 },
        { yd: 150, radius: 11, color: 0xFFC107 },
        { yd: 200, radius: 12, color: 0xFF5722 },
        { yd: 250, radius: 14, color: 0x9C27B0 },
        { yd: 300, radius: 16, color: 0x00E5FF }
    ];
    
    targets.forEach(t => {
        createTargetGreen(scene, t.yd, t.radius, t.color);
    });
    
    // 5. Yardage Hash Lines across the Fairway (50, 100, 150, 200, 250, 300)
    targets.forEach(t => {
        createYardageLine(scene, t.yd);
    });
    
    // 6. Background 3D Mountain Range
    loadBackgroundMountains(scene);
}

function createTargetGreen(scene, yardage, radius, ringColor) {
    const zDist = yardage;
    
    // Outer Target Green Ring
    const outerGeo = new THREE.CylinderGeometry(radius, radius + 1.2, 0.1, 48);
    const outerMat = new THREE.MeshStandardMaterial({ 
        color: 0x2f6d1f, 
        roughness: 0.7 
    });
    const outerGreen = new THREE.Mesh(outerGeo, outerMat);
    outerGreen.position.set(0, 0.05, -zDist);
    outerGreen.receiveShadow = true;
    scene.add(outerGreen);
    
    // Inner Bullseye Target Ring
    const innerGeo = new THREE.CylinderGeometry(radius * 0.45, radius * 0.45, 0.12, 32);
    const innerMat = new THREE.MeshStandardMaterial({ 
        color: ringColor, 
        roughness: 0.5,
        emissive: ringColor,
        emissiveIntensity: 0.2
    });
    const innerGreen = new THREE.Mesh(innerGeo, innerMat);
    innerGreen.position.set(0, 0.06, -zDist);
    innerGreen.receiveShadow = true;
    scene.add(innerGreen);
    
    // Center Cup Hole
    const cupGeo = new THREE.CylinderGeometry(0.6, 0.6, 0.15, 16);
    const cupMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
    const cup = new THREE.Mesh(cupGeo, cupMat);
    cup.position.set(0, 0.07, -zDist);
    scene.add(cup);
    
    // Pin Flagstick (White & Striped)
    const poleGeo = new THREE.CylinderGeometry(0.04, 0.04, 3.2, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.set(0, 1.6, -zDist);
    pole.castShadow = true;
    scene.add(pole);
    
    // High-Vis Flag
    const flagGeo = new THREE.PlaneGeometry(1.2, 0.7);
    const flagMat = new THREE.MeshStandardMaterial({ 
        color: ringColor, 
        side: THREE.DoubleSide,
        roughness: 0.4
    });
    const flag = new THREE.Mesh(flagGeo, flagMat);
    flag.position.set(0.6, 2.8, -zDist);
    flag.castShadow = true;
    scene.add(flag);
    
    // Yardage Target Board (Offset left)
    createDistanceSign(scene, -radius - 6, -zDist, `${yardage}`);
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
    sCtx.fillStyle = '#FFFFFF';
    sCtx.font = 'bold 54px monospace';
    sCtx.textAlign = 'center';
    sCtx.textBaseline = 'middle';
    sCtx.fillText(text, 128, 64);
    
    const texture = new THREE.CanvasTexture(signCanvas);
    const signGeo = new THREE.BoxGeometry(3.2, 1.8, 0.2);
    const signMat = new THREE.MeshStandardMaterial({ 
        map: texture,
        roughness: 0.3
    });
    const sign = new THREE.Mesh(signGeo, signMat);
    sign.position.set(x, 1.2, z);
    sign.castShadow = true;
    scene.add(sign);
    
    // Post
    const postGeo = new THREE.CylinderGeometry(0.06, 0.06, 1.2);
    const postMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const post = new THREE.Mesh(postGeo, postMat);
    post.position.set(x, 0.6, z);
    scene.add(post);
}

function createYardageLine(scene, yardage) {
    const lineGeo = new THREE.PlaneGeometry(160, 0.4);
    lineGeo.rotateX(-Math.PI / 2);
    const lineMat = new THREE.MeshBasicMaterial({ 
        color: 0xffffff, 
        transparent: true, 
        opacity: 0.35 
    });
    const line = new THREE.Mesh(lineGeo, lineMat);
    line.position.set(0, 0.03, -yardage);
    scene.add(line);
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
            console.log('[✓] Background 3D mountains loaded successfully!');
        }, undefined, (err) => {
            console.warn('[!] Mountain GLB not loaded, using natural horizon:', err);
        });
    }
}
