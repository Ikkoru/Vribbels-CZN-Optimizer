"""Memory Fragment data model, Gear Score and Potential.

A Memory Fragment is equippable gear, one per slot, slots 1-6. This
module holds the in-memory representation plus the GS and Potential
maths the optimizer and UI run on.

Fields: `slot_num` (1-6, see `EQUIPMENT_SLOTS`), `set_id` / `set_name`,
`rarity_num` (1=Normal … 4=Legendary), `level` (0 to the rarity's cap),
`main_stat`, `substats` (up to 4), `equipped_to`, and the cached
`gear_score` / `potential_low` / `potential_high`.

Gear Score
==========

One comparable number per fragment per preset. The raw score is a
weighted sum of substat rolls: `(value / max_value) * weight * 10`
each — the roll's fraction of its own maximum, times the user's weight.

The subtlety is making raw scores COMPARABLE ACROSS PRESETS, since two
presets with different weights produce different magnitudes. So every
raw score is mapped onto 0-100:

    normalize_gs(raw, bounds) = (raw - min_raw) / (max_raw - min_raw) * 100

`(min_raw, max_raw)` is the theoretical floor and ceiling under THIS
preset's weights AS THIS FRAGMENT CAN REACH THEM. **The fragment's main
stat is excluded from the bounds** — a fragment cannot roll its own main
as a substat, so without the exclusion a fragment whose main is a
top-weighted stat could never reach 100 even with perfect rolls.
`compute_gs_bounds(exclude_stat=...)`; `bounds_for_fragment` is the
wrapper that passes the main stat's name.

Consequences:

- Every fragment can in theory reach 100, relative to its own main-stat
  constraint.
- **Two fragments with identical substats but different mains score
  differently.** The one whose main is more highly weighted scores
  HIGHER, because excluding it lowers the bounds ceiling and the same
  raw value normalizes higher. That correctly reflects the build value
  of the main stat, which GS itself does not measure.
- Rare fragments cap below 100: they have fewer upgrade rolls than the
  bounds assume (`_MAX_UPGRADES_FOR_BOUNDS` is the Legendary count).

Potential (low, high)
=====================

The range a fragment can still reach with its remaining upgrades.
`remaining_upgrades` = the rarity's max level minus the current level,
and each level-up contributes exactly one roll — creating the next
substat while the fragment has fewer than four, otherwise landing on an
existing one.

- **Best per upgrade:** lands on the highest-weighted substat at
  `max_value` → `10 * best_weight`.
- **Worst per upgrade:** lands on the lowest `ratio_min * weight`
  substat at `min_value` → `10 * ratio_min * weight`.

Both extremes normalize through the same main-stat-excluding bounds.
When `low == high` there are no upgrades left and Potential is undefined
as a range — callers display `-`.

**The ends are bounds, not likely outcomes.** Reaching the top takes
every remaining level-up landing on the best substat at its best roll:
for a +1 with four to go, about one path in twenty thousand. The low end
is as rare.

Average Potential
=================

Where a fragment is EXPECTED to end: the mean over every way its
remaining level-ups can land. `compute_fragment_potential_mean`. It
rests on three rules, the first two measured on the maintainer's
inventory:

- **A roll is anywhere on its stat's grid alike**, so its mean is the
  midpoint of `min_value` and `max_value`. Starting rolls, added
  substats and upgrades all average there.
- **An upgrade lands on each of the four substats alike.** The fully
  levelled fragments' spread of four upgrades over four substats matches
  that, pattern by pattern.
- **An added substat is any stat the fragment can still gain, alike.**
  Not measurable from an inventory, which holds only what was kept.

By linearity each level-up adds its expected roll, so the mean is a
sum, not an enumeration.

Likely Potential
================

The middle of the same outcomes: `compute_fragment_potential_band`
gives the GS the fragment ends below one time in ten, and the one it
ends above one time in ten. Same three rules, but a band needs the
whole distribution, so each roll is taken at every point of its grid
-- steps of 0.1 for a percentage stat and 1 for a flat one, which is
where every roll in the maintainer's inventory sits -- and the
level-ups are convolved, in bins of `_DIST_BIN` GS. An added substat is
every stat it could be, alike; the later level-ups then land among the
substats that choice made.

Elemental stats and the max_roll sentinel
=========================================

`STATS` holds both rollable substats and main-stat-only entries (Passion
DMG%, Order DMG%, …). The latter carry `min_roll`/`max_roll` of 0 as a
sentinel: they cannot roll as substats. **Every iteration over `STATS`
that builds GS or Potential data must skip `max_roll <= 0`** or it
pollutes the bounds. Enforced in `_raw_substat_score`,
`compute_gs_bounds`, and the candidate-pool loop in
`compute_fragment_potential`.

That skip is also what lets fragments with elemental mains reach 100:
the elemental main is already out of the substat pool, so
`exclude_stat=main_name` is a no-op for them.

Module-level helpers vs methods
===============================

The numerical core (`_raw_substat_score`, `compute_gs_bounds`,
`normalize_gs`, `compute_fragment_potential`,
`compute_fragment_potential_mean`, `compute_fragment_potential_band`)
is module-level and pure.
`MemoryFragment.calculate_base_score` / `calculate_potential` delegate to
it and cache the result for display.

The split exists because the Memory Fragments tab's Highest GS and
Highest Potential columns score one fragment under many presets
back-to-back, and must not clobber the display values, which reflect the
globally applied preset.
"""

