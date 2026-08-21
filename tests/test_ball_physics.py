import math

class GolfPhysicsEngine:
    def __init__(self):
        self.gravity = -9.81  # m/s^2
        self.air_density = 1.225  # kg/m^3
        self.ball_mass = 0.0459  # kg
        self.ball_radius = 0.02135  # meters
        self.ball_area = math.pi * (self.ball_radius ** 2)
        
    def calculate_trajectory(self, speed_mph, vla_deg, hla_deg, total_spin_rpm, spin_axis_deg):
        speed_ms = speed_mph * 0.44704
        vla_rad = math.radians(vla_deg)
        hla_rad = math.radians(hla_deg)
        spin_rad_s = total_spin_rpm * 2 * math.pi / 60.0
        spin_axis_rad = math.radians(spin_axis_deg)
        
        vx = speed_ms * math.cos(vla_rad) * math.sin(hla_rad)
        vy = speed_ms * math.sin(vla_rad)
        vz = speed_ms * math.cos(vla_rad) * math.cos(hla_rad)
        
        x, y, z = 0.0, 0.02, 0.0
        dt = 0.01
        
        points = []
        
        while y >= 0 or len(points) < 5:
            v = math.sqrt(vx*vx + vy*vy + vz*vz)
            
            drag = 0.5 * self.air_density * self.ball_area * 0.12 * v * v
            lift = 0.5 * self.air_density * self.ball_area * 0.18 * v * (spin_rad_s / 100)
            
            ax = -(drag * (vx / v)) / self.ball_mass
            ay = self.gravity - (drag * (vy / v)) / self.ball_mass + (lift / self.ball_mass) * math.cos(spin_axis_rad)
            az = -(drag * (vz / v)) / self.ball_mass + (lift / self.ball_mass) * math.sin(spin_axis_rad)
            
            vx += ax * dt
            vy += ay * dt
            vz += az * dt
            
            x += vx * dt
            y += vy * dt
            z += vz * dt
            
            points.append({
                'x': x * 1.09361,
                'y': max(0, y * 1.09361),
                'z': z * 1.09361
            })
            
            if y <= 0 and len(points) > 10:
                break
                
        return points

def test_driver_trajectory():
    engine = GolfPhysicsEngine()
    # Typical driver stats
    points = engine.calculate_trajectory(156.0, 15.7, 0.0, 2784.0, 0.0)
    
    carry_y = points[-1]['y']
    carry_z = points[-1]['z']
    
    # Check if ball landed
    assert carry_y == 0
    # Expected driver carry is around 250-300 yards. Let's check sanity.
    assert 200 < carry_z < 350
    print(f"Driver Carry Z: {carry_z:.2f} yards")

def test_iron_trajectory():
    engine = GolfPhysicsEngine()
    # Typical 7-iron stats
    points = engine.calculate_trajectory(110.0, 20.0, 0.0, 6000.0, 0.0)
    carry_z = points[-1]['z']
    
    assert 120 < carry_z < 200
    print(f"Iron Carry Z: {carry_z:.2f} yards")
