"""Substat Readjustment: what readjusting a fully upgraded Legendary
Memory Fragment is worth, per Shuffling Quartz.

**What the game does** (its Memory Fragment Upgrade Probabilities
notice, and the client's `ui_piece_readjust_desc_*`): a readjustment
keeps every substat's type and the value it started at, and performs
`UPGRADES` upgrades again, each on one of the substats with equal
chance and each a roll anywhere on that stat's Legendary grid with
equal chance. One substat may be excluded first: it takes no upgrade
and goes back to its starting value. A readjustment costs 1 Shuffling
Quartz, 2 with an exclusion. The game then shows Before and After and
the player keeps either, so a readjustment never loses anything: its
worth is the expected `max(0, after - before)`.

A fragment's starting values are told apart from its upgrades in its
`stat_list` (`MemoryFragment.from_json`: `base_value`).

**Two measures of after**, each per combatant:

- `GearValuer`: the Gear Score under the combatant's preset, in GS
  points. Linear in the rolls, so the distribution is exact.
- `BuildValuer`: the Optimizer's score of the combatant's equipped
  build with the fragment in its slot, as the per cent it rises by.
  Before is the better of the build as worn and the build with the
  fragment as it stands. The distribution is the linear one, from
  what one max roll of each stat adds to the build (`worths`), and
  `refine` replaces it by sampling the real score for the fragments
  ranked highest.

**The work runs in worker processes** (`submit`), a job a chunk of
fragments: Python arithmetic on a thread holds the interpreter lock
in turns with Tk's event loop, which then answers the window only
between them. A worker imports `game_data` fresh, without the game
client's rolls laid over it, so each job carries `STATS` along
(`stats_snapshot`) and every build-score input already resolved
(`build_inputs`). No Tk on this module's import path.
"""

import atexit
import os
import random
from dataclasses import dataclass

from game_data.constants import MAX_LEVEL, MAX_LEVEL_PER_RARITY, STATS
from models.memory_fragment import (_convolve, compute_gs_bounds,
                                    _raw_substat_score)

QUARTZ = 3210004
PLAIN_COST = 1
EXCLUDE_COST = 2
LEGENDARY = 4
# How many upgrades a readjustment performs, whatever the fragment had.
UPGRADES = 4
# A distribution's resolution: the bins its whole span is cut into. A
# gain reads to about a 400th of the most four upgrades could add.
BINS = 400
# How many fragments `refine` samples, and how many readjustments
# each: the error of a mean gain is about its spread over the square
# root of the samples.
REFINE_TOP = 20
REFINE_SAMPLES = 800

GEAR = "gear"
BUILD = "build"


def readjustable(fragment):
    """A Legendary at its top level with four substats."""
    top = MAX_LEVEL_PER_RARITY.get(LEGENDARY, MAX_LEVEL)
    return (fragment.rarity_num == LEGENDARY and fragment.level >= top
            and len(fragment.substats) == 4)


def content(fragment):
    """Everything a reading of `fragment` depends on: its id, slot, set,
    rarity, level, main stat and each substat's starting value and
    upgrades. A readjusted fragment keeps its id and changes this, so an
    answer kept under it is never one of an older roll."""
    main = fragment.main_stat
    return (fragment.id, fragment.slot_num, fragment.set_id,
            fragment.rarity_num, fragment.level,
            (main.raw_name, main.value) if main is not None else None,
            tuple((s.raw_name, s.value, s.base_value,
                   tuple(s.upgrade_values)) for s in fragment.substats))


def roll_values(sub):
    """Every value one upgrade of `sub` can roll, alike: its stat's
    grid, steps of 0.1 for a percentage and 1 for a flat stat."""
    info = STATS.get(sub.raw_name)
    if not info or info[3] <= 0:
        return [0.0]
    _name, _short, is_pct, high, low = info
    step = 0.1 if is_pct else 1.0
    count = max(1, round((high - low) / step) + 1)
    return [round(low + i * step, 4) for i in range(count)]


def max_roll(sub):
    info = STATS.get(sub.raw_name)
    return info[3] if info and info[3] > 0 else 0.0


