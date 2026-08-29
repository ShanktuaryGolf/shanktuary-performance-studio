// Dispersion plot: top-down shot scatter with constant-distance arcs.
//
// Replaces the old corridor "radar minimap". The arcs are lines of constant
// distance from the tee; because the lateral axis is exaggerated (offline is
// tiny next to carry, so a true 1:1 plot collapses into a vertical line), a
// real circle maps to an ellipse whose semi-axes follow the two scales. Drawing
// them as ellipses is therefore the correct projection, not a cosmetic choice.
//
// The 1-sigma ring is computed from the plotted shots only -- it is a summary of
// real data, never a model. Fewer than MIN_SIGMA_SHOTS shots and it is not drawn
// at all rather than implying confidence we don't have.

const MIN_SIGMA_SHOTS = 3;

const COL = {
    bg: '#0F1613',
    arc: 'rgba(255,255,255,0.13)',
    arcLabel: 'rgba(255,255,255,0.34)',
    centerline: 'rgba(255,255,255,0.16)',
    shot: 'rgba(242,244,247,0.42)',
    shotSelected: '#9CC9AC',
    sigmaFill: 'rgba(76,140,94,0.16)',
    sigmaLine: 'rgba(111,168,128,0.55)',
    meanCross: 'rgba(156,201,172,0.85)',
    tee: '#6FA880',
    pin: '#F2F4F7',
    pinRing: 'rgba(242,244,247,0.45)',
};

/** Pick a round arc interval that yields roughly 4 rings. */
function niceStep(range) {
    const raw = range / 4;
    for (const s of [5, 10, 20, 25, 50, 100, 150, 200]) {
        if (raw <= s) return s;
    }
    return 250;
}

