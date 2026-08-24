/**
 * Shanktuary Performance Studio - Swing Lab Pressure & COP Canvas Tile Engine
 * Reusable across Driving Range HUD, OBS Overlay, and Web Dashboards.
 */

export class PressureTileRenderer {
    constructor() {
        this.history = [];
        this.maxHistory = 150;
    }

    pushSample(data) {
        if (!data) return;
        this.history.push(data);
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        }
    }

    /**
     * Render Dual-Foot Pressure Heatmap
     */
    renderHeatmap(canvas, data) {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        const raw = (data && data.raw_cells) ? data.raw_cells : [20, 20, 20, 20];
        const pctL = (data && data.pct_left !== undefined) ? data.pct_left : 50;
        const pctR = (data && data.pct_right !== undefined) ? data.pct_right : 50;

        const footW = (w - 30) / 2;
        const footH = h - 20;

        // Draw Left Foot & Right Foot
        this._drawFoot(ctx, 10, 10, footW, footH, true, raw[0], raw[2], pctL);
        this._drawFoot(ctx, 20 + footW, 10, footW, footH, false, raw[1], raw[3], pctR);
    }

    _drawFoot(ctx, x, y, w, h, isLeft, frontKg, backKg, totalPct) {
        const cx = x + w / 2;
        const fTop = y + 10;
        const fBot = y + h - 10;
        const halfW = w * 0.42;

        // 1. Draw foot outline
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(cx - halfW * 0.7, fTop + 12);
        ctx.quadraticCurveTo(cx, fTop, cx + halfW * 0.7, fTop + 12);
        ctx.quadraticCurveTo(cx + halfW * 0.9, fTop + h * 0.35, cx + halfW * 0.55, fTop + h * 0.60);
        ctx.quadraticCurveTo(cx + halfW * 0.65, fBot - 8, cx, fBot);
        ctx.quadraticCurveTo(cx - halfW * 0.65, fBot - 8, cx - halfW * 0.55, fTop + h * 0.60);
        ctx.quadraticCurveTo(cx - halfW * 0.9, fTop + h * 0.35, cx - halfW * 0.7, fTop + 12);
        ctx.closePath();

        ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
        ctx.fill();
        ctx.strokeStyle = isLeft ? "rgba(56, 189, 248, 0.5)" : "rgba(244, 63, 94, 0.5)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.clip(); // Clip heat gradients inside foot outline

        // 2. Front & Back Pressure Gaussian Heat Blobs
        const sensors = [
            { x: cx - halfW * 0.3, y: fTop + h * 0.22, val: frontKg * 0.55 },
            { x: cx + halfW * 0.3, y: fTop + h * 0.22, val: frontKg * 0.45 },
            { x: cx - halfW * 0.25, y: fBot - h * 0.18, val: backKg * 0.55 },
            { x: cx + halfW * 0.25, y: fBot - h * 0.18, val: backKg * 0.45 }
        ];

        for (const s of sensors) {
            const intensity = Math.min(1.0, Math.max(0.1, s.val / 35.0));
            const radius = Math.max(16, w * 0.45 * intensity);

            const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, radius);
            if (intensity > 0.75) {
                grad.addColorStop(0, "rgba(239, 68, 68, 0.9)");
                grad.addColorStop(0.5, "rgba(234, 179, 8, 0.6)");
                grad.addColorStop(1, "rgba(239, 68, 68, 0)");
            } else if (intensity > 0.45) {
                grad.addColorStop(0, "rgba(234, 179, 8, 0.85)");
                grad.addColorStop(0.5, "rgba(34, 197, 94, 0.5)");
                grad.addColorStop(1, "rgba(234, 179, 8, 0)");
            } else {
                grad.addColorStop(0, "rgba(56, 189, 248, 0.8)");
                grad.addColorStop(0.5, "rgba(59, 130, 246, 0.4)");
                grad.addColorStop(1, "rgba(56, 189, 248, 0)");
            }

            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(s.x, s.y, radius, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.restore();

        // 3. Foot Labels
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 10px 'Segoe UI', sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(`${Math.round(totalPct)}%`, cx, fBot + 8);
    }

    /**
     * Render Center of Pressure (COP) Dot & Trail
     */
    renderCOPDot(canvas, data) {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        const cx = w / 2;
        const cy = h / 2;
        const maxR = Math.min(w, h) / 2 - 12;

        ctx.clearRect(0, 0, w, h);

        // 1. Stance Target Rings & Axis
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineWidth = 1;
        [0.33, 0.66, 1.0].forEach(frac => {
            ctx.beginPath();
            ctx.arc(cx, cy, maxR * frac, 0, Math.PI * 2);
            ctx.stroke();
        });

        // Crosshairs
        ctx.beginPath();
        ctx.moveTo(10, cy); ctx.lineTo(w - 10, cy);
        ctx.moveTo(cx, 10); ctx.lineTo(cx, h - 10);
        ctx.stroke();

        // Scale: 150mm = maxR
        const scale = maxR / 150.0;

        // 2. Trailing Path
        if (this.history.length > 1) {
            ctx.lineWidth = 2;
            for (let i = 0; i < this.history.length - 1; i++) {
                const p1 = this.history[i];
                const p2 = this.history[i + 1];
                const x1 = cx + (p1.cop_x || 0) * scale;
                const y1 = cy - (p1.cop_y || 0) * scale;
                const x2 = cx + (p2.cop_x || 0) * scale;
                const y2 = cy - (p2.cop_y || 0) * scale;

                const phase = (p2.phase || "").toUpperCase();
                ctx.strokeStyle = phase.includes("IMPACT") ? "#ef4444" : (phase.includes("BACK") ? "#eab308" : "#38bdf8");
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();
            }
        }

        // 3. Current Live COP Bullseye
        const copX = data ? (data.cop_x || 0) : 0;
        const copY = data ? (data.cop_y || 0) : 0;
        const dotX = cx + copX * scale;
        const dotY = cy - copY * scale;

        // Glowing outer pulse
        ctx.beginPath();
        ctx.arc(dotX, dotY, 9, 0, Math.PI * 2);
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Center dot
        ctx.beginPath();
        ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
    }
}
