// Majestic Alpine Pine Tree Forest Corridors with Dynamic Fairway Width Reactivity

let masterFoliageGroup = null;
let leftTreeGroup = null;
let rightTreeGroup = null;
let backTreeGroup = null;
let currentFairwayWidth = 60; // Default 60 yards corridor

export function getFairwayWidth() {
    return currentFairwayWidth;
}

export function setFairwayWidth(yards) {
    if (isNaN(yards) || yards <= 0) return;
    currentFairwayWidth = Math.max(30, Math.min(120, Math.round(yards)));
    
    if (leftTreeGroup) leftTreeGroup.position.x = -currentFairwayWidth / 2;
    if (rightTreeGroup) rightTreeGroup.position.x = +currentFairwayWidth / 2;
    
    localStorage.setItem('sps_range_fairway_width', currentFairwayWidth);
}

export function setupFoliage(scene) {
    const savedWidth = localStorage.getItem('sps_range_fairway_width');
    if (savedWidth) {
        currentFairwayWidth = parseInt(savedWidth, 10);
    }

    masterFoliageGroup = new THREE.Group();
    scene.add(masterFoliageGroup);

    leftTreeGroup = new THREE.Group();
    rightTreeGroup = new THREE.Group();
    backTreeGroup = new THREE.Group();

    masterFoliageGroup.add(leftTreeGroup);
    masterFoliageGroup.add(rightTreeGroup);
    masterFoliageGroup.add(backTreeGroup);

    leftTreeGroup.position.x = -currentFairwayWidth / 2;
    rightTreeGroup.position.x = +currentFairwayWidth / 2;

    loadPineTreeModel(scene);
}

function loadPineTreeModel(scene) {
    if (typeof THREE.GLTFLoader !== 'function') return;

    const loader = new THREE.GLTFLoader();
    loader.load(
        '/range/models/trees/pine_tree.glb',
        (gltf) => {
            const treeModel = gltf.scene;

            // Ensure matrices are computed
            treeModel.updateMatrixWorld(true);

            // Configure shadow casting and high-quality alpha-cutout foliage materials
            treeModel.traverse(child => {
                if (child.isMesh) {
                    child.castShadow = true;
                    child.receiveShadow = true;
                    if (child.material) {
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        mats.forEach(m => {
                            m.side = THREE.DoubleSide;
                            m.transparent = false; // Solid alpha-mask cutout (no transparent sorting artifacts)
                            m.alphaTest = 0.25;
                            m.depthWrite = true;
                            m.depthTest = true;
                            m.roughness = 0.80;
                            m.metalness = 0.0;
                            if (m.map) {
                                m.map.colorSpace = THREE.SRGBColorSpace;
                            }
                        });
                    }
                }
            });

            // Calculate precise bounding box to center X/Z and ground base to Y = 0
            const box = new THREE.Box3().setFromObject(treeModel);
            const size = box.getSize(new THREE.Vector3());
            const center = box.getCenter(new THREE.Vector3());

            const targetHeight = 13.5;
            const normScale = targetHeight / Math.max(0.0001, size.y);

            const wrapper = new THREE.Group();
            treeModel.position.set(-center.x * normScale, -box.min.y * normScale, -center.z * normScale);
            treeModel.scale.set(normScale, normScale, normScale);
            wrapper.add(treeModel);

            console.log(`[✓] Loaded /range/models/trees/pine_tree.glb (height: ${targetHeight}m, normScale: ${normScale.toFixed(2)}x)`);
            populatePineCorridors(wrapper);
        },
        undefined,
        (err) => {
            console.error('[!] Error loading pine_tree.glb:', err);
        }
    );
}

function populatePineCorridors(treePrefab) {
    if (!treePrefab) return;

    // Clear previous placeholder instances
    while (leftTreeGroup.children.length > 0) leftTreeGroup.remove(leftTreeGroup.children[0]);
    while (rightTreeGroup.children.length > 0) rightTreeGroup.remove(rightTreeGroup.children[0]);
    while (backTreeGroup.children.length > 0) backTreeGroup.remove(backTreeGroup.children[0]);

    // 1. Left Tree Line Corridor (Z: +25 to -460, 4 deep staggered rows)
    for (let z = 25; z > -460; z -= 6.5) {
        const rows = 4;
        for (let r = 0; r < rows; r++) {
            const localX = -(r * 7.5) - 1.2 - (Math.random() * 3.5);
            const inst = treePrefab.clone(true);
            const s = 0.88 + Math.random() * 0.32 + (r * 0.08);
            inst.scale.set(s, s, s);
            inst.position.set(localX, 0, z + (Math.random() * 3.6 - 1.8));
            inst.rotation.y = Math.random() * Math.PI * 2;
            leftTreeGroup.add(inst);
        }
    }

    // 2. Right Tree Line Corridor (Z: +25 to -460, 4 deep staggered rows)
    for (let z = 25; z > -460; z -= 6.5) {
        const rows = 4;
        for (let r = 0; r < rows; r++) {
            const localX = +(r * 7.5) + 1.2 + (Math.random() * 3.5);
            const inst = treePrefab.clone(true);
            const s = 0.88 + Math.random() * 0.32 + (r * 0.08);
            inst.scale.set(s, s, s);
            inst.position.set(localX, 0, z + (Math.random() * 3.6 - 1.8));
            inst.rotation.y = Math.random() * Math.PI * 2;
            rightTreeGroup.add(inst);
        }
    }

    // 3. Deep Mountain Base Backing Forest (Z: -455 to -480)
    for (let x = -220; x <= 220; x += 8.0) {
        const depth = 3;
        for (let d = 0; d < depth; d++) {
            const inst = treePrefab.clone(true);
            const s = 1.1 + Math.random() * 0.5;
            inst.scale.set(s, s, s);
            inst.position.set(x + (Math.random() * 4.0 - 2.0), 0, -455 - (d * 8.5) - Math.random() * 6);
            inst.rotation.y = Math.random() * Math.PI * 2;
            backTreeGroup.add(inst);
        }
    }
}