function mean(xs) {
    return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function stdev(xs, mu) {
    if (xs.length < 2) return 0;
    return Math.sqrt(xs.reduce((a, x) => a + (x - mu) ** 2, 0) / xs.length);
}

/**
 * Summary stats for a set of shots. Returns null for an empty set so callers
 * render an explicit empty state instead of zeros.
 */
export function dispersionStats(shots) {
    if (!shots || shots.length === 0) return null;
    const carries = shots.map(s => s.carry);
    const offlines = shots.map(s => s.offline);
    const carryMean = mean(carries);
    const offlineMean = mean(offlines);
    return {
        count: shots.length,
        carryMean,
        carryStd: stdev(carries, carryMean),
        offlineMean,
        offlineStd: stdev(offlines, offlineMean),
        carryMin: Math.min(...carries),
        carryMax: Math.max(...carries),
    };
}

/** Match the backing store to the element's CSS size, DPI-corrected. */
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

/**
 * Draw the plot.
 *
 * shots          -- [{carry, offline, seq}]
 * selectedSeq    -- seq of the highlighted shot, or null
 * targetYards    -- pin distance, drawn as a reference marker
 */
export function drawDispersion(canvas, shots, selectedSeq, targetYards) {
    if (!canvas) return null;
    const { ctx, w, h } = fitCanvas(canvas);
    if (w < 8 || h < 8) return null;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COL.bg;
    ctx.fillRect(0, 0, w, h);

    const padTop = 12;
    const padBottom = 22;
    const teeY = h - padBottom;
    const cx = w / 2;

    const stats = dispersionStats(shots);

    // Depth scale. Anchoring at 0 wastes most of a tall plot when a club's
    // shots sit in a narrow carry band, so once the group is well clear of the
    // tee we zoom to the band instead. `baseYds` is the bottom of the plot; a
    // break marker is drawn when it isn't zero so the axis is never mistaken
    // for starting at the tee.
    let longest = targetYards || 0;
    for (const s of shots) longest = Math.max(longest, s.carry);

    let baseYds = 0;
    let maxRange = Math.max(40, longest * 1.15);
    if (stats) {
        const lo = Math.min(stats.carryMin, targetYards || stats.carryMin);
        const hi = Math.max(stats.carryMax, targetYards || stats.carryMax);
        const band = hi - lo;
        // Only zoom when the band is genuinely small next to the distance --
        // otherwise a full-range view is more informative.
        if (lo > 40 && band < lo * 0.6) {
            const pad = Math.max(12, band * 0.45);
            baseYds = Math.max(0, lo - pad);
            maxRange = hi + pad;
        }
    }
    const spanYds = Math.max(10, maxRange - baseYds);
    const depthPx = teeY - padTop;
    const sy = depthPx / spanYds;

    // Lateral scale: offline is tiny next to carry, so a true 1:1 plot collapses
    // into a vertical line. The lateral axis is exaggerated to make the miss
    // pattern legible; the multiplier is drawn on the plot so it is never
    // mistaken for a 1:1 overhead view. Two guards: MIN_HALF_SPAN stops a tight
    // group being blown up into fake spread, and MAX_ASPECT stops a very tight
    // group being stretched so far that normal misses look wild.
    const MIN_HALF_SPAN = 6;
    const MAX_ASPECT = 8;
    let widestOffline = 0;
    for (const s of shots) widestOffline = Math.max(widestOffline, Math.abs(s.offline));
    const halfSpanRaw = Math.max(MIN_HALF_SPAN, widestOffline * 1.35);
    const sxRaw = (w / 2 - 12) / halfSpanRaw;
    const sx = Math.min(sxRaw, sy * MAX_ASPECT);
    const halfSpan = (w / 2 - 12) / sx;

    const toX = (offline) => cx + offline * sx;
    const toY = (carry) => teeY - (carry - baseYds) * sy;

    // --- carry gridlines ---------------------------------------------------
    // These are lines of constant CARRY, not constant distance-from-tee. In an
    // anisotropic plot (lateral axis exaggerated so offline is legible) a true
    // constant-distance ring is visually flat near the centerline anyway, so
    // drawing curved "arcs" would imply a 1:1 overhead view we aren't showing.
    const step = niceStep(spanYds);
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.font = '600 8px Consolas, monospace';
    ctx.textAlign = 'left';
    const firstLine = Math.ceil((baseYds + step * 0.35) / step) * step;
    for (let d = firstLine; d <= maxRange; d += step) {
        const ly = toY(d);
        if (ly < padTop || ly > teeY) continue;
        ctx.strokeStyle = COL.arc;
        ctx.beginPath();
        ctx.moveTo(2, ly);
        ctx.lineTo(w - 2, ly);
        ctx.stroke();

        if (ly > padTop + 7) {
            ctx.fillStyle = COL.arcLabel;
            ctx.fillText(`${d}`, 3, ly - 2);
        }
    }
    ctx.setLineDash([]);

    // --- centerline + offline ticks ---------------------------------------
    ctx.strokeStyle = COL.centerline;
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(cx, teeY);
    ctx.lineTo(cx, padTop);
    ctx.stroke();
    ctx.setLineDash([]);

    // Lateral scale markers, so "how far offline" is readable off the plot.
    const offStep = niceStep(halfSpan * 2) / 2;
    ctx.font = '600 8px Consolas, monospace';
    ctx.textAlign = 'center';
    for (let o = offStep; o <= halfSpan; o += offStep) {
        for (const sign of [-1, 1]) {
            const x = toX(sign * o);
            if (x < 4 || x > w - 4) continue;
            ctx.strokeStyle = 'rgba(255,255,255,0.10)';
            ctx.beginPath();
            ctx.moveTo(x, teeY);
            ctx.lineTo(x, teeY - 4);
            ctx.stroke();
            ctx.fillStyle = COL.arcLabel;
            ctx.fillText(`${o}${sign < 0 ? 'L' : 'R'}`, x, h - 5);
        }
    }

    // --- target pin --------------------------------------------------------
    if (targetYards && targetYards <= maxRange && targetYards >= baseYds) {
        const py = toY(targetYards);
        ctx.strokeStyle = COL.pinRing;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, py, 5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = COL.pin;
        ctx.beginPath();
        ctx.arc(cx, py, 1.6, 0, Math.PI * 2);
        ctx.fill();
    }

    // --- 1-sigma dispersion ellipse ---------------------------------------
    if (stats && stats.count >= MIN_SIGMA_SHOTS) {
        // Floor the radii so a very tight group still renders as a visible
        // ellipse rather than a 1px sliver that reads as a drawing artifact.
        const rx = Math.max(6, stats.offlineStd * sx);
        const ry = Math.max(6, stats.carryStd * sy);
        const mx = toX(stats.offlineMean);
        const my = toY(stats.carryMean);

        ctx.fillStyle = COL.sigmaFill;
        ctx.strokeStyle = COL.sigmaLine;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(mx, my, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Mean cross
        ctx.strokeStyle = COL.meanCross;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mx - 4, my); ctx.lineTo(mx + 4, my);
        ctx.moveTo(mx, my - 4); ctx.lineTo(mx, my + 4);
        ctx.stroke();
    }

    // --- shots -------------------------------------------------------------
    for (const s of shots) {
        if (s.seq === selectedSeq) continue;
        ctx.fillStyle = COL.shot;
        ctx.beginPath();
        ctx.arc(toX(s.offline), toY(s.carry), 2.6, 0, Math.PI * 2);
        ctx.fill();
    }

    const sel = shots.find(s => s.seq === selectedSeq);
    if (sel) {
        const x = toX(sel.offline);
        const y = toY(sel.carry);
        ctx.fillStyle = COL.shotSelected;
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(156,201,172,0.45)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, 7.5, 0, Math.PI * 2);
        ctx.stroke();
    }

    // --- tee / axis break --------------------------------------------------
    if (baseYds <= 0) {
        ctx.fillStyle = COL.tee;
        ctx.beginPath();
        ctx.arc(cx, teeY, 3, 0, Math.PI * 2);
        ctx.fill();
    } else {
        // The axis does not start at the tee -- say so, rather than drawing a
        // tee marker at a distance that isn't zero.
        ctx.strokeStyle = 'rgba(255,255,255,0.22)';
        ctx.lineWidth = 1;
        for (const dy of [0, 4]) {
            ctx.beginPath();
            ctx.moveTo(cx - 7, teeY + 1 - dy);
            ctx.lineTo(cx - 1, teeY - 3 - dy);
            ctx.lineTo(cx + 5, teeY + 1 - dy);
            ctx.stroke();
        }
        ctx.fillStyle = COL.arcLabel;
        ctx.font = '600 8px Consolas, monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`${Math.round(baseYds)}`, 3, teeY - 2);
    }

    if (!stats) {
        ctx.fillStyle = 'rgba(242,244,247,0.30)';
        ctx.font = '600 10px "Segoe UI", system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No shots yet', cx, teeY - depthPx / 2);
    }

    // Be explicit that the lateral axis is stretched, so the plot is never
    // mistaken for a 1:1 overhead view. Top-right, clear of the offline ticks.
    const aspect = sx / sy;
    if (stats && aspect > 1.2) {
        ctx.fillStyle = 'rgba(242,244,247,0.28)';
        ctx.font = '600 8px Consolas, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(`lateral \u00d7${aspect.toFixed(1)}`, w - 4, padTop - 2);
    }

    return { stats, maxRange, aspect };
}
