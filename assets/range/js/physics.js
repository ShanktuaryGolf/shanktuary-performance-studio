// Full Quintavalla 3D Aerodynamic Flight Physics & Turf Ground Interaction Engine
// Adapted from ShanktuaryGolf/Minigames (physics-worker.js & empirical-golf-model.js)

export class GolfPhysicsEngine {
  constructor() {
    this.gravity = 9.81; // m/s^2 (downwards)
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.04593; // kg (1.62 oz)
    this.ballRadius = 0.02135; // meters (1.68" diameter)
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);

    // Quintavalla Aerodynamic Coefficients
    this.DRAG_CD_BASE = 0.22;
    this.LIFT_C = 0.083;
    this.LIFT_D = 0.885;
    this.SPIN_DECAY_RATE = 0.035; // ~3.5% spin decay per second in flight

    // Turf & Ground Interaction
    this.BOUNCE_RETENTION = 0.42; // Fairway bounce coefficient
    this.ROLL_FRICTION = 0.88; // Ground rolling resistance per tick
  }

  calculateTrajectory(shot) {
    const ballSpeedMPH = parseFloat(shot.ballSpeed || shot.ball_speed_mph || 150);
    const vlaDeg = parseFloat(shot.verticalLaunchAngle || shot.vertical_launch_angle_degrees || 12.0);
    const hlaDeg = parseFloat(shot.horizontalLaunchAngle || shot.horizontal_launch_angle_degrees || 0.0);
    const initialSpinRPM = parseFloat(shot.total_spin || shot.total_spin_rpm || shot.spinSpeed || 2500);
    const spinAxisDeg = parseFloat(shot.spin_axis || shot.spin_axis_degrees || 0.0);

    // Convert to standard SI units (m/s, radians)
    const speedMS = ballSpeedMPH * 0.44704;
    const vlaRad = (vlaDeg * Math.PI) / 180.0;
    const hlaRad = (hlaDeg * Math.PI) / 180.0;
    const spinAxisRad = (spinAxisDeg * Math.PI) / 180.0;

    let vx = speedMS * Math.cos(vlaRad) * Math.sin(hlaRad);
    let vy = speedMS * Math.sin(vlaRad);
    let vz = -speedMS * Math.cos(vlaRad) * Math.cos(hlaRad); // -Z is forward down range

    let currentSpinRPM = initialSpinRPM;

    let x = 0;
    let y = this.ballRadius; // Start on ground/tee surface
    let z = 0;

    const dt = 0.01; // 10ms simulation tick
    const trajectory = [];
    let bounces = 0;
    let inFlight = true;

    for (let step = 0; step < 1200; step++) {
      const v = Math.sqrt(vx * vx + vy * vy + vz * vz);
      
      // Save point in yards (1m = 1.09361 yards)
      trajectory.push({
        x: x * 1.09361,
        y: y * 1.09361,
        z: z * 1.09361,
        v: v * 2.237, // mph
        inFlight: inFlight,
        bounces: bounces
      });

      if (inFlight) {
        if (v > 0.5) {
          // Spin decay over time
          currentSpinRPM *= Math.exp(-this.SPIN_DECAY_RATE * dt);
          const spinRadS = (currentSpinRPM * 2 * Math.PI) / 60.0;
          const spinRatio = (this.ballRadius * spinRadS) / v;

          // Quintavalla Drag & Lift
          const cd = this.DRAG_CD_BASE + 0.55 * spinRatio;
          const cl = this.LIFT_C + this.LIFT_D * Math.pow(spinRatio, 0.7);

          const dragForce = 0.5 * this.airDensity * this.ballArea * cd * v * v;
          const liftForce = 0.5 * this.airDensity * this.ballArea * cl * v * v;

          // Aerodynamic Accelerations
          const dragAccelX = -(dragForce * (vx / v)) / this.ballMass;
          const dragAccelY = -(dragForce * (vy / v)) / this.ballMass;
          const dragAccelZ = -(dragForce * (vz / v)) / this.ballMass;

          // Magnus lift vector projected along spin axis tilt
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

        // Ground Collision Check (Flush with grass surface)
        if (y <= this.ballRadius && step > 10) {
          y = this.ballRadius;
          bounces++;

          // Bounce upward with restitution
          vy = -vy * this.BOUNCE_RETENTION;
          vz *= 0.85;
          vx *= 0.85;

          // If vertical bounce energy is depleted, enter pure turf roll
          if (Math.abs(vy) < 0.6 || bounces > 4) {
            inFlight = false;
            vy = 0;
          }
        }
      } else {
        // Turf Rolling & Friction Phase
        const groundSpeed = Math.sqrt(vx * vx + vz * vz);
        if (groundSpeed < 0.05) {
          break; // Ball came to full stop
        }

        vx *= Math.pow(this.ROLL_FRICTION, dt * 60);
        vz *= Math.pow(this.ROLL_FRICTION, dt * 60);
        y = this.ballRadius;

        x += vx * dt;
        z += vz * dt;
      }
    }

    return trajectory;
  }
}
