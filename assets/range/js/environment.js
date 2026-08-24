// High-Fidelity PGA Driving Range Environment with Concentric Target Greens & Dashed Centerline

let activeTargetGreen = null;
let signContext = null;
let signTexture = null;

export function setupEnvironment(scene, initialTargetYards = 150) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Atmospheric Fog
    scene.background = new THREE.Color(0x8ecae6);
    scene.fog = new THREE.FogExp2(0xbde0fe, 0.0010);
    
    // 2. High-Res Fairway Turf with immediate vibrant green base
    const terrainGeo = new THREE.PlaneGeometry(450, 800, 64, 64);
    terrainGeo.rotateX(-Math.PI / 2);
    
    const terrainMat = new THREE.MeshStandardMaterial({
        color: 0x3d7e2e,
        roughness: 0.82,
        metalness: 0.05
    });
    
    textureLoader.load('/range/textures/gen_fairway_tex.png', (tex) => {
        tex.wrapS = THREE.RepeatWrapping;
        tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(30, 60);
        tex.colorSpace = THREE.SRGBColorSpace;
        terrainMat.map = tex;
        terrainMat.needsUpdate = true;
    });
    
    const terrain = new THREE.Mesh(terrainGeo, terrainMat);
    terrain.position.set(0, 0, -250);
    terrain.receiveShadow = true;
    scene.add(terrain);
    
    // 3. Foreground Elevated Tee Box Mat
    createTeeBoxMat(scene);
    
    // 4. Dashed Fairway Centerline (Matching Reference Image)
    createDashedFairwayCenterline(scene);
    
    // 5. Concentric Bullseye Target Green (Outer White, Middle Blue, Inner Navy)
    createConcentricTargetGreen(scene, initialTargetYards);
    
    // 6. Realistic 3D Mountain Panorama Backdrop
    createMountainPanorama(scene);
}

function createTeeBoxMat(scene) {
    const teeGroup = new THREE.Group();
    const textureLoader = new THREE.TextureLoader();

    // 1. Manicured Natural Tee Deck (Blends naturally with organic fairway grass)
    const teeGeo = new THREE.CylinderGeometry(3.6, 3.8, 0.02, 32);
    const teeMat = new THREE.MeshStandardMaterial({
        color: 0x336d28,
        roughness: 0.88,
        metalness: 0.02
    });

    textureLoader.load('/range/textures/gen_fairway_tex.png', (tex) => {
        tex.wrapS = THREE.RepeatWrapping;
        tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(4, 4);
        tex.colorSpace = THREE.SRGBColorSpace;
        teeMat.map = tex;
        teeMat.needsUpdate = true;
    });

    const teeDeck = new THREE.Mesh(teeGeo, teeMat);
    teeDeck.position.set(0, 0.01, 0.0);
    teeDeck.receiveShadow = true;
    teeGroup.add(teeDeck);

    // 2. Classic White Championship Tee Markers flanking the tee box (Left & Right)
    const markerGeo = new THREE.SphereGeometry(0.08, 16, 16);
    const markerMat = new THREE.MeshStandardMaterial({
        color: 0xf0f4f8,
        roughness: 0.25,
        metalness: 0.1
    });

    const leftMarker = new THREE.Mesh(markerGeo, markerMat);
    leftMarker.position.set(-2.0, 0.08, 0.0);
    leftMarker.castShadow = true;
    leftMarker.receiveShadow = true;
    teeGroup.add(leftMarker);

    const rightMarker = new THREE.Mesh(markerGeo, markerMat);
    rightMarker.position.set(2.0, 0.08, 0.0);
    rightMarker.castShadow = true;
    rightMarker.receiveShadow = true;
    teeGroup.add(rightMarker);

    // 3. Subtle Natural Wooden Golf Tee under the ball
    const pegGeo = new THREE.CylinderGeometry(0.007, 0.004, 0.05, 8);
    const pegMat = new THREE.MeshStandardMaterial({
        color: 0xd2b48c,
        roughness: 0.6
    });
    const peg = new THREE.Mesh(pegGeo, pegMat);
    peg.position.set(0, 0.025, 0);
    peg.castShadow = true;
    teeGroup.add(peg);

    scene.add(teeGroup);
}

function createDashedFairwayCenterline(scene) {
    const centerGroup = new THREE.Group();
    
    // Crisp White Dashed Stripes along X=0 from Z=-2 to Z=-450
    const dashLength = 2.4; // 2.4 yards long
    const dashGap = 1.6;    // 1.6 yards gap
    const dashWidth = 0.38; // 0.38 yards wide

    const dashGeo = new THREE.PlaneGeometry(dashWidth, dashLength);
    dashGeo.rotateX(-Math.PI / 2);
    
    const dashMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.92,
        depthWrite: false
    });

    const totalDashes = Math.floor(450 / (dashLength + dashGap));
    const instancedDashes = new THREE.InstancedMesh(dashGeo, dashMat, totalDashes);
    const dummy = new THREE.Object3D();

    for (let i = 0; i < totalDashes; i++) {
        const zPos = -2.0 - i * (dashLength + dashGap);
        dummy.position.set(0, 0.018, zPos);
        dummy.updateMatrix();
        instancedDashes.setMatrixAt(i, dummy.matrix);
    }

    instancedDashes.instanceMatrix.needsUpdate = true;
    centerGroup.add(instancedDashes);
    
    scene.add(centerGroup);
}

