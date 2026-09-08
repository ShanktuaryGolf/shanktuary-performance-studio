// Ladder drill (SHA-55 T5). Port of putting-green.html L518, L1691–L1787.
// Clock/Gate/Circle/Star are out of v1. No physics, no scene, no websocket.

export const LADDER_DISTANCES = [
    2, 4, 6, 8, 10, 12, 14, 16, 18, 20,
    22, 24, 26, 28, 30, 32, 34, 36, 38, 40,
];

export class LadderDrill {
    constructor() {
        this.reset();
    }

    reset() {
        this.level = 1;
        this.makesAtLevel = 0;
        this.totalPutts = 0;
        this.totalMakes = 0;
        this.personalBest = LADDER_DISTANCES[0];
        this.completed = false;
        this.lastEvent = 'reset';
        return this.snapshot();
    }

    get distanceFt() {
        return LADDER_DISTANCES[this.level - 1];
    }

    snapshot() {
        const putts = this.totalPutts;
        return {
            level: this.level,
            distanceFt: this.distanceFt,
            makesAtLevel: this.makesAtLevel,
            totalPutts: putts,
            totalMakes: this.totalMakes,
            makePercent: putts > 0 ? Math.round((this.totalMakes / putts) * 100) : 0,
            personalBest: this.personalBest,
            completed: this.completed,
            lastEvent: this.lastEvent,
        };
    }

    applyResult(result) {
        if (result === 'make') return this.recordMake();
        return this.recordMiss();
    }

    recordMake() {
        this.totalPutts++;
        this.totalMakes++;
        this.makesAtLevel++;
        this.completed = false;

        const currentDist = this.distanceFt;
        if (currentDist > this.personalBest) {
            this.personalBest = currentDist;
            this.lastEvent = 'personal-best';
        }

        if (this.makesAtLevel >= 2) {
            if (this.level < LADDER_DISTANCES.length) {
                this.level++;
                this.makesAtLevel = 0;
                this.lastEvent = 'advance';
            } else {
                this.completed = true;
                this.lastEvent = 'complete';
            }
        } else if (this.lastEvent !== 'personal-best') {
            this.lastEvent = 'make';
        }

        return this.snapshot();
    }

    recordMiss() {
        this.totalPutts++;
        this.completed = false;
        if (this.level > 1) {
            this.level--;
            this.makesAtLevel = 0;
            this.lastEvent = 'drop';
        } else {
            this.makesAtLevel = 0;
            this.lastEvent = 'miss';
        }
        return this.snapshot();
    }
}
