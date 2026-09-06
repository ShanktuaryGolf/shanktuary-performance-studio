// Grid Challenge UI & 3D WebGL Zone Visualizer
//
// Strictly consumes gridMode state machine via getState() and subscribe().
// Manages:
//   1. Blueprint-styled zone picker modal (Classic & Custom Grid modes)
//   2. WebGL 3D fairway highlight marking ONLY the activeZoneIndex

import { gridMode } from './grid_mode.js';

const CSS_ID = 'sps-grid-ui-styles';

function ensureStyles() {
    if (typeof document === 'undefined') return;
    if (document.getElementById(CSS_ID)) return;
    const style = document.createElement('style');
    style.id = CSS_ID;
    style.textContent = `
        #grid-zone-picker {
            position: absolute;
            top: 76px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 950;
            pointer-events: auto;
            animation: gridPickerFadeIn 0.2s ease-out;
        }

        .grid-blueprint-modal {
            width: 450px;
            max-width: 94vw;
            background: #091733;
            border: 2px solid #38bdf8;
            border-radius: 12px;
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.75), 0 0 24px rgba(56, 189, 248, 0.35);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background-image: 
                linear-gradient(rgba(56, 189, 248, 0.09) 1px, transparent 1px),
                linear-gradient(90deg, rgba(56, 189, 248, 0.09) 1px, transparent 1px);
            background-size: 20px 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #f8fafc;
        }

        .grid-blueprint-header {
            padding: 14px 18px;
            background: rgba(14, 165, 233, 0.15);
            border-bottom: 2px solid #38bdf8;
            text-align: center;
        }

        .grid-blueprint-title {
            margin: 0;
            font-size: 1.15rem;
            font-weight: 900;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            color: #e0f2fe;
            text-shadow: 0 0 10px rgba(56, 189, 248, 0.7);
        }

        .grid-blueprint-sub {
            margin-top: 4px;
            font-size: 0.75rem;
            color: #93c5fd;
        }

        .grid-start-ctrl-bar {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 10px 14px;
            background: rgba(15, 23, 42, 0.75);
            border-bottom: 1px solid rgba(56, 189, 248, 0.25);
            font-size: 0.78rem;
        }

        .grid-start-ctrl-bar label {
            color: #93c5fd;
            font-weight: 700;
        }

        .grid-start-ctrl-bar input {
            width: 70px;
            padding: 4px 8px;
            background: #0b1528;
            border: 1.5px solid #38bdf8;
            border-radius: 6px;
            color: #ffffff;
            font-weight: 800;
            font-family: "Consolas", monospace;
            text-align: center;
        }

        .grid-start-ctrl-bar button {
            padding: 5px 12px;
            background: #0284c7;
            border: none;
            border-radius: 6px;
            color: white;
            font-size: 0.75rem;
            font-weight: 800;
            cursor: pointer;
            transition: background 0.15s ease;
        }
        .grid-start-ctrl-bar button:hover {
            background: #0369a1;
        }

        .grid-start-hint {
            font-size: 0.7rem;
            color: #7dd3fc;
            text-align: center;
            padding: 4px 10px;
            background: rgba(14, 165, 233, 0.08);
            border-bottom: 1px solid rgba(56, 189, 248, 0.15);
        }

        .grid-zones-grid {
            padding: 12px 14px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            max-height: 52vh;
            overflow-y: auto;
        }

        .grid-zone-pick-btn {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 9px 12px;
            background: rgba(15, 33, 68, 0.6);
            border: 1.5px solid rgba(56, 189, 248, 0.4);
            border-radius: 8px;
            color: #f8fafc;
            cursor: pointer;
            transition: all 0.15s ease-in-out;
            font-family: "Consolas", monospace;
        }

        .grid-zone-pick-btn:hover {
            background: rgba(56, 189, 248, 0.28);
            border-color: #38bdf8;
            transform: translateY(-1px);
            box-shadow: 0 0 14px rgba(56, 189, 248, 0.4);
        }

        .grid-zone-pick-label {
            font-size: 0.92rem;
            font-weight: 800;
            letter-spacing: 0.5px;
        }

        .grid-zone-pick-arrow {
            font-size: 0.72rem;
            color: #38bdf8;
            font-weight: 700;
        }

        @keyframes gridPickerFadeIn {
            from { opacity: 0; transform: translate(-50%, -6px); }
            to { opacity: 1; transform: translate(-50%, 0); }
        }
    `;
    document.head.appendChild(style);
}