function createConcentricTargetGreen(scene, yardage) {
    const greenGroup = new THREE.Group();
    
    // 1. Natural Short Grass Putting Green Surface (Organic Contour + High-Res Tiling Bentgrass Detail)
    const textureLoader = new THREE.TextureLoader();
    const greenTurfGeo = new THREE.PlaneGeometry(32.0, 32.0);
    greenTurfGeo.rotateX(-Math.PI / 2);

    const greenTurfMat = new THREE.MeshStandardMaterial({
        color: 0x488c38, // Natural rich manicured bentgrass (subtly lighter than 0x3d7e2e fairway)
        roughness: 0.86,
        metalness: 0.02,
        transparent: true,
        alphaTest: 0.02,
        side: THREE.DoubleSide
    });

    // Load High-Res Tiling Grass Detail Texture
    textureLoader.load('/range/textures/putting_green_detail.png', (grassTex) => {
        grassTex.wrapS = THREE.RepeatWrapping;
        grassTex.wrapT = THREE.RepeatWrapping;
        grassTex.repeat.set(6, 6);
        grassTex.colorSpace = THREE.SRGBColorSpace;
        greenTurfMat.map = grassTex;
        greenTurfMat.needsUpdate = true;
    });

    // Load Organic Golf Green Shape Mask (Matching TrackMan / YouTube Reference Contour)
    textureLoader.load('/range/textures/putting_green_mask.png', (maskTex) => {
        maskTex.wrapS = THREE.ClampToEdgeWrapping;
        maskTex.wrapT = THREE.ClampToEdgeWrapping;
        greenTurfMat.alphaMap = maskTex;
        greenTurfMat.needsUpdate = true;
    });

    const greenTurf = new THREE.Mesh(greenTurfGeo, greenTurfMat);
    greenTurf.position.set(0, 0.016, 0);
    greenTurf.receiveShadow = true;
    greenGroup.add(greenTurf);

    // 2. Center Cup & Flagstick
    const cupRimGeo = new THREE.RingGeometry(0.24, 0.32, 32);
    cupRimGeo.rotateX(-Math.PI / 2);
    const cupRimMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const cupRim = new THREE.Mesh(cupRimGeo, cupRimMat);
    cupRim.position.set(0, 0.022, 0);
    greenGroup.add(cupRim);

    // Flagstick Pole (Championship Fiberglass)
    const poleGeo = new THREE.CylinderGeometry(0.04, 0.04, 3.4, 16);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.2 });
    const pole = new THREE.Mesh(poleGeo, poleMat);
    pole.position.set(0, 1.7, 0);
    pole.castShadow = true;
    greenGroup.add(pole);

    // Flag Top Finial
    const finialGeo = new THREE.SphereGeometry(0.08, 12, 12);
    const finialMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.6, roughness: 0.2 });
    const finial = new THREE.Mesh(finialGeo, finialMat);
    finial.position.set(0, 3.4, 0);
    greenGroup.add(finial);

    // Flag
    const flagGeo = new THREE.PlaneGeometry(1.3, 0.8);
    const flagMat = new THREE.MeshStandardMaterial({
        color: 0xef4444,
        side: THREE.DoubleSide,
        roughness: 0.35
    });
    const flag = new THREE.Mesh(flagGeo, flagMat);
    flag.position.set(0.65, 3.0, 0);
    flag.castShadow = true;
    greenGroup.add(flag);

    // 5. Dynamic 3D Wooden Yardage Sign with Roof (Offset Left)
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 512;
    signCanvas.height = 256;
    signContext = signCanvas.getContext('2d');
    signTexture = new THREE.CanvasTexture(signCanvas);
    signTexture.colorSpace = THREE.SRGBColorSpace;
    
    const signContainerGroup = new THREE.Group();
    signContainerGroup.position.set(-16.0, 0, 0);
    signContainerGroup.rotation.y = 0.15; // Angled slightly towards tee box
    greenGroup.add(signContainerGroup);

    // Dynamic Yardage Text Plate on Sign Face (Transparent overlay so 3D wood planks show through)
    const textPlaneGeo = new THREE.PlaneGeometry(2.8, 1.38);
    const textPlaneMat = new THREE.MeshBasicMaterial({
        map: signTexture,
        transparent: true,
        side: THREE.FrontSide
    });
    const textPlane = new THREE.Mesh(textPlaneGeo, textPlaneMat);
    textPlane.position.set(0, 2.192, 0.08);
    signContainerGroup.add(textPlane);

    // Load 3D Wooden Sign with Roof GLB Model (Sketchfab PBR textures)
    if (typeof THREE.GLTFLoader === 'function') {
        const gltfLoader = new THREE.GLTFLoader();
        gltfLoader.load('/range/models/sign/wooden_sign_with_roof.glb', (gltf) => {
            const signModel = gltf.scene;
            const signScale = 1.6;
            signModel.scale.set(signScale, signScale, signScale);
            // Center model on local origin so board lines up with textPlane
            signModel.position.set(-2.45 * signScale, 0, 0.61 * signScale);
            signModel.traverse((child) => {
                if (child.isMesh) {
                    child.castShadow = false;
                    child.receiveShadow = true;
                    if (child.material) {
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        mats.forEach(m => {
                            m.roughness = 0.5;
                            m.metalness = 0.0;
                            if (m.color) {
                                m.color.setHex(0xffffff);
                            }
                            if (m.map) {
                                m.map.colorSpace = THREE.SRGBColorSpace;
                                m.emissive = new THREE.Color(0xffedd5);
                                m.emissiveMap = m.map;
                                m.emissiveIntensity = 0.65; // Brings out rich wood grain and slate tiles!
                            }
                        });
                    }
                }
            });
            signContainerGroup.add(signModel);
        }, undefined, (err) => {
            console.warn('[!] Could not load wooden sign model:', err);
        });
    }

    greenGroup.position.set(0, 0, -yardage);
    scene.add(greenGroup);

    activeTargetGreen = greenGroup;
    updateSignText(yardage);
}

