"""Parallel results must be byte-identical to sequential ones.

The headline engineering invariant. The parallel path partitions the
search, scores in worker processes, and merges; the sequential path does
it in one. They must agree on the results, their order, and the run
counters -- not merely on the best build.

**Bounded on purpose.** `top_percent=1` puts every slot on the
10-fragment floor, which is 10^6 combinations: comfortably above
`PARALLEL_MIN_COMBOS`, so the parallel path really engages, and about
two seconds per path instead of the many minutes an unbounded run takes.
The expensive half is the SEQUENTIAL one -- which is the whole reason
the parallel path exists -- so an unbounded parity check is a check
nobody runs. Pass `--full` to use each combatant's real settings.

What the bound cannot cover: behaviour that only appears at large
partition counts. `--full` exists for when that matters.
"""

import time

from ._harness import add_source_to_path, newest_snapshot, describe, Skip

NAME = "optimizer parallel/sequential parity"

BOUNDED_TOP_PERCENT = 1
COMBATANTS = 3


def _key(entry):
    gear, score, _stats = entry
    return (tuple(getattr(p, "id", None) for p in gear), round(score, 10))


def run(full=False):
    failures = []
    snap = newest_snapshot()
    if snap is None:
        raise Skip("no snapshot in Vribbels/snapshots/ -- needs captured data")

    add_source_to_path()
    from pathlib import Path
    from optimizer.optimizer import GearOptimizer
    import optimizer_settings_manager as osm

    probe = GearOptimizer()
    probe.load_data(snap)
    settings_mgr = osm.OptimizerSettingsManager(Path("."))
    settings_mgr.load()

    def optimize_with(workers, name, settings):
        o = GearOptimizer()
        o.load_data(snap)
        o._resolve_worker_count = lambda: workers
        t = time.time()
        results = o.optimize(name, settings)
        return results, time.time() - t, dict(o.last_optimize_stats or {})

    checked = 0
    for name in sorted(probe.characters):
        if checked >= COMBATANTS:
            break
        info = probe.character_info.get(name)
        if info is None:
            continue
        settings = dict(settings_mgr.get_character_data(str(info.res_id)) or {})
        if not settings:
            continue
        if not full:
            settings["top_percent"] = BOUNDED_TOP_PERCENT

        par, t_par, stats_par = optimize_with(4, name, settings)
        seq, t_seq, stats_seq = optimize_with(1, name, settings)
        if not par and not seq:
            continue
        checked += 1

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
        for counter in ("total_combinations", "passed_set_reqs",
                        "passed_have_at_least"):
            if stats_par.get(counter) != stats_seq.get(counter):
                failures.append(
                    f"{name}: counter {counter} differs -- "
                    f"parallel={stats_par.get(counter)} "
                    f"sequential={stats_seq.get(counter)}"
                )

    if checked == 0:
        raise Skip(
            f"{describe(snap)} has no combatant with saved optimizer settings"
        )
    return failures
