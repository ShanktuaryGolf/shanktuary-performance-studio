// Exact ShanktuaryGolf/Minigames Physics Engine
// Matches Minigames (physics-worker.js & empirical-golf-model.js)

export class GolfPhysicsEngine {
  constructor() {
    this.gravity = 9.81; // m/s^2
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.04593; // kg (1.62 oz)
    this.ballRadius = 0.02135; // meters (1.68" diameter)
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);

    // Minigames Ground Interaction Constants
    this.FAIRWAY_BOUNCE = 0.28;
    this.WEDGE_BOUNCE = 0.15; // Soft green bite
    this.ROLL_FACTOR = 0.70; // 30% horizontal velocity loss on first bounce
    this.ROLL_FRICTION = 0.85; // Natural turf rolling deceleration
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

    const dt = 0.01; // 10ms simulation tick
    const trajectory = [];
    let inFlight = true;
    let bounces = 0;

    // Determine bounce elasticity based on club regime (Wedges bite soft, Drivers skip)
    const bounceRetention = (vlaDeg >= 22.0 || currentSpinRPM >= 6000) 
        ? this.WEDGE_BOUNCE 
        : this.FAIRWAY_BOUNCE;

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
          // Spin decay from Minigames: Math.exp(-dt / 24.5)
          currentSpinRPM *= Math.exp(-dt / 24.5);
          const spinRadS = (currentSpinRPM * 2 * Math.PI) / 60.0;
          const spinRatio = Math.min(0.6, (this.ballRadius * spinRadS) / v);

          // Quintavalla Drag & Lift from Minigames
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

        // Ground Contact / Landing
        if (y <= this.ballRadius && step > 10) {
          y = this.ballRadius;
          bounces++;

          // Soft realistic bounce from Minigames
          vy = -vy * bounceRetention;
          vz *= this.ROLL_FACTOR;
          vx *= this.ROLL_FACTOR;

          // If vertical bounce energy is depleted or 2 small hops completed, enter pure turf roll
          if (Math.abs(vy) < 0.4 || bounces >= 2) {
            inFlight = false;
            vy = 0;
          }
        }
      } else {
        // Turf Rolling Phase
        const groundSpeed = Math.sqrt(vx * vx + vz * vz);
        if (groundSpeed < 0.08) {
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
