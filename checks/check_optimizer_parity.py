"""Parallel results must be byte-identical to sequential ones.

The headline engineering invariant. The parallel path partitions the
search, scores in worker processes, and merges; the sequential path does
it in one. They must agree on the results, their order, and the run
counters -- not merely on the best build.

**By default the run is a synthetic inventory**, `_parity_fixture`:
seeded, so it searches the same combos every run, built from nothing
captured, so it runs on a fresh clone, and shaped to reach what parity
breaks on -- the parallel path, the in-flight trim, exact ties, every
set type, element mains, Potential 7's steps and Have at Least. Each of
those is checked against the run (`PROPERTIES`): a fixture that drifts
out of reaching one is a check that passes for the wrong reason.

**`--full` runs the newest snapshot instead**, each combatant on its
real settings, unbounded. The expensive half is the SEQUENTIAL one --
which is the whole reason the parallel path exists -- so on a full
inventory it takes hours. It is for behaviour that only appears at
large partition counts, which the fixture cannot reach.
"""

import tempfile
import time
from pathlib import Path

from . import _parity_fixture as fixture
from ._harness import (add_source_to_path, newest_snapshot, describe, Skip,
                       SOURCE_ROOT)
import itertools

NAME = "optimizer parallel/sequential parity"

COMBATANTS = 3
WORKERS = 4

# What the fixture run has to reach for its agreement to mean anything,
# each as (what, why it matters).
PROPERTIES = (
    ("parallel", "the parallel path has to run, not fall back to the "
                 "sequential one -- which would compare a path with "
                 "itself"),
    ("trim", "more builds have to survive than twice the trim's pool, "
             "so both paths cut their survivor lists in flight"),
    ("ties", "the results have to hold builds of exactly equal score, "
             "ordered by the tie-break alone"),
    ("potential_7", "the results have to straddle a Potential 7 step, so "
                    "its grant is in some scores and not others"),
    ("have_at_least", "Have at Least has to turn builds away, so its "
                      "counter and the set rule's differ"),
    ("sets", "every set type has to be on offer: a 4-piece and a 2-piece "
             "conditional set and a 2-piece unconditional one"),
    ("elements", "Slot V has to offer the combatant's element, another "
                 "element and ATK%"),
    ("shield", "the shield/heal term has to vary across the results, so "
               "the Shielding/Healing run's two blends rank apart"),
)


def _key(entry):
    gear, score, _stats = entry
    return (tuple(getattr(p, "id", None) for p in gear), round(score, 10))


def _optimize(snap, name, settings, workers):
    """One run of `name` on `snap` with `workers` workers: (results,
    the run's counters, whether the parallel path returned)."""
    from optimizer import parallel
    from optimizer.optimizer import GearOptimizer
    o = GearOptimizer()
    o.load_data(snap)
    o._resolve_worker_count = lambda: workers
    real, ran = parallel.optimize_parallel, []

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        ran.append(True)
        return out

    parallel.optimize_parallel = spy
    try:
        results = o.optimize(name, dict(settings))
    finally:
        parallel.optimize_parallel = real
    return results, dict(o.last_optimize_stats or {}), bool(ran)


def _compare(name, par, seq, stats_par, stats_seq):
    """Where the two paths' runs disagree, as complaints."""
    failures = []
    if [_key(e) for e in par] != [_key(e) for e in seq]:
        where = next(
            (i for i, (a, b) in enumerate(zip(par, seq))
             if _key(a) != _key(b)),
            min(len(par), len(seq)),
        )
        failures.append(
            f"{name}: parallel and sequential disagree at row {where} "
            f"({len(par)} vs {len(seq)} results). The deterministic "
            f"tie-break or the merge has drifted."
        )
    # The substat tiebreaker's whole guarantee is that it is
    # BOUNDED: `_T` in [0, 1] means the term can move a score by at
    # most `SUBSTAT_TIEBREAK`, so a build ahead on the blend by more
    # than that stays ahead. A ceiling read off the wrong thing --
    # one fragment's total rather than six, a list that lost its
    # widest candidate -- lifts `_T` past 1 and the term starts
    # buying places, which no ordering here would look wrong for.
    loose = [st.get("_T") for _g, _s, st in par
             if not 0.0 <= (st.get("_T") or 0.0) <= 1.0]
    if loose:
        failures.append(
            f"{name}: {len(loose)} result(s) carry a substat term "
            f"outside [0, 1] (e.g. {loose[0]}). The term is bounded "
            f"by its per-run ceiling and `core.SUBSTAT_TIEBREAK` "
            f"bounds what it is worth -- past 1 it can overtake a "
            f"build that is genuinely better. See "
            f"core.build_substat_totals."
        )
    for counter in ("total_combinations", "passed_set_reqs",
                    "passed_have_at_least", "reranked"):
        if stats_par.get(counter) != stats_seq.get(counter):
            failures.append(
                f"{name}: counter {counter} differs -- "
                f"parallel={stats_par.get(counter)} "
                f"sequential={stats_seq.get(counter)}"
            )
    return failures


