// Optional rail widgets, and the registry behind "+ Add Widget".
//
// Every widget here plots only values the Nova actually measures (carry, ball
// speed, launch angle, spin, offline). Fields that extractShotTelemetry()
// synthesizes when the payload omits them -- attack angle, dynamic loft, face
// closure rate -- are deliberately NOT offered as widgets: a chart implies a
// measured series, and those would be drawing a formula back at the user.

const COL = {
    bg: '#0F1613',
    grid: 'rgba(255,255,255,0.13)',
    label: 'rgba(255,255,255,0.34)',
    dot: 'rgba(242,244,247,0.42)',
    sel: '#9CC9AC',
    mean: 'rgba(111,168,128,0.75)',
    band: 'rgba(76,140,94,0.16)',
    empty: 'rgba(242,244,247,0.30)',
};

const MONO = 'Consolas, monospace';

/** Match the backing store to the element's CSS box, DPI-corrected. */
function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const pw = Math.max(1, Math.round(rect.width * dpr));
    const ph = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== pw || canvas.height !== ph) {
        canvas.width = pw;
        canvas.height = ph;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w: rect.width, h: rect.height };
}

function emptyState(ctx, w, h, msg) {
    ctx.fillStyle = COL.empty;
    ctx.font = '600 10px "Segoe UI", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(msg, w / 2, h / 2);
}

function niceStep(range, target = 4) {
    const raw = range / target;
    for (const s of [1, 2, 5, 10, 20, 25, 50, 100, 250, 500, 1000, 2000]) {
        if (raw <= s) return s;
    }
    return 5000;
}

/* ------------------------------------------------------------------ *
 * Carry Trend -- carry per shot, in order, with mean and ±1σ band.
 * ------------------------------------------------------------------ */
function drawCarryTrend(canvas, ctx0) {
    const { ctx, w, h } = fitCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, w, h);

    const shots = [...ctx0.shots].sort((a, b) => a.seq - b.seq);
    if (shots.length === 0) { emptyState(ctx, w, h, 'No shots yet'); return; }

    const padL = 30, padR = 8, padT = 10, padB = 16;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    if (plotW < 20 || plotH < 20) return;

    const carries = shots.map(s => s.carry);
    const lo = Math.min(...carries);
    const hi = Math.max(...carries);
    const pad = Math.max(4, (hi - lo) * 0.35);
    const yLo = Math.max(0, lo - pad);
    const yHi = hi + pad;
    const span = Math.max(5, yHi - yLo);

    const toY = (v) => padT + plotH - ((v - yLo) / span) * plotH;
    const toX = (i) => shots.length === 1
        ? padL + plotW / 2
        : padL + (i / (shots.length - 1)) * plotW;

    // gridlines
    const step = niceStep(span, 3);
    ctx.setLineDash([3, 4]);
    ctx.font = `600 8px ${MONO}`;
    ctx.textAlign = 'right';
    for (let v = Math.ceil(yLo / step) * step; v <= yHi; v += step) {
        const y = toY(v);
        if (y < padT || y > padT + plotH) continue;
        ctx.strokeStyle = COL.grid;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillStyle = COL.label;
        ctx.fillText(`${v}`, padL - 4, y + 3);
    }
    ctx.setLineDash([]);

    // mean ±1σ. Needs a sample: below 3 shots a sigma is noise, so the band is
    // omitted rather than drawn misleadingly tight.
    const mean = carries.reduce((a, b) => a + b, 0) / carries.length;
    if (shots.length >= 3) {
        const sd = Math.sqrt(carries.reduce((a, x) => a + (x - mean) ** 2, 0) / carries.length);
        const yTop = toY(mean + sd), yBot = toY(mean - sd);
        ctx.fillStyle = COL.band;
        ctx.fillRect(padL, yTop, plotW, Math.max(1, yBot - yTop));
    }
    const my = toY(mean);
    ctx.strokeStyle = COL.mean;
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, my);
    ctx.lineTo(w - padR, my);
    ctx.stroke();
    ctx.setLineDash([]);

    // series
    ctx.strokeStyle = 'rgba(242,244,247,0.28)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    shots.forEach((s, i) => {
        const x = toX(i), y = toY(s.carry);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    shots.forEach((s, i) => {
        const sel = s.seq === ctx0.selectedSeq;
        ctx.fillStyle = sel ? COL.sel : COL.dot;
        ctx.beginPath();
        ctx.arc(toX(i), toY(s.carry), sel ? 4 : 2.4, 0, Math.PI * 2);
        ctx.fill();
    });

    ctx.fillStyle = COL.label;
    ctx.font = `600 8px ${MONO}`;
    ctx.textAlign = 'left';
    ctx.fillText(`avg ${mean.toFixed(1)}y`, padL + 2, padT + 8);
}

