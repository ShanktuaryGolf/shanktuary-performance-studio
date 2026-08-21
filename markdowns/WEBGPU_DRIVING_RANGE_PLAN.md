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

---

### Task 2: Minigames Ball Physics & Aerodynamic Trajectory Engine

**Files:**
- Create: `assets/range/js/physics.js`
- Create: `assets/range/js/ball.js`

**Interfaces:**
- Consumes: Live shot payload `{ ballSpeed, verticalLaunchAngle, horizontalLaunchAngle, total_spin, spin_axis }`
- Produces: High-precision 60Hz 3D trajectory calculation with Magnus lift, air drag, ground bounce restitution, and roll deceleration.

---

### Task 3: Sketchfab CC-BY-4.0 Instanced Foliage & Driving Range Environment

**Files:**
- Create: `assets/range/js/environment.js`
- Create: `assets/range/js/foliage.js`
- Create: `ATTRIBUTIONS.md`

**Interfaces:**
- Consumes: Procedural fairway terrain, target green coordinates (50, 100, 150, 200, 250, 300 yds), GLTF models
- Produces: Lush 3D environment with GPU-instanced Maple/Pine/Birch/Fir trees, bushes, grass clumps, distance markers, and water hazard with stone bridge.

---

### Task 4: Real-Time WebSocket Shot Listener & Camera Views

**Files:**
- Create: `assets/range/js/camera.js`
- Create: `assets/range/js/websocket.js`

**Interfaces:**
- Consumes: WebSocket events from `ws://localhost:9321`
- Produces: Instantaneous 3D ball launch, camera follow-cam tracking, broadcast tower cam, and landing distance badge.

---

### Task 5: Desktop App Mode 4 Integration & Hotkeys

**Files:**
- Modify: `shanktuary_performance_studio.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Hotkey `[4]` or `[Tab]`
- Produces: 1-click launch of 3D Driving Range in default browser, projector window, or OBS Browser Source.