import collections
import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from .stat import Stat, SubstatRoll
from game_data import (
    STATS,
    EQUIPMENT_SLOTS,
    RARITY,
    SETS,
    UPGRADES_PER_RARITY,
    get_character_name,
)
# Direct module-path imports to avoid relying on game_data/__init__.py
# re-exporting them.
from game_data.constants import MAX_LEVEL, MAX_LEVEL_PER_RARITY


# =============================================================================
# Module-level scoring helpers
# =============================================================================
#
# Gear Score is a weighted sum over substats — but the magnitude of that sum
# depends entirely on the chosen weights, so two presets produce numbers that
# aren't directly comparable. To keep the displayed score on a stable 0-100
# scale per preset, we compute the theoretical (min, max) raw score reachable
# by ANY fragment under the active weights, then linearly rescale every raw
# score into that window.

# Largest #upgrades any rarity supports. Anchors the upper bound so that
# Legendary fragments (with full upgrade headroom) can in principle reach
# the full 100 ceiling -- specifically, those Legendaries whose substats
# match the preset's top-4 weighted stats and whose upgrades all land on
# the top-weighted one. Lower-rarity fragments cap below 100 because they
# have fewer upgrades to spend on the high-weight stat.
_MAX_UPGRADES_FOR_BOUNDS = (
    max(UPGRADES_PER_RARITY.values()) if UPGRADES_PER_RARITY else 0
)


def _raw_substat_score(fragment, weights: dict) -> float:
    """Sum over substats of (value/max_roll) × weight × 10 — the raw weighted
    GS before normalization. Same formula the previous direct GS used."""
    total = 0.0
    for sub in fragment.substats:
        stat_info = STATS.get(
            sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1.0, 0.5)
        )
        max_roll = stat_info[3]
        if max_roll <= 0:
            continue
        normalized = sub.value / (max_roll * sub.roll_count)
        weight = weights.get(sub.name, 1.0)
        total += normalized * sub.roll_count * weight
    return total * 10


