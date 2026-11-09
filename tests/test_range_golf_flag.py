"""Validate real Three.js flag meshes and lifecycle without requiring WebGL."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_flag_fabric_deforms_without_moving_the_target_or_hoist():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    subprocess.run([node, '--input-type=module', '-e', r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
globalThis.THREE = require('./assets/range/js/three.min.js');
let onLogoLoad;
let logoDisposed = false;
const draws = [];
THREE.TextureLoader.prototype.load = (url, ready) => {
    assert.equal(url, '/range/textures/studio_flag_brand.png');
    assert.ok(fs.existsSync('.' + url.replace('/range/', '/assets/range/')));
    onLogoLoad = ready;
};
const context = {fillRect: (...args) => draws.push(args), drawImage: (...args) => draws.push(args)};
globalThis.document = {createElement: tag => {
    assert.equal(tag, 'canvas');
    return {getContext: () => context};
}};
const source = fs.readFileSync('assets/range/js/studio_flag.js', 'utf8');
const {createStudioGolfFlag} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const target = new THREE.Group();
target.position.z = -137.16;
const {group, update} = createStudioGolfFlag(target, '#e6ba54');
assert.equal(group.parent, target);
const cloth = group.getObjectByName('flag-cloth');
assert.ok(cloth.geometry.attributes.position.count > 500);
assert.equal(cloth.material.side, THREE.DoubleSide);
assert.ok(cloth.material.roughness > .8 && cloth.material.metalness === 0);
assert.equal(cloth.material.map, null, 'plain gold fallback while logo loads');
assert.equal(cloth.material.color.getHexString(), 'e6ba54');
const image = {width: 256, height: 256};
onLogoLoad({image, dispose: () => {logoDisposed = true;}});
assert.ok(logoDisposed, 'temporary source texture is released');
assert.ok(cloth.material.map.isCanvasTexture);
assert.equal(cloth.material.map.colorSpace, THREE.SRGBColorSpace);
assert.equal(cloth.material.color.getHexString(), 'ffffff', 'logo is not gold-tinted');
assert.equal(context.fillStyle, '#e6ba54');
assert.deepEqual(draws, [[0, 0, 1080, 660], [image, 320, 110, 440, 440]]);
assert.equal(cloth.material.map.image.width, 1080);
assert.equal(cloth.material.map.image.height, 660);
const before = [...cloth.geometry.attributes.position.array];
const uv = cloth.geometry.attributes.uv;
update(2.4);
const after = cloth.geometry.attributes.position.array;
assert.notDeepEqual([...after], before, 'free fabric moves');
for (let i = 0; i < uv.count; i++) {
    if (uv.getX(i) === 0) assert.deepEqual([...after.slice(i*3,i*3+3)], before.slice(i*3,i*3+3), 'hoist is pinned');
}
for (const time of [0, 1, 5, 10000, NaN]) {
    update(time);
    assert.ok([...after, ...cloth.geometry.attributes.normal.array].every(Number.isFinite));
    assert.ok(cloth.geometry.boundingSphere.radius < .8);
}
assert.equal(target.position.z, -137.16, 'visual wind cannot move the target');
assert.equal(group.getObjectByName('flagstick').geometry.parameters.height, 2.9);
assert.ok(group.getObjectByName('flag-cup-rim').geometry.parameters.outerRadius < .07);
target.position.z = -18.288;
target.updateMatrixWorld(true);
assert.equal(group.getWorldPosition(new THREE.Vector3()).z, -18.288);
assert.ok(!/requestAnimationFrame|setInterval|setTimeout/.test(source), 'reuse existing animation loop');
const main = fs.readFileSync('assets/range/js/main.js', 'utf8');
assert.ok(main.includes('updateEnvironmentWind(elapsed)'));
const environment = fs.readFileSync('assets/range/js/environment.js', 'utf8');
assert.ok(environment.includes("from './studio_flag.js'"));
assert.ok(environment.includes('createStudioGolfFlag(greenGroup'));
"""], cwd=ROOT, check=True, capture_output=True, text=True)
