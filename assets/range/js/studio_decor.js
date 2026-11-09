// Lightweight, local WebGL scenery for the approved studio range treatment.
// Distance guides use the same yard-based world coordinates as setTargetDistance.
// These meshes are visual references only, never scoring zones or shot data.
export function studioColor(token, fallback) {
    return getComputedStyle(document.body).getPropertyValue(token).trim() || fallback;
}
export function createStudioRangeDecor(scene, teeGroup) {
    const teal = studioColor('--accent-line', 'turquoise');
    const navy = studioColor('--bg', 'midnightblue');
    const gold = studioColor('--gold', 'gold');
    const white = studioColor('--text', 'white');
    const guideGroup = new THREE.Group();
    guideGroup.name = 'studio-distance-guides';
    const ringMaterial = new THREE.MeshBasicMaterial({ color: teal, side: THREE.DoubleSide,
        transparent: true, opacity: .6, depthWrite: false, polygonOffset: true,
        polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
    for (const [index, yards] of [100, 150, 200, 250].entries()) {
        const radius = 19 + index * 3;
        const ring = new THREE.Mesh(new THREE.RingGeometry(radius - .12, radius + .12, 128), ringMaterial);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(0, .04, -yards);
        ring.name = `distance-guide-${yards}yd`;
        guideGroup.add(ring);
        const canvas = document.createElement('canvas');
        canvas.width = 256; canvas.height = 160;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        context.fillStyle = navy; context.fillRect(0, 0, 256, 160);
        context.strokeStyle = gold; context.lineWidth = 5; context.strokeRect(4, 4, 248, 152);
        context.fillStyle = white; context.font = '700 90px sans-serif'; context.textAlign = 'center';
        context.fillText(String(yards), 128, 100);
        context.font = '24px sans-serif'; context.fillText('YARDS', 128, 137);
        const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
        const signMaterial = new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide });
        for (const side of [-1, 1]) {
            const sign = new THREE.Mesh(new THREE.PlaneGeometry(4.5, 2.8), signMaterial);
            sign.position.set(side * (radius + 4), 1.5, -yards);
            sign.rotation.y = side * -.08;
            guideGroup.add(sign);
        }
    }
    scene.add(guideGroup);
    createStudioBayDividers(teeGroup);
    return guideGroup;
}


// Low, lengthwise bay partitions frame the mat rather than standing across the
// player's view as front-facing advertising boards. Dimensions are in yards.
export function createStudioBayDividers(teeGroup) {
    const frameMaterial = new THREE.MeshStandardMaterial({
        color: 0x46514e, roughness: .72, metalness: .25,
    });
    const panelMaterial = new THREE.MeshStandardMaterial({
        color: 0x293632, roughness: .88, metalness: .04,
    });
    const footMaterial = new THREE.MeshStandardMaterial({
        color: 0x343e3b, roughness: .8, metalness: .2,
    });
    const logoTexture = new THREE.TextureLoader().load('/assets/studio_brand_mark.png');
    logoTexture.colorSpace = THREE.SRGBColorSpace;
    const logoMaterial = new THREE.MeshStandardMaterial({
        map: logoTexture, transparent: true, roughness: .72, metalness: .1,
        depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
    });
    const roundedPanel = (width, height, radius, depth) => {
        const shape = new THREE.Shape();
        const x = -width / 2, y = -height / 2;
        shape.moveTo(x + radius, y);
        shape.lineTo(x + width - radius, y);
        shape.quadraticCurveTo(x + width, y, x + width, y + radius);
        shape.lineTo(x + width, y + height - radius);
        shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        shape.lineTo(x + radius, y + height);
        shape.quadraticCurveTo(x, y + height, x, y + height - radius);
        shape.lineTo(x, y + radius);
        shape.quadraticCurveTo(x, y, x + radius, y);
        const geometry = new THREE.ExtrudeGeometry(shape, {
            depth, bevelEnabled: true, bevelThickness: .008,
            bevelSize: .008, bevelSegments: 2, steps: 1, curveSegments: 6,
        });
        geometry.translate(0, 0, -depth / 2);
        return geometry;
    };
    const frameGeometry = roundedPanel(2.25, 1.04, .07, .10);
    const panelGeometry = roundedPanel(2.13, .92, .045, .014);
    for (const side of [-1, 1]) {
        const divider = new THREE.Group();
        divider.name = `studio-bay-${side < 0 ? 'left' : 'right'}`;
        divider.position.set(side * 2.75, .56, 2.35);
        // Local +Z is the inner face on both sides; local X runs downrange.
        divider.rotation.y = -side * Math.PI / 2;
        const frame = new THREE.Mesh(frameGeometry, frameMaterial);
        frame.name = 'studio-bay-frame';
        frame.castShadow = true; frame.receiveShadow = true;
        divider.add(frame);
        for (const face of [-1, 1]) {
            const panel = new THREE.Mesh(panelGeometry, panelMaterial);
            panel.name = 'studio-bay-inset';
            panel.position.z = face * .057;
            panel.receiveShadow = true;
            divider.add(panel);
        }
        for (const end of [-1, 1]) {
            const foot = new THREE.Mesh(new THREE.BoxGeometry(.18, .045, .28), footMaterial);
            foot.position.set(end * .94, -.525, 0);
            foot.castShadow = true; foot.receiveShadow = true;
            divider.add(foot);
        }
        const logo = new THREE.Mesh(new THREE.PlaneGeometry(.28, .38), logoMaterial);
        logo.name = 'studio-bay-logo';
        logo.position.set(0, .01, .074);
        divider.add(logo);
        teeGroup.add(divider);
    }
}