def compute_gs_bounds(
    weights: dict, exclude_stat: str | None = None
) -> tuple[float, float]:
    """Theoretical (min_raw, max_raw) GS achievable by ANY fragment under
    these weights -- with optional exclusion of a single stat. Used as the
    calibration window for normalize_gs().

    The exclude_stat parameter exists so we can compute per-fragment bounds
    that respect the rule "a fragment's main stat cannot appear as a
    substat". When excluded, that stat is skipped in the top-4 / bottom-4
    sums AND in the best/worst-per-upgrade picks, so the theoretical max
    drops appropriately. This lets each fragment's GS be normalized against
    what THIS fragment can actually achieve rather than against an abstract
    "any fragment" max -- otherwise fragments whose main stat happens to
    be high-weighted under the preset would cap below 100 even with
    perfectly-rolled substats, which misleads users.

    Pass exclude_stat=None to get the preset-wide bounds (useful when
    the caller genuinely wants "best any fragment could be" semantics, or
    in tests).

    Mechanics modelled (matches calculate_potential):
      - A fragment has up to 4 substats (one per stat, no duplicates)
      - All upgrade rolls beyond the initial 4 substats can land on a single
        substat -- so the "best" stat absorbs every upgrade in the best case,
        and the "worst" stat absorbs every upgrade in the worst case
      - Each individual roll's value lies in [min_roll, max_roll] for that stat

    For each stat the per-roll contribution is bracketed by:
      high_per_roll = weight x 1.0           (max roll)
      low_per_roll  = weight x min_roll/max_roll
    For positive weights, high > low; for negative weights it flips. Taking
    max/min handles both correctly.

    Bounds:
      max_raw = (sum of top-4 high_per_roll values
                 + max_upgrades x largest high_per_roll) x 10
      min_raw = (sum of bottom-4 low_per_roll values
                 + max_upgrades x smallest low_per_roll) x 10

    Returns (0.0, 0.0) when no usable stat data exists.
    """
    stat_bounds = []  # list[(high_per_roll, low_per_roll)]
    for _raw_name, info in STATS.items():
        if len(info) < 5:
            continue
        display_name = info[0]
        max_roll = info[3]
        min_roll = info[4]
        if max_roll <= 0:
            # Main-stat-only entries (elemental DMG%) -- never substats.
            continue
        if exclude_stat is not None and display_name == exclude_stat:
            # Per-fragment exclusion: this fragment's main stat can never
            # be a substat for this fragment, so it doesn't contribute to
            # the achievable max/min.
            continue
        weight = weights.get(display_name, 1.0)
        ratio_min = min_roll / max_roll
        c_high = weight * 1.0
        c_low = weight * ratio_min
        stat_bounds.append((max(c_high, c_low), min(c_high, c_low)))

    if not stat_bounds:
        return (0.0, 0.0)

    sorted_max = sorted(stat_bounds, key=lambda t: t[0], reverse=True)
    top_4_max = sum(t[0] for t in sorted_max[:4])
    best_per_upgrade = sorted_max[0][0]
    abs_max = (top_4_max + _MAX_UPGRADES_FOR_BOUNDS * best_per_upgrade) * 10

    sorted_min = sorted(stat_bounds, key=lambda t: t[1])
    bottom_4_min = sum(t[1] for t in sorted_min[:4])
    worst_per_upgrade = sorted_min[0][1]
    abs_min = (bottom_4_min + _MAX_UPGRADES_FOR_BOUNDS * worst_per_upgrade) * 10

    return (abs_min, abs_max)


def bounds_for_fragment(
    fragment, weights: dict
) -> tuple[float, float]:
    """Convenience wrapper around compute_gs_bounds that excludes the
    fragment's main stat from consideration. The right bounds to use when
    normalizing this fragment's GS or Potential under `weights`.

    Callers iterating many fragments under the same weights should cache
    by main_stat name -- there are only ~16 possible main stats, so the
    cache caps at that size regardless of fragment count.
    """
    main_name = fragment.main_stat.name if fragment.main_stat else None
    return compute_gs_bounds(weights, exclude_stat=main_name)


def normalize_gs(raw: float, bounds: tuple[float, float]) -> float:
    """Linearly rescale a raw GS into [0, 100] using the theoretical
    (min, max) from compute_gs_bounds(). Values outside that window are
    clamped. Returns 0 when bounds collapse (e.g., all-zero weights)."""
    abs_min, abs_max = bounds
    if abs_max <= abs_min:
        return 0.0
    val = (raw - abs_min) / (abs_max - abs_min) * 100
    return round(max(0.0, min(100.0, val)), 1)


def compute_fragment_gs(
    fragment, weights: dict, bounds: tuple[float, float] | None = None
) -> float:
    """Pure function: this fragment's normalized 0-100 Gear Score under the
    given weights. Does NOT mutate fragment.gear_score.

    Symmetric companion to compute_fragment_potential. Useful when scoring
    the same fragment under multiple presets back-to-back (e.g., the
    Optimizer-tab detail tree using the character's assigned preset rather
    than the active one) without clobbering the active preset's cached
    value.

    Args:
        fragment: the MemoryFragment instance (read-only; only substats /
                  main_stat are read).
        weights:  stat_name -> weight. Missing keys default to 1.0.
        bounds:   pre-computed (min_raw, max_raw). Computed lazily otherwise
                  using bounds_for_fragment (the fragment's main stat is
                  excluded -- Philosophy B). Pass it in when iterating many
                  fragments under the same weights to skip per-call work.
    """
    if weights is None:
        weights = {}
    if bounds is None:
        main_name = fragment.main_stat.name if fragment.main_stat else None
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    raw = _raw_substat_score(fragment, weights)
    return normalize_gs(raw, bounds)


