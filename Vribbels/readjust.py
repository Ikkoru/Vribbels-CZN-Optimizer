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
- `BuildValuer`: the Optimizer's score against the combatant's Top
  build, the one the Optimizer tab would find, in per cent. Each
  fragment is read in the best build the Optimizer can make around it
  (`read_build`), its readjustments sampled off the real score: a
  fragment no readjustment lifts past the Top build gains nothing.

**The work runs in worker processes** (`submit`), a job a chunk of
fragments: Python arithmetic on a thread holds the interpreter lock
in turns with Tk's event loop, which then answers the window only
between them. A worker imports `game_data` fresh, without the game
client's rolls laid over it, so each job carries `STATS` along
(`stats_snapshot`), and a build-score job the Optimizer itself
(`lean_optimizer`) with the combatant's run settings. No Tk on this
module's import path.
"""

import atexit
import copy
import json
import math
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
# How many readjustments the build score samples per option: the error
# of a mean gain is about its spread over the square root of this.
BUILD_SAMPLES = 1000
# The outcome the second build around a fragment is found for: the one
# a plain readjustment beats this share of the time (`read_build`).
HIGH_SHARE = 0.10
# The build score reads only the fragments whose Gear Score at their
# best could reach this top share of their slot's candidates
# (`gear_cut`): one that cannot is never part of a top build.
CUT_SHARE = 1 / 3

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
    the chance of any gain at all, the most it can -- and `avg`, the
    average after, in the units of before, whether or not it is kept."""
    excluded: str | None
    cost: int
    mean: float
    chance: float
    best: float
    avg: float = 0.0

    @property
    def per_quartz(self):
        return self.mean / self.cost


@dataclass
class Reading:
    """A fragment readjusted for one combatant: its before (`now`, in
    the measure's units), the plain readjustment and the best
    exclusion."""
    fragment: object
    combatant: str
    now: float
    plain: Option
    exclude: Option
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
    mean = chance = avg = 0.0
    for i, p in enumerate(chances):
        after = start + (first + i) * width
        avg += p * after
        if after > ref + width / 2:
            mean += p * (after - ref)
            chance += p
    best = max(0.0, start + UPGRADES * max(tops) - ref)
    return Option(excluded, cost, mean, min(1.0, chance), best, avg)


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


def at_values(fragment, values):
    """A copy of `fragment` with its substats at `values`: what the
    Optimizer is handed to build around a readjustment's outcome. Same
    id, so `optimize(pinned=...)` holds it to the original's filters."""
    out = copy.deepcopy(fragment)
    for sub, value in zip(out.substats, values, strict=True):
        sub.value = value
    return out


class _OneProcess:
    """The settings a GearOptimizer reads inside a worker: enumerate in
    this process, never a pool of its own (`_resolve_worker_count`)."""

    @staticmethod
    def get(key, default=None):
        return 1 if key == "optimizer_workers" else default


def lean_optimizer(optimizer):
    """A copy of `optimizer` to hand a worker: without the capture's raw
    data, which the Optimizer never reads once loaded and which is most
    of what it would pickle, and set to enumerate in one process."""
    lean = copy.copy(optimizer)
    lean.raw_data = {}
    lean.settings_manager = _OneProcess()
    return lean


def build_signature(optimizer, name, settings):
    """What `name`'s build-score answers depend on beyond a fragment's
    own rolls, as one string: the run settings, the combatant's stats
    at the Optimizer's level, the fragments a run searches -- each
    slot's candidates after the Top % trim, picked as `optimize` picks
    them -- and whose each readjustable fragment is, which decides
    whether the run's filters let it be pinned. A pinned fragment
    stands in for its slot's candidates, so these are everything a
    build around it is made of: a capture that changes none of them
    changes no answer, whichever capture it is, and a new fragment the
    trim leaves out changes nothing."""
    pool = []
    for slot, filters in optimizer.slot_filters(name, settings).items():
        for f in optimizer.get_gear_by_slot(
                slot, top_percent=settings.get("top_percent", 100),
                use_priority_score=False,
                score_weights=settings.get("slot_filter_weights") or None,
                **filters):
            pool.append(content(f))
    owners = sorted((f.id, f.equipped_to or "")
                    for f in optimizer.fragments if readjustable(f))
    level = optimizer._resolve_effective_level(
        name, settings.get("optimize_for_level"))
    return json.dumps({"settings": settings,
                       "cs": optimizer._build_char_static(name, level),
                       "pool": sorted(pool, key=repr), "owners": owners},
                      sort_keys=True, default=repr)


