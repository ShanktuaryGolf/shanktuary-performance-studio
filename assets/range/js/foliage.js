// Fir forest corridors: instanced, distance-LOD, wind-animated.
//
// Replaces the previous approach of cloning one 2.2k-tri pine 768 times as
// individual scene-graph objects. Three problems with that:
//   1. The pine's foliage was a handful of flat cutout cards -- readable as
//      "low poly" from the tee, which is exactly where the player looks.
//   2. 768 clones = 768 draw calls per material, so we could not afford a
//      denser mesh anywhere in the scene.
//   3. Every tree was the same tree at the same detail, near and far.
//
// Now: three fir species x three LOD tiers from fir_trees_lod.glb, drawn with
// InstancedMesh (one draw call per mesh per LOD tier regardless of count), so
// the near trees can carry ~13k tris each while distant rows collapse to
// cheap billboards.

let masterFoliageGroup = null;
let leftTreeGroup = null;
let rightTreeGroup = null;
let backTreeGroup = null;
let currentFairwayWidth = 60; // Default 60 yards corridor

// Every InstancedMesh we build, for per-frame wind + LOD bookkeeping.
let instancedMeshes = [];
// Placement records (position/rotation/scale/species), regenerated when the
// fairway width changes so we can rebuild instance matrices without reloading.
let placements = { left: [], right: [], back: [] };

const TARGET_HEIGHT = 13.5;   // metres, canopy fir -- matches the old pine scale

// Per-species target height. The three source models are NOT the same kind of
// tree: measured raw bounds are 9.29m tall x 5.29m wide (a full canopy fir),
// 4.16 x 2.72 (a younger fir), and 1.53 x 1.50 -- that last one is a squat
// understory shrub, nearly as wide as it is tall. Normalising all three to
// 13.5m (the old behaviour for the single pine) inflated the shrub into a
// ~14m-wide blob that walled off the fairway. Scale each to its own natural
// height instead and let the shrub be a shrub.
//
// Note: GLTFLoader sanitizes node names, replacing spaces and dots with
// underscores ("Christmas tree_LOD0" in the file becomes
// "Christmas_tree_LOD0" on the Object3D). These are the sanitized forms.
const SPECIES_HEIGHT = {
    'Christmas_tree': 13.5,   // mature canopy fir
    'Christmas_tree_2': 10.5, // younger, narrower fir
    'Christmas_tree_3': 4.2   // understory shrub -- fills gaps at the base
};
const SPECIES = Object.keys(SPECIES_HEIGHT);

// The shrub reads badly as a standalone "tree" in the front row, so weight
// species selection by row depth: canopy firs at the fairway edge, shrubs
// mixed into the deeper rows where they fill the trunk gaps.
const CANOPY_SPECIES = ['Christmas_tree', 'Christmas_tree_2'];

// Distance thresholds (metres from the tee) for LOD selection. Chosen so the
// LOD0->LOD2 swap lands well beyond where a player can resolve branch detail,
// and the billboard tier only covers the far mountain-base backing forest.
const LOD_NEAR = 90;
const LOD_FAR = 260;

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

    loadFirTrees();
}

// ---------------------------------------------------------------------------
// Asset loading
// ---------------------------------------------------------------------------

function loadFirTrees() {
    if (typeof THREE.GLTFLoader !== 'function') return;

    const loader = new THREE.GLTFLoader();
    loader.load(
        '/range/models/trees/fir_trees_lod.glb',
        (gltf) => {
            const root = gltf.scene;
            root.updateMatrixWorld(true);

            const prefabs = extractSpeciesPrefabs(root);
            const usable = SPECIES.filter(s => prefabs[s] && prefabs[s].LOD0);
            if (usable.length === 0) {
                console.error('[!] fir_trees_lod.glb loaded but no species LOD0 found');
                return;
            }

            generatePlacements();
            buildInstancedForest(prefabs, usable);

            console.log(`[\u2713] Fir forest: ${usable.length} species, ` +
                        `${instancedMeshes.length} instanced draw groups, ` +
                        `${placements.left.length + placements.right.length + placements.back.length} trees`);
        },
        undefined,
        (err) => {
            console.error('[!] Error loading fir_trees_lod.glb:', err);
        }
    );
}

