"""Real Three.js geometry checks for the reference's low side partitions."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_bay_partitions_frame_the_tee_without_crossing_the_shot_lane():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    subprocess.run([node, '--input-type=module', '-e', r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
globalThis.THREE = require('./assets/range/js/three.min.js');
// Only image loading is stubbed; geometry uses the real bundled Three.js.
THREE.TextureLoader.prototype.load = () => new THREE.Texture();
const source = fs.readFileSync('assets/range/js/studio_decor.js', 'utf8');
const {createStudioBayDividers} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const tee = new THREE.Group();
createStudioBayDividers(tee);
tee.updateMatrixWorld(true);
assert.equal(tee.children.length, 2);
for (const [index, bay] of tee.children.entries()) {
    const side = index === 0 ? -1 : 1;
    const bounds = new THREE.Box3().setFromObject(bay);
    const size = bounds.getSize(new THREE.Vector3());
    assert.ok(size.z > 2.2 && size.x < .3, 'partitions run along the mat');
    assert.ok(size.y < 1.1 && bounds.min.y >= 0, 'low panels on apron');
    assert.ok(side < 0 ? bounds.max.x < -2.4 : bounds.min.x > 2.4, 'clear hitting mat');
    const normal = new THREE.Vector3(0, 0, 1).transformDirection(bay.matrixWorld);
    assert.ok(normal.x * side < -.99, 'logo faces inward');
    const logo = bay.getObjectByName('studio-bay-logo');
    assert.ok(logo.material.transparent && !logo.material.depthWrite);
    assert.ok(logo.material.isMeshStandardMaterial, 'logo responds to lighting');
    assert.equal(bay.getObjectByName('studio-bay-inset').material.color.getHex(), 0x293632);
    const frame = bay.getObjectByName('studio-bay-frame');
    assert.ok(frame.castShadow && frame.receiveShadow);
    assert.ok(frame.geometry.parameters.options.bevelEnabled);
    for (const aspect of [16 / 9, 2.26]) {
        const camera = new THREE.PerspectiveCamera(50, aspect, .1, 1500);
        camera.position.set(0, 2.4, 5.8);
        camera.lookAt(0, .5, -9);
        camera.updateMatrixWorld(true);
        const edge = new THREE.Vector3(side * 2.68, 1.08, bounds.min.z).project(camera);
        assert.ok(Math.abs(edge.x) > .5, 'partitions frame outer edges');
    }
}
"""], cwd=ROOT, check=True, capture_output=True, text=True)
