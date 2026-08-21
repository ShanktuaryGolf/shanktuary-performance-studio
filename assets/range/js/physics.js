// Exact Par-3 Holes Physics Engine from ShanktuaryGolf/Minigames
// Implements Minigames Regime Bounce Retentions (0.70 - 0.78) and USGA Stimpmeter Green Roll

export class GolfPhysicsEngine {
  constructor() {
    this.gravity = 9.81; // m/s^2
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.04593; // kg
    this.ballRadius = 0.02135; // meters
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);

    // Par-3 Green & Fairway Properties from Minigames (physics-worker.js)
    this.GREEN_ROLL_FACTOR = 0.95; // Retains 95% horizontal forward velocity on green impact
    this.GREEN_STIMP_MU = 0.082; // Realistic tournament Stimpmeter friction (11.5 Stimp)
  }

  getPhysicsRegime(vlaDeg, ballSpeedMPH) {
    if (vlaDeg >= 22.0 || ballSpeedMPH <= 75.0) return 'WEDGE';
    if (vlaDeg <= 14.0 && ballSpeedMPH >= 140.0) return 'LOW_TRAJECTORY';
    if (ballSpeedMPH >= 150.0) return 'POWER_SHOT';
    if (vlaDeg >= 18.0) return 'HIGH_IRON';
    return 'MID_IRON';
  }

  getRegimeBounceRetention(regime) {
    switch (regime) {
      case 'WEDGE': return 0.70;
      case 'LOW_TRAJECTORY': return 0.78;
      case 'MID_IRON': return 0.75;
      case 'HIGH_IRON': return 0.70;
      case 'POWER_SHOT': return 0.75;
      default: return 0.74;
    }
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

    const regime = this.getPhysicsRegime(vlaDeg, ballSpeedMPH);
    const bounceRetention = this.getRegimeBounceRetention(regime);

    for (let step = 0; step < 3000; step++) {
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
          // Spin decay from Minigames: Math.exp(-dt / 24.5)
          currentSpinRPM *= Math.exp(-dt / 24.5);
          const spinRadS = (currentSpinRPM * 2 * Math.PI) / 60.0;
          const spinRatio = Math.min(0.6, (this.ballRadius * spinRadS) / v);

          // Quintavalla Drag & Lift
          const cd = 0.22 + 0.38 * spinRatio;
          const cl = Math.min(0.28, 0.07 + 0.80 * spinRatio);

          const dragForce = 0.5 * this.airDensity * this.ballArea * cd * v * v;
          const liftForce = 0.5 * this.airDensity * this.ballArea * cl * v * v;

          const dragAccelX = -(dragForce * (vx / v)) / this.ballMass;
          const dragAccelY = -(dragForce * (vy / v)) / this.ballMass;
          const dragAccelZ = -(dragForce * (vz / v)) / this.ballMass;

          const liftAccelY = (liftForce * Math.cos(spinAxisRad)) / this.ballMass;
          const liftAccelX = (liftForce * Math.sin(-spinAxisRad)) / this.ballMass;

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

        // Ground Impact & Bounce
        if (y <= this.ballRadius && step > 10) {
          y = this.ballRadius;
          bounces++;

          // Minigames Bounce & Roll Retention
          vy = -vy * (bounceRetention * (1.0 - bounces * 0.12));
          vz *= this.GREEN_ROLL_FACTOR;
          vx *= this.GREEN_ROLL_FACTOR;

          // Transition to smooth green roll when vertical bounce subsides
          if (Math.abs(vy) < 0.25 || bounces >= 3) {
            inFlight = false;
            vy = 0;
          }
        }
      } else {
        // Physical Green Roll (Stimpmeter Deceleration: a = mu * g)
        const groundSpeed = Math.sqrt(vx * vx + vz * vz);
        if (groundSpeed < 0.04) {
          break; // Ball fully stopped naturally
        }

        // Linear physical friction force: F_friction = mu * m * g
        const decel = this.GREEN_STIMP_MU * this.gravity * dt;
        const newSpeed = Math.max(0, groundSpeed - decel);
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