/**
 * Pull "<species>_LOD<n>" nodes out of the glTF and normalise each species so
 * it stands at its SPECIES_HEIGHT with its base at y=0 and centred on x/z.
 *
 * IMPORTANT: in the source file the variants are laid out side by side for
 * preview -- species are offset in X (0, 836, 1552) and LOD tiers in Z
 * (0, -2000, -3000), all at scale 100. So the centering translation MUST be
 * computed per tier from that tier's own bounding box. Deriving it once from
 * LOD0 and reusing it leaves LOD2/LOD3 carrying a ~-50m Z displacement after
 * scaling, which scatters distant trees across the middle of the fairway.
 *
 * The SCALE is still taken from LOD0 for the whole species, so every tier is
 * the same size and swapping LODs does not pop.
 *
 * Returns { [species]: { LOD0: [{geometry, material}], LOD2: [...], LOD3: [...] } }
 */
function extractSpeciesPrefabs(root) {
    const nodes = {};
    root.traverse(child => {
        if (child.name) nodes[child.name] = child;
    });

    const prefabs = {};

    for (const species of SPECIES) {
        const lod0Node = nodes[`${species}_LOD0`];
        if (!lod0Node) continue;

        // One scale per species, derived from LOD0's true height.
        lod0Node.updateMatrixWorld(true);
        const lod0Box = new THREE.Box3().setFromObject(lod0Node);
        const lod0Size = lod0Box.getSize(new THREE.Vector3());
        const scale = (SPECIES_HEIGHT[species] || TARGET_HEIGHT)
                      / Math.max(0.0001, lod0Size.y);

        const tiers = {};
        for (const lod of ['LOD0', 'LOD2', 'LOD3']) {
            const node = nodes[`${species}_${lod}`];
            if (!node) continue;

            node.updateMatrixWorld(true);

            // Per-tier bounds -> per-tier centering. This is what cancels the
            // preview layout offsets baked into the source node transforms.
            const box = new THREE.Box3().setFromObject(node);
            const center = box.getCenter(new THREE.Vector3());
            const norm = new THREE.Matrix4()
                .makeTranslation(-center.x * scale, -box.min.y * scale, -center.z * scale)
                .multiply(new THREE.Matrix4().makeScale(scale, scale, scale));

            const parts = [];
            node.traverse(child => {
                if (!child.isMesh || !child.geometry) return;

                // Bake the node's own world transform plus the normalisation
                // into the geometry, so instance matrices are pure placement.
                const geom = child.geometry.clone();
                geom.applyMatrix4(child.matrixWorld);
                geom.applyMatrix4(norm);
                geom.computeBoundingBox();
                geom.computeBoundingSphere();

                parts.push({
                    geometry: geom,
                    material: prepareFoliageMaterial(child.material, lod,
                                                     SPECIES_HEIGHT[species] || TARGET_HEIGHT)
                });
            });
            if (parts.length) tiers[lod] = parts;
        }

        if (tiers.LOD0) prefabs[species] = tiers;
    }

    return prefabs;
}

/**
 * Alpha-cutout foliage setup. The needle atlases are MASK materials: we keep
 * them opaque with alphaTest so they depth-sort correctly against each other
 * (768 transparent trees would be a sorting disaster), and add a touch of
 * subsurface-ish flatness via low roughness variance.
 */
function prepareFoliageMaterial(material, lod, treeHeight) {
    const src = Array.isArray(material) ? material[0] : material;
    if (!src) return new THREE.MeshStandardMaterial({ color: 0x2d4a22 });

    const m = src.clone();
    // Consumed by the wind shader patch so sway scales with species height.
    m.userData = Object.assign({}, m.userData, { treeHeight: treeHeight || TARGET_HEIGHT });

    const isFoliage = /Brunches|Billboard/i.test(m.name || '');

    if (isFoliage) {
        // Cutout, not blended -- avoids per-instance transparency sorting.
        m.transparent = false;
        m.alphaTest = lod === 'LOD3' ? 0.35 : 0.42;
        m.depthWrite = true;
        m.side = THREE.DoubleSide;
        m.roughness = 0.88;
        m.metalness = 0.0;
    } else {
        // Bark: single-sided is correct and halves the fragment work.
        m.transparent = false;
        m.side = THREE.FrontSide;
        m.roughness = 0.95;
        m.metalness = 0.0;
    }

    if (m.map) {
        m.map.colorSpace = THREE.SRGBColorSpace;
        // Sharpen the needle atlas at grazing angles -- without this the
        // distant tree lines mush into a flat green band.
        m.map.anisotropy = 8;
        m.map.wrapS = m.map.wrapT = THREE.ClampToEdgeWrapping;
    }
    if (m.normalMap) {
        m.normalScale = new THREE.Vector2(1.0, 1.0);
    }

    m.needsUpdate = true;
    return m;
}

