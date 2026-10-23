"""Derive the shipped Gear Score presets' weights from the Optimizer's own
score. The method, its assumptions and how to redo it:
`docs/preset_weights.md`; the derivation itself is
`Vribbels/preset_derivation.py`, which the program also runs.

    python docs/preset_weights.py            # derived against current
    python docs/preset_weights.py --derive   # re-derive the archetypes
    python docs/preset_weights.py --check    # have the weights drifted?
    python docs/preset_weights.py --write    # into default_settings/

The archetype averages are derived from the maintainer's inventory and
kept in `Vribbels/default_settings/preset_archetypes.json`, so the
weights are reproducible without running the Optimizer; `--derive` and
`--check` run it again (`--check` also records the season part it ran
in, which `checks/check_preset_weights.py` reads). `--write` records
beside them the max rolls the weights were derived with, which is what
tells the program to re-work its presets when the game client's differ.

Read-only over Vribbels/settings/ and the snapshots; `--write` writes
default_settings/presets.json and the archetypes file's `max_rolls`
only, and prints what it changed.
"""

import glob
import io
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
sys.path.insert(0, str(SOURCE))

import preset_derivation as pd                                # noqa: E402
from preset_derivation import (                               # noqa: E402
    LEVEL, STATS_SHOWN, VARIANTS, archetype, baseline, combatant_of,
    current_max_rolls, derive_preset)

ARCHETYPES = SOURCE / "default_settings" / pd.ARCHETYPES_FILE
PROPOSAL = HERE.parent / "_tmp" / "preset_weights_proposal.json"
MF_KEYS = STATS_SHOWN


class World(pd.Reference):
    """The program's data, read once: the optimizer on the newest
    snapshot, the maintainer's settings and presets."""

    def __init__(self):
        os.chdir(SOURCE)
        from optimizer.optimizer import GearOptimizer
        opt = GearOptimizer()
        self.snapshot = max(glob.glob("snapshots/memory_fragments_*.json"),
                            key=os.path.getmtime)
        opt.load_data(self.snapshot)
        self.by_id = {f.id: f for f in opt.fragments}
        read = lambda p: json.load(io.open(p, encoding="utf-8"))
        osm = read("settings/optimizer_settings.json")["characters"]
        super().__init__({s["name_hint"]: s for s in osm.values()},
                         read("settings/presets.json")["presets"], opt)
        self.glob_settings = read("settings/settings.json")
        real = self.opt._build_char_static
        self.opt._build_char_static = lambda name, level: self.statics(
            name, real)

    def run_settings(self, name, s, forced=None):
        """What `OptimizerTab._build_optimizer_settings` would build, at
        LEVEL, with nothing excluded."""
        from game_data import SETS
        fm = s.get("force_main") or {}
        slot6 = [m for k, m in (("slot6_hp", "HP%"), ("slot6_ego", "Ego"))
                 if fm.get(k)]
        sets = [forced] if forced else list(s.get("sets_selected", []))
        preset = self.presets.get(self.assigned_preset(name)) or {}
        return {
            "four_piece_sets": [i for i in sets
                                if (SETS.get(i) or {}).get("pieces") == 4],
            "two_piece_sets": [i for i in sets
                               if (SETS.get(i) or {}).get("pieces") == 2],
            "main_stat_4": ["HP%"] if fm.get("slot4_hp") else None,
            "main_stat_5": ["HP%"] if fm.get("slot5_hp") else None,
            "main_stat_6": slot6 or None,
            "top_percent": 20, "include_equipped": True,
            "excluded_heroes": [], "max_results": 100,
            "min_gear_level": int(self.glob_settings.get(
                "optimizer_min_gear_level", 0) or 0),
            "ignore_offelement_slot5": bool(self.glob_settings.get(
                "optimizer_ignore_offelement", True)),
            "sets_selected": sets,
            "max_flex_slots": 2 if forced else int(
                s.get("max_flex_slots", 6)),
            "slot_filter_weights": preset or None,
            "optimize_for_level": LEVEL,
            **{k: s.get(k, d) for k, d in (
                ("extra_pct", 0), ("dot_pct", 0), ("fracture_pct", 0),
                ("atk_def_split", 0), ("shielding_healing_weight", 0),
                ("avg_card_dmg_pct", 100), ("avg_mult_buff_pct", 0),
                ("avg_add_buff_pct", 0), ("element_override", None))},
            "set_effect_pcts": dict(s.get("set_effect_pcts", {}) or {}),
            "have_at_least": s.get("have_at_least", {}),
        }

    def assigned_preset(self, name):
        if not hasattr(self, "_assigned"):
            osm = json.load(io.open("settings/optimizer_settings.json",
                                    encoding="utf-8"))["characters"]
            cp = json.load(io.open("settings/character_preset.json",
                                   encoding="utf-8"))["assignments"]
            self._assigned = {s.get("name_hint"): cp.get(rid)
                              for rid, s in osm.items()}
        return self._assigned.get(name)


