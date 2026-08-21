// Realistic Multi-Layer 3D Foliage System (Pine, Maple, Birch & Dense Forest Undergrowth)

export function setupFoliage(scene) {
    const treeGroup = new THREE.Group();
    
    // 1. Materials for Multi-Species Forest
    const barkDarkMat = new THREE.MeshStandardMaterial({ color: 0x3d2817, roughness: 0.95 });
    const barkBirchMat = new THREE.MeshStandardMaterial({ color: 0xdedede, roughness: 0.85 });
    
    // Foliage Materials with realistic variation
    const pineLeavesMat = new THREE.MeshStandardMaterial({ color: 0x1a3d1c, roughness: 0.8 });
    const mapleLeavesMat = new THREE.MeshStandardMaterial({ color: 0x2e5c1e, roughness: 0.75 });
    const birchLeavesMat = new THREE.MeshStandardMaterial({ color: 0x487a27, roughness: 0.75 });
    const bushMat = new THREE.MeshStandardMaterial({ color: 0x244f19, roughness: 0.85 });
    
    // 2. Realistic 3D Tree Prototype Builders
    function buildPineTree(scale) {
        const group = new THREE.Group();
        // Trunk
        const trunkGeo = new THREE.CylinderGeometry(0.25 * scale, 0.45 * scale, 4 * scale, 8);
        const trunk = new THREE.Mesh(trunkGeo, barkDarkMat);
        trunk.position.y = 2 * scale;
        trunk.castShadow = true;
        group.add(trunk);
        
        // 4 Staggered Layered Needle Tiers
        const tiers = [
            { y: 3.2 * scale, r: 2.8 * scale, h: 3.0 * scale },
            { y: 5.0 * scale, r: 2.2 * scale, h: 2.8 * scale },
            { y: 6.8 * scale, r: 1.6 * scale, h: 2.4 * scale },
            { y: 8.2 * scale, r: 0.9 * scale, h: 2.0 * scale }
        ];
        
        tiers.forEach(t => {
            const foliageGeo = new THREE.ConeGeometry(t.r, t.h, 7);
            const foliage = new THREE.Mesh(foliageGeo, pineLeavesMat);
            foliage.position.y = t.y;
            foliage.castShadow = true;
            group.add(foliage);
        });
        
        return group;
    }
    
    function buildMapleTree(scale) {
        const group = new THREE.Group();
        // Gnarled Trunk
        const trunkGeo = new THREE.CylinderGeometry(0.35 * scale, 0.55 * scale, 4.5 * scale, 8);
        const trunk = new THREE.Mesh(trunkGeo, barkDarkMat);
        trunk.position.y = 2.25 * scale;
        trunk.castShadow = true;
        group.add(trunk);
        
        // Multi-Cluster Broadleaf Canopy
        const canopyPositions = [
            { x: 0, y: 5.2 * scale, z: 0, r: 2.5 * scale },
            { x: 1.2 * scale, y: 4.8 * scale, z: 0.6 * scale, r: 1.9 * scale },
            { x: -1.1 * scale, y: 4.6 * scale, z: -0.5 * scale, r: 1.8 * scale },
            { x: 0.3 * scale, y: 6.3 * scale, z: -0.8 * scale, r: 1.7 * scale },
            { x: -0.4 * scale, y: 5.8 * scale, z: 1.0 * scale, r: 1.6 * scale }
        ];
        
        canopyPositions.forEach(c => {
            const clusterGeo = new THREE.DodecahedronGeometry(c.r, 1);
            const cluster = new THREE.Mesh(clusterGeo, mapleLeavesMat);
            cluster.position.set(c.x, c.y, c.z);
            cluster.castShadow = true;
            group.add(cluster);
        });
        
        return group;
    }
    
    function buildBirchTree(scale) {
        const group = new THREE.Group();
        // Slender White Trunk
        const trunkGeo = new THREE.CylinderGeometry(0.18 * scale, 0.28 * scale, 5 * scale, 8);
        const trunk = new THREE.Mesh(trunkGeo, barkBirchMat);
        trunk.position.y = 2.5 * scale;
        trunk.castShadow = true;
        group.add(trunk);
        
        // Weeping Birch Foliage Clusters
        const clusters = [
            { x: 0, y: 5.5 * scale, z: 0, r: 2.0 * scale },
            { x: 0.8 * scale, y: 4.8 * scale, z: 0.4 * scale, r: 1.4 * scale },
            { x: -0.7 * scale, y: 4.5 * scale, z: -0.3 * scale, r: 1.3 * scale },
            { x: 0.2 * scale, y: 6.4 * scale, z: -0.5 * scale, r: 1.2 * scale }
        ];
        
        clusters.forEach(c => {
            const cGeo = new THREE.DodecahedronGeometry(c.r, 1);
            const cMesh = new THREE.Mesh(cGeo, birchLeavesMat);
            cMesh.position.set(c.x, c.y, c.z);
            cMesh.castShadow = true;
            group.add(cMesh);
        });
        
        return group;
    }
    
    function buildBushCluster(scale) {
        const group = new THREE.Group();
        const clusterCoords = [
            { x: 0, y: 0.6 * scale, z: 0, r: 0.8 * scale },
            { x: 0.5 * scale, y: 0.5 * scale, z: 0.3 * scale, r: 0.6 * scale },
            { x: -0.4 * scale, y: 0.4 * scale, z: -0.2 * scale, r: 0.55 * scale }
        ];
        clusterCoords.forEach(c => {
            const bGeo = new THREE.DodecahedronGeometry(c.r, 1);
            const bMesh = new THREE.Mesh(bGeo, bushMat);
            bMesh.position.set(c.x, c.y, c.z);
            bMesh.castShadow = true;
            group.add(bMesh);
        });
        return group;
    }
    
    // 3. Populate Left & Right Tree Lines along Driving Range Perimeter
    const treeTypes = [buildPineTree, buildMapleTree, buildBirchTree];
    
    // Left Boundary (X = -45 to -90, Z = +20 to -400)
    for (let z = 20; z > -400; z -= 12) {
        const xOffset = -42 - Math.random() * 30;
        const scale = 0.85 + Math.random() * 0.45;
        const typeIndex = Math.floor(Math.random() * treeTypes.length);
        const tree = treeTypes[typeIndex](scale);
        tree.position.set(xOffset, 0, z + (Math.random() * 6 - 3));
        tree.rotation.y = Math.random() * Math.PI * 2;
        treeGroup.add(tree);
        
        // Add Undergrowth Bush
        if (Math.random() > 0.4) {
            const bush = buildBushCluster(0.9 + Math.random() * 0.5);
            bush.position.set(xOffset + (Math.random() * 6 - 3), 0, z + (Math.random() * 6 - 3));
            treeGroup.add(bush);
        }
    }
    
    // Right Boundary (X = +45 to +90, Z = +20 to -400)
    for (let z = 20; z > -400; z -= 12) {
        const xOffset = 42 + Math.random() * 30;
        const scale = 0.85 + Math.random() * 0.45;
        const typeIndex = Math.floor(Math.random() * treeTypes.length);
        const tree = treeTypes[typeIndex](scale);
        tree.position.set(xOffset, 0, z + (Math.random() * 6 - 3));
        tree.rotation.y = Math.random() * Math.PI * 2;
        treeGroup.add(tree);
        
        // Add Undergrowth Bush
        if (Math.random() > 0.4) {
            const bush = buildBushCluster(0.9 + Math.random() * 0.5);
            bush.position.set(xOffset + (Math.random() * 6 - 3), 0, z + (Math.random() * 6 - 3));
            treeGroup.add(bush);
        }
    }
    
    scene.add(treeGroup);
}