/**
 * Validates and snaps a user start distance to an even 10-yard multiple.
 * E.g., 57 -> 60, 43 -> 40. Clamped between 20 and 450 yards.
 */
export function sanitizeStartDistance(val) {
    const n = Number(val);
    if (!Number.isFinite(n)) return 180;
    const rounded = Math.round(n / 10) * 10;
    return Math.max(20, Math.min(450, rounded));
}

/**
 * Renders the blueprint-styled zone picker into the host container.
 * Supports both Classic Grid and Custom Grid (with validated start yardage input).
 */
export function renderGridPicker(host, state, { isCustom = false, onStartChange = null } = {}) {
    if (!host) return;
    ensureStyles();

    if (!state || state.status !== 'picking' || !Array.isArray(state.zones)) {
        host.innerHTML = '';
        return;
    }

    host.style.cssText = [
        'position:absolute',
        'top:76px',
        'left:50%',
        'transform:translateX(-50%)',
        'z-index:950',
        'display:flex',
        'justify-content:center',
        'max-width:95%',
        'pointer-events:auto',
    ].join(';');

    const title = isCustom ? '📐 Custom Grid' : '📐 Classic Grid';
    const sub = isCustom
        ? 'Choose start distance in even 10y increments. Then pick your opening zone.'
        : '180 to 280 yards. Pick your opening zone (remaining 9 will be randomized).';

    const customCtrlHtml = isCustom ? `
        <div class="grid-start-ctrl-bar">
            <label for="grid-custom-start-input">Start Yardage:</label>
            <input type="number" id="grid-custom-start-input" min="20" max="450" step="10" value="${state.startYards || 50}">
            <span style="color:#7dd3fc;font-weight:700;">yds</span>
            <button type="button" id="grid-custom-start-btn">Set Grid</button>
        </div>
        <div class="grid-start-hint">Only even 10-yard increments accepted (e.g. 50, 60, 70y).</div>
    ` : '';

    host.innerHTML = `
        <div class="grid-blueprint-modal">
            <div class="grid-blueprint-header">
                <div class="grid-blueprint-title">${title}</div>
                <div class="grid-blueprint-sub">${sub}</div>
            </div>
            ${customCtrlHtml}
            <div class="grid-zones-grid">
                ${state.zones.map((z) => `
                    <button type="button" class="grid-zone-pick-btn" data-grid-zone="${z.index}">
                        <span class="grid-zone-pick-label">${z.label} YDS</span>
                        <span class="grid-zone-pick-arrow">START ➜</span>
                    </button>
                `).join('')}
            </div>
        </div>
    `;

    if (isCustom) {
        const input = host.querySelector('#grid-custom-start-input');
        const btn = host.querySelector('#grid-custom-start-btn');
        const applyCustomStart = () => {
            if (!input) return;
            const sanitized = sanitizeStartDistance(input.value);
            input.value = sanitized;
            if (typeof onStartChange === 'function') {
                onStartChange(sanitized);
            } else {
                gridMode.begin({ startYards: sanitized });
            }
        };

        if (btn) btn.addEventListener('click', applyCustomStart);
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') applyCustomStart();
            });
            input.addEventListener('blur', () => {
                input.value = sanitizeStartDistance(input.value);
            });
        }
    }
}

/**
 * Creates 3D WebGL Fairway Active Zone Highlight mesh group.
 * Placed in the Three.js scene; strictly updates based on activeZoneIndex.
 */
