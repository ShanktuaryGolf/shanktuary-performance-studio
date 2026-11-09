// Studio daylight scenery: real meshes and procedural material detail over the
// bundled turf/normal maps. No photographed shot, fake flight or scoring data.
const NOISE = `
float studioHash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453123); }
float studioNoise(vec2 p) {
    vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(studioHash(i),studioHash(i+vec2(1,0)),f.x),
               mix(studioHash(i+vec2(0,1)),studioHash(i+vec2(1,1)),f.x),f.y);
}
float studioFbm(vec2 p) {
    return .57*studioNoise(p)+.28*studioNoise(p*2.03)+.15*studioNoise(p*4.09);
}`;

function worldMaterial(material, fragment) {
    material.onBeforeCompile = shader => {
        shader.vertexShader = shader.vertexShader
            .replace('#include <common>', '#include <common>\nvarying vec3 vStudioWorld;')
            .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvStudioWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
        shader.fragmentShader = shader.fragmentShader
            .replace('#include <common>', '#include <common>\nvarying vec3 vStudioWorld;\n' + NOISE)
            .replace('#include <color_fragment>', '#include <color_fragment>\n' + fragment);
    };
    material.customProgramCacheKey = () => fragment;
    return material;
}

export function createStudioTurf(textureLoader, { tee = false } = {}) {
    const material = new THREE.MeshStandardMaterial({
        color: tee ? 0x8b996e : 0xaeb78a, roughness: .96, metalness: 0,
        normalScale: new THREE.Vector2(.16, .16),
    });
    const repeat = tee ? [3, 3] : [110, 180];
    for (const [property, file] of [['map', 'gen_fairway_tex.png'], ['normalMap', 'gen_fairway_map.png']]) {
        textureLoader.load('/range/textures/' + file, texture => {
            texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
            texture.repeat.set(...repeat);
            texture.anisotropy = 8;
            if (property === 'map') texture.colorSpace = THREE.SRGBColorSpace;
            material[property] = texture;
            material.needsUpdate = true;
        });
    }
    if (!tee) worldMaterial(material, `
        // Alternating mower direction, softened to avoid aliasing at distance.
        float mow = smoothstep(-.18,.18,sin(vStudioWorld.z * .205 + vStudioWorld.x * .015));
        float rough = smoothstep(32.0,65.0,abs(vStudioWorld.x));
        float variation = studioFbm(vStudioWorld.xz*.035);
        diffuseColor.rgb *= mix(.82,1.09,mow) * mix(.89,1.04,variation);
        diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb*vec3(.73,.79,.60),rough*.7);
    `);
    return material;
}

export function createStudioSky(scene) {
    const geometry = new THREE.SphereGeometry(1250, 32, 20);
    const material = new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        vertexShader: `varying vec3 vSkyDirection; void main() {
            vSkyDirection=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
        }`,
        fragmentShader: `varying vec3 vSkyDirection; ${NOISE}
        void main() {
            vec3 d=normalize(vSkyDirection);
            float altitude=max(d.y,0.0);
            vec3 color=mix(vec3(.79,.84,.84),vec3(.24,.48,.69),pow(altitude,.42));
            vec2 cloudUv=d.xz/max(.16,altitude)*1.4;
            float cloud=studioFbm(cloudUv+vec2(4.1,7.3));
            float body=smoothstep(.52,.72,cloud)*smoothstep(.01,.12,altitude);
            color=mix(color,vec3(.95,.93,.86),body*.78);
            float sun=max(dot(d,normalize(vec3(-.46,.48,-.75))),0.0);
            color+=vec3(1.0,.81,.57)*(pow(sun,30.0)*.10+pow(sun,400.0)*.28);
            gl_FragColor=vec4(color,1.0);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
        }`,
    });
    const sky = new THREE.Mesh(geometry, material);
    sky.name = 'studio-daylight-sky'; sky.renderOrder = -10;
    scene.add(sky);
    scene.fog = new THREE.FogExp2(0xa5b7bf, .00048);
    return sky;
}

function woodlandMaterial(tint) {
    const material = new THREE.MeshStandardMaterial({ color: tint, roughness: 1, metalness: 0 });
    return worldMaterial(material, `
        // Canopy-scale variation, not a flat grey mountain silhouette.
        float canopy = studioFbm(vStudioWorld.xz*.095);
        float ridge = studioFbm(vStudioWorld.xz*.013);
        float shade = mix(.72,1.12,canopy)*mix(.88,1.06,ridge);
        diffuseColor.rgb *= shade;
    `);
}

export function createStudioMountains(scene) {
    const addGeometry = geometry => {
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        geometry.translate(-center.x, -box.min.y, -center.z);
        // Reuse the bundled 64×64 sculpted terrain, with several actual ridges
        // at distinct depths rather than the old over-scaled distant plane.
        const layers = [
            { x: -80, z: -1100, width: 1900, height: 280, depth: 650, color: 0x617a87, angle: .14 },
            { x: 160, z: -880, width: 1500, height: 205, depth: 530, color: 0x496758, angle: -.22 },
            { x: -120, z: -620, width: 1250, height: 135, depth: 360, color: 0x3e553d, angle: .08 },
        ];
        for (const layer of layers) {
            const mesh = new THREE.Mesh(geometry, woodlandMaterial(layer.color));
            mesh.name = 'studio-wooded-ridge';
            mesh.scale.set(layer.width/size.x, layer.height/size.y, layer.depth/size.z);
            mesh.position.set(layer.x,-5,layer.z);
            mesh.rotation.y=layer.angle;
            mesh.receiveShadow = true;
            scene.add(mesh);
        }
    };
    const fallback = () => {
        // True undulating terrain still reads as woodland if an optional GLB
        // fails. This is not a screen-facing landscape image.
        const g = new THREE.PlaneGeometry(100,100,64,64);
        g.rotateX(-Math.PI/2);
        const p=g.attributes.position;
        for(let i=0;i<p.count;i++) {
            const x=p.getX(i),z=p.getZ(i);
            p.setY(i,Math.max(0,11+Math.sin(x*.08+z*.03)*4+Math.cos(z*.07-x*.04)*5+Math.sin(x*.21+z*.16)*1.2));
        }
        g.computeVertexNormals();addGeometry(g);
    };
    if (typeof THREE.GLTFLoader !== 'function') { fallback(); return; }
    new THREE.GLTFLoader().load('/range/models/rangeMtns.glb', gltf => {
        gltf.scene.updateMatrixWorld(true);
        let geometry;
        gltf.scene.traverse(child => {
            if (!geometry && child.isMesh) geometry=child.geometry.clone().applyMatrix4(child.matrixWorld);
        });
        if(geometry) addGeometry(geometry); else fallback();
    }, undefined, fallback);
}