def top_gs(fragment, valuer):
    """`fragment`'s Gear Score at its best readjustment, under the
    GearValuer `valuer`: its starting values and every upgrade a top
    roll on its best substat."""
    scaled = valuer.bind(fragment)
    _now, _ref, extra = scaled.reference(fragment)
    start = extra + sum(scaled.points(s, s.base_value)
                        for s in fragment.substats)
    return start + UPGRADES * max(scaled.points(s, max_roll(s))
                                  for s in fragment.substats)


def gear_cut(optimizer, name, settings):
    """The readjustable fragments the build score leaves unread, as ids:
    those the run's filters refuse, which no build can wear, and those
    whose Gear Score at their best (`top_gs`) falls short of the top
    `CUT_SHARE` of their slot's candidates as they stand, under the
    combatant's preset (`slot_filter_weights`; every weight 1 without
    one). A fragment that cannot reach the top third even at its best is
    not worth a rare Quartz, and its Optimizer runs are saved."""
    valuer = GearValuer(settings.get("slot_filter_weights") or {})
    cut = []
    for slot, filters in optimizer.slot_filters(name, settings).items():
        pool = optimizer.get_gear_by_slot(slot, top_percent=100, **filters)
        allowed = {f.id for f in pool}
        scores = sorted((valuer.bind(f).reference(f)[0] for f in pool),
                        reverse=True)
        bar = scores[max(1, math.ceil(len(scores) * CUT_SHARE)) - 1] \
            if scores else 0.0
        for f in optimizer.fragments:
            if f.slot_num == slot and readjustable(f) \
                    and (f.id not in allowed or top_gs(f, valuer) < bar):
                cut.append(f.id)
    return cut


def top_build(optimizer, name, settings, pinned=None):
    """The Optimizer's best build for `name` under `settings`, wearing
    `pinned` where given: its fragments, or None where the run finds no
    build (the filters refuse `pinned`, or nothing meets the set rule or
    Have at least)."""
    results = optimizer.optimize(name, settings, pinned=pinned)
    return list(results[0][0]) if results else None


class BuildValuer:
    """The combatant's Optimizer score of a build, as the per cent it
    rises over a reference build, the Top build (`top_build`). Blended
    as the preset derivation blends it: damage, and shielding/healing by
    the combatant's weight."""

    def __init__(self, optimizer, name, settings, reference):
        from optimizer import core
        self.core = core
        level = optimizer._resolve_effective_level(
            name, settings.get("optimize_for_level"))
        self.cs = optimizer._build_char_static(name, level)
        self.sp = core.build_score_precompute(settings)
        self.attribute = optimizer._resolve_attribute(name, settings)
        self.h = self.sp["heal_share"]
        self.d0, self.s0 = self._components(reference)

    def _components(self, gear):
        stats = self.core.compute_build_stats(
            gear, self.cs, set_effect_shares=self.sp["set_effect_shares"])
        return self.core.compute_score_components(gear, stats, self.sp,
                                                  self.attribute)

    def rel(self, gear):
        """The score of `gear` over the reference build's, less 1."""
        d, s = self._components(gear)
        out = (1 - self.h) * (d / self.d0 - 1) if self.d0 else 0.0
        if self.h and self.s0:
            out += self.h * (s / self.s0 - 1)
        return out

    @staticmethod
    def around(build, fragment, values=None):
        """`build` with `fragment` in its slot, its substats at `values`
        (as they stand without)."""
        gear = [_Piece(f) for f in build if f.slot_num != fragment.slot_num]
        return gear + [_Piece(fragment, values)]


def _deal(fragment, eligible, rng):
    """One readjustment's substat values: `UPGRADES` upgrades over the
    substats at `eligible` (indices), each a fresh roll."""
    values = [sub.base_value for sub in fragment.substats]
    grids = [roll_values(sub) for sub in fragment.substats]
    for _ in range(UPGRADES):
        i = rng.choice(eligible)
        values[i] += rng.choice(grids[i])
    return values