// ---------------------------------------------------------------------------
// Placement
// ---------------------------------------------------------------------------

/**
 * Deterministic PRNG so the forest is identical between reloads -- a forest
 * that reshuffles every refresh makes it impossible to judge a visual change.
 */
function makeRandom(seed) {
    let s = seed >>> 0;
    return function () {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 4294967296;
    };
}

function generatePlacements() {
    const rand = makeRandom(20260904);
    placements = { left: [], right: [], back: [] };

    const pickSpecies = () => SPECIES[Math.floor(rand() * SPECIES.length)];

    // 1 & 2. Corridor tree lines. Denser spacing than before (5.2 vs 6.5) and
    // a per-tree jitter in x, z, scale, rotation and lean, so the eye stops
    // reading a repeated silhouette.
    //
    // Row offsets matter more than they did with the old pine: a normalised fir
    // canopy measures ~7.7m across (vs the pine's ~9.5m, but the fir actually
    // fills that width instead of being a few sparse cards). The front row is
    // pushed out to 4.0m from the corridor edge so its canopy does not overhang
    // the fairway and occlude the pin, target sign and mountains from the tee.
    const ROW0_OFFSET = 4.0;
    const ROW_SPACING = 7.5;

    for (const side of ['left', 'right']) {
        const dir = side === 'left' ? -1 : 1;
        for (let z = 25; z > -460; z -= 5.2) {
            const rows = 4;
            for (let r = 0; r < rows; r++) {
                const localX = dir * (ROW0_OFFSET + r * ROW_SPACING + rand() * 3.0);
                // Front rows are canopy firs only -- the understory shrub reads
                // as a green lump when it is the nearest thing to the player.
                const species = r === 0
                    ? CANOPY_SPECIES[Math.floor(rand() * CANOPY_SPECIES.length)]
                    : pickSpecies();
                // Back rows sit slightly taller: reads as a rising treeline.
                const s = 0.80 + rand() * 0.45 + r * 0.09;
                placements[side].push({
                    species,
                    x: localX,
                    y: 0,
                    z: z + (rand() * 3.6 - 1.8),
                    rotY: rand() * Math.PI * 2,
                    // Small random lean -- perfectly vertical trees look CG.
                    tiltX: (rand() - 0.5) * 0.055,
                    tiltZ: (rand() - 0.5) * 0.055,
                    scale: s,
                    phase: rand() * Math.PI * 2
                });
            }
        }
    }

    // 3. Deep mountain-base backing forest.
    for (let x = -220; x <= 220; x += 7.0) {
        const depth = 3;
        for (let d = 0; d < depth; d++) {
            placements.back.push({
                species: pickSpecies(),
                x: x + (rand() * 4.0 - 2.0),
                y: 0,
                z: -455 - d * 8.5 - rand() * 6,
                rotY: rand() * Math.PI * 2,
                tiltX: (rand() - 0.5) * 0.04,
                tiltZ: (rand() - 0.5) * 0.04,
                scale: 1.05 + rand() * 0.55,
                phase: rand() * Math.PI * 2
            });
        }
    }
}

// ---------------------------------------------------------------------------
// Instanced build
// ---------------------------------------------------------------------------

/**
 * Distance from the tee (roughly the camera in Golfer view) used to pick a LOD
 * tier. Corridor placements are in group-local space, so add the group offset.
 */
function lodForPlacement(p, groupKey) {
    const worldX = groupKey === 'left' ? p.x - currentFairwayWidth / 2
                 : groupKey === 'right' ? p.x + currentFairwayWidth / 2
                 : p.x;
    const dist = Math.hypot(worldX, p.z);
    if (dist < LOD_NEAR) return 'LOD0';
    if (dist < LOD_FAR) return 'LOD2';
    return 'LOD3';
}