@dataclass
class Option:
    """One way to readjust: `excluded` the substat left out (None for
    none), what it costs, and what it gains over before -- the mean,
    the chance of any gain at all, the most it can."""
    excluded: str | None
    cost: int
    mean: float
    chance: float
    best: float

    @property
    def per_quartz(self):
        return self.mean / self.cost


@dataclass
class Reading:
    """A fragment readjusted for one combatant: its before (`now`, in
    the measure's units), the plain readjustment, the best exclusion,
    and whether `refine` sampled it."""
    fragment: object
    combatant: str
    now: float
    plain: Option
    exclude: Option
    sampled: bool = False
    weight: float = 1.0

    @property
    def best(self):
        """The option a Quartz does most with."""
        return max((self.plain, self.exclude),
                   key=lambda o: (o.per_quartz, -o.cost))

    @property
    def value(self):
        """What the list ranks by: gain per Quartz, times the weight."""
        return self.best.per_quartz * self.weight


# ---------------------------------------------------------------- engine


def _one_upgrade(grids, width):
    """One upgrade landing on one of `grids` alike and on any of its
    values alike, binned at `width`: (first bin, [chance per bin])."""
    bins = {}
    share = 1.0 / len(grids)
    for grid in grids:
        each = share / len(grid)
        for value in grid:
            at = round(value / width)
            bins[at] = bins.get(at, 0.0) + each
    first = min(bins)
    chances = [0.0] * (max(bins) - first + 1)
    for at, chance in bins.items():
        chances[at - first] = chance
    return first, chances


def _times(dist, count):
    """`dist` added to itself `count` times, by squaring."""
    out, square = (0, [1.0]), dist
    while count:
        if count & 1:
            out = _convolve(out, square)
        count >>= 1
        if count:
            square = _convolve(square, square)
    return out


def _option(grids, start, ref, excluded, cost):
    """The Option of dealing `UPGRADES` upgrades over `grids` (each a
    list of what a roll adds), onto `start`, against `ref`."""
    tops = [max(grid) for grid in grids]
    lows = [min(grid) for grid in grids]
    span = max(UPGRADES * (max(tops) - min(lows)), 1e-9)
    width = span / BINS
    first, chances = _times(_one_upgrade(grids, width), UPGRADES)
    mean = chance = 0.0
    for i, p in enumerate(chances):
        after = start + (first + i) * width
        if after > ref + width / 2:
            mean += p * (after - ref)
            chance += p
    best = max(0.0, start + UPGRADES * max(tops) - ref)
    return Option(excluded, cost, mean, min(1.0, chance), best)


def read(fragment, valuer, combatant=""):
    """The fragment's Reading under `valuer`: `valuer.points(sub, v)`,
    what `v` of `sub` is worth, and `valuer.reference(fragment)`,
    (now, ref, extra): before, what after has to beat, and the
    constant the substats' points sit on."""
    now, ref, extra = valuer.reference(fragment)
    starts = [valuer.points(sub, sub.base_value) for sub in fragment.substats]
    grids = [[valuer.points(sub, v) for v in roll_values(sub)]
             for sub in fragment.substats]
    start = extra + sum(starts)
    plain = _option(grids, start, ref, None, PLAIN_COST)
    exclude = None
    for i, sub in enumerate(fragment.substats):
        rest = grids[:i] + grids[i + 1:]
        option = _option(rest, start, ref, sub.name, EXCLUDE_COST)
        if exclude is None or option.mean > exclude.mean:
            exclude = option
    return Reading(fragment, combatant, now, plain, exclude)


# --------------------------------------------------------------- valuers


class GearValuer:
    """The Gear Score under `weights`, in GS points: what
    `MemoryFragment.calculate_base_score` reads, unclamped."""

    def __init__(self, weights):
        self.weights = weights or {}
        self._bounds = {}

    def _scale(self, fragment):
        main = fragment.main_stat.name if fragment.main_stat else None
        if main not in self._bounds:
            self._bounds[main] = compute_gs_bounds(self.weights,
                                                   exclude_stat=main)
        low, high = self._bounds[main]
        return low, (100.0 / (high - low) if high > low else 0.0)

    def points(self, sub, value):
        top = max_roll(sub)
        if not top:
            return 0.0
        return self.weights.get(sub.name, 1.0) * value / top * 10

    def reference(self, fragment):
        low, scale = self._scale(fragment)
        now = (_raw_substat_score(fragment, self.weights) - low) * scale
        return now, now, -low * scale

    def bind(self, fragment):
        """`points` scaled to this fragment's bounds."""
        _low, scale = self._scale(fragment)
        return _Scaled(self, scale)