def sampled(score, fragment, eligible, ref, excluded, cost, samples, rng):
    """An Option by sampling: `score(values)` what after is worth with
    the substats at `values`, `samples` readjustments dealt over the
    substats at `eligible`, against `ref`."""
    mean = chance = avg = 0.0
    for _ in range(samples):
        after = score(_deal(fragment, eligible, rng))
        avg += after
        if after > ref + 1e-9:
            mean += after - ref
            chance += 1
    # The most it can: every upgrade a top roll on one substat.
    best = 0.0
    for i in eligible:
        values = [sub.base_value for sub in fragment.substats]
        values[i] += UPGRADES * max(roll_values(fragment.substats[i]))
        best = max(best, score(values) - ref)
    return Option(excluded, cost, mean / samples, chance / samples, best,
                  avg / samples)


def options(score, fragment, ref, samples, rng):
    """(plain, the best exclusion) by `sampled`, every exclusion tried."""
    every = list(range(len(fragment.substats)))
    plain = sampled(score, fragment, every, ref, None, PLAIN_COST,
                    samples, rng)
    exclude = None
    for i, sub in enumerate(fragment.substats):
        option = sampled(score, fragment, every[:i] + every[i + 1:], ref,
                         sub.name, EXCLUDE_COST, samples, rng)
        if exclude is None or option.mean > exclude.mean:
            exclude = option
    return plain, exclude


def read_build(optimizer, name, settings, valuer, fragment,
               samples=BUILD_SAMPLES):
    """(now, plain, exclude) for `fragment` under the build score, in
    per cent of the Top build `valuer` reads against; None where no
    build can wear it.

    The build around it is the Optimizer's best with it pinned
    (`top_build`), and again with it pinned at the outcome a plain
    readjustment beats only `HIGH_SHARE` of the time: a much better roll
    can make other fragments the better company, and an outcome is
    scored in whichever of the two builds does more with it. Before is
    the fragment as it stands in its own build, and what after has to
    beat is that or the Top build, whichever is higher."""
    base = top_build(optimizer, name, settings, pinned=fragment)
    if base is None:
        return None
    builds = [base]
    rng = random.Random(fragment.id)
    every = list(range(len(fragment.substats)))
    deals = sorted((_deal(fragment, every, rng) for _ in range(samples)),
                   key=lambda v: valuer.rel(valuer.around(base, fragment, v)))
    high = deals[min(len(deals) - 1, int(len(deals) * (1 - HIGH_SHARE)))]
    anchored = top_build(optimizer, name, settings,
                         pinned=at_values(fragment, high))
    if anchored is not None and sorted(f.id for f in anchored) \
            != sorted(f.id for f in base):
        builds.append(anchored)

    def score(values):
        return max(valuer.rel(valuer.around(b, fragment, values))
                   for b in builds) * 100

    now = score(None)
    plain, exclude = options(score, fragment, max(0.0, now), samples, rng)
    return now, plain, exclude


# ------------------------------------------------------------ a deal


def dealt(fragment, stat_list):
    """`fragment` as a readjustment's Before or After: the stat list the
    game deals (`piece_readjust_info`'s `before_stat_list` or
    `after_stat_list`) on the fragment's own id, set, slot, level and
    owner."""
    from models.memory_fragment import MemoryFragment
    res_id = int("11%d%d%03d" % (fragment.slot_num, fragment.rarity_num,
                                 fragment.set_id))
    return MemoryFragment.from_json({
        "id": fragment.id, "res_id": res_id, "level": fragment.level,
        "lock": fragment.locked,
        "char_res_id": getattr(fragment, "equipped_char_id", 0) or 0,
        "stat_list": stat_list})


