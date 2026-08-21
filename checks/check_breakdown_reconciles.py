"""The contributions popup must add up to the stats the optimizer used.

`compute_build_breakdown` re-derives the layered Final ATK/DEF/HP
through separate code from `calculate_build_stats`, so that the
Optimizer tab's "Show all stat contributions" popup can show where every
number comes from. Its docstring promises the two reconcile exactly.

Two implementations of one formula drift silently: the popup would keep
showing a plausible set of numbers that no longer sum to the figure the
build was actually ranked by, and nothing would raise.
"""

from ._harness import add_source_to_path, newest_snapshot, Skip

NAME = "breakdown reconciles with build stats"

TOLERANCE = 1e-9


def run():
    failures = []
    snap = newest_snapshot()
    if snap is None:
        raise Skip("no snapshot in Vribbels/snapshots/ -- needs captured data")

    add_source_to_path()
    from pathlib import Path
    from optimizer.optimizer import GearOptimizer
    from optimizer import core
    import optimizer_settings_manager as osm

    o = GearOptimizer()
    o.load_data(snap)
    settings_mgr = osm.OptimizerSettingsManager(Path("."))
    settings_mgr.load()

    checked = 0
    for name in sorted(o.characters):
        info = o.character_info.get(name)
        gear = [p for p in (o.characters.get(name) or []) if p]
        if info is None or not gear:
            continue
        settings = settings_mgr.get_character_data(str(info.res_id)) or {}

        stats = o.calculate_build_stats(
            gear, name,
            effective_level=settings.get("optimize_for_level"),
            set_effect_shares=core.parse_set_effect_shares(settings),
        )
        breakdown = o.compute_build_breakdown(gear, name, settings=settings)
        checked += 1

        for stat in ("ATK", "DEF", "HP"):
            total = stats.get(stat)
            parts = (breakdown.get(stat) or {}).get("sum")
            if total is None or parts is None:
                failures.append(f"{name}: {stat} missing from one of the two")
                continue
            if abs(total - parts) > TOLERANCE:
                failures.append(
                    f"{name}: {stat} does not reconcile -- "
                    f"build stats {total:.6f}, breakdown sum {parts:.6f} "
                    f"(off by {abs(total - parts):.6f})"
                )

    if checked == 0:
        raise Skip("no combatant in the snapshot has equipped fragments")
    return failures
