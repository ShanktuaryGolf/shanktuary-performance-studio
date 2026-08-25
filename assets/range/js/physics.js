// Calibrated Golf Physics Engine with Realistic Turf Restitution & Controlled Rollout
// Zero Trampoline Bounces (0.28 / 0.15 Restitution) & Natural Roll Friction (12 m/s^2)

export class GolfPhysicsEngine {
  constructor() {
    this.gravity = 9.81; // m/s^2
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.04593; // kg
    this.ballRadius = 0.02135; // meters
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);

    // Realistic Ground Interaction Constants
    this.FAIRWAY_BOUNCE = 0.28; // Small natural check hop (no trampoline)
    this.WEDGE_BOUNCE = 0.14;   // Soft bite for wedges & high-spin shots
    this.ROLL_FACTOR = 0.65;    // 35% horizontal velocity absorbed per bounce
    this.TURF_DECEL = 13.5;     // 13.5 m/s^2 linear turf roll friction
  }

  calculateTrajectory(shot) {
    const ballSpeedMPH = parseFloat(shot.ballSpeed || shot.ball_speed_mph || 110);
    const vlaDeg = parseFloat(shot.verticalLaunchAngle || shot.vertical_launch_angle_degrees || 18.0);
    const hlaDeg = parseFloat(shot.horizontalLaunchAngle || shot.horizontal_launch_angle_degrees || 0.0);
    const initialSpinRPM = parseFloat(shot.total_spin || shot.total_spin_rpm || shot.spinSpeed || 5000);
    const spinAxisDeg = parseFloat(shot.spin_axis || shot.spin_axis_degrees || 0.0);

    const speedMS = ballSpeedMPH * 0.44704;
    const vlaRad = (vlaDeg * Math.PI) / 180.0;
    const hlaRad = (hlaDeg * Math.PI) / 180.0;
    const spinAxisRad = (spinAxisDeg * Math.PI) / 180.0;

    let vx = speedMS * Math.cos(vlaRad) * Math.sin(hlaRad);
    let vy = speedMS * Math.sin(vlaRad);
    let vz = -speedMS * Math.cos(vlaRad) * Math.cos(hlaRad); // -Z forward down range

    let currentSpinRPM = initialSpinRPM;

    let x = 0;
    let y = this.ballRadius;
    let z = 0;

    const dt = 0.01; // 10ms tick
    const trajectory = [];
    let inFlight = true;
    let bounces = 0;

    // Wedge / High-spin regime bites soft
    const isWedgeOrHighSpin = vlaDeg >= 22.0 || currentSpinRPM >= 6000 || ballSpeedMPH <= 75;
    const bounceRetention = isWedgeOrHighSpin ? this.WEDGE_BOUNCE : this.FAIRWAY_BOUNCE;

    for (let step = 0; step < 2500; step++) {
      const v = Math.sqrt(vx * vx + vy * vy + vz * vz);

      trajectory.push({
        x: x * 1.09361,
        y: y * 1.09361,
        z: z * 1.09361,
        v: v * 2.237,
        inFlight: inFlight,
        bounces: bounces
      });

      if (inFlight) {
        if (v > 0.5) {
          // Spin decay: Math.exp(-dt / 24.5)
          currentSpinRPM *= Math.exp(-dt / 24.5);
          const spinRadS = (currentSpinRPM * 2 * Math.PI) / 60.0;
          const spinRatio = Math.min(0.6, (this.ballRadius * spinRadS) / v);

          // Quintavalla Aerodynamics
          const cd = 0.22 + 0.38 * spinRatio;
          const cl = Math.min(0.28, 0.07 + 0.80 * spinRatio);

          const dragForce = 0.5 * this.airDensity * this.ballArea * cd * v * v;
          const liftForce = 0.5 * this.airDensity * this.ballArea * cl * v * v;

          const dragAccelX = -(dragForce * (vx / v)) / this.ballMass;
          const dragAccelY = -(dragForce * (vy / v)) / this.ballMass;
          const dragAccelZ = -(dragForce * (vz / v)) / this.ballMass;

          const liftAccelY = (liftForce * Math.cos(spinAxisRad)) / this.ballMass;
          // Nova/TrackMan convention: positive spin axis = tilt right = fade.
          // +X is RIGHT (offline > 0 renders "R"), so lateral lift must use
          // sin(+axis) — sin(-axis) mirrored every curve (fades flew as draws).
          const liftAccelX = (liftForce * Math.sin(spinAxisRad)) / this.ballMass;

          const ax = dragAccelX + liftAccelX;
          const ay = -this.gravity + dragAccelY + liftAccelY;
          const az = dragAccelZ;

          vx += ax * dt;
          vy += ay * dt;
          vz += az * dt;
        } else {
          vy -= this.gravity * dt;
        }

        x += vx * dt;
        y += vy * dt;
        z += vz * dt;

        // Ground Impact Handling
        if (y <= this.ballRadius && step > 10) {
          y = this.ballRadius;
          bounces++;

          // Gentle ground check bounce (NO trampoline!)
          vy = -vy * bounceRetention;
          vz *= this.ROLL_FACTOR;
          vx *= this.ROLL_FACTOR;

          // Transition to rolling after initial hop dissipation
          if (Math.abs(vy) < 0.4 || bounces >= 2) {
            inFlight = false;
            vy = 0;
          }
        }
      } else {
        // Controlled Ground Turf Roll Phase
        const groundSpeed = Math.sqrt(vx * vx + vz * vz);
        if (groundSpeed < 0.05) {
          break; // Ball came to full stop
        }

        // Linear turf deceleration: a = 13.5 m/s^2
        const newSpeed = Math.max(0, groundSpeed - this.TURF_DECEL * dt);
        const ratio = newSpeed / groundSpeed;

        vx *= ratio;
        vz *= ratio;
        y = this.ballRadius;

        x += vx * dt;
        z += vz * dt;
      }
    }

    return trajectory;
  }
}