def read_deal(optimizer, name, settings, before, after, top=None):
    """What keeping `after` rather than `before` does for `name`, in
    per cent of their Top build, or None where no build can wear either:

    - "change": their best build's score with After less with Before --
      the best build with the fragment pinned, or the best without it,
      whichever is higher; 0 where the fragment is in neither.
    - "before", "after": the best build with that version pinned, over
      the Top build -- how close the fragment is to being worth wearing.
    - "in_top": which versions are in their best build ("Before",
      "After", "Both" or "").

    `top` is the Top build's fragment ids where already known."""
    if top is None:
        found = top_build(optimizer, name, settings)
        if found is None:
            return None
    else:
        by_id = {f.id: f for f in optimizer.fragments}
        found = [by_id[i] for i in top if i in by_id]
    valuer = BuildValuer(optimizer, name, settings, found)
    if any(f.id == before.id for f in found):
        others = copy.copy(optimizer)
        others.fragments = [f for f in optimizer.fragments
                            if f.id != before.id]
        alone = top_build(others, name, settings)
        without = valuer.rel(alone) * 100 if alone else None
    else:
        without = 0.0
    pinned = {}
    for key, version in (("before", before), ("after", after)):
        build = top_build(optimizer, name, settings, pinned=version)
        pinned[key] = valuer.rel(build) * 100 if build else None
    if pinned["before"] is None and pinned["after"] is None:
        return None
    floor = without if without is not None else float("-inf")
    best = {k: max(floor, v if v is not None else float("-inf"))
            for k, v in pinned.items()}
    wears = [k.capitalize() for k, v in pinned.items()
             if v is not None and v >= floor - 1e-9]
    change = best["after"] - best["before"] \
        if best["after"] > float("-inf") and best["before"] > float("-inf") \
        else 0.0
    return {"change": change, "before": pinned["before"],
            "after": pinned["after"],
            "in_top": "Both" if len(wears) == 2 else "".join(wears)}


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
    """One job, module-level so a worker process can be handed it.

    - Gear Score: {fragment id: (now, plain, exclude)} for
      `job["fragments"]`, under `job["weights"]`.
    - Build score, `job["kind"]` "top": {None: {"top": the Top build's
      fragment ids, "cut": `gear_cut`'s}, or None where the Optimizer
      finds no build}.
    - Build score, "deal": {None: `read_deal`'s} for `job["before"]`
      and `job["after"]`, a readjustment's two versions.
    - Build score, "read": {fragment id: (now, plain, exclude), or None
      where no build can wear it}, against the Top build
      `job["top"]` (ids). `job["optimizer"]` is `lean_optimizer`'s,
      `job["settings"]` the combatant's run settings.
    """
    _use_stats(job.get("stats"))
    if job["measure"] == GEAR:
        valuer = GearValuer(job["weights"])
        out = {}
        for fragment in job["fragments"]:
            reading = read_gear(fragment, valuer)
            out[fragment.id] = (reading.now, reading.plain, reading.exclude)
        return out
    optimizer, name = job["optimizer"], job["name"]
    settings = job["settings"]
    if job["kind"] == "deal":
        return {None: read_deal(optimizer, name, settings, job["before"],
                                job["after"], job.get("top"))}
    if job["kind"] == "top":
        top = top_build(optimizer, name, settings)
        if top is None:
            return {None: None}
        return {None: {"top": [f.id for f in top],
                       "cut": gear_cut(optimizer, name, settings)}}
    by_id = {f.id: f for f in optimizer.fragments}
    top = [by_id[i] for i in job["top"]]
    valuer = BuildValuer(optimizer, name, settings, top)
    return {f.id: read_build(optimizer, name, settings, valuer,
                             by_id.get(f.id, f))
            for f in job["fragments"]}


# The two speeds the work runs at, each a pool of its own.
BACKGROUND = "background"
FULL = "full"
# Windows' priority class for the background worker: it is given only
# the time nothing else wants, the game and the window included.
IDLE_PRIORITY_CLASS = 0x40

_pools = {}


def _idle():
    """A background worker's initializer: run at the lowest priority."""
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(),
                                IDLE_PRIORITY_CLASS)
    except (AttributeError, OSError):
        try:
            os.nice(19)
        except (AttributeError, OSError):
            pass


def workers(speed):
    """How many processes `speed` runs: one in the background, every
    core but one at full speed."""
    return 1 if speed == BACKGROUND else max(1, (os.cpu_count() or 2) - 1)


def submit(job, speed=FULL):
    """Run `work(job)` in a worker process of `speed`'s pool: a Future.
    The workers are started the first time and kept, since starting one
    costs about a second."""
    if speed not in _pools:
        from concurrent.futures import ProcessPoolExecutor
        _pools[speed] = ProcessPoolExecutor(
            max_workers=workers(speed),
            initializer=_idle if speed == BACKGROUND else None)
    return _pools[speed].submit(work, job)


@atexit.register
def _shutdown():
    for speed in list(_pools):
        _pools.pop(speed).shutdown(wait=False, cancel_futures=True)