class _Scaled:
    """A GearValuer's points in one fragment's GS points."""

    def __init__(self, valuer, scale):
        self.valuer, self.scale = valuer, scale

    def points(self, sub, value):
        return self.valuer.points(sub, value) * self.scale

    def reference(self, fragment):
        return self.valuer.reference(fragment)


def read_gear(fragment, valuer, combatant=""):
    """`read` under a GearValuer, its points in this fragment's GS."""
    return read(fragment, valuer.bind(fragment), combatant)


class _Piece:
    """A fragment as the score reads one: its set, its main stat and
    its stat totals, with the substats at `values`."""
    __slots__ = ("id", "set_id", "main_stat", "_totals")

    def __init__(self, fragment, values=None):
        self.id = fragment.id
        self.set_id = fragment.set_id
        self.main_stat = fragment.main_stat
        totals = fragment.get_total_stats()
        if values is not None:
            for sub, value in zip(fragment.substats, values, strict=True):
                totals[sub.name] = totals.get(sub.name, 0) - sub.value + value
        self._totals = totals

    def get_total_stats(self):
        return self._totals


class _Bare:
    """Stats with no set and no main stat: one max roll."""
    set_id = None
    main_stat = None

    def __init__(self, stats):
        self._stats = stats

    def get_total_stats(self):
        return dict(self._stats)


def build_inputs(optimizer, name, settings):
    """What a `BuildValuer` reads, resolved here where the optimizer
    and the game client's data are: the combatant's static stats at the
    Optimizer's level, the score's precomputed settings, the Element
    their damage is scored as, and the fragments they wear. Plain data,
    for a worker process."""
    from optimizer import core
    level = optimizer._resolve_effective_level(
        name, settings.get("optimize_for_level"))
    return {"cs": optimizer._build_char_static(name, level),
            "sp": core.build_score_precompute(settings),
            "attribute": optimizer._resolve_attribute(name, settings),
            "worn": list(optimizer.characters.get(name, []))}


class BuildValuer:
    """The combatant's Optimizer score with a fragment in its slot, as
    the per cent it rises over the equipped build. `inputs` is
    `build_inputs`'."""

    def __init__(self, inputs):
        from optimizer import core
        self.core = core
        self.cs, self.sp = inputs["cs"], inputs["sp"]
        self.attribute = inputs["attribute"]
        self.h = self.sp["heal_share"]
        self.worn = {f.slot_num: f for f in inputs["worn"]}
        self.d0, self.s0 = self._components(list(self.worn.values()))
        base = [_Piece(f) for f in self.worn.values()]
        self.worths = {}
        for info in STATS.values():
            if info[3] > 0 and info[0] not in self.worths:
                self.worths[info[0]] = self.rel(
                    base + [_Bare({info[0]: info[3]})])

    def _components(self, gear):
        stats = self.core.compute_build_stats(
            gear, self.cs, set_effect_shares=self.sp["set_effect_shares"])
        return self.core.compute_score_components(gear, stats, self.sp,
                                                  self.attribute)

    def rel(self, gear):
        """The score of `gear` over the equipped build's, less 1."""
        d, s = self._components(gear)
        out = (1 - self.h) * (d / self.d0 - 1) if self.d0 else 0.0
        if self.h and self.s0:
            out += self.h * (s / self.s0 - 1)
        return out

    def swapped(self, fragment, values=None):
        """The equipped build with `fragment` in its slot, its substats
        at `values` (as they stand without)."""
        gear = [_Piece(f) for slot, f in self.worn.items()
                if slot != fragment.slot_num]
        return gear + [_Piece(fragment, values)]

    def points(self, sub, value):
        top = max_roll(sub)
        if not top:
            return 0.0
        return self.worths.get(sub.name, 0.0) * value / top * 100

    def reference(self, fragment):
        """Before is the build with the fragment as it stands; after
        has to beat that or the build as worn, whichever is better.
        The substats' points sit on the build with every substat at
        its starting value."""
        now = self.rel(self.swapped(fragment)) * 100
        bare = self.rel(self.swapped(
            fragment, [sub.base_value for sub in fragment.substats])) * 100
        start = sum(self.points(sub, sub.base_value)
                    for sub in fragment.substats)
        return now, max(0.0, now), bare - start