def compute_fragment_potential(
    fragment, weights: dict, bounds: tuple[float, float] | None = None
) -> tuple[float, float]:
    """Pure function: (potential_low, potential_high) for one fragment under
    the given weights, normalized to the 0-100 scale.

    Same math as MemoryFragment.calculate_potential() but without mutating
    the fragment. Useful when scoring the same fragment under many presets in
    a row (e.g., the Highest Potential GS column) — each call needs to leave
    fragment.potential_low/high untouched so the active preset's values stay
    valid for elsewhere in the UI.

    Args:
        fragment: the MemoryFragment instance (only its substats / main_stat /
                  rarity_num are read — never written).
        weights:  stat_name -> weight. Missing keys default to 1.0.
        bounds:   pre-computed (min_raw, max_raw). Computed lazily otherwise.
                  When iterating many fragments under the same weights, pass
                  it in to skip the per-call recomputation.
    """
    if weights is None:
        weights = {}

    raw_base = _raw_substat_score(fragment, weights)

    if fragment.rarity_num < 3 or not fragment.substats:
        raw_low = raw_high = raw_base
    else:
        # Remaining level-ups, taken straight from the fragment's level and
        # its rarity's cap. Each level-up is exactly one roll -- it creates
        # the fragment's next substat while it has fewer than four, else it
        # lands on an existing one, and the candidate pool below covers both
        # cases.
        #
        # Deriving this from the level rather than from accumulated
        # roll_counts also stops a maxed fragment from appearing to have
        # headroom left: UPGRADES_PER_RARITY counts only the level-ups that
        # roll into an EXISTING substat, so subtracting the observed upgrade
        # count from it left a fully levelled Rare with one phantom upgrade.
        max_level = MAX_LEVEL_PER_RARITY.get(fragment.rarity_num, MAX_LEVEL)
        remaining_upgrades = max(0, max_level - fragment.level)

        if remaining_upgrades == 0:
            raw_low = raw_high = raw_base
        else:
            # Candidate pool: existing substats; if fragment has <4 substats,
            # also any other STAT not already present and not the main stat.
            candidates = []
            existing_names = {s.name for s in fragment.substats}
            for sub in fragment.substats:
                stat_info = STATS.get(
                    sub.raw_name,
                    (sub.name, sub.name, sub.is_percentage, 1.0, 0.5),
                )
                max_roll = stat_info[3]
                min_roll = stat_info[4]
                weight = weights.get(sub.name, 1.0)
                candidates.append((sub.name, max_roll, min_roll, weight))

            if len(fragment.substats) < 4:
                main_name = fragment.main_stat.name if fragment.main_stat else None
                for _raw, info in STATS.items():
                    name, _short, _is_pct, max_roll, min_roll = info
                    if max_roll <= 0:
                        # Main-stat-only entries (elemental DMG%) are not
                        # rollable and must not be considered as potential
                        # 4th-substat candidates.
                        continue
                    if name in existing_names or name == main_name:
                        continue
                    weight = weights.get(name, 1.0)
                    candidates.append((name, max_roll, min_roll, weight))

            if not candidates:
                raw_low = raw_high = raw_base
            else:
                best_per_upgrade = max(w for _n, _mx, _mn, w in candidates)
                worst_per_upgrade = min(
                    ((mn / mx) if mx > 0 else 0.5) * w
                    for _n, mx, mn, w in candidates
                )
                raw_high = raw_base + remaining_upgrades * best_per_upgrade * 10
                raw_low = raw_base + remaining_upgrades * worst_per_upgrade * 10

    if bounds is None:
        # Lazy bounds match what the caller would compute via
        # bounds_for_fragment() -- main stat excluded so 100 is reachable
        # under perfect substat rolls regardless of which main this
        # fragment happens to have. Pass `bounds` explicitly when looping
        # many fragments to skip this per-call overhead (use a cache keyed
        # by main_stat name).
        main_name = fragment.main_stat.name if fragment.main_stat else None
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    return (normalize_gs(raw_low, bounds), normalize_gs(raw_high, bounds))


def _expected_roll(name, max_roll, min_roll, weights):
    """One roll's expected raw contribution: the grid's midpoint as a
    fraction of the maximum, times the weight, times 10."""
    return weights.get(name, 1.0) * (max_roll + min_roll) / (2 * max_roll) * 10


