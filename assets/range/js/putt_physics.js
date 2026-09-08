// Putt physics port from Minigames putting-green.html (SHA-56: flat green).
// Formulas and GSPro constants: PUTT_PHYSICS_SPEC.md (repo root).
// THREE/DOM/drill callbacks are not ported — they are not physics.
//
// Source map (putting-green.html):
//   GSPRO_PUTT_COEFFS / getGSProPuttDistance / computePuttDeceleration  L1558–L1610
//   updateFrictionFromStimp                                            L1533–L1556
//   updatePhysics                                                      L1088–L1229
//   checkHoleCollisionPredictive                                       L1255–L1359
//   checkHoleCollision                                                 L1361–L1427
//   hitBall                                                            L2531–L2583
//   ballRadius 0.021, gravity 9.81, restitution 0.5, hole.radius 0.054

export const BALL_RADIUS = 0.021;
export const GRAVITY = 9.81;
export const RESTITUTION = 0.5;
export const HOLE_RADIUS = 0.054;
export const GREEN_RADIUS = 14.8;
export const STOP_SPEED = 0.001;
export const FAST_BALL_SPEED = 2.0;
export const MPH_TO_MS = 0.44704;
export const FT_TO_M = 0.3048;

// GSPro putting distance coefficients: distance(ft) = a*v² + b*v + c (v in mph)
// Derived from GSPro putting chart — matches every row to <0.1 ft
export const GSPRO_PUTT_COEFFS = {
    7:  { a: 0.1296, b: 2.200, c: -4.366 },
    8:  { a: 0.1208, b: 2.715, c: -5.132 },
    9:  { a: 0.112,  b: 3.23,  c: -5.898 },
    10: { a: 0.111,  b: 3.500, c: -6.0   },
    11: { a: 0.1011, b: 3.957, c: -6.481 },
    12: { a: 0.0962, b: 4.263, c: -6.755 },
    13: { a: 0.0979, b: 4.613, c: -7.22  },
    14: { a: 0.0996, b: 4.963, c: -7.685 }
};

export function getGSProPuttDistance(speedMPH, stimp) {
    const s = Math.max(7, Math.min(14, Math.round(stimp)));
    const coeff = GSPRO_PUTT_COEFFS[s];
    const a = coeff.a, b = coeff.b, c = coeff.c;

    // Low speed fallback: linear from 0 to chart value at 2 mph
    if (speedMPH < 2) {
        const distAt2 = a * 4 + b * 2 + c;
        const safeDist = Math.max(distAt2, 0.1);
        return Math.max(0.1, (safeDist / 2) * speedMPH);
    }

    // Quadratic formula: d = a*v² + b*v + c
    const dist = a * speedMPH * speedMPH + b * speedMPH + c;
    return Math.max(0.1, dist);
}

export function computePuttDeceleration(speedMPH, stimp) {
    const distFt = getGSProPuttDistance(speedMPH, stimp);
    const distM = distFt * 0.3048;
    const speedMS = speedMPH * 0.44704;
    // v² = 2*a*d → a = v² / (2*d)
    const decel = (speedMS * speedMS) / (2 * distM);
    return decel;
}

export function updateFrictionFromStimp(currentStimp, gravity = GRAVITY) {
    // Based on Stanford physics paper (Kolkowitz 2007)
    // Deceleration: a = -(5/7) × ρ_g × g
    // Stimpmeter releases ball at 1.83 m/s
    // Fast green (Stimp 12): rolls 3.66m → ρ_g = 0.065
    // Slow green (Stimp 4): rolls 1.22m → ρ_g = 0.196

    // Stimp range: 7 (slow) to 14 (fast), integer only
    const stimp = Math.max(7, Math.min(14, Math.round(currentStimp)));
    const stimpRange = 14 - 7;
    const rhoGFast = 0.065;
    const rhoGSlow = 0.196;
    const t = (stimp - 7) / stimpRange; // 0 = slow, 1 = fast
    const rhoG = rhoGSlow - t * (rhoGSlow - rhoGFast); // Interpolate

    // Deceleration = (5/7) × ρ_g × g
    const deceleration = (5 / 7) * rhoG * gravity;

    // For our physics update: friction coefficient such that
    // frictionForce = friction × gravity × deltaTime gives correct deceleration
    const friction = rhoG * (5 / 7);

    return { rhoG, deceleration, friction };
}