def _deal(fragment, eligible, rng):
    """One readjustment's substat values: `UPGRADES` upgrades over the
    substats at `eligible` (indices), each a fresh roll."""
    values = [sub.base_value for sub in fragment.substats]
    grids = [roll_values(sub) for sub in fragment.substats]
    for _ in range(UPGRADES):
        i = rng.choice(eligible)
        values[i] += rng.choice(grids[i])
    return values


def _sampled(valuer, fragment, eligible, ref, excluded, cost, samples, rng):
    """An Option by sampling the build's real score."""
    mean = chance = 0.0
    for _ in range(samples):
        after = valuer.rel(valuer.swapped(
            fragment, _deal(fragment, eligible, rng))) * 100
        if after > ref + 1e-9:
            mean += after - ref
            chance += 1
    # The most it can: every upgrade a top roll on one substat.
    best = 0.0
    for i in eligible:
        values = [sub.base_value for sub in fragment.substats]
        values[i] += UPGRADES * max(roll_values(fragment.substats[i]))
        best = max(best, valuer.rel(valuer.swapped(fragment, values)) * 100
                   - ref)
    return Option(excluded, cost, mean / samples, chance / samples, best)


def refine(reading, valuer, samples=REFINE_SAMPLES):
    """`reading` with its options sampled off the real score: every
    exclusion's, keeping the best."""
    fragment = reading.fragment
    rng = random.Random(fragment.id)
    ref = max(0.0, reading.now)
    every = list(range(len(fragment.substats)))
    plain = _sampled(valuer, fragment, every, ref, None, PLAIN_COST,
                     samples, rng)
    exclude = None
    for i, sub in enumerate(fragment.substats):
        option = _sampled(valuer, fragment, every[:i] + every[i + 1:], ref,
                          sub.name, EXCLUDE_COST, samples, rng)
        if exclude is None or option.mean > exclude.mean:
            exclude = option
    return Reading(fragment, reading.combatant, reading.now, plain, exclude,
                   sampled=True, weight=reading.weight)


# ------------------------------------------------------------- the jobs


def stats_snapshot():
    """`STATS` as this process holds it, the game client's rolls laid
    over the shipped ones: what a job carries to its worker."""
    return dict(STATS)


def _use_stats(snapshot):
    """Hold this process's `STATS` to `snapshot`, in place: every module
    holding the table holds this one dict."""
    if snapshot is not None and snapshot != STATS:
        STATS.clear()
        STATS.update(snapshot)


def work(job):
    """One job: {fragment id: (now, plain, exclude, sampled)} for the
    fragments in `job["fragments"]`, read for one combatant under
    `job["measure"]` -- `job["weights"]` for the Gear Score,
    `job["build"]` (`build_inputs`) for the build score, whose
    `job["refine"]` samples the real score. Module-level, so a worker
    process can be handed it."""
    _use_stats(job.get("stats"))
    if job["measure"] == GEAR:
        valuer = GearValuer(job["weights"])
    else:
        valuer = BuildValuer(job["build"])
    out = {}
    for fragment in job["fragments"]:
        if job["measure"] == GEAR:
            reading = read_gear(fragment, valuer)
        else:
            reading = read(fragment, valuer)
            if job.get("refine"):
                reading = refine(reading, valuer)
        out[fragment.id] = (reading.now, reading.plain, reading.exclude,
                            reading.sampled)
    return out


_pool = None


def submit(job):
    """Run `work(job)` in a worker process: a Future. The workers are
    started the first time and kept, since starting one costs about a
    second; up to four, a core left for the window and the game."""
    global _pool
    if _pool is None:
        from concurrent.futures import ProcessPoolExecutor
        _pool = ProcessPoolExecutor(
            max_workers=max(1, min(4, (os.cpu_count() or 2) - 1)))
    return _pool.submit(work, job)


@atexit.register
def _shutdown():
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
