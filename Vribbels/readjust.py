"""Substat Readjustment: what readjusting a fully upgraded Legendary
Memory Fragment is worth, per Shuffling Quartz.

**What the game does** (the client's `ui_piece_readjust_desc_*`):
readjustment keeps every substat's type, and with it the value the
substat started at; the fragment's upgrades are dealt out again, each
to one of its substats at random with a fresh roll. One substat may be
excluded first: it takes no upgrade and goes back to its starting
value. A readjustment costs 1 Shuffling Quartz, 2 with an exclusion.
The game then shows Before and After and the player keeps either, so
a readjustment never loses anything: its worth is the expected
`max(0, after - before)`.

A fragment's starting values and its upgrades are told apart in its
`stat_list` (`MemoryFragment.from_json`: `base_value` and
`upgrade_values`); every upgrade lands on one of the substats alike
and on any value of its roll alike (`_roll_grid`'s grid), as the
Potential's model has it.

**Two measures of after**, each per combatant:

- `gear_valuer`: the Gear Score under the combatant's preset, in GS
  points. Linear in the rolls, so the distribution is exact.
- `BuildValuer`: the Optimizer's score of the combatant's equipped
  build with the fragment in its slot, as the per cent it rises by.
  Before is the better of the build as worn and the build with the
  fragment as it stands. The distribution is the linear one, from
  what one max roll of each stat adds to the build (`worths`), and
  `refine` replaces it by sampling the real score for the fragments
  ranked highest.

No Tk: the tab calls this on a worker thread.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

from game_data.constants import MAX_LEVEL, MAX_LEVEL_PER_RARITY, STATS
from models.memory_fragment import (_convolve, compute_gs_bounds,
                                    _raw_substat_score)

QUARTZ = 3210004
PLAIN_COST = 1
EXCLUDE_COST = 2
LEGENDARY = 4
# A distribution's resolution: the bins its whole span is cut into. A
# gain reads to about a 400th of the most four upgrades could add.
BINS = 400
# How many fragments `refine` samples, and how many readjustments
# each: the error of a mean gain is about its spread over the square
# root of the samples.
REFINE_TOP = 20
REFINE_SAMPLES = 800


def upgrades(fragment):
    """How many upgrades a readjustment deals out: the fragment's."""
    return sum(len(sub.upgrade_values) for sub in fragment.substats)


def readjustable(fragment):
    """A Legendary at its top level with four substats, upgraded."""
    top = MAX_LEVEL_PER_RARITY.get(LEGENDARY, MAX_LEVEL)
    return (fragment.rarity_num == LEGENDARY and fragment.level >= top
            and len(fragment.substats) == 4 and upgrades(fragment) > 0)


def roll_values(sub):
    """Every value one upgrade of `sub` can roll, alike: its stat's
    grid, steps of 0.1 for a percentage and 1 for a flat stat."""
    info = STATS.get(sub.raw_name)
    if not info or info[3] <= 0:
        return [0.0]
    _name, _short, is_pct, high, low = info
    step = 0.1 if is_pct else 1.0
    count = max(1, int(round((high - low) / step)) + 1)
    return [round(low + i * step, 4) for i in range(count)]


def max_roll(sub):
    info = STATS.get(sub.raw_name)
    return info[3] if info and info[3] > 0 else 0.0


@dataclass
class Option:
    """One way to readjust: `excluded` the substat left out (None for
    none), what it costs, and what it gains over before -- the mean,
    the chance of any gain at all, the most it can."""
    excluded: Optional[str]
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
            at = int(round(value / width))
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


def _option(grids, count, start, ref, excluded, cost):
    """The Option of dealing `count` upgrades over `grids` (each a list
    of what a roll adds), onto `start`, against `ref`."""
    tops = [max(grid) for grid in grids]
    lows = [min(grid) for grid in grids]
    span = max(count * (max(tops) - min(lows)), 1e-9)
    width = span / BINS
    first, chances = _times(_one_upgrade(grids, width), count)
    mean = chance = 0.0
    for i, p in enumerate(chances):
        after = start + (first + i) * width
        if after > ref + width / 2:
            mean += p * (after - ref)
            chance += p
    best = max(0.0, start + count * max(tops) - ref)
    return Option(excluded, cost, mean, min(1.0, chance), best)


def read(fragment, valuer, combatant=""):
    """The fragment's Reading under `valuer`: `valuer.points(sub, v)`,
    what `v` of `sub` is worth, and `valuer.reference(fragment)`,
    (now, ref, extra): before, what after has to beat, and the
    constant the substats' points sit on."""
    count = upgrades(fragment)
    now, ref, extra = valuer.reference(fragment)
    starts = [valuer.points(sub, sub.base_value) for sub in fragment.substats]
    grids = [[valuer.points(sub, v) for v in roll_values(sub)]
             for sub in fragment.substats]
    start = extra + sum(starts)
    plain = _option(grids, count, start, ref, None, PLAIN_COST)
    exclude = None
    for i, sub in enumerate(fragment.substats):
        rest = grids[:i] + grids[i + 1:]
        option = _option(rest, count, start, ref, sub.name, EXCLUDE_COST)
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
        now =(_raw_substat_score(fragment, self.weights) - low) * scale
        return now, now, -low * scale

    def bind(self, fragment):
        """`points` scaled to this fragment's bounds."""
        low, scale = self._scale(fragment)
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
            for sub, value in zip(fragment.substats, values):
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


