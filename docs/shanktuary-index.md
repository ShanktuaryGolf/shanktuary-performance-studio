# Shanktuary Index — design note

Status: **proposal, not built.** No code exists for this. This note records
the design so it survives the conversation it came out of.

A 0–99 skill rating that a golfer can move by practising, built only from
what the Nova actually measures. Named after the golf term for a portable
skill rating — every golfer already knows what "my index is 12" means, so it
inherits that credibility and pairs naturally with the handicap anchoring
below.

---

## Step zero — before any of this is built

**The benchmark constants must come from a citable source.** Every threshold
in this document is a placeholder written from memory and should be treated
as wrong until sourced.

Candidates:

- TrackMan published club averages (tour and amateur, by club)
- PGA Tour ShotLink proximity-by-distance data
- Published dispersion-by-handicap studies

If these constants end up invented, the Index is decoration with a confident
font — the same failure as the fabricated strike-location formula that was
removed from this app in August 2026. That is the bar to clear.

Two specific figures to check hard, because they look wrong:

- "±4 yds dispersion for a tour 7-iron" (from an LLM-generated benchmark
  table). Tour *proximity* from that distance is measured in tens of feet,
  on course. Suspect this is too tight by a wide margin.
- Tour 7-iron ball speed ~120 mph / carry ~172 yds looks plausible but is
  still unsourced.

---

## Hardware constraints — what may and may not be used

The Nova measures exactly five ball parameters:

```
ball_speed · vertical_launch_angle · horizontal_launch_angle
total_spin_rpm · spin_axis_degrees
```

Everything else in the payload — club speed, smash factor, club path, face
to target, face to path — is **derived by OpenGolfCoach**, not measured.

### Excluded from the Index, with reasons

| Excluded | Why |
|---|---|
| Smash factor | OGC clamps effective COR at a 0.52 floor, so smash collapses to the constant `1.2361241003537593` below ~90 mph ball speed and for all wedges. Verified in this repo: 7 Iron and Putter both average exactly 1.2361 across the current session. |
| Club speed | Derived as `ball_speed / smash`. When smash is clamped, this is just ball speed times a constant — no independent information. |
| Ball speed / carry as a *raw value* | Scoring distance hard-caps slower swingers regardless of skill. An explicit product decision: a golfer who hits it 180 dead straight must be able to reach a high Index. |
| Attack angle, dynamic loft | Not measured. The app already renders these as `NOT MEASURED`. |
| Face angle, face-to-path | Derived, and downstream of the same clamp. |
| Pressure / balance board data | Only some users own boards. Nobody should score lower for not buying hardware. Fine as a separate panel; not a component. |

`compute_smash_confidence()` already detects the clamp per shot and is the
existing gate for this — any future scoring code should reuse it rather than
re-deriving the test.

### Also excluded

- **Putter shots.** They would pollute every component. (The current session
  file holds 8, from a period when the club dropdown was mis-set.)
- **Shots flagged `excluded`** in the shot table.

---

## The four components

Weighting is a starting point, not a settled answer.

### 1. Consistency — 30%

*Can you repeat a distance?*

Carry standard deviation per club, as a **percentage of that club's mean
carry**, not in raw yards.

The percentage is the fairness mechanism: a 90-yard 7-iron with ±4 yds
scores identically to a 170-yard 7-iron with ±7.5 yds. Same skill, different
engine.

Input already exists: `get_bag_club_stats()` returns `avg_carry` and
`std_carry` per club.

### 2. Command — 30%

*Does it go where you aimed?*

Offline dispersion as a percentage of carry. Horizontal launch angle is
measured directly by the Nova, so this is real data.

Offline is the **outcome** of start line plus curvature. Score the outcome
only; use HLA versus spin axis in the diagnostic breakdown to say *why* a
shot missed. Scoring start line, curvature and outcome separately
triple-counts one miss.

### 3. Contact — 25%

*Are you finding the middle repeatably?*

Consistency of vertical launch angle relative to the club's static loft.
This is the one strike signal that is honest on a Nova — vertical deviation
carries real information; horizontal deviation is near-circular noise.

**Depends on correct lofts in the bag.** A club with a wrong or zero loft
scores its strikes against the wrong reference. Generic default lofts were
found to be up to 4° off real specs, which flipped ~21% of strike-height
verdicts. The Index should refuse to score Contact for a club whose
`loft_deg` is 0.0, and say so.

### 4. Coverage — 15%

*Does your set cover the yardages?*

Gapping quality from the bag: are the gaps sensible, consistent and
non-overlapping.

