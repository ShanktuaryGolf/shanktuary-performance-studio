import { createStudioTurf, createStudioSky, createStudioMountains } from './studio_environment.js';
import { createStudioRangeDecor, studioColor } from './studio_decor.js';
import { createStudioGolfFlag } from './studio_flag.js';

// High-Fidelity PGA Driving Range Environment with Concentric Target Greens & Dashed Centerline

let activeTargetGreen = null;
let targetFlag = null;

export function updateEnvironmentWind(seconds) {
    targetFlag?.update(seconds);
}
let signContext = null;
let signTexture = null;
let teeBoxGroup = null;
let fairwayCenterline = null;
let studioDistanceGuides = null;

export function setupEnvironment(scene, initialTargetYards = 150) {
    const textureLoader = new THREE.TextureLoader();
    
    // 1. Sky and Atmospheric Fog
    createStudioSky(scene);
    
    // 2. High-Res Fairway Turf with immediate vibrant green base
    const terrainGeo = new THREE.PlaneGeometry(450, 800, 64, 64);
    terrainGeo.rotateX(-Math.PI / 2);
    
    const terrainMat = createStudioTurf(textureLoader);

    const terrain = new THREE.Mesh(terrainGeo, terrainMat);
    terrain.name = 'range-fairway';
    terrain.position.set(0, 0, -250);
    terrain.receiveShadow = true;
    scene.add(terrain);
    
    // 3. Foreground Elevated Tee Box Mat
    createTeeBoxMat(scene);
    
    // 4. Dashed Fairway Centerline (Matching Reference Image)
    // Keep a subtle aiming reference rather than the former runway-wide stripe.
    createDashedFairwayCenterline(scene);
    
    // 5. Concentric Bullseye Target Green (Outer White, Middle Blue, Inner Navy)
    createConcentricTargetGreen(scene, initialTargetYards);
    
    // 6. Realistic 3D Mountain Panorama Backdrop
    createStudioMountains(scene);
    studioDistanceGuides = createStudioRangeDecor(scene, teeBoxGroup);
}

function createTeeBoxMat(scene) {
    const teeGroup = new THREE.Group();
    teeGroup.name = 'range-tee';
    teeBoxGroup = teeGroup;
    const textureLoader = new THREE.TextureLoader();

    // A raised, rectangular hitting mat and stone apron ground the tee bay.
    const surround = new THREE.Mesh(new THREE.BoxGeometry(7.2,.10,4.8),
        new THREE.MeshStandardMaterial({color:0x79776b,roughness:.98}));
    surround.position.set(0,-.045,.3); surround.receiveShadow=true; teeGroup.add(surround);
    const teeDeck = new THREE.Mesh(new THREE.BoxGeometry(4.8,.075,3.8), createStudioTurf(textureLoader,{tee:true}));
    teeDeck.position.set(0,-.0175,.3); teeDeck.receiveShadow=true; teeGroup.add(teeDeck);

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
    leftMarker.visible = false;
    teeGroup.add(leftMarker);

    const rightMarker = new THREE.Mesh(markerGeo, markerMat);
    rightMarker.position.set(2.0, 0.08, 0.0);
    rightMarker.castShadow = true;
    rightMarker.receiveShadow = true;
    rightMarker.visible = false;
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
    centerGroup.name = 'fairway-centerline';
    fairwayCenterline = centerGroup;
    
    // Crisp White Dashed Stripes along X=0 from Z=-2 to Z=-450
    const dashLength = 1.4; // 2.4 yards long
    const dashGap = 3.6;    // 1.6 yards gap
    const dashWidth = 0.045; // 0.38 yards wide

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

    // Cup and cloth share the target group, so changing yardage moves them together.
    targetFlag = createStudioGolfFlag(greenGroup, studioColor('--gold', 'gold'));

    // 5. Dynamic 3D Wooden Yardage Sign with Roof (Offset Left)
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 512;
    signCanvas.height = 256;
    // willReadFrequently keeps the 2D backing store in CPU memory. Firefox
    // otherwise GPU-accelerates canvas2d, and uploading such a surface into
    // a WebGL texture can fail with
    //   "WebGL warning: texSubImage: Failed to map source surface for upload"
    // leaving this sign blank (the texture samples uninitialized memory).
    signContext = signCanvas.getContext('2d', { willReadFrequently: true });
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

export function setTargetGreenVisible(visible) {
    if (studioDistanceGuides) studioDistanceGuides.visible = Boolean(visible);
    if (activeTargetGreen) {
        activeTargetGreen.visible = Boolean(visible);
    }
}

export function setRangeDecorVisible(visible) {
    const v = Boolean(visible);
    if (teeBoxGroup) teeBoxGroup.visible = v;
    if (fairwayCenterline) fairwayCenterline.visible = v;
    if (studioDistanceGuides) studioDistanceGuides.visible = v;
}