# ---------------------------------------------------------------------------
# The archetypes: every combatant's best build, averaged per group.
# ---------------------------------------------------------------------------

def mf_vector(gear):
    out = defaultdict(float)
    for piece in gear:
        for k, v in piece.get_total_stats().items():
            if k in MF_KEYS:
                out[k] += v
    return dict(out)


def set_vector(gear, shares):
    """What a build's sets add, routed as `compute_build_stats` does."""
    from game_data import SETS
    from game_data.sets import SET_STAT_NAME_MAP, set_effects
    out = defaultdict(float)
    counts = defaultdict(int)
    for piece in gear:
        counts[piece.set_id] += 1
    for sid, n in counts.items():
        info = SETS.get(sid)
        if not info or n < info["pieces"]:
            continue
        for stat, value in set_effects(info):
            if info["type"] == "conditional":
                if stat not in ("Crit DMG", "Crit Rate"):
                    continue
                value *= shares.get(sid, 0.0)
            elif info["type"] != "unconditional":
                continue
            name = SET_STAT_NAME_MAP.get(stat)
            if name in ("ATK%", "DEF%", "HP%", "CDmg", "CRate"):
                out[name] += value
    return dict(out)


def forced_set(name):
    """The 4-piece the combatant's ASSIGNED preset names, if any."""
    for preset, spec in VARIANTS.items():
        if combatant_of(preset) == name and spec.get("set"):
            return spec["set"]
    return None


def derive(world):
    """Every combatant's best build, and the archetype averages."""
    from optimizer import core
    sets, groups = {}, defaultdict(list)
    for name, s in sorted(world.settings.items()):
        spec = VARIANTS.get(world.assigned_preset(name)) or {}
        s = dict(s, **spec.get("settings", {}))
        forced = forced_set(name)
        start = time.perf_counter()
        results = world.opt.optimize(name, world.run_settings(name, s,
                                                              forced))
        took = time.perf_counter() - start
        if not results:
            print("  %-11s no build (%.1f s)" % (name, took))
            continue
        gear = results[0][0]
        shares = core.build_score_precompute(s)["set_effect_shares"]
        # Stats only, never fragment ids: this file is tracked, and an
        # id is the maintainer's account's.
        sets[name] = set_vector(gear, shares)
        groups[archetype(s)].append((name, mf_vector(gear)))
        print("  %-11s %.1f s" % (name, took))
    averages = {g: {k: round(sum(v.get(k, 0) for _n, v in rows) / len(rows),
                             3) for k in MF_KEYS}
                for g, rows in groups.items()}
    members = {g: [n for n, _v in rows] for g, rows in groups.items()}
    return {"averages": averages, "members": members, "sets": sets}


def season_part(snapshot, now=None):
    """(season, part) a snapshot's live Galactic Disaster is in at `now`,
    as the Checklist dates its shop pages; (None, None) outside one. Also
    what `checks/check_preset_weights.py` reads."""
    import schedules
    import shop_stock
    from chaos_estimate import part_of
    from ui.tabs import checklist_tab
    raw = json.load(io.open(snapshot, encoding="utf-8"))
    now = time.time() if now is None else now
    name, window = schedules.live(shop_stock.season_group_of(
        checklist_tab.SEASONAL_SHOP_CATEGORY), raw, now)
    if not name:
        return None, None
    starts = checklist_tab._page_openings(raw, name, window)
    return name, part_of(now, starts) if starts else None


