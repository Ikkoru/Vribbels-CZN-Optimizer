"""The Results list is the true best `max_results`, at every
Shielding/Healing weight.

The list ranks builds by the DISPLAY blend, whose references are the
largest D and S of every build the run scored; the in-flight trim ranks
by the TRIM blend, whose references are fixed before the run. Between
weight 0 and 100 the two blends differ, so a build the display would
rank in the list can be one the trim threw away -- and nothing says so:
the list looks like a list. A captured run once had 15 of the true best
100 missing and the wrong top row, at weight 70.

Held here by brute force on the parity fixture: every combo scored
through `core.evaluate_combo`, ranked by `core.display_blend` against
the true maxima with `result_sort_key`'s tie-break, and `optimize()`'s
list held to that id for id, at several weights, on both paths.

It also holds the certificate to its job: on the fixture the pool's
headroom suffices, so no run should need its second enumeration. One
that does costs the player the run's time twice over.
"""

import itertools
import tempfile
from pathlib import Path

from . import _parity_fixture as fixture
from ._harness import add_source_to_path

NAME = "optimizer results are the true best"

WEIGHTS = (0, 30, 50, 70, 100)
WORKERS = 4


def _truth(optimizer, settings):
    """{weight: [id tuples]}: the true best `max_results` at each
    weight, by brute force over the run's own candidates and context."""
    from game_data import SLOT_ORDER
    from optimizer import core
    seen = {}
    real = optimizer._enumerate

    def spy(slot_candidates, ctx, *a, **k):
        seen.setdefault("slots", slot_candidates)
        seen.setdefault("ctx", ctx)
        return real(slot_candidates, ctx, *a, **k)

    optimizer._enumerate = spy
    optimizer._resolve_worker_count = lambda: 1
    try:
        optimizer.optimize(fixture.COMBATANT_NAME, dict(settings))
    finally:
        optimizer._enumerate = real
    slots, ctx = seen["slots"], seen["ctx"]
    rows = []
    for combo in itertools.product(*[slots[n] for n in SLOT_ORDER]):
        status, _score, stats = core.evaluate_combo(combo, ctx)
        if status == core.COMBO_OK:
            rows.append((stats["_D"], stats["_S"], stats["_T"],
                         tuple(p.id for p in combo)))
    d_ref = max(r[0] for r in rows)
    s_ref = max(r[1] for r in rows)
    d_ref, s_ref = max(d_ref, 1e-9), max(s_ref, 1e-9)
    truth = {}
    for weight in WEIGHTS:
        sp = dict(ctx["score_pre"], heal_share=weight / 100.0)
        ranked = sorted(
            (-core.display_blend(d, s, sp, d_ref, s_ref, t), ids)
            for d, s, t, ids in rows)
        truth[weight] = [ids for _score, ids in
                         ranked[:settings["max_results"]]]
    spread = (min(r[1] for r in rows), s_ref)
    return truth, spread


def run():
    add_source_to_path()
    from optimizer.optimizer import GearOptimizer
    snap = str(fixture.write(
        Path(tempfile.mkdtemp(prefix="exact_")) / "fixture.json"))
    o = GearOptimizer()
    o.load_data(snap)
    settings = dict(fixture.SETTINGS)
    truth, (s_low, s_high) = _truth(o, settings)
    failures = []
    if not s_low < s_high:
        failures.append(
            f"every build on the fixture has the same shield/heal term "
            f"({s_high}), so a Shielding/Healing weight changes no ranking "
            f"and this check proves nothing. The fixture's combatant needs "
            f"DEF that varies across builds.")
    for workers, path in ((1, "sequential"), (WORKERS, "parallel")):
        o._resolve_worker_count = lambda w=workers: w
        for weight in WEIGHTS:
            run_settings = dict(settings, shielding_healing_weight=weight)
            shown = [tuple(p.id for p in gear) for gear, _sc, _st in
                     o.optimize(fixture.COMBATANT_NAME, run_settings)]
            want = truth[weight]
            if shown != want:
                absent = [i for i, ids in enumerate(want)
                          if ids not in set(shown)]
                first = next((i for i, (a, b) in enumerate(zip(want, shown))
                              if a != b), min(len(want), len(shown)))
                failures.append(
                    f"at Shielding/Healing weight {weight}, the {path} "
                    f"Results list is not the true best "
                    f"{settings['max_results']}: {len(absent)} of them "
                    f"absent, first row that differs {first + 1}. The trim "
                    f"threw away builds the display ranks in the list -- "
                    f"see core.trimmed_bound and the certificate in "
                    f"optimize().")
            if o.last_optimize_stats.get("reranked"):
                failures.append(
                    f"at weight {weight} the {path} run had to enumerate "
                    f"twice: the certificate could not show its pool held "
                    f"the list. Its results are still right, but every run "
                    f"like it takes twice as long -- the trim references "
                    f"(core.build_trim_refs) or HEADROOM have drifted.")
    return failures


def _no_certificate_short_pool():
    """A list taken on trust from a pool no larger than the list. The
    certificate is what makes a short pool safe: without it, a build the
    display ranks in the list but the trim ranked out is simply lost.
    Sequential only: a worker process reads `HEADROOM` afresh."""
    from optimizer import core
    core.HEADROOM = 1
    core.trimmed_bound = lambda *a: float("-inf")


def _greedy_refs_without_certificate():
    """The trim before this check existed: references read off the one
    greedy build, and a list taken on trust. Over a pool of 3x, which
    the fixture's own refs would have filled correctly."""
    from game_data import SLOT_ORDER
    from optimizer import core
    core.HEADROOM = 3

    def greedy(slot_candidates, ctx):
        build = [slot_candidates[s][0] for s in SLOT_ORDER]
        stats = core.compute_build_stats(
            build, ctx["char_static"],
            set_effect_shares=ctx["set_effect_shares"])
        d, s = core.compute_score_components(
            build, stats, ctx["score_pre"], ctx["attribute"])
        return {"D": max(d, 1e-9), "S": max(s, 1e-9)}

    core.build_trim_refs = greedy
    core.trimmed_bound = lambda *a: float("-inf")


FAULTS = [
    ("the greedy refs restored with the certificate removed",
     _greedy_refs_without_certificate, None, None,
     "is not the true best"),
    ("the certificate removed over a pool of 1x",
     _no_certificate_short_pool, None, None,
     "is not the true best"),
    ("headroom 1", "optimizer.core:HEADROOM",
     "HEADROOM = 10", "HEADROOM = 1",
     "had to enumerate twice"),
    ("the display dividing by the pool's maxima",
     "optimizer.optimizer:GearOptimizer.optimize",
     "                results, ctx, max(d_max, EPS), max(s_max, EPS))",
     "                results, ctx,\n"
     "                max(max(st['_D'] for _g, _s, st in results), EPS),\n"
     "                max(max(st['_S'] for _g, _s, st in results), EPS))",
     "is not the true best"),
    ("the certificate's comparison inverted",
     "optimizer.optimizer:GearOptimizer.optimize",
     "            if not core.trimmed_bound(",
     "            if core.trimmed_bound(",
     "had to enumerate twice"),
]
