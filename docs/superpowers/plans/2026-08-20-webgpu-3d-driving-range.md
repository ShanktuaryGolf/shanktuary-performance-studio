# WebGPU Photorealistic 3D Driving Range Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a photorealistic 3D Golf Driving Range visualizer powered by WebGPU (with automatic WebGL2 fallback), incorporating the proven physics engine from `ShanktuaryGolf/Minigames` (`cannon-es` + aerodynamic trajectory model) and instanced Sketchfab CC-BY-4.0 foliage (Maple, Pine, Birch, Fir trees, bushes, grass, stone bridge, and yardage targets).

**Architecture:** 
1. **Frontend Renderer:** Modern Three.js `WebGPURenderer` / WebGL2 fallback with PBR shaders, dynamic shadow mapping (`PCFSoftShadowMap`), ACESFilmic tone mapping, volumetric atmospheric sky, and GPU instancing (`THREE.InstancedMesh`) for foliage.
2. **Physics Core:** Ported from `ShanktuaryGolf/Minigames` (`physics-worker.js` + `empirical-golf-model.js` / WASM), running 60Hz rigid-body ground collision, bounce damping, rolling friction, and Magnus lift/drag trajectory.
3. **Server & Live Streaming:** Served directly by Shanktuary's built-in HTTP/WebSocket server at `http://localhost:9321/range` with 1-click OBS Browser Source integration and fullscreen projector support.
4. **Desktop Integration:** Mode 4 in `shanktuary_performance_studio.py` (`[4]` or `[Tab]`).

**Tech Stack:** Three.js (WebGPU / TSL / WebGL2), Cannon-es, JavaScript / ES Modules, Python 3 (asyncio / aiohttp / websockets), Tkinter.

**Spec / References:**
- `https://github.com/ShanktuaryGolf/Minigames` (Physics engine & ball trajectory)
- `https://github.com/OpenGolfSim/fuse` (Range camera and setup reference)
- Sketchfab CC-BY-4.0 3D Asset List (LOLIPOP, mfhscoobydoo, Gravity Jack, etc.)

## Global Constraints

- Must run smoothly at 60+ FPS on standard hardware (and 120+ FPS on gaming GPUs).
- Must have automatic WebGL2 fallback if WebGPU is unsupported on the client browser.
- Must receive real-time shot telemetry over `ws://localhost:9321` and launch ball flight instantaneously.
- Must preserve all CC-BY-4.0 creator attributions in `ATTRIBUTIONS.md` and in-game credits modal.
- Full backup preserved at git tag `backup-pre-driving-range`.

---

### Task 1: WebGPU / Three.js 3D Scene Foundation & Server Endpoint

**Files:**
- Create: `assets/range/index.html`
- Create: `assets/range/js/main.js`
- Create: `assets/range/js/renderer.js`
- Modify: `obs_server.py:50-120`
- Test: `tests/test_range_server.py`

**Interfaces:**
- Consumes: HTTP GET `/range` and WebSocket `ws://localhost:9321`
- Produces: WebGPU 3D canvas viewport with camera controls, ACESFilmic tone mapping, and directional sun lighting.

- [ ] **Step 1: Write failing unit test for range server route**

```python
import urllib.request, pytest

def test_range_endpoint_served():
    req = urllib.request.urlopen("http://localhost:9321/range")
    assert req.status == 200
    html = req.read().decode()
    assert "WebGPU" in html or "Driving Range" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_range_server.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Add `/range` route to `obs_server.py`**

```python
# In obs_server.py:
async def handle_range(request):
    range_path = os.path.join(ASSETS_DIR, "range", "index.html")
    if os.path.exists(range_path):
        return web.FileResponse(range_path)
    return web.Response(text="3D Driving Range not found", status=404)

