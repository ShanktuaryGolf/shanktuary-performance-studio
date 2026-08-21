// Realistic Contoured PGA Golf Green Complex with Manicured Putting Surface & Fringe Collar

let activeTargetGreen = null;
let signContext = null;
let signTexture = null;

export function setupEnvironment(scene, initialTargetYards = 150) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Soft Atmospheric Fog
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
    
    // Tee Markers
    const markerGeo = new THREE.SphereGeometry(0.12, 16, 16);
    const markerMat = new THREE.MeshStandardMaterial({ color: 0x00E5FF, roughness: 0.3 });
    const markerL = new THREE.Mesh(markerGeo, markerMat);
    markerL.position.set(-2.5, 0.12, 0);
    scene.add(markerL);
    const markerR = new THREE.Mesh(markerGeo, markerMat);
    markerR.position.set(2.5, 0.12, 0);
    scene.add(markerR);
    
    // 4. Create Organic Contoured PGA Target Green
    createOrganicTargetGreen(scene, initialTargetYards, textureLoader);
    
    // 5. Background 3D Mountains
    loadBackgroundMountains(scene);
}

function createOrganicTargetGreen(scene, yardage, textureLoader) {
    const greenGroup = new THREE.Group();
    
    // 1. Create Organic Teardrop / Kidney Green Shape Curve
    const shape = new THREE.Shape();
    const w = 12; // Width radius
    const l = 16; // Length radius
    
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
    
    const fringeGeo = new THREE.ExtrudeGeometry(fringeShape, {
        depth: 0.08,
        bevelEnabled: true,
        bevelSegments: 4,
        steps: 1,
        bevelSize: 0.8,
        bevelThickness: 0.06
    });
    fringeGeo.rotateX(-Math.PI / 2);
    
    const fringeMat = new THREE.MeshStandardMaterial({
        color: 0x275e1a, // Darker green fringe collar
        roughness: 0.85
    });
    const fringeMesh = new THREE.Mesh(fringeGeo, fringeMat);
    fringeMesh.position.set(0, 0.02, 0);
    fringeMesh.receiveShadow = true;
    greenGroup.add(fringeMesh);
    
    // Manicured Putting Surface (Pristine Bentgrass with Mower Stripes)
    const greenGeo = new THREE.ExtrudeGeometry(shape, {
        depth: 0.12,
        bevelEnabled: true,
        bevelSegments: 4,
        steps: 1,
        bevelSize: 0.4,
        bevelThickness: 0.04
    });
    greenGeo.rotateX(-Math.PI / 2);
    
    // Create striped bentgrass putting texture
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
    greenMesh.position.set(0, 0.06, 0);
    greenMesh.receiveShadow = true;
    greenGroup.add(greenMesh);
    
    // 2. Center Cup Hole with White Plastic Liner
    const cupRimGeo = new THREE.RingGeometry(0.22, 0.28, 32);
    cupRimGeo.rotateX(-Math.PI / 2);
    const cupRimMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const cupRim = new THREE.Mesh(cupRimGeo, cupRimMat);
    cupRim.position.set(0, 0.185, 0);
    greenGroup.add(cupRim);
    
    const cupInteriorGeo = new THREE.CircleGeometry(0.22, 32);
    cupInteriorGeo.rotateX(-Math.PI / 2);
    const cupInteriorMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
    const cupInterior = new THREE.Mesh(cupInteriorGeo, cupInteriorMat);
    cupInterior.position.set(0, 0.184, 0);
    greenGroup.add(cupInterior);
    
    // 3. Pin Flagstick (Fiberglass Striped Stick)
    const poleGeo = new THREE.CylinderGeometry(0.035, 0.035, 3.2, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xfafafa, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.set(0, 1.7, 0);
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
    
    // 5. Fairway Yardage Hash Line
    const lineGeo = new THREE.PlaneGeometry(180, 0.5);
    lineGeo.rotateX(-Math.PI / 2);
    const lineMat = new THREE.MeshBasicMaterial({ 
        color: 0xffffff, 
        transparent: true, 
        opacity: 0.4 
    });
    const yardageLine = new THREE.Mesh(lineGeo, lineMat);
    yardageLine.position.y = 0.03;
    greenGroup.add(yardageLine);
    
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