// Minimal THREE.Vector3 stand-in for the methods the original physics calls.
// Not a formula change — the original depended on THREE for vector ops only.
export class Vec3 {
    constructor(x = 0, y = 0, z = 0) {
        this.x = x;
        this.y = y;
        this.z = z;
    }

    set(x, y, z) {
        this.x = x;
        this.y = y;
        this.z = z;
        return this;
    }

    length() {
        return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
    }

    multiplyScalar(s) {
        this.x *= s;
        this.y *= s;
        this.z *= s;
        return this;
    }

    add(v) {
        this.x += v.x;
        this.y += v.y;
        this.z += v.z;
        return this;
    }

    addScaledVector(v, s) {
        this.x += v.x * s;
        this.y += v.y * s;
        this.z += v.z * s;
        return this;
    }

    normalize() {
        const lenSq = this.x * this.x + this.y * this.y + this.z * this.z;
        if (lenSq > 0) this.multiplyScalar(1 / Math.sqrt(lenSq));
        return this;
    }

    dot(v) {
        return this.x * v.x + this.y * v.y + this.z * v.z;
    }

    crossVectors(a, b) {
        const ax = a.x, ay = a.y, az = a.z;
        const bx = b.x, by = b.y, bz = b.z;
        this.x = ay * bz - az * by;
        this.y = az * bx - ax * bz;
        this.z = ax * by - ay * bx;
        return this;
    }

    reflect(n) {
        const d = 2 * this.dot(n);
        this.x -= d * n.x;
        this.y -= d * n.y;
        this.z -= d * n.z;
        return this;
    }
}

export class PuttSimulation {
    constructor(opts = {}) {
        this.gravity = GRAVITY;
        this.ballRadius = BALL_RADIUS;
        this.restitution = RESTITUTION;
        this.greenRadius = opts.greenRadius !== undefined ? opts.greenRadius : GREEN_RADIUS;

        this.currentStimp = opts.stimp !== undefined ? Math.max(7, Math.min(14, Math.round(opts.stimp))) : 10;
        this.currentPuttDeceleration = 0;
        this.friction = updateFrictionFromStimp(this.currentStimp, this.gravity).friction;

        const distanceFt = opts.distanceFt !== undefined ? opts.distanceFt : 20;
        this.holes = opts.holes !== undefined
            ? opts.holes
            : [{ x: 0, z: 0, number: 1, radius: HOLE_RADIUS }];

        const startZ = opts.startZ !== undefined ? opts.startZ : (distanceFt * FT_TO_M);
        this.position = new Vec3(0, BALL_RADIUS, startZ);
        this.ballVelocity = new Vec3(0, 0, 0);
        this.ballSpin = new Vec3(0, 0, 0);
        this.isMoving = false;
        this.puttResultProcessed = false;
        this.puttCount = 0;
        this.result = null; // 'make' | 'miss' | null
        this.tempSpinEffect = new Vec3(0, 0, 0);
        this.tempNormal = new Vec3(0, 0, 0);
    }

    setGreen({ stimp } = {}) {
        if (stimp !== undefined) {
            this.currentStimp = Math.max(7, Math.min(14, Math.round(stimp)));
            this.friction = updateFrictionFromStimp(this.currentStimp, this.gravity).friction;
        }
    }

    setDistanceFt(distanceFt) {
        if (this.holes[0]) {
            this.holes[0].x = 0;
            this.holes[0].z = 0;
        } else {
            this.holes = [{ x: 0, z: 0, number: 1, radius: HOLE_RADIUS }];
        }
        if (!this.isMoving) {
            this.position.set(0, BALL_RADIUS, distanceFt * FT_TO_M);
        }
    }

    // hitBall — putting-green.html L2531–L2583 (DOM / gate tracking omitted)
    hitBall(speed, backspin, sidespin, hla = 0) {
        if (this.isMoving) return;

        this.puttCount++;

        // Convert mph to m/s
        const speedMS = speed * 0.44704;

        // Compute per-putt deceleration from GSPro model
        this.currentPuttDeceleration = computePuttDeceleration(speed, this.currentStimp);

        // Ball at +Z, hole at origin: roll −Z. HLA: negative = left, positive = right
        // when looking toward the pin (down −Z, +X is right).
        const hlaRad = hla * Math.PI / 180;
        this.ballVelocity.set(
            speedMS * Math.sin(hlaRad),
            0,
            -speedMS * Math.cos(hlaRad)
        );

        // Set spin (convert RPM to rad/s)
        this.ballSpin.set(
            backspin * Math.PI / 30,  // backspin
            0,
            -sidespin * Math.PI / 30  // sidespin
        );

        this.isMoving = true;
        this.puttResultProcessed = false;
        this.result = null;
    }