app.router.add_get('/range', handle_range)
app.router.add_static('/range/', path=os.path.join(ASSETS_DIR, 'range'), name='range_static')
```

- [ ] **Step 4: Create Three.js WebGPU Scene (`assets/range/index.html` & `assets/range/js/renderer.js`)**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Shanktuary 3D WebGPU Driving Range</title>
  <style>
    body { margin: 0; overflow: hidden; background: #000; font-family: 'Segoe UI', sans-serif; }
    #canvas-container { width: 100vw; height: 100vh; position: absolute; }
    #ui-overlay { position: absolute; top: 20px; left: 20px; color: #fff; z-index: 10; }
  </style>
  <script type="importmap">
    {
      "imports": {
        "three": "https://unpkg.com/three@0.170.0/build/three.module.js",
        "three/addons/": "https://unpkg.com/three@0.170.0/examples/jsm/"
      }
    }
  </script>
</head>
<body>
  <div id="canvas-container"></div>
  <div id="ui-overlay">
    <div style="font-size: 24px; font-weight: 800; color: #00FF66;">SHANKTUARY 3D DRIVING RANGE</div>
    <div id="shot-telemetry">Ready for shot...</div>
  </div>
  <script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_range_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add assets/range/ obs_server.py tests/test_range_server.py
git commit -m "feat: Add WebGPU 3D Driving Range scene foundation and /range server route (Task 1)"
```

---

### Task 2: Minigames Ball Physics & Aerodynamic Trajectory Engine

**Files:**
- Create: `assets/range/js/physics.js`
- Create: `assets/range/js/ball.js`
- Test: `tests/test_range_physics.js` or `tests/test_ball_physics.py`

**Interfaces:**
- Consumes: Live shot payload `{ ballSpeed, verticalLaunchAngle, horizontalLaunchAngle, total_spin, spin_axis }`
- Produces: High-precision 60Hz 3D trajectory calculation with Magnus lift, air drag, ground bounce restitution, and roll deceleration.

- [ ] **Step 1: Implement `physics.js` adapted from `ShanktuaryGolf/Minigames`**

```javascript
export class GolfPhysicsEngine {
  constructor() {
    this.gravity = -9.81; // m/s^2
    this.airDensity = 1.225; // kg/m^3
    this.ballMass = 0.0459; // kg
    this.ballRadius = 0.02135; // meters
    this.ballArea = Math.PI * Math.pow(this.ballRadius, 2);
    this.restitution = 0.45; // Green / Fairway bounce coefficient
    this.friction = 0.75; // Turf rolling resistance
  }

  calculateTrajectory(shot) {
    // Convert units: MPH to m/s, degrees to radians, RPM to rad/s
    const speedMs = shot.ballSpeed * 0.44704;
    const vlaRad = (shot.verticalLaunchAngle * Math.PI) / 180.0;
    const hlaRad = (shot.horizontalLaunchAngle * Math.PI) / 180.0;
    const spinRadS = (shot.total_spin * 2 * Math.PI) / 60.0;
    const spinAxisRad = (shot.spin_axis * Math.PI) / 180.0;

    let vx = speedMs * Math.cos(vlaRad) * Math.sin(hlaRad);
    let vy = speedMs * Math.sin(vlaRad);
    let vz = speedMs * Math.cos(vlaRad) * Math.cos(hlaRad);

    let x = 0, y = 0.02, z = 0; // Starting position at tee
    const dt = 0.01; // 10ms integration step
    const trajectoryPoints = [];

    while (y >= 0 || trajectoryPoints.length < 5) {
      const v = Math.sqrt(vx * vx + vy * vy + vz * vz);
      const drag = 0.5 * this.airDensity * this.ballArea * 0.22 * v * v;
      const lift = 0.5 * this.airDensity * this.ballArea * 0.18 * v * (spinRadS / 100);

      // Apply aerodynamic forces
      const ax = -(drag * (vx / v)) / this.ballMass;
      const ay = this.gravity - (drag * (vy / v)) / this.ballMass + (lift / this.ballMass) * Math.cos(spinAxisRad);
      const az = -(drag * (vz / v)) / this.ballMass + (lift / this.ballMass) * Math.sin(spinAxisRad);

      vx += ax * dt;
      vy += ay * dt;
      vz += az * dt;

      x += vx * dt;
      y += vy * dt;
      z += vz * dt;

      // Convert meters to yards for golf rendering
      trajectoryPoints.push({
        x: x * 1.09361,
        y: Math.max(0, y * 1.09361),
        z: z * 1.09361,
        velocity: { vx, vy, vz }
      });

      if (y <= 0 && trajectoryPoints.length > 10) break;
    }

    return trajectoryPoints;
  }
}
```