def compute_fragment_potential_mean(
    fragment, weights: dict, bounds: tuple[float, float] | None = None
) -> float:
    """Pure function: the GS `fragment` is expected to end at under
    `weights`, on the 0-100 scale -- see *Average Potential* in the
    module docstring. Its current GS where nothing is left to roll."""
    if weights is None:
        weights = {}
    raw = _raw_substat_score(fragment, weights)
    max_level = MAX_LEVEL_PER_RARITY.get(fragment.rarity_num, MAX_LEVEL)
    remaining = max(0, max_level - fragment.level)
    if fragment.rarity_num >= 3 and fragment.substats and remaining:
        existing = []
        for sub in fragment.substats:
            info = STATS.get(sub.raw_name,
                             (sub.name, sub.name, sub.is_percentage, 1.0, 0.5))
            if info[3] > 0:
                existing.append(_expected_roll(sub.name, info[3], info[4],
                                               weights))
        # The first level-ups each add a substat, drawn from the stats
        # the fragment has not got and cannot have (its main).
        present = {sub.name for sub in fragment.substats}
        main_name = fragment.main_stat.name if fragment.main_stat else None
        pool = [_expected_roll(info[0], info[3], info[4], weights)
                for info in STATS.values()
                if info[3] > 0 and info[0] not in present
                and info[0] != main_name]
        added = min(4 - len(fragment.substats), remaining) if pool else 0
        pool_mean = sum(pool) / len(pool) if pool else 0.0
        raw += added * pool_mean
        # The rest land on one of the substats alike, the added ones
        # included.
        into_existing = remaining - added
        slots = len(existing) + added
        if into_existing > 0 and slots:
            raw += into_existing * (sum(existing) + added * pool_mean) / slots
    if bounds is None:
        main_name = fragment.main_stat.name if fragment.main_stat else None
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    return normalize_gs(raw, bounds)


# The Potential distribution's resolution, in GS points. The display
# rounds to whole points; the work grows with the square of this.
_DIST_BIN = 0.25

# The share of outcomes a likely band leaves out at EACH end.
BAND_TAIL = 0.1


def _roll_grid(info, weight, scale):
    """Every value one roll of a stat can take, as the GS it adds: its
    grid runs `min_value` to `max_value` in steps of 0.1 for a
    percentage stat and 1 for a flat one."""
    _name, _short, is_pct, max_roll, min_roll = info
    step = 0.1 if is_pct else 1.0
    count = max(1, int(round((max_roll - min_roll) / step)) + 1)
    return tuple(weight * (min_roll + i * step) / max_roll * 10 * scale
                 for i in range(count))


def _dist(grids):
    """One level-up landing on one of `grids` alike and anywhere on it
    alike, as (first bin, [chance per bin])."""
    bins = {}
    share = 1.0 / len(grids)
    for grid in grids:
        each = share / len(grid)
        for value in grid:
            at = int(round(value / _DIST_BIN))
            bins[at] = bins.get(at, 0.0) + each
    first = min(bins)
    chances = [0.0] * (max(bins) - first + 1)
    for at, chance in bins.items():
        chances[at - first] = chance
    return first, chances


def _convolve(a, b):
    """The distribution of the sum of two independent ones."""
    (first_a, chances_a), (first_b, chances_b) = a, b
    if len(chances_b) > len(chances_a):
        chances_a, chances_b = chances_b, chances_a
    # The inner loop takes the shorter side's filled bins only. That
    # side is mostly one level-up, whose bins are mostly empty: a
    # substat the preset weighs 0 puts all its rolls in one, and a
    # weighted one's steps are often wider than a bin.
    filled = [(j, y) for j, y in enumerate(chances_b) if y]
    out = [0.0] * (len(chances_a) + len(chances_b) - 1)
    for i, x in enumerate(chances_a):
        if x:
            for j, y in filled:
                out[i + j] += x * y
    return first_a + first_b, out


def _power(dist, times):
    """`dist` added to itself `times` times; the zero distribution for 0."""
    out = (0, [1.0])
    for _ in range(times):
        out = _convolve(out, dist)
    return out


def _blend(parts):
    """The sum of `share` times `dist` over `(share, dist)` pairs: a
    mixture where the shares add up to 1."""
    first = min(f for _share, (f, _c) in parts)
    out = [0.0] * (max(f + len(c) for _share, (f, c) in parts) - first)
    for share, (f, chances) in parts:
        at = f - first
        for i, chance in enumerate(chances):
            out[at + i] += chance * share
    return first, out


