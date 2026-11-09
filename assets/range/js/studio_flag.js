// A restrained fabric flag: all deformation is driven by the range's render loop.
// Decorative wind only; it never changes ball physics or the target location.
export function createStudioGolfFlag(parent, color) {
    const group = new THREE.Group();
    group.name = 'studio-golf-flag';
    parent.add(group);
    const add = (name, geometry, material, x, y, z = 0) => {
        const mesh = new THREE.Mesh(geometry, material);
        mesh.name = name;
        mesh.position.set(x, y, z);
        group.add(mesh);
        return mesh;
    };
    const poleMaterial = new THREE.MeshStandardMaterial({color: 0xf1eee2, roughness: .48, metalness: .08});
    const darkMaterial = new THREE.MeshStandardMaterial({color: 0x26342e, roughness: .65});
    const rim = new THREE.RingGeometry(.054, .067, 32);
    rim.rotateX(-Math.PI / 2);
    add('flag-cup-rim', rim, poleMaterial, 0, .025);
    const hole = new THREE.CircleGeometry(.054, 32);
    hole.rotateX(-Math.PI / 2);
    add('flag-cup-interior', hole, new THREE.MeshBasicMaterial({color: 0x101b13}), 0, .024);
    const pole = add('flagstick', new THREE.CylinderGeometry(.014, .021, 2.9, 16), poleMaterial, 0, 1.47);
    pole.castShadow = true;
    add('flagstick-ferrule', new THREE.CylinderGeometry(.022, .024, .17, 16), darkMaterial, 0, .11);
    add('flagstick-cap', new THREE.SphereGeometry(.025, 12, 8), poleMaterial, 0, 2.93);
    // The hoist sleeve stays fixed; the free edge has both sag and billowing folds.
    add('flag-hoist-sleeve', new THREE.CylinderGeometry(.023, .023, .66, 12), poleMaterial, 0, 2.54);
    const geometry = new THREE.PlaneGeometry(1, 1, 32, 16);
    const material = new THREE.MeshStandardMaterial({
        color, side: THREE.DoubleSide, roughness: .93, metalness: 0, vertexColors: true,
    });
    const cloth = add('flag-cloth', geometry, material, .025, 2.88);
    cloth.castShadow = true;
    // Print the supplied Shanktuary icon into the fabric UVs, rather than placing
    // a rigid badge in front of it. The reverse shows the natural mirrored print.
    // Keep the plain gold flag visible if the optional artwork cannot be loaded.
    new THREE.TextureLoader().load('/range/textures/studio_flag_brand.png', source => {
        const canvas = document.createElement('canvas');
        canvas.width = 1080;
        canvas.height = 660;
        const context = canvas.getContext('2d');
        if (!context) {
            source.dispose();
            return;
        }
        context.fillStyle = `#${new THREE.Color(color).getHexString()}`;
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.imageSmoothingEnabled = true;
        context.imageSmoothingQuality = 'high';
        // Square print, generous breathing room, and no edits to the brand art.
        context.drawImage(source.image, 320, 110, 440, 440);
        const print = new THREE.CanvasTexture(canvas);
        print.colorSpace = THREE.SRGBColorSpace;
        material.map = print;
        material.color.set(0xffffff); // Preserve the icon's original gold/teal.
        material.needsUpdate = true;
        source.dispose();
    }, undefined, () => {});
    // Slightly darker sewn hems, without a texture fetch or shiny plastic finish.
    const uv = geometry.attributes.uv;
    const colors = new Float32Array(uv.count * 3);
    for (let i = 0; i < uv.count; i++) {
        const u = uv.getX(i), v = uv.getY(i);
        const hem = u < .04 || u > .96 || v < .065 || v > .935;
        const shade = hem ? .83 : 1;
        colors.set([shade, shade, shade], i * 3);
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.attributes.position.setUsage(THREE.DynamicDrawUsage);
    const update = seconds => {
        const time = Number.isFinite(seconds) ? seconds : 0;
        const position = geometry.attributes.position;
        for (let i = 0; i < uv.count; i++) {
            const u = uv.getX(i), v = uv.getY(i);
            const wave = Math.sin(u * 8.5 - time * 2.1 + v * .7);
            const ripple = Math.sin(u * 17 - time * 3.4 - v * 1.3);
            position.setXYZ(i,
                1.08 * u - .035 * u * (1 - Math.cos(u * 8.5 - time * 2.1)),
                -.66 * (1 - v) - .13 * u * u + .035 * u * wave,
                u * (.105 * wave + .025 * ripple));
        }
        position.needsUpdate = true;
        geometry.computeVertexNormals();
        geometry.computeBoundingSphere();
    };
    update(0);
    return {group, update};
}
