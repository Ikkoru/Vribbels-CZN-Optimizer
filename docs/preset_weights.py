"""Derive the shipped Gear Score presets' weights from the Optimizer's own
score. The method, its assumptions and how to redo it:
`docs/preset_weights.md`; the derivation itself is
`Vribbels/preset_derivation.py`, which the program also runs.

    python docs/preset_weights.py            # derived against current
    python docs/preset_weights.py --derive   # re-derive the archetypes
    python docs/preset_weights.py --check    # have the weights drifted?
    python docs/preset_weights.py --write    # into default_settings/
    python docs/preset_weights.py --new Blazebell [--like Mika]
                                             # a new combatant's preset

The archetype averages are derived from the maintainer's inventory and
kept in `Vribbels/default_settings/preset_archetypes.json`, so the
weights are reproducible without running the Optimizer; `--derive` and
`--check` run it again (`--check` also records the season part it ran
in, which `checks/check_preset_weights.py` reads). `--write` records
beside them the max rolls the weights were derived with, which is what
tells the program to re-work its presets when the game client's differ.

`--new` derives the preset of one combatant the shipped presets lack,
from the stored archetypes, and leaves every other preset alone: see
`add_new`.

Read-only over Vribbels/settings/ and the snapshots; `--write` writes
default_settings/presets.json and the archetypes file's `max_rolls`
only, `--new` the one combatant's entries in default_settings/, and
each prints what it changed. Both also write what they wrote into
`docs/preset_weights.tsv` (`preset_weights_table`).
"""