class BuildValuer:
    """The combatant's Optimizer score with a fragment in its slot, as
    the per cent it rises over the equipped build.

    `optimizer` a loaded GearOptimizer, `settings` the combatant's
    Optimizer settings (`OptimizerSettingsManager.get_character_data`).
    """

    def __init__(self, optimizer, name, settings):
        from optimizer import core
        self.core = core
        self.name = name
        self.sp = core.build_score_precompute(settings)
        self.h = self.sp["heal_share"]
        self.attribute = optimizer._resolve_attribute(name, settings)
        level = optimizer._resolve_effective_level(
            name, settings.get("optimize_for_level"))
        self.cs = optimizer._build_char_static(name, level)
        self.worn = {f.slot_num: f
                     for f in optimizer.characters.get(name, [])}
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


def _deal(fragment, eligible, count, rng):
    """One readjustment's substat values: `count` upgrades over the
    substats at `eligible` (indices), each a fresh roll."""
    values = [sub.base_value for sub in fragment.substats]
    grids = [roll_values(sub) for sub in fragment.substats]
    for _ in range(count):
        i = rng.choice(eligible)
        values[i] += rng.choice(grids[i])
    return values


def _sampled(valuer, fragment, eligible, ref, excluded, cost, count,
             samples, rng):
    """An Option by sampling the build's real score."""
    mean = chance = 0.0
    for _ in range(samples):
        after = valuer.rel(valuer.swapped(
            fragment, _deal(fragment, eligible, count, rng))) * 100
        if after > ref + 1e-9:
            mean += after - ref
            chance += 1
    # The most it can: every upgrade a top roll on one substat.
    best = 0.0
    for i in eligible:
        values = [sub.base_value for sub in fragment.substats]
        values[i] += count * max(roll_values(fragment.substats[i]))
        best = max(best, valuer.rel(valuer.swapped(fragment, values)) * 100
                   - ref)
    return Option(excluded, cost, mean / samples, chance / samples, best)


def refine(reading, valuer, samples=REFINE_SAMPLES):
    """`reading` with its options sampled off the real score: every
    exclusion's, keeping the best."""
    fragment = reading.fragment
    count = upgrades(fragment)
    rng = random.Random(fragment.id)
    ref = max(0.0, reading.now)
    every = list(range(len(fragment.substats)))
    plain = _sampled(valuer, fragment, every, ref, None, PLAIN_COST, count,
                     samples, rng)
    exclude = None
    for i, sub in enumerate(fragment.substats):
        option = _sampled(valuer, fragment, every[:i] + every[i + 1:], ref,
                          sub.name, EXCLUDE_COST, count, samples, rng)
        if exclude is None or option.mean > exclude.mean:
            exclude = option
    return Reading(fragment, reading.combatant, reading.now, plain, exclude,
                   sampled=True, weight=reading.weight)


# ------------------------------------------------------------- the list


@dataclass
class Request:
    """What the tab asks for. `combatants` {name: weight}; `presets`
    {name: weights} for the Gear Score; `settings` {name: Optimizer
    settings} for the build score; `owner` 'all', 'theirs' (worn by
    the one combatant) or 'unequipped'; `slot` 0 for every slot."""
    measure: str
    combatants: dict
    presets: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    owner: str = "all"
    slot: int = 0


GEAR = "gear"
BUILD = "build"


def candidates(fragments, request):
    out = []
    names = list(request.combatants)
    for fragment in fragments:
        if not readjustable(fragment):
            continue
        if request.slot and fragment.slot_num != request.slot:
            continue
        if request.owner == "unequipped" and fragment.equipped_to:
            continue
        if request.owner == "theirs" and fragment.equipped_to not in names:
            continue
        out.append(fragment)
    return out


def rank(optimizer, request, cancelled=lambda: False):
    """[Reading], best first: each readjustable fragment read for the
    combatant whose weighted gain per Quartz is highest, the build
    measure's top `REFINE_TOP` sampled. None when `cancelled()` turns
    true on the way."""
    fragments = candidates(optimizer.fragments, request)
    valuers = {}
    for name, weight in request.combatants.items():
        if weight <= 0:
            continue
        if request.measure == GEAR:
            weights = request.presets.get(name)
            if weights is not None:
                valuers[name] = GearValuer(weights)
        else:
            settings = request.settings.get(name)
            if settings is not None:
                valuers[name] = BuildValuer(optimizer, name, settings)
    out = []
    for fragment in fragments:
        if cancelled():
            return None
        best = None
        for name, valuer in valuers.items():
            if request.measure == GEAR:
                reading = read_gear(fragment, valuer, name)
            else:
                reading = read(fragment, valuer, name)
            reading.weight = request.combatants[name]
            if best is None or reading.value > best.value:
                best = reading
        if best is not None:
            out.append(best)
    out.sort(key=lambda r: (-r.value, r.fragment.id))
    if request.measure == BUILD:
        for i, reading in enumerate(out[:REFINE_TOP]):
            if cancelled():
                return None
            out[i] = refine(reading, valuers[reading.combatant])
        out.sort(key=lambda r: (-r.value, r.fragment.id))
    return out
