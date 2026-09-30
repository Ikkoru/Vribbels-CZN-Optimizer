"""The contributions popup must add up to the stats the optimizer used.

`compute_build_breakdown` re-derives the layered Final ATK/DEF/HP
through separate code from `calculate_build_stats`, so that the
Optimizer tab's "Show all stat contributions" popup can show where every
number comes from. Its docstring promises the two reconcile exactly.

Two implementations of one formula drift silently: the popup would keep
showing a plausible set of numbers that no longer sum to the figure the
build was actually ranked by, and nothing would raise.

Then again with a node 7 forced onto every combatant (`FORCED_NODE_7`),
over every row the popup shows: its bonus sits inside `Pot` and `Other`
and comes out of the Pot7 rows again, which only the popup does.
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
    return failures + _with_node_7(o, settings_mgr)


# A node 7 every build meets part-way, granting everything the score
# prices, one of them at the start of battle: forced onto every
# combatant, since whether a captured build meets its own node 7's
# threshold is up to the account.
FORCED_NODE_7 = (
    {"grants": "ATK%", "value": 10},
    {"grants": "DEF%", "value": 6},
    {"grants": "CRate", "value": 5, "stat": "ATK", "at": 1, "per": 100,
     "add": 1, "max": 5},
    {"grants": "CDmg", "value": 7, "stat": "DEF", "at": 1, "start": True},
    {"grants": "Extra DMG%", "value": 3},
    {"grants": "Element%", "value": 4},
)


def _with_node_7(o, settings_mgr):
    """Every popup row against the build stats, with node 7 in both.

    The popup folds node 7's bonus into `Pot` and `Other`, and its Pot7
    rows take it out again; the build stats keep the check values apart
    from the finals. Two derivations of that, and the one only the
    popup shows could drift unseen.
    """
    import optimizer.optimizer as om
    from optimizer import core
    out = []
    saved = om.get_potential_7
    om.get_potential_7 = lambda _rid: FORCED_NODE_7
    try:
        for name in sorted(o.characters):
            info = o.character_info.get(name)
            gear = [p for p in (o.characters.get(name) or []) if p]
            if info is None or not gear:
                continue
            taken = info.potential_nodes.get(70)
            info.potential_nodes[70] = 1
            try:
                settings = settings_mgr.get_character_data(
                    str(info.res_id)) or {}
                stats = o.calculate_build_stats(
                    gear, name,
                    effective_level=settings.get("optimize_for_level"),
                    set_effect_shares=core.parse_set_effect_shares(settings))
                bd = o.compute_build_breakdown(gear, name, settings=settings)
            finally:
                if taken is None:
                    info.potential_nodes.pop(70, None)
                else:
                    info.potential_nodes[70] = taken
            if not stats.get("_p7"):
                out.append(f"{name}: a forced node 7 gave the build stats "
                           f"no bonus, so nothing below was tested.")
                continue
            cr, cd, ex = bd["CRate"], bd["CDmg"], bd["Extra DMG%"]
            pairs = [(f"{s} with node 7", stats[s], bd[s]["sum"])
                     for s in ("ATK", "DEF", "HP")]
            pairs += [(f"Pot7 {s}", stats["_inner_" + s.lower()],
                       bd[s]["inner"]) for s in ("ATK", "DEF", "HP")]
            for label, row, final, hal in (("CRate", cr, "CRate", "_hal_crate"),
                                           ("CDmg", cd, "CDmg", "_hal_cdmg")):
                total = (row["base"] + row["mf_main"] + row["mf_sub"]
                         + row["set_effect"] + row["other"])
                pairs.append((label, stats[final], total))
                pairs.append((f"Pot7 {label}", stats[hal],
                              total - row["pot7_excluded"]))
            total = ex["mf_sub"] + ex["set_effect"] + ex["other"]
            pairs.append(("Extra DMG%", stats["Extra DMG%"], total))
            pairs.append(("Pot7 Extra DMG%", stats["_hal_extra"],
                          total - ex["pot7_excluded"]))
            pairs.append(("node 7's Element%", stats["_p7"].get("Element%"),
                          bd["Element%"]["other"]))
            for label, built, shown in pairs:
                if built is None or abs(built - shown) > 1e-6:
                    out.append(f"{name}: {label} is {built} in the build "
                               f"stats and {shown} in the contributions "
                               f"popup, with node 7 taken.")
    finally:
        om.get_potential_7 = saved
    return out