import glob
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
sys.path.insert(0, str(HERE))
import preset_weights_table                                   # noqa: E402
from preset_derivation import (                               # noqa: E402
    LEVEL, STATS_SHOWN, VARIANTS, archetype, combatant_of,
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
        def read(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        osm = read("settings/optimizer_settings.json")["characters"]
        self.osm_by_rid = osm
        super().__init__({s["name_hint"]: s for s in osm.values()},
                         read("settings/presets.json")["presets"], opt)
        self.glob_settings = read("settings/settings.json")
        real = self.opt._build_char_static
        self.opt._build_char_static = lambda name, level: self.statics(
            name, real)

    def run_settings(self, name, s, forced=None):
        """What `optimizer.run_settings.run_settings` would build, at
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
            osm = json.loads(Path("settings/optimizer_settings.json")
                             .read_text(encoding="utf-8"))["characters"]
            cp = json.loads(Path("settings/character_preset.json")
                            .read_text(encoding="utf-8"))["assignments"]
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
    raw = json.loads(Path(snapshot).read_text(encoding="utf-8"))
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


def _option(argv, flag):
    """The value after `flag` in `argv`, or None."""
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return argv[argv.index(flag) + 1]
    return None


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, data):
    """The managers' own layout and the file's own line endings, so an
    untouched entry stays byte for byte."""
    path = Path(path)
    ending = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    path.write_bytes(json.dumps(data, indent=2).replace("\n", ending)
                     .encode("utf-8"))


def add_new(world, name, like=None, confirm=input):
    """Derive the preset of `name`, a combatant the shipped presets lack,
    and write it with what ships beside it.

    The preset is named as the maintainer's settings assign it (the
    combatant's own name where they assign none). Its weights come from
    the STORED archetypes, so no other preset moves; the tie-breakers
    the score cannot price are those of `like`, by default the first
    preset, by name, of a combatant in the same archetype. Her best
    build's set bonuses join the archetypes file's `sets`, the averages
    untouched until the next `--derive`. Written, after `confirm` says
    yes: the preset into default_settings/presets.json, and her
    assignment and Optimizer settings into their files where they lack
    them."""
    from optimizer import core
    if name not in world.settings:
        print("%s has no Optimizer settings: set them in the Optimizer "
              "tab and save, then run this again." % name)
        return False
    preset = world.assigned_preset(name)
    if not preset or preset == "Default Preset":
        preset = name
    target = SOURCE / "default_settings" / "presets.json"
    shipped = _read_json(target)
    if preset in shipped["presets"] or preset in world.presets:
        print("%r is already a preset: `--write` re-derives it with the "
              "others." % preset)
        return False
    s = world.settings[name]
    group = archetype(s)
    if like is None:
        like = next((p for p in sorted(world.presets)
                     if combatant_of(p) in world.settings
                     and p not in VARIANTS
                     and archetype(world.settings[combatant_of(p)])
                     == group), None)
    if like not in world.presets:
        print("No preset to take the tie-breakers from (%r): name one "
              "with --like." % like)
        return False
    stored = _read_json(ARCHETYPES)
    if group not in stored["averages"]:
        print("No %r archetype in the stored averages: run --derive "
              "first." % group)
        return False
    print("%s: preset %r, archetype %r, tie-breakers from %r" % (
        name, preset, group, like))
    # The candidate cut takes the preset's weights; the tie-breaker
    # preset stands in for the one being made.
    world.presets[preset] = dict(world.presets[like])
    results = world.opt.optimize(name, world.run_settings(name, s))
    if results:
        shares = core.build_score_precompute(s)["set_effect_shares"]
        stored["sets"][name] = set_vector(results[0][0], shares)
        print("   best build's set bonuses: %s" % (
            stored["sets"][name] or "none"))
    else:
        print("   note: no build in the inventory, so no set bonuses")
    derived, stats, notes = derive_preset(world, stored, preset)
    print("   reference CR %.1f CD %.1f ATK %.0f DEF %.0f" % (
        stats["CRate"], stats["CDmg"], stats["ATK"], stats["DEF"]))
    for note_ in notes:
        print("   note: " + note_)
    print("   %-8s" % "" + "".join("%9s" % k[:8] for k in STATS_SHOWN))
    print("   %-8s" % "derived" + "".join(
        "%9s" % ("%.3g" % derived[k]) for k in STATS_SHOWN))
    if confirm("Write it into default_settings/? [y/N] ").strip().lower() \
            not in ("y", "yes"):
        print("Nothing written.")
        return False
    shipped["presets"][preset] = derived
    _write_json(target, shipped)
    print("Written: %r into %s" % (preset, target.name))
    preset_weights_table.update({preset: derived})
    print("Written: %r into %s" % (preset, preset_weights_table.TABLE.name))
    _write_archetypes(stored)
    print("Written: %s's set bonuses into %s" % (name, ARCHETYPES.name))
    rid = next((r for r, c in world.osm_by_rid.items()
                if c.get("name_hint") == name), None)
    path = SOURCE / "default_settings" / "character_preset.json"
    assign = _read_json(path)
    if rid and not assign["assignments"].get(rid):
        assign["assignments"][rid] = preset
        _write_json(path, assign)
        print("Written: %s assigned %r in %s" % (name, preset, path.name))
    path = SOURCE / "default_settings" / "optimizer_settings.json"
    osm = _read_json(path)
    if rid and rid not in osm["characters"]:
        osm["characters"][rid] = world.osm_by_rid[rid]
        _write_json(path, osm)
        print("Written: %s's Optimizer settings into %s" % (name,
                                                            path.name))
    # Without the shipped values in the history, a player's untouched
    # copies read as their own edits and stop following the defaults.
    import subprocess
    sys.stdout.flush()
    subprocess.run([sys.executable, str(SOURCE / "default_settings"
                                        / "normalize" / "defaults_history.py")],
                   cwd=SOURCE, check=False)
    return True


def main(argv):
    world = World()
    new = _option(argv, "--new")
    if "--new" in argv:
        if not new:
            print("--new needs a combatant's name: --new Blazebell")
            return
        add_new(world, new, _option(argv, "--like"))
        return
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
        shipped = json.loads(Path(target).read_text(encoding="utf-8"))
        shipped["presets"].update(proposal)
        target.write_text(json.dumps(shipped, indent=2), encoding="utf-8")
        stored["max_rolls"] = current_max_rolls()
        _write_archetypes(stored)
        preset_weights_table.update(proposal)
        print("Written into %s and %s, and the max rolls into %s" % (
            target, preset_weights_table.TABLE, ARCHETYPES))


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