/* ------------------------------------------------------------------ *
 * Launch Window -- launch angle vs total spin. Both are measured.
 * ------------------------------------------------------------------ */
function drawLaunchWindow(canvas, ctx0) {
    const { ctx, w, h } = fitCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, w, h);

    const pts = ctx0.shots
        .map(s => ({
            seq: s.seq,
            spin: s.telemetry && s.telemetry.total_spin,
            vla: s.telemetry && s.telemetry.verticalLaunchAngle,
        }))
        .filter(p => typeof p.spin === 'number' && isFinite(p.spin)
                  && typeof p.vla === 'number' && isFinite(p.vla));

    if (pts.length === 0) { emptyState(ctx, w, h, 'No launch data yet'); return; }

    const padL = 32, padR = 10, padT = 10, padB = 20;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    if (plotW < 20 || plotH < 20) return;

    const spins = pts.map(p => p.spin);
    const vlas = pts.map(p => p.vla);
    const sLo = Math.max(0, Math.min(...spins) - 600);
    const sHi = Math.max(...spins) + 600;
    const vLo = Math.max(0, Math.min(...vlas) - 3);
    const vHi = Math.max(...vlas) + 3;
    const sSpan = Math.max(500, sHi - sLo);
    const vSpan = Math.max(3, vHi - vLo);

    const toX = (spin) => padL + ((spin - sLo) / sSpan) * plotW;
    const toY = (vla) => padT + plotH - ((vla - vLo) / vSpan) * plotH;

    // grid
    ctx.setLineDash([3, 4]);
    ctx.font = `600 8px ${MONO}`;
    const vStep = niceStep(vSpan, 3);
    ctx.textAlign = 'right';
    for (let v = Math.ceil(vLo / vStep) * vStep; v <= vHi; v += vStep) {
        const y = toY(v);
        if (y < padT || y > padT + plotH) continue;
        ctx.strokeStyle = COL.grid;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
        ctx.fillStyle = COL.label;
        ctx.fillText(`${v}\u00b0`, padL - 4, y + 3);
    }
    const sStep = niceStep(sSpan, 3);
    ctx.textAlign = 'center';
    for (let s = Math.ceil(sLo / sStep) * sStep; s <= sHi; s += sStep) {
        const x = toX(s);
        if (x < padL || x > w - padR) continue;
        ctx.strokeStyle = COL.grid;
        ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
        ctx.fillStyle = COL.label;
        ctx.fillText(`${Math.round(s / 1000)}k`, x, h - 6);
    }
    ctx.setLineDash([]);

    for (const p of pts) {
        const sel = p.seq === ctx0.selectedSeq;
        ctx.fillStyle = sel ? COL.sel : COL.dot;
        ctx.beginPath();
        ctx.arc(toX(p.spin), toY(p.vla), sel ? 4.5 : 2.6, 0, Math.PI * 2);
        ctx.fill();
    }

    ctx.fillStyle = COL.label;
    ctx.font = `600 8px ${MONO}`;
    ctx.textAlign = 'left';
    ctx.fillText('launch\u00b0 / spin', padL + 2, padT + 8);
}

/**
 * Widget registry. `kind: 'canvas'` gets a <canvas> body and a draw(canvas, ctx)
 * call; `kind: 'dom'` gets a plain div and a render(host, ctx) call.
 *
 * `fixed: true` marks the two widgets that already exist in the markup and are
 * toggled rather than created.
 */
export const WIDGET_REGISTRY = {
    dispersion: {
        title: '\u2295 Dispersion',
        desc: 'Top-down shot scatter with 1\u03c3 group ellipse',
        fixed: true,
        element: 'minimap-container',
    },
    pressure: {
        title: '\u2696 Pressure',
        desc: 'Live centre-of-pressure mat and weight balance',
        fixed: true,
        element: 'range-pressure-tile',
    },
    carryTrend: {
        title: '\u2197 Carry Trend',
        desc: 'Carry per shot with mean and \u00b11\u03c3 band',
        kind: 'canvas',
        draw: drawCarryTrend,
    },
    launchWindow: {
        title: '\u25ce Launch Window',
        desc: 'Launch angle against total spin',
        kind: 'canvas',
        draw: drawLaunchWindow,
    },
    // NOTE: no "Club Averages" widget. The shot list rail already pins an AVG
    // carry/offline row per club group, so a rail widget would duplicate it and
    // spend a rail slice -- which every other widget then has to share -- on
    // information already on screen.
};
