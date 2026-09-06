// Grid Challenge mode — single source of truth for zone state and scoring.
//
// Other range modes keep their counters as locals inside websocket.js.
// Grid is a state machine (pick zone → lock until land → random remaining),
// so it lives in this module. UI should only render getState(); the shot
// path should only feed carry yards into applyShot(). Do not duplicate
// activeZoneIndex / remainingZonePool elsewhere.

export const GRID_ZONE_COUNT = 10;
export const GRID_ZONE_WIDTH_YARDS = 10;
export const GRID_DEFAULT_START_YARDS = 180;
export const GRID_MIN_START_YARDS = 20;
export const GRID_MAX_START_YARDS = 450;

/** True only for finite multiples of 10 in the allowed start range. */
export function isValidGridStartYards(value) {
    const n = Number(value);
    return Number.isFinite(n)
        && n >= GRID_MIN_START_YARDS
        && n <= GRID_MAX_START_YARDS
        && n % 10 === 0;
}

function defaultRng() {
    return Math.random();
}

export function buildGridZones(
    startYards = GRID_DEFAULT_START_YARDS,
    count = GRID_ZONE_COUNT,
    width = GRID_ZONE_WIDTH_YARDS,
) {
    const start = Number(startYards);
    if (!Number.isFinite(start)) throw new Error('startYards must be a number');
    const zones = [];
    for (let i = 0; i < count; i++) {
        const minYards = start + i * width;
        const maxYards = minYards + width;
        zones.push({
            index: i,
            minYards,
            maxYards,
            label: `${minYards}-${maxYards}`,
            landed: false,
            shots: 0,
        });
    }
    return zones;
}

/** Inclusive min; exclusive max except the last zone, which includes maxYards. */
export function zoneContains(zone, carryYards, isLast) {
    if (!zone || !Number.isFinite(carryYards)) return false;
    if (isLast) return carryYards >= zone.minYards && carryYards <= zone.maxYards;
    return carryYards >= zone.minYards && carryYards < zone.maxYards;
}

function shuffleCopy(items, rng) {
    const arr = items.slice();
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(rng() * (i + 1));
        const tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
    }
    return arr;
}

function cloneState(s) {
    return {
        status: s.status,
        startYards: s.startYards,
        zones: s.zones.map((z) => ({ ...z })),
        activeZoneIndex: s.activeZoneIndex,
        remainingZonePool: s.remainingZonePool.slice(),
        totalShots: s.totalShots,
        completedCount: s.completedCount,
        lastResult: s.lastResult ? { ...s.lastResult } : null,
    };
}

export function createGridMode({ rng = defaultRng } = {}) {
    const listeners = new Set();
    let state = emptyState();

    function emptyState() {
        return {
            status: 'idle',
            startYards: GRID_DEFAULT_START_YARDS,
            zones: [],
            activeZoneIndex: null,
            remainingZonePool: [],
            totalShots: 0,
            completedCount: 0,
            lastResult: null,
        };
    }

    function emit() {
        const snap = cloneState(state);
        listeners.forEach((fn) => fn(snap));
        return snap;
    }

    function zoneIndexFor(carryYards) {
        for (let i = 0; i < state.zones.length; i++) {
            if (zoneContains(state.zones[i], carryYards, i === state.zones.length - 1)) {
                return i;
            }
        }
        return null;
    }

    function begin({ startYards = GRID_DEFAULT_START_YARDS } = {}) {
        const n = Number(startYards);
        if (!isValidGridStartYards(n)) {
            throw new Error('startYards must be a multiple of 10 between ' + GRID_MIN_START_YARDS + ' and ' + GRID_MAX_START_YARDS);
        }
        state = {
            status: 'picking',
            startYards: n,
            zones: buildGridZones(n),
            activeZoneIndex: null,
            remainingZonePool: [],
            totalShots: 0,
            completedCount: 0,
            lastResult: null,
        };
        return emit();
    }

    function selectInitialZone(index) {
        if (state.status !== 'picking') return cloneState(state);
        const idx = Number(index);
        if (!Number.isInteger(idx) || idx < 0 || idx >= state.zones.length) {
            throw new Error('initial zone index out of range');
        }
        const remaining = [];
        for (let i = 0; i < state.zones.length; i++) {
            if (i !== idx) remaining.push(i);
        }
        state.activeZoneIndex = idx;
        state.remainingZonePool = shuffleCopy(remaining, rng);
        state.status = 'playing';
        return emit();
    }

    function start({ startYards = GRID_DEFAULT_START_YARDS, initialZoneIndex } = {}) {
        begin({ startYards });
        if (initialZoneIndex !== undefined && initialZoneIndex !== null) {
            return selectInitialZone(initialZoneIndex);
        }
        return cloneState(state);
    }

    function applyShot(carryYards) {
        if (state.status !== 'playing') return cloneState(state);
        const carry = Number(carryYards);
        const completedZoneIndex = state.activeZoneIndex;
        const active = state.zones[completedZoneIndex];
        const isLastBand = completedZoneIndex === state.zones.length - 1;
        const hit = zoneContains(active, carry, isLastBand);

        // Every thrown shot counts, attributed to the then-active zone.
        active.shots += 1;
        state.totalShots += 1;

        let advanced = false;
        let completedGame = false;
        if (hit) {
            active.landed = true;
            state.completedCount += 1;
            advanced = true;
            if (state.remainingZonePool.length === 0) {
                state.activeZoneIndex = null;
                state.status = 'complete';
                completedGame = true;
            } else {
                state.activeZoneIndex = state.remainingZonePool.shift();
            }
        }

        state.lastResult = {
            carryYards: carry,
            hit,
            landedZoneIndex: zoneIndexFor(carry),
            completedZoneIndex: hit ? completedZoneIndex : null,
            activeZoneIndex: state.activeZoneIndex,
            advanced,
            completedGame,
            totalShots: state.totalShots,
        };
        return emit();
    }

    function reset() {
        state = emptyState();
        return emit();
    }

    function getState() {
        return cloneState(state);
    }

    function subscribe(fn) {
        listeners.add(fn);
        return () => listeners.delete(fn);
    }

    return {
        begin,
        selectInitialZone,
        start,
        applyShot,
        reset,
        getState,
        subscribe,
    };
}

export const gridMode = createGridMode();
