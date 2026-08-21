import math

class GolfPhysicsEngine:
    def __init__(self):
        self.gravity = 9.81
        self.air_density = 1.225
        self.ball_mass = 0.04593
        self.ball_radius = 0.02135
        self.ball_area = math.pi * (self.ball_radius ** 2)
        self.DRAG_CD_BASE = 0.22
        self.LIFT_C = 0.083
        self.LIFT_D = 0.885
        self.SPIN_DECAY_RATE = 0.035
        
    def calculate_trajectory(self, speed_mph, vla_deg, hla_deg, total_spin_rpm, spin_axis_deg):
        speed_ms = speed_mph * 0.44704
        vla_rad = math.radians(vla_deg)
        hla_rad = math.radians(hla_deg)
        spin_axis_rad = math.radians(spin_axis_deg)
        
        vx = speed_ms * math.cos(vla_rad) * math.sin(hla_rad)
        vy = speed_ms * math.sin(vla_rad)
        vz = -speed_ms * math.cos(vla_rad) * math.cos(hla_rad)
        
        current_spin = total_spin_rpm
        x, y, z = 0.0, self.ball_radius, 0.0
        dt = 0.01
        
        points = []
        
        for _ in range(1000):
            v = math.sqrt(vx*vx + vy*vy + vz*vz)
            points.append({
                'x': x * 1.09361,
                'y': y * 1.09361,
                'z': abs(z) * 1.09361
            })
            
            if v > 0.5:
                current_spin *= math.exp(-self.SPIN_DECAY_RATE * dt)
                spin_rad_s = current_spin * 2 * math.pi / 60.0
                spin_ratio = (self.ball_radius * spin_rad_s) / v
                
                cd = self.DRAG_CD_BASE + 0.55 * spin_ratio
                cl = self.LIFT_C + self.LIFT_D * (spin_ratio ** 0.7)
                
                drag = 0.5 * self.air_density * self.ball_area * cd * v * v
                lift = 0.5 * self.air_density * self.ball_area * cl * v * v
                
                ax = -(drag * (vx / v)) / self.ball_mass + (lift * math.sin(-spin_axis_rad)) / self.ball_mass
                ay = -self.gravity - (drag * (vy / v)) / self.ball_mass + (lift * math.cos(spin_axis_rad)) / self.ball_mass
                az = -(drag * (vz / v)) / self.ball_mass
                
                vx += ax * dt
                vy += ay * dt
                vz += az * dt
            else:
                vy -= self.gravity * dt
                
            x += vx * dt
            y += vy * dt
            z += vz * dt
            
            if y <= self.ball_radius and len(points) > 10:
                break
                
        return points

def test_driver_trajectory():
    engine = GolfPhysicsEngine()
    points = engine.calculate_trajectory(156.0, 14.5, 0.0, 2600.0, 0.0)
    carry_z = points[-1]['z']
    assert 240 < carry_z < 310
    print(f"Driver Carry Z: {carry_z:.2f} yards")

def test_iron_trajectory():
    engine = GolfPhysicsEngine()
    points = engine.calculate_trajectory(110.0, 19.5, 0.0, 5800.0, 0.0)
    carry_z = points[-1]['z']
    assert 140 < carry_z < 210
    print(f"Iron Carry Z: {carry_z:.2f} yards")
