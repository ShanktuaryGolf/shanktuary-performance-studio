// Putting green scene. Cup/flag at origin, ball walks back +Z (look toward −Z / mountains).

import {
    BALL_RADIUS,
    HOLE_RADIUS,
    FT_TO_M,
} from './putt_physics.js';
import { LADDER_DISTANCES } from './putt_drills.js';

const GREEN_SEGS = 1;
const GREEN_SIZE = 32;
const GREEN_Y = 0.02;
const FLAG_HEIGHT = 1.5;
const FLAG_W = 0.48;
const FLAG_H = 0.28;
const FLAG_LOGO_ASPECT = 712 / 640;

if (THREE.Cache) THREE.Cache.enabled = true;
const turfLoader = new THREE.TextureLoader();
const TURF_TEX = turfLoader.load('/range/textures/putting_green_detail.png', (tex) => {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(8, 8);
    tex.anisotropy = 8;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;
});
TURF_TEX.wrapS = THREE.RepeatWrapping;
TURF_TEX.wrapT = THREE.RepeatWrapping;
TURF_TEX.repeat.set(8, 8);

const COLOR_GREEN = 0x488c38;
const COLOR_COLLAR = 0x1e3d1c;
const COLOR_CUP = 0x141414;
const COLOR_RIM = 0xf0f4f8;
const COLOR_POLE = 0xf8fafc;
const COLOR_FINIAL = 0xfacc15;
const COLOR_BALL = 0xf5f5f0;

export class PuttScene {
    constructor(parentScene, opts = {}) {
        this.parent = parentScene;
        this.distanceFt = opts.distanceFt !== undefined ? opts.distanceFt : 20;

        this.group = new THREE.Group();
        this.group.name = 'putt-scene';

        this._buildGreen();
        this._buildCupAndFlag();
        this._buildLadder();
        this._buildBall();
        this.placeBallAtDistance(this.distanceFt);

        if (parentScene) parentScene.add(this.group);
    }

    getParams() {
        return { distanceFt: this.distanceFt };
    }

    heightAt(_x, _z) {
        return GREEN_Y;
    }

    setDistanceFt(distanceFt) {
        this.placeBallAtDistance(distanceFt);
    }

    setLadderVisible(on) {
        if (this.ladderGroup) this.ladderGroup.visible = !!on;
    }

    randomize() {
        const distances = [];
        for (let d = 2; d <= 40; d += 2) distances.push(d);
        this.placeBallAtDistance(distances[Math.floor(Math.random() * distances.length)]);
        return this.getParams();
    }

    placeBallAtDistance(distanceFt) {
        this.distanceFt = distanceFt;
        this.ball.position.set(0, BALL_RADIUS + GREEN_Y, distanceFt * FT_TO_M);
        this.cupGroup.position.set(0, GREEN_Y, 0);
        this.cupGroup.quaternion.identity();
    }

    setBallXZ(x, z) {
        this.ball.position.set(x, BALL_RADIUS + GREEN_Y, z);
    }

    dispose() {
        if (this.parent) this.parent.remove(this.group);
    }

    _buildGreen() {
        const geo = new THREE.PlaneGeometry(GREEN_SIZE, GREEN_SIZE, GREEN_SEGS, GREEN_SEGS);
        geo.rotateX(-Math.PI / 2);
        const mat = new THREE.MeshStandardMaterial({
            color: COLOR_GREEN,
            map: TURF_TEX,
            roughness: 0.86,
            metalness: 0.02,
            side: THREE.FrontSide,
        });
        this.green = new THREE.Mesh(geo, mat);
        this.green.position.y = GREEN_Y;
        this.green.receiveShadow = true;
        this.green.name = 'putt-green';
        this.group.add(this.green);
    }

