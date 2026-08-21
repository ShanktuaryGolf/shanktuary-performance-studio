// Dynamic 3D Driving Range with Single Adjustable Target Green

let activeTargetGreen = null;
let activeDistanceSign = null;
let activeYardageLine = null;
let signContext = null;
let signTexture = null;

export function setupEnvironment(scene, initialTargetYards = 150) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Volumetric Atmospheric Fog
    scene.background = new THREE.Color(0xa8d8ea);
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
    
    // 4. Create Single Dynamic Target Green
    createDynamicTargetGreen(scene, initialTargetYards);
    
    // 5. Background 3D Mountains
    loadBackgroundMountains(scene);
}

function createDynamicTargetGreen(scene, yardage) {
    const greenGroup = new THREE.Group();
    const radius = 10;
    
    // Outer Green Ring
    const outerGeo = new THREE.CylinderGeometry(radius, radius + 1.2, 0.1, 48);
    const outerMat = new THREE.MeshStandardMaterial({ 
        color: 0x2f6d1f, 
        roughness: 0.7 
    });
    const outerGreen = new THREE.Mesh(outerGeo, outerMat);
    outerGreen.position.y = 0.05;
    outerGreen.receiveShadow = true;
    greenGroup.add(outerGreen);
    
    // Inner Bullseye Ring (Neon Cyan Highlight)
    const innerGeo = new THREE.CylinderGeometry(radius * 0.45, radius * 0.45, 0.12, 32);
    const innerMat = new THREE.MeshStandardMaterial({ 
        color: 0x00E5FF, 
        roughness: 0.5,
        emissive: 0x00E5FF,
        emissiveIntensity: 0.25
    });
    const innerGreen = new THREE.Mesh(innerGeo, innerMat);
    innerGreen.position.y = 0.06;
    innerGreen.receiveShadow = true;
    greenGroup.add(innerGreen);
    
    // Center Cup Hole
    const cupGeo = new THREE.CylinderGeometry(0.6, 0.6, 0.15, 16);
    const cupMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
    const cup = new THREE.Mesh(cupGeo, cupMat);
    cup.position.y = 0.07;
    greenGroup.add(cup);
    
    // Pin Flagstick
    const poleGeo = new THREE.CylinderGeometry(0.04, 0.04, 3.2, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.y = 1.6;
    pole.castShadow = true;
    greenGroup.add(pole);
    
    // High-Vis Neon Red Flag
    const flagGeo = new THREE.PlaneGeometry(1.2, 0.7);
    const flagMat = new THREE.MeshStandardMaterial({ 
        color: 0xff1744, 
        side: THREE.DoubleSide,
        roughness: 0.4
    });
    const flag = new THREE.Mesh(flagGeo, flagMat);
    flag.position.set(0.6, 2.8, 0);
    flag.castShadow = true;
    greenGroup.add(flag);
    
    // Dynamic Yardage Sign Canvas
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
    signMesh.position.set(-radius - 6, 1.2, 0);
    signMesh.castShadow = true;
    greenGroup.add(signMesh);
    
    // Sign Post
    const postGeo = new THREE.CylinderGeometry(0.06, 0.06, 1.2);
    const postMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const post = new THREE.Mesh(postGeo, postMat);
    post.position.set(-radius - 6, 0.6, 0);
    greenGroup.add(post);
    
    // Fairway Yardage Hash Line
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
    
    // Set initial position
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