export function createGrid3DHighlight(scene) {
    if (!scene || typeof window === 'undefined' || typeof window.THREE === 'undefined') return null;
    const THREE = window.THREE;

    const group = new THREE.Group();
    group.name = 'GridModeActiveZoneHighlight';
    group.visible = false;

    const FAIRWAY_WIDTH = 56; // fairway span in yards (-28 to +28)

    // 1. Zone Floor Plane (translucent cyan glowing turf highlight)
    const planeGeo = new THREE.PlaneGeometry(FAIRWAY_WIDTH, 10);
    planeGeo.rotateX(-Math.PI / 2);

    const planeMat = new THREE.MeshBasicMaterial({
        color: 0x0ea5e9,
        transparent: true,
        opacity: 0.28,
        depthWrite: false,
        side: THREE.DoubleSide,
    });
    const zonePlane = new THREE.Mesh(planeGeo, planeMat);
    zonePlane.position.y = 0.024;
    group.add(zonePlane);

    // 2. Front & Back Boundary Marker Lines
    const lineMat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
    });

    const frontLineGeo = new THREE.PlaneGeometry(FAIRWAY_WIDTH, 0.35);
    frontLineGeo.rotateX(-Math.PI / 2);
    const frontLine = new THREE.Mesh(frontLineGeo, lineMat);
    frontLine.position.set(0, 0.026, 5);
    group.add(frontLine);

    const backLineGeo = new THREE.PlaneGeometry(FAIRWAY_WIDTH, 0.35);
    backLineGeo.rotateX(-Math.PI / 2);
    const backLine = new THREE.Mesh(backLineGeo, lineMat);
    backLine.position.set(0, 0.026, -5);
    group.add(backLine);

    // 3. Floating 3D Target Distance Yardage Sign Billboard
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    const spriteTexture = new THREE.CanvasTexture(canvas);
    spriteTexture.colorSpace = THREE.SRGBColorSpace;

    const spriteMat = new THREE.SpriteMaterial({
        map: spriteTexture,
        transparent: true,
        depthWrite: false,
    });
    const billboardSprite = new THREE.Sprite(spriteMat);
    billboardSprite.scale.set(16, 4, 1);
    billboardSprite.position.set(0, 2.6, 0);
    group.add(billboardSprite);

    function updateBillboardText(label) {
        ctx.clearRect(0, 0, 512, 128);

        ctx.fillStyle = 'rgba(8, 20, 45, 0.88)';
        ctx.beginPath();
        ctx.roundRect(16, 12, 480, 104, 16);
        ctx.fill();

        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 4;
        ctx.stroke();

        ctx.fillStyle = '#7dd3fc';
        ctx.font = '800 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🎯 ACTIVE GRID ZONE', 256, 42);

        ctx.fillStyle = '#ffffff';
        ctx.font = '900 48px "Consolas", monospace';
        ctx.fillText(`${label} YDS`, 256, 92);

        spriteTexture.needsUpdate = true;
    }

    scene.add(group);

    return {
        group,
        update(activeZone) {
            if (!activeZone) {
                group.visible = false;
                return;
            }
            const centerZ = -(activeZone.minYards + activeZone.maxYards) / 2;
            const depth = activeZone.maxYards - activeZone.minYards;

            group.position.set(0, 0, centerZ);
            frontLine.position.z = depth / 2;
            backLine.position.z = -depth / 2;
            updateBillboardText(activeZone.label);
            group.visible = true;
        },
        destroy() {
            scene.remove(group);
            planeGeo.dispose();
            planeMat.dispose();
            frontLineGeo.dispose();
            backLineGeo.dispose();
            lineMat.dispose();
            spriteTexture.dispose();
            spriteMat.dispose();
        }
    };
}

/**
 * Initializes Grid Mode 3D WebGL highlight and subscribes to gridMode state.
 */
export function setupGridModeUI(scene) {
    const highlight3D = createGrid3DHighlight(scene);

    function onStateChange(state) {
        if (!state || state.status !== 'playing' || !Number.isInteger(state.activeZoneIndex)) {
            if (highlight3D) highlight3D.update(null);
            return;
        }
        const activeZone = state.zones[state.activeZoneIndex];
        if (highlight3D) highlight3D.update(activeZone);
    }

    const unsubscribe = gridMode.subscribe(onStateChange);
    onStateChange(gridMode.getState());

    return {
        highlight3D,
        renderPicker: renderGridPicker,
        destroy() {
            unsubscribe();
            if (highlight3D) highlight3D.destroy();
        }
    };
}