def _reached(items, results, stats, ran):
    """{property: whether the fixture run reached it}."""
    from game_data import CHARACTERS, SETS
    from optimizer import core, parallel
    scores = [round(score, 10) for _g, score, _st in results]
    steps = {(st.get("_p7") or {}).get("Extra DMG%", 0)
             for _g, _s, st in results}
    offered = {int(str(i["res_id"])[4:]) for i in items}
    types = {(SETS[s].get("type"), SETS[s].get("pieces"))
             for s in offered if s in fixture.SETTINGS["sets_selected"]}
    element = CHARACTERS[fixture.COMBATANT]["attribute"]
    names = {"S_RED_DMG_RATE_INC_ADD": "Passion",
             "S_BLUE_DMG_RATE_INC_ADD": "Justice",
             "S_ATK_INC_RATE_OUT": "ATK%"}
    slot_5 = {names.get(s["stat"]) for i in items
              if str(i["res_id"])[2] == "5"
              for s in i["stat_list"] if s["slot"] == 0}
    survived = stats.get("passed_have_at_least", 0)
    return {
        "parallel": ran and stats.get("total_combinations", 0)
        >= parallel.PARALLEL_MIN_COMBOS,
        "trim": survived > 2 * core.pool_size(
            fixture.SETTINGS["max_results"]),
        "ties": any(a == b for a, b in itertools.pairwise(scores)),
        "potential_7": len(steps) > 1,
        "have_at_least": stats.get("passed_set_reqs", 0) > survived > 0,
        "sets": types >= {("conditional", 4), ("conditional", 2),
                          ("unconditional", 2)},
        "elements": {element, "Justice", "ATK%"} <= slot_5,
        "shield": len({round(st.get("_S", 0.0), 9)
                       for _g, _s, st in results}) > 1,
    }


def _fixture_run():
    """Parity on the synthetic inventory, and every property it must
    reach."""
    snap = Path(tempfile.mkdtemp(prefix="parity_")) / "fixture.json"
    fixture.write(snap)
    items = fixture.build()["inventory"]["piece_items"]
    name = fixture.COMBATANT_NAME
    failures = []
    reached = {}
    for label, settings in (("fixture", fixture.SETTINGS),
                            ("fixture, shielding", fixture.SHIELD_SETTINGS)):
        par, stats_par, ran = _optimize(snap, name, settings, WORKERS)
        seq, stats_seq, _ran = _optimize(snap, name, settings, 1)
        failures += _compare(f"{name} ({label})", par, seq, stats_par,
                             stats_seq)
        for what, got in _reached(items, par, stats_par, ran).items():
            reached[what] = reached.get(what, False) or got
    for what, why in PROPERTIES:
        if not reached[what]:
            counters = {k: stats_par.get(k) for k in (
                "total_combinations", "passed_set_reqs",
                "passed_have_at_least")}
            failures.append(
                f"the parity fixture no longer reaches '{what}': {why}. "
                f"Until checks/_parity_fixture.py is reshaped, parity says "
                f"nothing about that case (run counters: {counters}).")
    return failures


def _full_run():
    """Parity on the newest snapshot, each combatant on its real
    settings, unbounded."""
    snap = newest_snapshot()
    if snap is None:
        raise Skip("no snapshot in Vribbels/snapshots/ -- --full needs "
                   "captured data")
    from optimizer.optimizer import GearOptimizer
    import optimizer_settings_manager as osm
    probe = GearOptimizer()
    probe.load_data(snap)
    settings_mgr = osm.OptimizerSettingsManager(SOURCE_ROOT)
    settings_mgr.load()
    failures, checked = [], 0
    for name in sorted(probe.characters):
        if checked >= COMBATANTS:
            break
        info = probe.character_info.get(name)
        if info is None:
            continue
        settings = dict(settings_mgr.get_character_data(str(info.res_id))
                        or {})
        if not settings:
            continue
        t = time.time()
        par, stats_par, _ran = _optimize(snap, name, settings, WORKERS)
        seq, stats_seq, _ran = _optimize(snap, name, settings, 1)
        if not par and not seq:
            continue
        checked += 1
        failures += _compare(name, par, seq, stats_par, stats_seq)
        print(f"   {name}: {time.time() - t:.0f}s", flush=True)
    if checked == 0:
        raise Skip(
            f"{describe(snap)} has no combatant with saved optimizer settings"
        )
    return failures


def run(full=False):
    add_source_to_path()
    return _full_run() if full else _fixture_run()


def _no_def_on_any_fragment():
    """A fixture whose fragments carry no DEF: the shield/heal term is
    the same for every build, and the Shielding/Healing run ranks by
    damage alone."""
    fixture.MAINS[2] = (("S_HP_INC_ADD_OUT", 36.65),)
    fixture.MAINS[6] = (("S_ATK_INC_RATE_OUT", 25.0),
                        ("S_HP_INC_RATE_OUT", 25.0))
    for stat in ("S_DEF_INC_ADD_OUT", "S_DEF_INC_RATE_OUT"):
        fixture.SUBSTATS.pop(stat)


FAULTS = [
    ("a fixture with no shield/heal term", _no_def_on_any_fragment,
     None, None, "no longer reaches 'shield'"),
]