    // Launch along +Z without aiming at the origin. Same GSPro deceleration as hitBall.
    // Used for flat rollout QA so the hole/aim geometry cannot clip the stop distance.
    launchAlongZ(speedMPH) {
        if (this.isMoving) return;
        this.puttCount++;
        const speedMS = speedMPH * 0.44704;
        this.currentPuttDeceleration = computePuttDeceleration(speedMPH, this.currentStimp);
        this.ballVelocity.set(0, 0, speedMS);
        this.ballSpin.set(0, 0, 0);
        this.isMoving = true;
        this.puttResultProcessed = false;
        this.result = null;
    }

    updatePhysics(deltaTime) {
        if (!this.isMoving) return;

        const ballVelocity = this.ballVelocity;
        const ballSpin = this.ballSpin;
        const ball = { position: this.position };
        const currentPuttDeceleration = this.currentPuttDeceleration;
        const restitution = this.restitution;
        const tempSpinEffect = this.tempSpinEffect;
        const tempNormal = this.tempNormal;
        const greenRadius = this.greenRadius;

        // Apply GSPro-matched per-putt deceleration
        const speed = ballVelocity.length();
        if (speed > 0.001) {
            const frictionForce = currentPuttDeceleration * deltaTime;
            const frictionDecel = Math.min(frictionForce / speed, 1);
            ballVelocity.multiplyScalar(1 - frictionDecel);

            // Apply spin effect (Magnus force - simplified)
            if (ballSpin.length() > 0.1) {
                tempSpinEffect
                    .crossVectors(ballSpin, ballVelocity)
                    .multiplyScalar(0.0001 * deltaTime);
                ballVelocity.add(tempSpinEffect);

                // Spin decay
                ballSpin.multiplyScalar(1 - deltaTime * 2);
            }

            // Check for hole collision BEFORE moving (predictive)
            const hadCollision = this.checkHoleCollisionPredictive(deltaTime);

            // Update position (only if no collision happened, since collision already positioned the ball)
            if (!hadCollision) {
                ball.position.addScaledVector(ballVelocity, deltaTime);
            }

            // Keep ball on green (simple collision)
            const distFromCenter = Math.sqrt(ball.position.x ** 2 + ball.position.z ** 2);
            if (distFromCenter > greenRadius) {
                // Bounce off edge
                tempNormal.set(ball.position.x, 0, ball.position.z).normalize();
                ballVelocity.reflect(tempNormal).multiplyScalar(restitution);
                ball.position.x = tempNormal.x * greenRadius;
                ball.position.z = tempNormal.z * greenRadius;
            }

            // Check for hole (post-movement for slow balls)
            this.checkHoleCollision();

            // Re-check speed after friction / spin
            const finalSpeed = ballVelocity.length();
            if (finalSpeed < 0.001) {
                ballVelocity.set(0, 0, 0);
                ballSpin.set(0, 0, 0);
                this.isMoving = false;

                if (!this.puttResultProcessed) {
                    this.puttResultProcessed = true;
                    this.result = 'miss';
                }
            }
        } else {
            // Ball stopped
            ballVelocity.set(0, 0, 0);
            ballSpin.set(0, 0, 0);
            this.isMoving = false;
            if (!this.puttResultProcessed) {
                this.puttResultProcessed = true;
                this.result = 'miss';
            }
        }
    }