This is deliberately the odd component out — it measures equipment, not
swing. It is also the one a user can fix in an afternoon with a wrench,
which makes it the obvious first win. Lowest weight because it is bought
rather than earned.

Input already exists: `calculate_bag_gapping()` returns per-gap deltas, a
mean gap and a consistency grade, and already flags collisions.

---

## Thresholds

### Per club

| Shots | State |
|---|---|
| < 15 | No rating. Show progress toward one. |
| 15–29 | Provisional. Always displayed with the count. |
| 30+ | Established. |

Driven by the statistics: a standard deviation from fewer than ~10 samples
is close to noise; by 30 it is within roughly 13% of the true value. Below
15, a single shot swings the rating ~10 points.

### Overall Index

Coverage matters more than raw volume:

- Minimum **3 clubs established**, spanning at least **2 categories**
- Full-bag Index needs ~6 clubs including a wood, a mid-iron and a wedge

This is the anti-gaming mechanism. Wedges will always score best on
dispersion, so without a coverage requirement the rational strategy is to
hit nothing but wedges.

First overall Index lands around 90–100 shots — two or three range sessions.

### Rolling window

Once established: **last 50 shots per club, recency weighted.** The Index
should track the current game, and one bad session should dent it rather
than erase it. Frustration kills engagement faster than a low number does.

### Outliers

Borrow the handicap convention: **best N of the last M** (a golf handicap
uses best 8 of last 20). This handles the occasional shank without letting
anyone cherry-pick, golfers already accept it as fair, and it makes the
existing "exclude shot" checkbox non-gameable — which, as things stand, it
would not be.

---

## Scale and anchoring

| Index | Level |
|---|---|
| 99 | Tour elite |
| 75 | Scratch |
| 50 | ~15 handicap |
| 20 | Beginner |

Anchored to **published benchmarks, not to the SPS user pool.** A
self-referential scale ("99 = best SPS user") is meaningless and drifts as
the userbase grows. Anchoring externally means a 75 has a fixed, explainable
meaning and the gap to scratch can be stated honestly.

**Show the handicap equivalent alongside the number.** A median user sitting
at 50 is honest but flat; *"Shanktuary Index 58 — striking it like a 12
handicap"* is legible immediately. Golfers know what a 12 means. Nobody
knows what a 58 means.

Data honesty note: the Index measures **ball-striking on a range**, not
scoring. It cannot see putting, chipping, course management or pressure. It
should never be presented as a predicted handicap — only as "striking like".

---

## How a user improves it

Every component must point at a specific action, or the number is just a
mood ring:

| Component | The fix |
|---|---|
| Consistency | Tighter carry band — same club, same target |
| Command | Diagnostic says face or curvature; different drills |
| Contact | Centeredness of strike; validate with impact tape |
| Coverage | Bend a loft, swap a club, fill the gap |

Two features that would make this genuinely worth using, neither of which
any launch monitor software currently does well:

**Show what moved.**
`Index 71 → 73. Command improved 6 points over your last 40 shots.`
Attribution, not a number that silently drifts.

**Show the highest-leverage fix.**
`Weakest component: Coverage (48). Your PW→52° gap is 11°; closing it moves
your Index +4.`
That is the cheapest available improvement, stated plainly.

---

## Build order

1. Source the benchmark constants. Nothing else starts until this is done.
2. Build the four components as standalone, visible metrics. **Do not label
   them an Index yet.**
3. Run them over several weeks of real sessions. Confirm they are stable and
   that they move in the direction a coach would expect.
4. Only then add the weighted overall.

The overall is a one-line weighted sum once the parts are right. If the
parts are noisy, the overall is noise with a confident font.

---

## Naming

**Shanktuary Index.** "Index" is the real golf term for a portable skill
rating, so it inherits instant credibility and pairs with the handicap
anchoring.

Alternatives considered: Shanktuary Score (alliterative, but "score" inverts
— in golf, low is good), Standard, Status, Stripe.

UI note: spell it out. Avoid abbreviating to two initials anywhere in the
interface — that particular pair of letters carries an unfortunate
historical association for a product distributed publicly. `Shanktuary Index
71`, or `Index 71` where space is tight.

---

## Open questions

- Are the component weights right? 30/30/25/15 is a guess.
- Should Coverage be in the Index at all, or a separate equipment score?
  It measures the bag, not the golfer.
- How should a brand-new club with no history affect an established Index?
- Should the Index be per-session, all-time, or both?
- Is 99 reachable in practice with only these four components, or does
  excluding distance compress the top of the scale?
- Does a left-handed golfer's data need any different treatment here?
  (Handed fields in the Nova payload are dicts keyed
  `right_handed`/`left_handed`.)