function buildInstancedForest(prefabs, usable) {
    for (const mesh of instancedMeshes) {
        mesh.geometry.dispose();
        mesh.parent && mesh.parent.remove(mesh);
    }
    instancedMeshes = [];

    const groups = { left: leftTreeGroup, right: rightTreeGroup, back: backTreeGroup };

    for (const groupKey of ['left', 'right', 'back']) {
        const parent = groups[groupKey];
        while (parent.children.length) parent.remove(parent.children[0]);

        // Bucket placements by (species, LOD) so each bucket is one InstancedMesh.
        const buckets = new Map();
        for (const p of placements[groupKey]) {
            if (!usable.includes(p.species)) p.species = usable[0];
            let lod = lodForPlacement(p, groupKey);
            // Fall back down the tiers if this species lacks one.
            const tiers = prefabs[p.species];
            if (!tiers[lod]) lod = tiers.LOD2 ? 'LOD2' : 'LOD0';
            const key = `${p.species}|${lod}`;
            if (!buckets.has(key)) buckets.set(key, []);
            buckets.get(key).push(p);
        }

        for (const [key, items] of buckets) {
            const [species, lod] = key.split('|');
            const parts = prefabs[species][lod];

            parts.forEach((part, partIdx) => {
                const inst = new THREE.InstancedMesh(part.geometry, part.material, items.length);
                inst.castShadow = true;
                inst.receiveShadow = true;
                // Trees never move as a group; skip per-frame matrix recompute.
                inst.instanceMatrix.setUsage(THREE.StaticDrawUsage);

                const m = new THREE.Matrix4();
                const q = new THREE.Quaternion();
                const e = new THREE.Euler();
                const pos = new THREE.Vector3();
                const scl = new THREE.Vector3();

                items.forEach((p, i) => {
                    e.set(p.tiltX, p.rotY, p.tiltZ, 'YXZ');
                    q.setFromEuler(e);
                    pos.set(p.x, p.y, p.z);
                    scl.set(p.scale, p.scale, p.scale);
                    m.compose(pos, q, scl);
                    inst.setMatrixAt(i, m);
                });
                inst.instanceMatrix.needsUpdate = true;
                inst.frustumCulled = true;
                inst.computeBoundingSphere && inst.computeBoundingSphere();

                // Only the foliage parts get wind; bark stays rigid.
                inst.userData.isFoliage = /Brunches|Billboard/i.test(part.material.name || '');
                inst.userData.lod = lod;
                inst.userData.partIdx = partIdx;

                parent.add(inst);
                instancedMeshes.push(inst);
            });
        }
    }
}

// ---------------------------------------------------------------------------
// Wind
// ---------------------------------------------------------------------------

/**
 * Cheap vertex-shader wind sway, injected into the standard material so we keep
 * PBR lighting and shadows. Displacement scales with height above the tree base
 * (y in baked local space), so trunks stay planted and tops move most.
 *
 * Call from the render loop: updateFoliageWind(elapsedSeconds).
 */
let windTime = { value: 0 };
let windPatched = false;

function patchWindShaders() {
    if (windPatched) return;
    windPatched = true;

    for (const mesh of instancedMeshes) {
        if (!mesh.userData.isFoliage) continue;
        const mat = mesh.material;
        if (mat.userData.windPatched) continue;
        mat.userData.windPatched = true;

        mat.onBeforeCompile = (shader) => {
            shader.uniforms.uWindTime = windTime;
            shader.uniforms.uTreeHeight = { value: mat.userData.treeHeight || TARGET_HEIGHT };
            shader.vertexShader = shader.vertexShader
                .replace('#include <common>',
                    '#include <common>\nuniform float uWindTime;\nuniform float uTreeHeight;')
                .replace('#include <begin_vertex>', `
                    #include <begin_vertex>
                    // Sway grows with height above the baked base, normalised
                    // against this mesh's own height (species differ), so a 4m
                    // shrub and a 13.5m fir sway proportionally rather than by
                    // the same absolute distance.
                    //
                    // 0.55 gives roughly a half-metre of travel at the crown of
                    // a 13.5m fir. Measured: at 0.16 the motion moved only
                    // ~0.04% of treeline pixels between frames -- invisible from
                    // the tee, i.e. shader cost for nothing.
                    float swayH = clamp(max(transformed.y, 0.0) / uTreeHeight, 0.0, 1.0);
                    float swayAmt = swayH * swayH * 0.55 * uTreeHeight / 13.5;
                    #ifdef USE_INSTANCING
                        float instPhase = instanceMatrix[3][0] * 0.35
                                        + instanceMatrix[3][2] * 0.21;
                    #else
                        float instPhase = 0.0;
                    #endif
                    float w = sin(uWindTime * 1.15 + instPhase)
                            + 0.4 * sin(uWindTime * 2.7 + instPhase * 1.7);
                    transformed.x += w * swayAmt;
                    transformed.z += w * swayAmt * 0.45;
                `);
        };
        mat.needsUpdate = true;
    }
}

export function updateFoliageWind(elapsed) {
    if (!instancedMeshes.length) return;
    patchWindShaders();
    windTime.value = elapsed;
}
