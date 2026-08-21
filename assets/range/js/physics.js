// 3D Ball Physics & Aerodynamic Trajectory Engine

export class GolfPhysicsEngine {
  constructor() {
    this.gravity = -9.81; // m/s^2
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.0459; // kg
    this.ballRadius = 0.02135; // meters
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);
    this.restitution = 0.45; // Bounce elasticity
    this.friction = 0.85; // Turf rolling resistance
  }

  calculateTrajectory(shot) {
    // Standardize input properties
    const ballSpeed = parseFloat(shot.ballSpeed || shot.ball_speed_mph || 150);
    const vla = parseFloat(shot.verticalLaunchAngle || shot.vertical_launch_angle_degrees || shot.vla || 12);
    const hla = parseFloat(shot.horizontalLaunchAngle || shot.horizontal_launch_angle_degrees || shot.hla || 0);
    const totalSpin = parseFloat(shot.total_spin || shot.total_spin_rpm || shot.spinSpeed || 2500);
    const spinAxis = parseFloat(shot.spin_axis || shot.spin_axis_degrees || shot.spinAxis || 0);

    const speedMs = ballSpeed * 0.44704;
    const vlaRad = (vla * Math.PI) / 180.0;
    const hlaRad = (hla * Math.PI) / 180.0;
    const spinRadS = (totalSpin * 2 * Math.PI) / 60.0;
    const spinAxisRad = (spinAxis * Math.PI) / 180.0;

    let vx = speedMs * Math.cos(vlaRad) * Math.sin(hlaRad);
    let vy = speedMs * Math.sin(vlaRad);
    let vz = -speedMs * Math.cos(vlaRad) * Math.cos(hlaRad); // Forward velocity down -Z

    let x = 0, y = 0.04, z = 0; // Starting position at tee
    const dt = 0.016; // ~60fps simulation step
    const trajectoryPoints = [];

    // Ball Flight Phase (In-Air)
    let inAir = true;
    let iterations = 0;

    while ((y >= 0 || iterations < 5) && iterations < 800) {
      const v = Math.sqrt(vx * vx + vy * vy + vz * vz);
      if (v < 0.1) break;

      // Aerodynamic Drag & Magnus Lift
      const cd = 0.22;
      const cl = 0.18 * (spinRadS / 200.0);
      const drag = 0.5 * this.airDensity * this.ballArea * cd * v * v;
      const lift = 0.5 * this.airDensity * this.ballArea * cl * v * v;

      const ax = -(drag * (vx / v)) / this.ballMass - (lift / this.ballMass) * Math.sin(spinAxisRad);
      const ay = this.gravity - (drag * (vy / v)) / this.ballMass + (lift / this.ballMass) * Math.cos(spinAxisRad);
      const az = -(drag * (vz / v)) / this.ballMass;

      vx += ax * dt;
      vy += ay * dt;
      vz += az * dt;

      x += vx * dt;
      y += vy * dt;
      z += vz * dt;

      trajectoryPoints.push({
        x: x * 1.09361,
        y: Math.max(0.04, y * 1.09361),
        z: z * 1.09361
      });

      if (y <= 0 && iterations > 10) {
        break;
      }
      iterations++;
    }

    // Ground Bounce & Roll Phase
    vy = -vy * this.restitution;
    let rollSteps = 60;
    while (rollSteps > 0 && Math.abs(vz) > 0.5) {
      vz *= 0.94;
      vx *= 0.94;
      z += vz * dt;
      x += vx * dt;
      y = 0.04;
      
      trajectoryPoints.push({
        x: x * 1.09361,
        y: 0.04,
        z: z * 1.09361
      });
      rollSteps--;
    }

    return trajectoryPoints;
  }
}