    _buildLadder() {
        this.ladderGroup = new THREE.Group();
        this.ladderGroup.name = 'putt-ladder';
        this.ladderGroup.visible = false;

        const railSpan = 2 * FT_TO_M;
        const half = railSpan / 2;
        const maxZ = LADDER_DISTANCES[LADDER_DISTANCES.length - 1] * FT_TO_M;
        const railW = 0.04;
        const railH = 0.015;
        const paintY = GREEN_Y + 0.007;

        const mat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            polygonOffset: true,
            polygonOffsetFactor: -4,
            polygonOffsetUnits: -4,
        });

        const leftRail = new THREE.Mesh(new THREE.BoxGeometry(railW, railH, maxZ), mat);
        leftRail.position.set(-half, paintY + railH / 2, maxZ / 2);
        this.ladderGroup.add(leftRail);

        const rightRail = new THREE.Mesh(new THREE.BoxGeometry(railW, railH, maxZ), mat);
        rightRail.position.set(half, paintY + railH / 2, maxZ / 2);
        this.ladderGroup.add(rightRail);

        const rungGeo = new THREE.BoxGeometry(railSpan, railH, 0.025);
        const dotGeo = new THREE.CircleGeometry(0.045, 18);
        dotGeo.rotateX(-Math.PI / 2);
        const dotMat = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            side: THREE.DoubleSide,
            polygonOffset: true,
            polygonOffsetFactor: -5,
            polygonOffsetUnits: -5,
        });

        LADDER_DISTANCES.forEach((ft) => {
            const z = ft * FT_TO_M;
            const rung = new THREE.Mesh(rungGeo, mat);
            rung.position.set(0, paintY + railH / 2, z);
            this.ladderGroup.add(rung);
            const dot = new THREE.Mesh(dotGeo, dotMat);
            dot.position.set(0, paintY + railH + 0.004, z);
            this.ladderGroup.add(dot);
        });

        this.group.add(this.ladderGroup);
    }

    _buildCupAndFlag() {
        this.cupGroup = new THREE.Group();
        this.cupGroup.name = 'putt-cup';
        this.cupGroup.position.set(0, GREEN_Y, 0);

        const collarGeo = new THREE.RingGeometry(HOLE_RADIUS + 0.012, HOLE_RADIUS + 0.09, 32);
        collarGeo.rotateX(-Math.PI / 2);
        const collar = new THREE.Mesh(collarGeo, new THREE.MeshStandardMaterial({
            color: COLOR_COLLAR,
            roughness: 0.92,
        }));
        collar.position.y = 0.003;
        this.cupGroup.add(collar);

        const rimGeo = new THREE.RingGeometry(HOLE_RADIUS, HOLE_RADIUS + 0.012, 32);
        rimGeo.rotateX(-Math.PI / 2);
        const rim = new THREE.Mesh(rimGeo, new THREE.MeshBasicMaterial({ color: COLOR_RIM }));
        rim.position.y = 0.004;
        this.cupGroup.add(rim);

        const cupGeo = new THREE.CylinderGeometry(HOLE_RADIUS, HOLE_RADIUS, 0.12, 24, 1, true);
        const cup = new THREE.Mesh(cupGeo, new THREE.MeshStandardMaterial({
            color: COLOR_CUP,
            roughness: 0.95,
            side: THREE.DoubleSide,
        }));
        cup.position.y = -0.06;
        this.cupGroup.add(cup);

        const floorGeo = new THREE.CircleGeometry(HOLE_RADIUS, 24);
        floorGeo.rotateX(-Math.PI / 2);
        const floor = new THREE.Mesh(floorGeo, new THREE.MeshStandardMaterial({ color: COLOR_CUP }));
        floor.position.y = -0.12;
        this.cupGroup.add(floor);

        const pole = new THREE.Mesh(
            new THREE.CylinderGeometry(0.006, 0.006, FLAG_HEIGHT, 12),
            new THREE.MeshStandardMaterial({ color: COLOR_POLE, roughness: 0.2 })
        );
        pole.position.y = FLAG_HEIGHT / 2;
        pole.castShadow = true;
        this.cupGroup.add(pole);

        const finial = new THREE.Mesh(
            new THREE.SphereGeometry(0.018, 12, 12),
            new THREE.MeshStandardMaterial({ color: COLOR_FINIAL, metalness: 0.6, roughness: 0.2 })
        );
        finial.position.y = FLAG_HEIGHT;
        this.cupGroup.add(finial);

        const pennant = new THREE.Mesh(
            new THREE.PlaneGeometry(FLAG_W, FLAG_H),
            new THREE.MeshStandardMaterial({
                color: 0xffffff,
                side: THREE.DoubleSide,
                roughness: 0.55,
                metalness: 0.0,
            })
        );
        pennant.position.set(FLAG_W / 2, FLAG_HEIGHT - FLAG_H / 2, 0);
        pennant.castShadow = true;
        this.cupGroup.add(pennant);

        let logoH = FLAG_H * 0.86;
        let logoW = logoH * FLAG_LOGO_ASPECT;
        if (logoW > FLAG_W * 0.9) {
            logoW = FLAG_W * 0.9;
            logoH = logoW / FLAG_LOGO_ASPECT;
        }
        const logoMat = new THREE.MeshStandardMaterial({
            color: 0xffffff,
            side: THREE.DoubleSide,
            roughness: 0.4,
            transparent: true,
            alphaTest: 0.08,
        });
        const logoLoader = new THREE.TextureLoader();
        logoLoader.load('/range/textures/putt_flag_logo.png', (tex) => {
            tex.colorSpace = THREE.SRGBColorSpace;
            logoMat.map = tex;
            logoMat.needsUpdate = true;
        });
        const logo = new THREE.Mesh(new THREE.PlaneGeometry(logoW, logoH), logoMat);
        logo.position.set(FLAG_W / 2, FLAG_HEIGHT - FLAG_H / 2, 0.004);
        this.cupGroup.add(logo);

        this.group.add(this.cupGroup);
    }

    _buildBall() {
        this.ball = new THREE.Mesh(
            new THREE.SphereGeometry(BALL_RADIUS, 24, 16),
            new THREE.MeshStandardMaterial({
                color: COLOR_BALL,
                roughness: 0.22,
                metalness: 0.05,
            })
        );
        this.ball.castShadow = true;
        this.ball.receiveShadow = true;
        this.ball.name = 'putt-ball';
        this.group.add(this.ball);
    }
}