def _added_then_rest(existing, pool, added, rest):
    """The sum of `added` first rolls on stats drawn from `pool`, no
    two alike and every draw alike, and `rest` level-ups each landing
    on one of `existing` and the added substats alike.

    How many of the `rest` land on an added substat, K, is binomial,
    and given K the existing substats' rolls and the added ones' are
    independent: the sum is the mixture over K of existing^(rest - K)
    convolved with H_K, the added substats' first rolls plus K more
    among them, mixed over every draw. Only H_K depends on the draw,
    and its grids are the small ones, so the existing substats' rolls
    are convolved in once rather than once per draw -- by Horner's
    scheme, one level-up at a time."""
    rolls = [_dist([grid]) for grid in pool]
    # Draws that roll alike are one -- every stat the preset weighs 0
    # rolls a lone 0 -- and weigh as often as they occur.
    draws = collections.Counter(
        tuple(sorted(chosen)) for chosen in itertools.combinations(
            [(first, tuple(chances)) for first, chances in rolls], added))
    count = sum(draws.values())
    by_more = [[] for _ in range(rest + 1)]
    for chosen, times in draws.items():
        part = chosen[0]
        for roll in chosen[1:]:
            part = _convolve(part, roll)
        more = _blend([(1.0 / added, roll) for roll in chosen])
        for k in range(rest + 1):
            if k:
                part = _convolve(part, more)
            by_more[k].append((times / count, part))
    if not existing:
        return _blend(by_more[rest])
    step = _dist(existing)
    chance = added / (len(existing) + added)
    total = None
    for k in range(rest + 1):
        share = (math.comb(rest, k) * chance ** k
                 * (1.0 - chance) ** (rest - k))
        mixed = _blend(by_more[k])
        if total is None:
            total = _blend([(share, mixed)])
        else:
            total = _blend([(1.0, _convolve(total, step)), (share, mixed)])
    return total


def _quantile(dist, share):
    """The bin at which `share` of a distribution is reached, in GS."""
    first, chances = dist
    total = 0.0
    for i, chance in enumerate(chances):
        total += chance
        if total >= share - 1e-9:
            return (first + i) * _DIST_BIN
    return (first + len(chances) - 1) * _DIST_BIN


# Bands already worked out, by everything a band depends on. The Memory
# Fragments tab asks for the same ones again on every refresh -- a
# filter, a capture's save -- and working one out is the slow part, so
# only a fragment or a preset that changed costs anything. Cleared whole
# past this many.
_BAND_CACHE = {}
_BAND_CACHE_MAX = 50000

# One copy of each set of weights, shared by every key made with it: a
# key's own copy would be most of what a cached band costs.
_WEIGHTS_SEEN = {}


def _band_key(fragment, weights, bounds, tail, main_name):
    weights_key = tuple(sorted(weights.items()))
    weights_key = _WEIGHTS_SEEN.setdefault(weights_key, weights_key)
    return (fragment.rarity_num, fragment.level, main_name,
            tuple((s.raw_name, s.value, s.roll_count)
                  for s in fragment.substats),
            weights_key, tuple(bounds), tail)


def compute_fragment_potential_band(
    fragment, weights: dict, bounds: tuple[float, float] | None = None,
    tail: float = BAND_TAIL,
) -> tuple[float, float]:
    """Pure function: (low, high) GS on the 0-100 scale between which the
    middle `1 - 2 * tail` of `fragment`'s outcomes under `weights` end --
    see *Likely Potential* in the module docstring. Its current GS twice
    where nothing is left to roll."""
    if weights is None:
        weights = {}
    main_name = fragment.main_stat.name if fragment.main_stat else None
    if bounds is None:
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    key = _band_key(fragment, weights, bounds, tail, main_name)
    band = _BAND_CACHE.get(key)
    if band is None:
        band = _work_out_band(fragment, weights, bounds, tail, main_name)
        if len(_BAND_CACHE) >= _BAND_CACHE_MAX:
            _BAND_CACHE.clear()
            _WEIGHTS_SEEN.clear()
        _BAND_CACHE[key] = band
    return band