def _write_archetypes(data):
    ARCHETYPES.write_text(json.dumps(data, indent=1, sort_keys=True),
                          encoding="utf-8")


def main(argv):
    world = World()
    stored = None
    if ARCHETYPES.exists() and "--derive" not in argv \
            and "--check" not in argv:
        stored = json.loads(ARCHETYPES.read_text(encoding="utf-8"))
    if stored is None or "--check" in argv:
        print("Deriving the archetypes from every combatant's best build:")
        fresh = derive(world)
        season, part = season_part(world.snapshot)
        fresh.update(derived_at=time.strftime("%Y-%m-%d"),
                     checked={"season": season, "part": part,
                              "at": time.strftime("%Y-%m-%d")})
        if ARCHETYPES.exists():
            old = json.loads(ARCHETYPES.read_text(encoding="utf-8"))
            # The rolls the shipped presets were derived with stay until
            # `--write` writes presets derived with others.
            if "max_rolls" in old:
                fresh["max_rolls"] = old["max_rolls"]
            if "--check" in argv:
                report_drift(world, old, fresh)
                old["checked"] = fresh["checked"]
                _write_archetypes(old)
                print("Recorded the check: %s part %s." % (season, part))
                return
        _write_archetypes(fresh)
        stored = fresh
    proposal = {}
    for preset in pd.all_presets(world.presets):
        name = combatant_of(preset)
        if name not in world.settings:
            print("%s: no Optimizer settings for %s" % (preset, name))
            continue
        derived, stats, notes = derive_preset(world, stored, preset)
        proposal[preset] = derived
        current = world.presets.get(preset, {})
        print()
        print("%s  [%s]  reference CR %.1f CD %.1f ATK %.0f DEF %.0f%s" % (
            preset, archetype(dict(world.settings[name],
                                   **(VARIANTS.get(preset) or {}).get(
                                       "settings", {}))),
            stats["CRate"], stats["CDmg"], stats["ATK"], stats["DEF"],
            "  NEW" if preset not in world.presets else ""))
        for note_ in notes:
            print("   note: " + note_)
        print("   %-8s" % "" + "".join("%9s" % k[:8] for k in STATS_SHOWN))
        print("   %-8s" % "current" + "".join(
            "%9s" % ("%.3g" % current[k] if k in current else "-")
            for k in STATS_SHOWN))
        print("   %-8s" % "derived" + "".join(
            "%9s" % ("%.3g" % derived[k]) for k in STATS_SHOWN))
    PROPOSAL.parent.mkdir(exist_ok=True)
    PROPOSAL.write_text(json.dumps({"presets": proposal}, indent=1),
                        encoding="utf-8")
    print()
    print("Proposal written to %s" % PROPOSAL)
    if "--write" in argv:
        target = SOURCE / "default_settings" / "presets.json"
        shipped = json.load(io.open(target, encoding="utf-8"))
        shipped["presets"].update(proposal)
        target.write_text(json.dumps(shipped, indent=2), encoding="utf-8")
        stored["max_rolls"] = current_max_rolls()
        _write_archetypes(stored)
        print("Written into %s, and the max rolls into %s" % (
            target, ARCHETYPES))


def report_drift(world, old, fresh):
    """How far the weights move with today's archetypes, per preset."""
    worst = []
    for preset in pd.all_presets(world.presets):
        if combatant_of(preset) not in world.settings:
            continue
        before, _s, _n = derive_preset(world, old, preset)
        after, _s, _n = derive_preset(world, fresh, preset)
        for stat in STATS_SHOWN:
            a, b = before.get(stat, 0), after.get(stat, 0)
            if max(abs(a), abs(b)) >= 0.2 and abs(a - b) / max(abs(a),
                                                                abs(b)) > 0.1:
                worst.append((preset, stat, a, b))
    if not worst:
        print("The archetypes still give the same weights (every change "
              "under 10%).")
        return
    print("Weights that move by more than 10% with today's archetypes -- "
          "re-derive (--derive) and review:")
    for preset, stat, a, b in worst:
        print("  %-32s %-10s %.3g -> %.3g" % (preset, stat, a, b))


if __name__ == "__main__":
    main(sys.argv[1:])