    checkHoleCollisionPredictive(deltaTime) {
        const ballVelocity = this.ballVelocity;
        const ball = { position: this.position };
        const ballRadius = this.ballRadius;
        const tempNormal = this.tempNormal;
        const holes = this.holes;

        const ballSpeed = ballVelocity.length();

        // Only check fast balls predictively
        if (ballSpeed < 2.0) {
            return false;
        }

        let collisionHappened = false;

        holes.forEach(hole => {
            const collisionRadius = hole.radius + ballRadius;

            // Current distance to hole
            const currentDx = ball.position.x - hole.x;
            const currentDz = ball.position.z - hole.z;
            const currentDist = Math.sqrt(currentDx * currentDx + currentDz * currentDz);

            // Next position after movement
            const nextX = ball.position.x + ballVelocity.x * deltaTime;
            const nextZ = ball.position.z + ballVelocity.z * deltaTime;
            const nextDx = nextX - hole.x;
            const nextDz = nextZ - hole.z;
            const nextDist = Math.sqrt(nextDx * nextDx + nextDz * nextDz);

            // Check if ball will cross into collision radius this frame
            if (currentDist > collisionRadius && nextDist <= collisionRadius) {
                // Ball is about to collide - find exact collision point
                const dirX = ballVelocity.x / ballSpeed;
                const dirZ = ballVelocity.z / ballSpeed;

                // Use quadratic equation to find collision time
                // Circle-ray intersection
                const ex = ball.position.x - hole.x;
                const ez = ball.position.z - hole.z;
                const a = dirX * dirX + dirZ * dirZ;
                const b = 2 * (ex * dirX + ez * dirZ);
                const c = ex * ex + ez * ez - collisionRadius * collisionRadius;

                const discriminant = b * b - 4 * a * c;

                if (discriminant >= 0) {
                    const t = (-b - Math.sqrt(discriminant)) / (2 * a);

                    if (t > 0 && t <= ballSpeed * deltaTime) {
                        // Move ball to exact collision point
                        ball.position.x += dirX * t;
                        ball.position.z += dirZ * t;

                        // Calculate normal at collision point (points from hole center to ball)
                        tempNormal.set(
                            ball.position.x - hole.x,
                            0,
                            ball.position.z - hole.z
                        ).normalize();

                        // Reflect velocity using vector reflection formula: V' = V - 2(V·N)N
                        const dot = ballVelocity.dot(tempNormal);

                        ballVelocity.x -= 2 * dot * tempNormal.x;
                        ballVelocity.y -= 2 * dot * tempNormal.y;
                        ballVelocity.z -= 2 * dot * tempNormal.z;

                        // Energy loss
                        ballVelocity.multiplyScalar(0.7);

                        collisionHappened = true;
                    }
                }
            }
        });

        return collisionHappened;
    }

    checkHoleCollision() {
        const ballVelocity = this.ballVelocity;
        const ball = { position: this.position };
        const ballRadius = this.ballRadius;
        const tempNormal = this.tempNormal;
        const holes = this.holes;

        holes.forEach(hole => {
            const dx = ball.position.x - hole.x;
            const dz = ball.position.z - hole.z;
            const dist = Math.sqrt(dx * dx + dz * dz);

            const ballSpeed = ballVelocity.length();
            const collisionRadius = hole.radius + ballRadius;

            // Check if ball is going too fast - it will bounce off flagstick/hole edge
            if (dist <= collisionRadius && ballSpeed >= 2.0) {
                // Ball hit the flagstick/hole edge going too fast - bounce off
                tempNormal.set(dx, 0, dz).normalize();

                // Position ball exactly at collision point (not past it)
                ball.position.x = hole.x + tempNormal.x * collisionRadius;
                ball.position.z = hole.z + tempNormal.z * collisionRadius;

                // Reflect velocity smoothly
                const dot = ballVelocity.dot(tempNormal);
                ballVelocity.x -= 2 * dot * tempNormal.x;
                ballVelocity.z -= 2 * dot * tempNormal.z;

                // Energy loss on impact
                ballVelocity.multiplyScalar(0.7);

                return; // Don't process as holed
            }

            // Ball going slow enough to drop in hole
            if (dist < collisionRadius && ballSpeed < 2.0) {
                // Ball in hole!
                ballVelocity.set(0, 0, 0);
                this.isMoving = false;
                this.puttResultProcessed = true; // Mark as processed
                this.result = 'make';
            }
        });
    }
}

export function simulateFlatPutt(speedMPH, stimp, { dt = 1 / 240, maxTime = 60 } = {}) {
    const sim = new PuttSimulation({
        stimp,
        holes: [],
        greenRadius: 1e9,
    });
    sim.position.set(0, BALL_RADIUS, 0);
    sim.launchAlongZ(speedMPH);
    const startX = sim.position.x;
    const startZ = sim.position.z;
    let t = 0;
    while (sim.isMoving && t < maxTime) {
        sim.updatePhysics(dt);
        t += dt;
    }
    const distM = Math.hypot(sim.position.x - startX, sim.position.z - startZ);
    const distFt = distM / FT_TO_M;
    const expectedFt = getGSProPuttDistance(speedMPH, stimp);
    return {
        distFt,
        expectedFt,
        errFt: distFt - expectedFt,
        timeS: t,
        stopped: !sim.isMoving,
        result: sim.result,
        x: sim.position.x,
        z: sim.position.z,
    };
}