def cached_potential_band(fragment, weights: dict,
                          bounds: tuple[float, float],
                          tail: float = BAND_TAIL):
    """`compute_fragment_potential_band`'s answer where it costs nothing
    -- worked out already, or nothing left to roll -- else None: for a
    caller that must not wait for one."""
    weights = weights or {}
    max_level = MAX_LEVEL_PER_RARITY.get(fragment.rarity_num, MAX_LEVEL)
    if (fragment.rarity_num < 3 or not fragment.substats
            or fragment.level >= max_level or bounds[1] <= bounds[0]):
        return compute_fragment_potential_band(fragment, weights, bounds,
                                               tail)
    main_name = fragment.main_stat.name if fragment.main_stat else None
    return _BAND_CACHE.get(
        _band_key(fragment, weights, bounds, tail, main_name))


def _work_out_band(fragment, weights, bounds, tail, main_name):
    """`compute_fragment_potential_band`, uncached."""
    raw = _raw_substat_score(fragment, weights)
    max_level = MAX_LEVEL_PER_RARITY.get(fragment.rarity_num, MAX_LEVEL)
    remaining = max(0, max_level - fragment.level)
    low_raw, high_raw = bounds
    if (fragment.rarity_num < 3 or not fragment.substats or not remaining
            or high_raw <= low_raw):
        gs = normalize_gs(raw, bounds)
        return gs, gs
    scale = 100.0 / (high_raw - low_raw)
    existing = []
    for sub in fragment.substats:
        info = STATS.get(sub.raw_name,
                         (sub.name, sub.name, sub.is_percentage, 1.0, 0.5))
        if info[3] > 0:
            existing.append(_roll_grid(info, weights.get(sub.name, 1.0),
                                       scale))
    present = {sub.name for sub in fragment.substats}
    pool = [_roll_grid(info, weights.get(info[0], 1.0), scale)
            for info in STATS.values()
            if info[3] > 0 and info[0] not in present and info[0] != main_name]
    added = min(4 - len(fragment.substats), remaining) if pool else 0
    rest = remaining - added
    if not existing and not added:
        gs = normalize_gs(raw, bounds)
        return gs, gs
    if not added:
        total = _power(_dist(existing), rest)
    else:
        total = _added_then_rest(existing, pool, added, rest)
    start = (raw - low_raw) * scale
    return tuple(round(max(0.0, min(100.0, start + _quantile(total, share))),
                       1)
                 for share in (tail, 1.0 - tail))


