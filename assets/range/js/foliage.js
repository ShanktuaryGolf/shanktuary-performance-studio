// Realistic Perimeter Boundary Tree Wall (Fir, Birch & Maple 3D Models)

export function setupFoliage(scene) {
    const treeGroup = new THREE.Group();
    scene.add(treeGroup);

    // List of Sketchfab Tree Model Packs
    const modelSources = [
        {
            url: '/range/models/trees/realistic_fir_trees_pack_lods_gameready.glb',
            targetHeight: 14.0,
            extract: (gltf) => {
                const candidates = [];
                gltf.scene.traverse(child => {
                    if (child.name && (child.name.includes('Christmas tree_LOD0') || child.name.includes('Christmas tree_2_LOD0') || child.name.includes('Christmas tree_3_LOD0') || child.name.includes('Christmas tree_LOD1'))) {
                        candidates.push(child);
                    }
                });
                return candidates.length > 0 ? candidates : [gltf.scene];
            }
        },
        {
            url: '/range/models/trees/five_birch_trees_pack_lowpoly_lods.glb',
            targetHeight: 12.0,
            extract: (gltf) => {
                const candidates = [];
                gltf.scene.traverse(child => {
                    if (child.name && child.name.startsWith('Birch ') && !child.name.includes('LOD')) {
                        candidates.push(child);
                    }
                });
                return candidates.length > 0 ? candidates : [gltf.scene];
            }
        },
        {
            url: '/range/models/trees/maple_trees_pack_lowpoly_game_ready_lods.glb',
            targetHeight: 11.0,
            extract: (gltf) => {
                const candidates = [];
                gltf.scene.traverse(child => {
                    if (child.name && (child.name.includes('Acer_large_1') || child.name.includes('Acer_large_2') || child.name.includes('Acer_medium_1') || child.name.includes('Acer_small_1')) && !child.name.includes('Billboard')) {
                        candidates.push(child);
                    }
                });
                return candidates.length > 0 ? candidates : [gltf.scene];
            }
        }
    ];

    const treePrototypes = [];

    function normalizePrototype(node, targetHeight) {
        const cloned = node.clone(true);
        
        // 1. Ensure two-sided materials and shadows
        cloned.traverse(child => {
            if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
                if (child.material) {
                    const mats = Array.isArray(child.material) ? child.material : [child.material];
                    mats.forEach(m => {
                        m.side = THREE.DoubleSide;
                        m.shadowSide = THREE.DoubleSide;
                        if (m.roughness !== undefined) {
                            m.roughness = Math.max(0.75, m.roughness);
                        }
                    });
                }
            }
        });

        // 2. Compute bounding box and fix orientation if height was modeled on Z axis
        let box = new THREE.Box3().setFromObject(cloned);
        let size = box.getSize(new THREE.Vector3());

        if (size.z > size.y * 1.4) {
            // Up-axis is Z (e.g. from 3ds Max / Blender raw FBX) -> rotate to +Y
            cloned.rotation.x = -Math.PI / 2;
            box = new THREE.Box3().setFromObject(cloned);
            size = box.getSize(new THREE.Vector3());
        } else if (box.max.y <= 0.05 && box.min.y < -1) {
            // Inverted Y -> rotate upright
            cloned.rotation.x = Math.PI;
            box = new THREE.Box3().setFromObject(cloned);
            size = box.getSize(new THREE.Vector3());
        }

        const center = box.getCenter(new THREE.Vector3());
        const currentHeight = size.y > 0.5 ? size.y : targetHeight;
        const scaleFactor = targetHeight / currentHeight;

        // 3. Anchor wrapper: Bottom of trunk at Y=0, centered at (0,0) in X/Z
        const wrapper = new THREE.Group();
        cloned.position.set(-center.x, -box.min.y, -center.z);
        wrapper.add(cloned);
        wrapper.scale.set(scaleFactor, scaleFactor, scaleFactor);
        return wrapper;
    }

    function populateOuterBoundaryWalls() {
        if (treePrototypes.length === 0) return;
        
        console.log(`[+] Building Outer Boundary Tree Walls (reduced count, 180yd center corridor clear)...`);
        
        // 1. Left Outer Boundary Wall (X: -95 to -145, Z: +20 to -450, stride: 18yd)
        for (let z = 20; z > -450; z -= 18) {
            const count = 1 + (Math.random() > 0.5 ? 1 : 0);
            for (let r = 0; r < count; r++) {
                const xOffset = -95 - (r * 22) - Math.random() * 18;
                const proto = treePrototypes[Math.floor(Math.random() * treePrototypes.length)];
                const instance = proto.clone(true);
                const s = 0.85 + Math.random() * 0.35;
                instance.scale.multiplyScalar(s);
                instance.position.set(xOffset, 0, z + (Math.random() * 8 - 4));
                instance.rotation.y = Math.random() * Math.PI * 2;
                treeGroup.add(instance);
            }
        }

        // 2. Right Outer Boundary Wall (X: +95 to +145, Z: +20 to -450, stride: 18yd)
        for (let z = 20; z > -450; z -= 18) {
            const count = 1 + (Math.random() > 0.5 ? 1 : 0);
            for (let r = 0; r < count; r++) {
                const xOffset = 95 + (r * 22) + Math.random() * 18;
                const proto = treePrototypes[Math.floor(Math.random() * treePrototypes.length)];
                const instance = proto.clone(true);
                const s = 0.85 + Math.random() * 0.35;
                instance.scale.multiplyScalar(s);
                instance.position.set(xOffset, 0, z + (Math.random() * 8 - 4));
                instance.rotation.y = Math.random() * Math.PI * 2;
                treeGroup.add(instance);
            }
        }

        // 3. Deep Mountain Base Boundary (Z: -450 to -480, strictly outside center view |X| > 85)
        for (let x = -160; x <= 160; x += 18) {
            if (Math.abs(x) < 85) continue; // Keep 170yd center fairway and all target flags 100% unobstructed
            const proto = treePrototypes[Math.floor(Math.random() * treePrototypes.length)];
            const instance = proto.clone(true);
            const s = 1.0 + Math.random() * 0.5;
            instance.scale.multiplyScalar(s);
            instance.position.set(x + (Math.random() * 6 - 3), 0, -450 - Math.random() * 30);
            instance.rotation.y = Math.random() * Math.PI * 2;
            treeGroup.add(instance);
        }
    }

    if (typeof THREE.GLTFLoader === 'function') {
        const loader = new THREE.GLTFLoader();
        let loadedPacks = 0;

        modelSources.forEach(source => {
            loader.load(
                source.url,
                (gltf) => {
                    const extractedNodes = source.extract(gltf);
                    extractedNodes.forEach(node => {
                        const normalized = normalizePrototype(node, source.targetHeight);
                        treePrototypes.push(normalized);
                    });
                    loadedPacks++;
                    if (loadedPacks === modelSources.length) {
                        populateOuterBoundaryWalls();
                    }
                },
                undefined,
                (err) => {
                    console.warn(`[!] Failed loading tree model from ${source.url}:`, err);
                    loadedPacks++;
                    if (loadedPacks === modelSources.length && treePrototypes.length > 0) {
                        populateOuterBoundaryWalls();
                    }
                }
            );
        });
    }
}



