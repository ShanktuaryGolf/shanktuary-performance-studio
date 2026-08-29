// Club picker: choose the club for the next shot from My Bag.
//
// The bag is owned by the desktop app and served read-only at /api/bag. If that
// fetch fails we say so and fall back to monitor-reported clubs -- we never
// invent a bag, because a wrong club label silently files shots under the wrong
// club's stats and corrupts the averages the user is trying to build.

const GROUP_ORDER = [
    'Woods & Drivers',
    'Hybrids & Utilities',
    'Irons',
    'Wedges',
    'Putter',
];

const GROUP_LABEL = {
    'Woods & Drivers': 'Woods',
    'Hybrids & Utilities': 'Hybrids',
    'Irons': 'Irons',
    'Wedges': 'Wedges',
    'Putter': 'Putter',
};

/** Mirrors infer_club_category() in shanktuary_performance_studio.py. */
export function inferCategory(name) {
    const n = (name || '').toLowerCase();
    if (/putter|blade|mallet/.test(n)) return 'Putter';
    if (/driver|wood|mini/.test(n)) return 'Woods & Drivers';
    if (/hybrid|rescue|utility|driving iron/.test(n)) return 'Hybrids & Utilities';
    if (/pw|gw|sw|lw|wedge|°|deg|pitching|gap|sand|lob/.test(n)) return 'Wedges';
    return 'Irons';
}

/**
 * Short label for a circular pill: "7i", "Dr", "3w", "50°".
 * Wedges show loft because that's how golfers actually identify them -- the
 * reference UI does the same. Falls back to the raw name when nothing matches
 * so a custom club is never silently mislabelled.
 */
export function pillLabel(club) {
    const name = (club.name || '').trim();
    const n = name.toLowerCase();
    const cat = club.category || inferCategory(name);

    if (cat === 'Wedges') {
        // Named wedges (PW/GW/AW/SW/LW) keep their name -- that is how they are
        // stamped and how golfers refer to them. Only unnamed/degree wedges are
        // labelled by loft, matching the reference UI's "50° 54° 58°".
        const named = n.match(/^(pw|gw|aw|sw|lw)$/);
        if (named) return named[1].toUpperCase();

        const loft = Number(club.loft_deg);
        if (isFinite(loft) && loft > 0) return `${Math.round(loft)}\u00b0`;
        return name.length <= 3 ? name : name.slice(0, 3);
    }
    if (/^driver$/.test(n)) return 'Dr';
    if (/^mini driver$/.test(n)) return 'MD';

    const wood = n.match(/^(\d+)\s*wood$/);
    if (wood) return `${wood[1]}w`;

    const hybrid = n.match(/^(\d+)\s*(hybrid|rescue|utility)$/);
    if (hybrid) return `${hybrid[1]}h`;

    const iron = n.match(/^(\d+)\s*iron$/);
    if (iron) return `${iron[1]}i`;

    if (/putter/.test(n)) return 'Pt';

    return name.length <= 3 ? name : name.slice(0, 3);
}

/** Subtitle for the club chip: brand/model and loft when known. */
export function clubSubtitle(club) {
    if (!club) return '';
    const bits = [];
    const brandModel = [club.brand, club.model].filter(Boolean).join(' ').trim();
    if (brandModel && !/^generic\b/i.test(brandModel)) bits.push(brandModel);
    const loft = Number(club.loft_deg);
    if (isFinite(loft) && loft > 0) bits.push(`${loft}\u00b0`);
    return bits.join(' \u00b7 ');
}

/** Group clubs for display, preserving bag order within each category. */
export function groupClubs(clubs) {
    const byCat = new Map();
    for (const c of clubs) {
        const cat = c.category || inferCategory(c.name);
        if (!byCat.has(cat)) byCat.set(cat, []);
        byCat.get(cat).push(c);
    }
    const groups = [];
    for (const cat of GROUP_ORDER) {
        if (byCat.has(cat)) {
            groups.push({ category: cat, label: GROUP_LABEL[cat] || cat, clubs: byCat.get(cat) });
            byCat.delete(cat);
        }
    }
    // Anything with an unrecognised category still gets shown, under its own name.
    for (const [cat, list] of byCat.entries()) {
        groups.push({ category: cat, label: cat, clubs: list });
    }
    return groups;
}

/** Fetch My Bag. Returns {clubs, is_left_handed, error}. */
export async function fetchBag() {
    try {
        const res = await fetch('/api/bag', { cache: 'no-store' });
        if (!res.ok) return { clubs: [], is_left_handed: false, error: `HTTP ${res.status}` };
        const data = await res.json();
        return {
            clubs: Array.isArray(data.clubs) ? data.clubs : [],
            is_left_handed: !!data.is_left_handed,
            error: null,
        };
    } catch (e) {
        return { clubs: [], is_left_handed: false, error: String(e && e.message || e) };
    }
}