@dataclass
class MemoryFragment:
    id: int
    slot_name: str
    slot_num: int
    rarity: str
    rarity_num: int
    set_name: str
    set_id: int
    level: int
    locked: bool
    equipped_to: Optional[str]
    equipped_char_id: int
    main_stat: Optional[Stat] = None
    substats: list[Stat] = field(default_factory=list)
    gear_score: float = 0.0
    priority_score: float = 0.0
    potential_low: float = 0.0
    potential_high: float = 0.0

    @classmethod
    def from_json(cls, data: dict) -> "MemoryFragment":
        res_id = data["res_id"]
        res_str = str(res_id)
        slot_num = int(res_str[2])
        rarity_num = int(res_str[3])
        set_id = int(res_str[4:])

        main_stat = None
        substat_map = {}
        substat_rolls = {}

        for stat_data in data.get("stat_list", []):
            raw_stat = stat_data["stat"]
            stat_info = STATS.get(raw_stat, (raw_stat, raw_stat, False, 1, 1))
            slot = stat_data["slot"]
            stat_type = stat_data["type"]
            value = stat_data["value"]

            if slot == 0 and stat_type == 0:
                main_stat = Stat(name=stat_info[0], raw_name=raw_stat, value=value,
                                is_percentage=stat_info[2], is_main=True)
            else:
                if slot not in substat_map:
                    substat_map[slot] = Stat(
                        name=stat_info[0], raw_name=raw_stat, value=value,
                        is_percentage=stat_info[2], roll_count=1,
                        base_value=value if stat_type in [1, 2] else 0.0
                    )
                    substat_rolls[slot] = [(value, stat_type)]
                else:
                    substat_map[slot].value += value
                    substat_map[slot].roll_count += 1
                    substat_rolls[slot].append((value, stat_type))
                    if stat_type == 3:
                        substat_map[slot].upgrade_values.append(value)
                    elif stat_type in [1, 2] and substat_map[slot].base_value == 0:
                        substat_map[slot].base_value = value

        for slot, stat in substat_map.items():
            stat_info = STATS.get(stat.raw_name, (stat.name, stat.name, stat.is_percentage, 1.0, 0.5))
            max_roll = stat_info[3]
            min_roll = stat_info[4]

            for value, stat_type in substat_rolls.get(slot, []):
                is_min = abs(value - min_roll) < 0.01
                is_max = abs(value - max_roll) < 0.01
                stat.rolls.append(SubstatRoll(value=value, stat_type=stat_type,
                                             is_min_roll=is_min, is_max_roll=is_max))

            if stat.base_value == 0 and stat.rolls:
                stat.base_value = stat.rolls[0].value

        substats = list(substat_map.values())
        char_id = data.get("char_res_id", 0)
        equipped_to = get_character_name(char_id)
        # Unknown sets are displayed by their bare numeric ID (no "Unknown(...)").
        set_info = SETS.get(set_id, {"name": str(set_id)})
        set_name = set_info["name"] if isinstance(set_info, dict) else set_info

        return cls(
            id=data["id"], slot_name=EQUIPMENT_SLOTS.get(slot_num, f"Unknown({slot_num})"),
            slot_num=slot_num, rarity=RARITY.get(rarity_num, f"Unknown({rarity_num})"),
            rarity_num=rarity_num, set_name=set_name, set_id=set_id,
            level=data.get("level", 0), locked=data.get("lock", False),
            equipped_to=equipped_to, equipped_char_id=char_id,
            main_stat=main_stat, substats=substats,
        )

    def calculate_base_score(
        self,
        weights: Optional[dict] = None,
        bounds: Optional[tuple[float, float]] = None,
    ) -> float:
        """Compute and store this fragment's gear score, normalized to a
        0-100 scale based on the theoretical bounds for the given weights.

        Args:
            weights: stat_name -> weight. Missing stats default to 1.0. Pass
                     None or {} for unweighted (= flat 1.0 across all stats).
            bounds:  pre-computed (min_raw, max_raw) for the same weights.
                     Pass it in when looping over many fragments to avoid
                     recomputing the bounds on every call. Computed lazily
                     if omitted.
        """
        if weights is None:
            weights = {}
        raw = _raw_substat_score(self, weights)
        if bounds is None:
            # Match the Philosophy B convention used elsewhere: exclude this
            # fragment's main stat from the bounds so 100 is reachable for
            # this fragment specifically (rather than the abstract "any
            # fragment" ceiling). Callers iterating many fragments under
            # the same weights should pass `bounds` explicitly from a
            # per-main-stat cache to skip this per-call work.
            main_name = self.main_stat.name if self.main_stat else None
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
        self.gear_score = normalize_gs(raw, bounds)
        return self.gear_score

    def calculate_priority_score(self, priorities: dict[str, int]) -> float:
        priority_score = 0.0
        for sub in self.substats:
            stat_info = STATS.get(sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1, 1))
            max_roll = stat_info[3]
            normalized = sub.value / (max_roll * sub.roll_count) if max_roll > 0 else 0
            priority = priorities.get(sub.name, 0)
            priority_score += normalized * priority * sub.roll_count
        self.priority_score = round(priority_score * 10, 1)
        return self.priority_score

    def calculate_potential(
        self,
        weights: Optional[dict] = None,
        bounds: Optional[tuple[float, float]] = None,
    ) -> tuple[float, float]:
        """Compute and store the worst- and best-case GS reachable through
        remaining upgrades, normalized to the same 0-100 scale as gear_score.

        The math lives in module-level compute_fragment_potential(); this
        method just stores the result on self for later display. Callers that
        need to score this fragment under multiple presets back-to-back
        without clobbering self.potential_low/high should call the pure
        helper directly.

        Args:
            weights: stat_name -> weight. Missing stats default to 1.0.
            bounds:  pre-computed (min_raw, max_raw) for these weights —
                     pass when iterating many fragments to avoid recomputation.
        """
        low, high = compute_fragment_potential(self, weights or {}, bounds)
        self.potential_low = low
        self.potential_high = high
        return (low, high)

    def get_total_stats(self) -> dict[str, float]:
        stats = {}
        if self.main_stat:
            stats[self.main_stat.name] = stats.get(self.main_stat.name, 0) + self.main_stat.value
        for sub in self.substats:
            stats[sub.name] = stats.get(sub.name, 0) + sub.value
        return stats

    def get_set_pieces(self) -> int:
        set_info = SETS.get(self.set_id)
        if set_info:
            return set_info.get("pieces", 2)
        return 2