- [ ] **Step 2: Create animated glowing tracer with particle ribbon**
- [ ] **Step 3: Verify physics trajectory produces exact carry yardage matching OpenGolfCoach**
- [ ] **Step 4: Commit**

```bash
git add assets/range/js/physics.js assets/range/js/ball.js
git commit -m "feat: Implement Minigames 3D golf ball physics and trajectory engine (Task 2)"
```

---

### Task 3: Sketchfab CC-BY-4.0 Instanced Foliage & Driving Range Environment

**Files:**
- Create: `assets/range/js/environment.js`
- Create: `assets/range/js/foliage.js`
- Create: `ATTRIBUTIONS.md`

**Interfaces:**
- Consumes: Procedural fairway terrain, target green coordinates (50, 100, 150, 200, 250, 300 yds), GLTF models
- Produces: Lush 3D environment with GPU-instanced Maple/Pine/Birch/Fir trees, bushes, grass clumps, distance markers, and water hazard with stone bridge.

- [ ] **Step 1: Implement PBR Fairway & Mowing Stripe Shader**
- [ ] **Step 2: Place Target Greens at 50, 100, 150, 200, 250, 300 yards with distance flags**
- [ ] **Step 3: Setup `THREE.InstancedMesh` for 500+ perimeter forest trees (Maple, Pine, Birch, Fir)**
- [ ] **Step 4: Add scenic 175-yard water hazard with 3D stone bridge**
- [ ] **Step 5: Document all 3D asset creator licenses in `ATTRIBUTIONS.md`**
- [ ] **Step 6: Commit**

```bash
git add assets/range/js/environment.js assets/range/js/foliage.js ATTRIBUTIONS.md
git commit -m "feat: Add instanced 3D foliage, target greens, stone bridge, and attributions (Task 3)"
```

---

### Task 4: Real-Time WebSocket Shot Listener & Camera Views

**Files:**
- Create: `assets/range/js/camera.js`
- Create: `assets/range/js/websocket.js`

**Interfaces:**
- Consumes: WebSocket events from `ws://localhost:9321`
- Produces: Instantaneous 3D ball launch, camera follow-cam tracking, broadcast tower cam, and landing distance badge.

- [ ] **Step 1: Connect to WebSocket server on startup**
- [ ] **Step 2: Implement dynamic 3D Follow-Cam smoothly tracking the ball flight to the landing green**
- [ ] **Step 3: Implement camera view switcher (`[V]` key / UI button: Golfer Cam, Follow Cam, Overhead Blimp Cam, Target Green Cam)**
- [ ] **Step 4: Commit**

```bash
git add assets/range/js/camera.js assets/range/js/websocket.js
git commit -m "feat: Add WebSocket auto-launch and dynamic 3D follow-cam tracking (Task 4)"
```

---

### Task 5: Desktop App Mode 4 Integration & Hotkeys

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Hotkey `[4]` or `[Tab]`
- Produces: 1-click launch of 3D Driving Range in default browser, projector window, or OBS Browser Source.

- [ ] **Step 1: Add Mode 4 UI button and hotkey `[4]` in `shanktuary_performance_studio.py`**
- [ ] **Step 2: Add 3D Driving Range documentation to `README.md`**
- [ ] **Step 3: Test full end-to-end launch workflow**
- [ ] **Step 4: Commit**

```bash
git add shanktuary_performance_studio.py README.md
git commit -m "feat: Integrate 3D Driving Range Mode 4 into Shanktuary desktop app (Task 5)"
```
