// GPU Instanced Foliage: Trees and Bushes along Driving Range perimeter

export function setupFoliage(scene) {
    // 1. Pine / Fir Trees (Conical Evergreen)
    const treeTrunkGeo = new THREE.CylinderGeometry(0.3, 0.5, 3, 8);
    const treeTrunkMat = new THREE.MeshStandardMaterial({ color: 0x4a2e18, roughness: 0.9 });
    
    const treeLeavesGeo = new THREE.ConeGeometry(3.5, 8, 8);
    const treeLeavesMat = new THREE.MeshStandardMaterial({ color: 0x1c441c, roughness: 0.8 });
    
    // Create instanced meshes for 400 trees
    const treeCount = 400;
    const trunkInstanced = new THREE.InstancedMesh(treeTrunkGeo, treeTrunkMat, treeCount);
    const leavesInstanced = new THREE.InstancedMesh(treeLeavesGeo, treeLeavesMat, treeCount);
    
    trunkInstanced.castShadow = true;
    leavesInstanced.castShadow = true;
    
    const dummy = new THREE.Object3D();
    let idx = 0;
    
    // Left Tree Line (X = -45 to -90, Z = +20 to -400)
    for (let z = 20; z > -400; z -= 4) {
        if (idx >= treeCount / 2) break;
        const x = -45 - Math.random() * 35;
        const scale = 0.8 + Math.random() * 0.6;
        
        // Trunk
        dummy.position.set(x, 1.5 * scale, z + (Math.random() * 4 - 2));
        dummy.scale.set(scale, scale, scale);
        dummy.rotation.y = Math.random() * Math.PI;
        dummy.updateMatrix();
        trunkInstanced.setMatrixAt(idx, dummy.matrix);
        
        // Foliage
        dummy.position.set(x, (3 + 3.5) * scale, z + (Math.random() * 4 - 2));
        dummy.scale.set(scale, scale, scale);
        dummy.updateMatrix();
        leavesInstanced.setMatrixAt(idx, dummy.matrix);
        
        idx++;
    }
    
    // Right Tree Line (X = +45 to +90, Z = +20 to -400)
    for (let z = 20; z > -400; z -= 4) {
        if (idx >= treeCount) break;
        const x = 45 + Math.random() * 35;
        const scale = 0.8 + Math.random() * 0.6;
        
        // Trunk
        dummy.position.set(x, 1.5 * scale, z + (Math.random() * 4 - 2));
        dummy.scale.set(scale, scale, scale);
        dummy.rotation.y = Math.random() * Math.PI;
        dummy.updateMatrix();
        trunkInstanced.setMatrixAt(idx, dummy.matrix);
        
        // Foliage
        dummy.position.set(x, (3 + 3.5) * scale, z + (Math.random() * 4 - 2));
        dummy.scale.set(scale, scale, scale);
        dummy.updateMatrix();
        leavesInstanced.setMatrixAt(idx, dummy.matrix);
        
        idx++;
    }
    
    trunkInstanced.instanceMatrix.needsUpdate = true;
    leavesInstanced.instanceMatrix.needsUpdate = true;
    
    scene.add(trunkInstanced);
    scene.add(leavesInstanced);
    
    // 2. Instanced Bushes around target greens
    const bushGeo = new THREE.DodecahedronGeometry(1.2, 1);
    const bushMat = new THREE.MeshStandardMaterial({ color: 0x255220, roughness: 0.9 });
    const bushCount = 150;
    const bushInstanced = new THREE.InstancedMesh(bushGeo, bushMat, bushCount);
    bushInstanced.castShadow = true;
    
    for (let i = 0; i < bushCount; i++) {
        const side = i % 2 === 0 ? -1 : 1;
        const x = side * (35 + Math.random() * 20);
        const z = -Math.random() * 350;
        const scale = 0.7 + Math.random() * 0.8;
        
        dummy.position.set(x, 0.6 * scale, z);
        dummy.scale.set(scale, scale * 0.8, scale);
        dummy.rotation.set(Math.random(), Math.random(), Math.random());
        dummy.updateMatrix();
        bushInstanced.setMatrixAt(i, dummy.matrix);
    }
    
    bushInstanced.instanceMatrix.needsUpdate = true;
    scene.add(bushInstanced);
}
