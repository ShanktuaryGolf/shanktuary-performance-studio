// Metric catalog for the configurable bottom strip.
//
// One definition per metric: how to pull it from a telemetry object, how to
// format it, and whether it is a measurement or something we derived.
//
// `est: true` marks a metric the Nova never measures directly -- the value comes
// from a model or a constant fallback in extractShotTelemetry(). Those render
// with an EST tag. `estIfDerived` marks metrics that are usually measured but
// were filled in for THIS shot (tracked in telemetry.derived), so the tag
// appears only when the number really is a fallback.
//
// Values are returned as {text, unit, muted, est}. `muted` means "not available
// / carries no information" and renders as '--' in the disabled colour -- never
// as a plausible-looking number.

const DASH = '\u2014\u2014';

function fmtSigned(v, digits = 1, suffix = '') {
    if (typeof v !== 'number' || !isFinite(v)) return null;
    return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}${suffix}`;
}

function fmtFixed(v, digits = 1) {
    if (typeof v !== 'number' || !isFinite(v)) return null;
    return v.toFixed(digits);
}

function fmtRound(v) {
    if (typeof v !== 'number' || !isFinite(v)) return null;
    return String(Math.round(v));
}

/**
 * METRICS[key] = {
 *   label, unit, accent?, est?, estIfDerived?,
 *   get(t, ctx) -> {text, unit?, muted?, est?, title?} | null
 * }
 *
 * ctx carries the resolved display values that aren't on the raw telemetry
 * object (carry/total/offline/apex fall back to simulated values).
 */
export const METRICS = {
    carry: {
        label: 'Carry', short: 'Carry', unit: 'yds', accent: true,
        get: (t, c) => ({ text: fmtFixed(c.carryYds) }),
    },
    total: {
        label: 'Total', short: 'Total', unit: 'yds', estIfDerived: 'total',
        get: (t, c) => ({ text: fmtFixed(c.totalYds) }),
    },
    offline: {
        label: 'Offline', short: 'Offline', unit: 'yds',
        get: (t, c) => {
            if (typeof c.offlineYds !== 'number' || !isFinite(c.offlineYds)) return null;
            return {
                html: `${Math.abs(c.offlineYds).toFixed(1)}<span class="suffix">${c.offlineYds >= 0 ? 'R' : 'L'}</span>`,
            };
        },
    },
    ballSpeed: {
        label: 'Ball Speed', short: 'Ball Spd', unit: 'mph', accent: true,
        get: (t) => ({ text: fmtFixed(t.ballSpeed) }),
    },
    clubSpeed: {
        label: 'Club Speed', short: 'Club Spd', unit: 'mph', estIfDerived: 'clubSpeed',
        get: (t) => ({ text: fmtFixed(t.clubSpeed) }),
    },
    smash: {
        label: 'Smash', short: 'Smash', unit: 'ratio',
        // Special-cased by the renderer: an OGC clamp boundary carries no
        // information about the strike, so it renders muted with unit
        // "clamped". See compute_smash_confidence() in the desktop app.
        get: (t, c) => {
            if (c.smashClamped) {
                return {
                    text: '--', muted: true, unit: 'clamped',
                    title: 'OpenGolfCoach clamped its effective COR, so this smash '
                         + 'factor is a constant boundary value, not a measurement.',
                };
            }
            const text = fmtFixed(t.smash, 2);
            return text ? { text } : null;
        },
    },
    launch: {
        label: 'Launch Ang', short: 'Launch', unit: 'deg',
        get: (t) => ({ text: fmtFixed(t.verticalLaunchAngle) }),
    },
    hla: {
        label: 'Launch Dir', short: 'Lch Dir', unit: 'deg',
        get: (t) => ({ text: fmtSigned(t.horizontalLaunchAngle) }),
    },
    totalSpin: {
        label: 'Total Spin', short: 'Spin', unit: 'rpm',
        get: (t) => ({ text: fmtRound(t.total_spin) }),
    },
    spinAxis: {
        label: 'Spin Axis', short: 'Axis', unit: 'deg',
        get: (t) => ({ text: fmtSigned(t.spin_axis) }),
    },
    backspin: {
        label: 'Backspin', short: 'Backspin', unit: 'rpm', estIfDerived: 'backspin',
        get: (t) => ({ text: fmtRound(t.backspin) }),
    },
    sidespin: {
        label: 'Sidespin', short: 'Sidespin', unit: 'rpm', estIfDerived: 'sidespin',
        get: (t) => ({ text: fmtRound(t.sidespin) }),
    },
    apex: {
        label: 'Apex', short: 'Apex', unit: 'ft', estIfDerived: 'apex',
        get: (t, c) => ({ text: fmtRound(c.apexFt) }),
    },
    descent: {
        label: 'Descent Ang', short: 'Descent', unit: 'deg', estIfDerived: 'descent',
        get: (t) => ({ text: fmtFixed(t.descent) }),
    },
    hangTime: {
        label: 'Hang Time', short: 'Hang', unit: 'sec', estIfDerived: 'hangTime',
        get: (t) => ({ text: fmtFixed(t.hangTime) }),
    },
    clubPath: {
        label: 'Club Path', short: 'Path', unit: 'deg',
        get: (t) => ({ text: fmtSigned(t.clubPath) }),
    },
    faceToPath: {
        label: 'Face to Path', short: 'Face/Pth', unit: 'deg',
        get: (t) => ({ text: fmtSigned(t.faceAngle) }),
    },
    attackAngle: {
        label: 'Attack Ang', short: 'Attack', unit: 'deg', estIfDerived: 'attackAngle',
        get: (t) => ({ text: fmtSigned(t.attackAngle) }),
    },
    dynamicLoft: {
        label: 'Dynamic Loft', short: 'Dyn Loft', unit: 'deg', estIfDerived: 'dynamicLoft',
        get: (t) => ({ text: fmtFixed(t.dynamicLoft) }),
    },
    closureRate: {
        label: 'Closure Rate', short: 'Closure', unit: 'deg/s', estIfDerived: 'closureRate',
        get: (t) => ({ text: fmtRound(t.closureRate) }),
    },
};

/** Strip layout limits. Below 4 the strip looks broken; above 10 cells clip. */
export const MIN_STRIP = 3;
export const MAX_STRIP = 10;

export const DEFAULT_STRIP = [
    'carry', 'total', 'offline', 'ballSpeed',
    'smash', 'launch', 'totalSpin', 'apex',
];

const STORAGE_KEY = 'sps_range_strip_metrics';

/** Read the saved layout, falling back to DEFAULT_STRIP if absent/corrupt. */
export function loadStripLayout() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [...DEFAULT_STRIP];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [...DEFAULT_STRIP];
        // Drop unknown keys so a renamed/removed metric can't wedge the strip.
        const clean = parsed.filter(k => Object.hasOwn(METRICS, k));
        return clean.length >= MIN_STRIP ? clean.slice(0, MAX_STRIP) : [...DEFAULT_STRIP];
    } catch {
        return [...DEFAULT_STRIP];
    }
}

export function saveStripLayout(keys) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
    } catch {
        /* private mode / quota -- layout just won't persist */
    }
}

/**
 * Resolve one metric to display values.
 * Returns {label, unit, text|html, muted, est, accent, title}.
 */
export function readMetric(key, telemetry, ctx) {
    const def = METRICS[key];
    if (!def) return null;

    const base = {
        label: def.label,
        unit: def.unit,
        accent: !!def.accent,
        muted: false,
        est: false,
        text: DASH,
        html: null,
        title: '',
    };

    if (!telemetry) return { ...base, muted: true, text: DASH };

    let out = null;
    try {
        out = def.get(telemetry, ctx || {});
    } catch {
        out = null;
    }
    if (!out || (out.text == null && out.html == null)) {
        return { ...base, muted: true, text: DASH };
    }

    const derivedMap = telemetry.derived || {};
    const est = !!def.est || (def.estIfDerived ? !!derivedMap[def.estIfDerived] : false);

    return {
        ...base,
        ...out,
        est: out.muted ? false : est,   // an unavailable value isn't an estimate
        unit: out.unit || def.unit,
        title: out.title || '',
    };
}
