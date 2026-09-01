# Ball flight model validation

`assets/range/js/physics.js` drives the virtual range and the minigames.
Coefficients were refit 2026-08-31 against real shot data. This file records
what was used, what the result was, and where the model is *not* trustworthy.

## Sources

| source | n | what it is | coverage |
|---|---|---|---|
| tim-blackmore/launch-monitor-regression | 9,677 | TrackMan, carry and total separate | driver only, 40-186 mph |
| Kaggle `jamieb122/golf-swing-and-trajectory-data` (MIT) | 805 | 100% **measured** spin | 51-142 mph, no club labels |
| Foresight Sports published reference tables | 26 | per-club measured rows | 65-165 mph, driver to LW |
| jgamblin/golf | 247 | Garmin R10 range sessions, measured-spin subset | 66-125 mph, mostly irons |

Blackmore and Kaggle were speed-stratified (max 90 shots per 10 mph band) so
10,000 driver shots could not drown 26 iron rows. Half of each went to fitting,
half to held-out validation. The Garmin sessions were **held out entirely** —
that unit reads about 5 yards short, and fitting to it would bake one device's
bias into the model.

## Result

Held-out (n=1,156), carry error in yards:

```
band        current              refit
 40-60      -0.8 / 2.7          -2.9 / 2.7
 60-80      +1.2 / 6.5          -2.6 / 6.6
 80-100     -1.3 / 7.3          -3.4 / 6.5
100-120     -0.5 / 10.6         -0.8 / 8.4
120-140     -1.4 / 14.8         +1.8 / 11.9
140-160     -7.6 / 15.6         +1.3 / 9.6
160-180    -11.8 / 16.2         -2.2 / 10.1

overall  -2.33 / 11.41  69% within 10y
          -1.60 /  8.50  83% within 10y
```

## What changed and why

```
cd = 0.22 + 0.38*sr                 ->  clamp(0.22 + 0.38*sr + 0.05*(60/v - 1), 0.12, 0.60)
cl = min(0.28, 0.07 + 0.80*sr)      ->  min(0.27, 0.09 + 0.95*sr)
```

The velocity term is the substantive fix. Real dimpled-ball drag **falls** as
speed rises (the drag crisis — Bearman & Harvey 1976, Mehta 1985). The old model
had drag depending only on spin, so it flew progressively shorter the harder the
ball was hit: 12 yards short at 160-180 mph.

## Known limits

- **Below ~50 mph ball speed is unvalidated.** No source covers it. Chip and
  putt flight is extrapolation.
- **The refit is ~2 yards more biased at 40-100 mph** than the old
  coefficients. Accepted because the old model's apparent accuracy there is
  partly one device's short read (Garmin -4.3 y at 40-100 while TrackMan and
  the Kaggle set were unbiased), and because scatter improves everywhere.
- **Bounce and roll are untouched.** `FAIRWAY_BOUNCE`, `ROLL_FACTOR` and
  `TURF_DECEL` remain unvalidated. Blackmore has a `Total` column, so roll is
  fittable later.
- **Carry is the first ground crossing.** The engine leaves `inFlight === true`
  through the bounce phase, so anything measuring "the last in-flight point"
  reads carry + bounce — 10 yards long on a driver. `tests/test_ball_physics.py`
  interpolates the descending `y` crossing instead.

## Approaches tried and rejected

- **Empirical regression** (`Minigames/empirical-golf-model.js`, 99 shots):
  linear in launch and spin, so distance rises without bound — a 90° pop-up
  scores as the longest drive. Fine for predicting a real shot, useless as an
  optimum. Also predicts carry+roll, running +25.8 y (sd 8.1) against carry.
- **Driver-only fit:** better on driver (43% -> 76% within 10 y) but pushed
  irons to -6.2 y bias. Rejected; refit jointly.
- **UpstreamDrift's Reynolds `tanh` drag curve** (MIT, cites Bearman & Harvey):
  more principled and better for extrapolation, but 78% within 10 y vs 83%, and
  out of the box it flew 20 y long because it carries no spin-drag term. A
  hybrid (their Reynolds blend + our spin drag) scored 76%. Kept the simpler
  velocity term on measured accuracy; revisit if the model ever needs to run
  outside 40-190 mph.
- **FlightScope Trajectory Optimizer:** its API enforces reCAPTCHA
  server-side. Not scripted, deliberately.

## Reproducing

The fitting corpus is third-party and not vendored. `Launch-Monitor-Data`'s
261k-row authority is private, and jgamblin/golf carries no LICENSE, so its
rows are not redistributed here.