function updateSignText(yardage) {
    if (!signContext || !signTexture) return;
    
    // 1. Clear to transparent so the 3D wooden planks and grain show through completely
    signContext.clearRect(0, 0, 512, 256);
    
    // Warm translucent amber backing plate with soft glow
    signContext.fillStyle = 'rgba(30, 20, 12, 0.28)';
    signContext.beginPath();
    signContext.roundRect(20, 20, 472, 216, 16);
    signContext.fill();

    // Vibrant gold border
    signContext.strokeStyle = '#f59e0b';
    signContext.lineWidth = 6;
    signContext.stroke();

    // Inner gold pin-stripe
    signContext.strokeStyle = 'rgba(253, 230, 138, 0.5)';
    signContext.lineWidth = 2;
    signContext.beginPath();
    signContext.roundRect(28, 28, 456, 200, 12);
    signContext.stroke();
    
    // Upper Label: "⛳ TARGET DISTANCE" with drop shadow
    signContext.shadowColor = '#000000';
    signContext.shadowBlur = 8;
    signContext.shadowOffsetX = 2;
    signContext.shadowOffsetY = 2;
    
    signContext.fillStyle = '#fde047';
    signContext.font = '800 26px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    signContext.textAlign = 'center';
    signContext.textBaseline = 'middle';
    signContext.fillText('⛳ TARGET DISTANCE', 256, 62);

    // Large Bold Painted White Yardage: "150 YDS"
    signContext.fillStyle = '#ffffff';
    signContext.font = '900 98px "Consolas", "Courier New", monospace';
    signContext.textAlign = 'center';
    signContext.textBaseline = 'middle';
    signContext.fillText(`${Math.round(yardage)} YDS`, 256, 148);
    
    // Reset shadow
    signContext.shadowColor = 'transparent';
    signContext.shadowBlur = 0;
    signContext.shadowOffsetX = 0;
    signContext.shadowOffsetY = 0;
    
    signTexture.needsUpdate = true;
}

export function setTargetDistance(yards) {
    if (activeTargetGreen) {
        activeTargetGreen.position.z = -yards;
        updateSignText(yards);
    }
}

function createMountainPanorama(scene) {
    // 1. Try GLB 3D Mountain Mesh
    if (typeof THREE.GLTFLoader === 'function') {
        const loader = new THREE.GLTFLoader();
        loader.load('/range/models/rangeMtns.glb', (gltf) => {
            const mountains = gltf.scene;
            mountains.position.set(0, -2, -470);
            mountains.scale.set(22, 18, 20);
            
            mountains.traverse((child) => {
                if (child.isMesh) {
                    child.material = new THREE.MeshStandardMaterial({
                        color: 0x64748b,
                        roughness: 0.95,
                        metalness: 0.05
                    });
                }
            });
            
            scene.add(mountains);
        }, undefined, () => {
            createProceduralMountainWall(scene);
        });
    } else {
        createProceduralMountainWall(scene);
    }
}

function createProceduralMountainWall(scene) {
    const mtnGeo = new THREE.PlaneGeometry(600, 140, 64, 16);
    const pos = mtnGeo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
        const x = pos.getX(i);
        const y = pos.getY(i);
        if (y > -50) {
            const noise = Math.sin(x * 0.03) * 25 + Math.cos(x * 0.07) * 15;
            pos.setY(i, y + noise);
        }
    }
    mtnGeo.computeVertexNormals();

    const mtnMat = new THREE.MeshStandardMaterial({
        color: 0x52667a,
        roughness: 0.9,
        metalness: 0.05,
        side: THREE.DoubleSide
    });
    const mtnMesh = new THREE.Mesh(mtnGeo, mtnMat);
    mtnMesh.position.set(0, 45, -480);
    scene.add(mtnMesh);
}
