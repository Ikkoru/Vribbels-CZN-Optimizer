"""Derive the shipped Gear Score presets' weights from the Optimizer's own
score. The method, its assumptions and how to redo it:
`docs/preset_weights.md`.

    python docs/preset_weights.py            # derived against current
    python docs/preset_weights.py --derive   # re-derive the archetypes
    python docs/preset_weights.py --check    # have the weights drifted?
    python docs/preset_weights.py --write    # into default_settings/

**A weight is what one MAX roll of a stat adds to the score**, divided
by what one max roll of the preset's scaling stat adds: the relative
gain of `(1 - h) * D + h * S`, `core.compute_score_components`'s damage
and shield/heal terms, at a reference build. Max rolls, because the
Gear Score divides every roll by its stat's max roll.

**The reference build is in a vacuum**: the combatant at level 61 with
their class's 5-star partner, their signature partner's passives (a
5-star or 4.5-star one at limit break 0, a 4-star one at its highest),
potential nodes 5 and 6 maxed, node 7 taken and the highest Affection,
wearing their
ARCHETYPE's average fragment stats -- the mean of the fragment stats of
every archetype member's best Optimizer build -- and their own sets.
Those averages are derived once and kept in
`docs/preset_weights_archetypes.json`, so the weights are reproducible
without running the Optimizer; `--derive` and `--check` run it again
(`--check` also records the season part it ran in, which
`checks/check_preset_weights.py` reads).

**What the score cannot price keeps the preset's own weight**: Ego, HP,
and any stat worth exactly nothing to the score -- a tie-breaker the
maintainer sets (Ego and DEF ahead of HP), never a derived value.

Read-only over Vribbels/settings/ and the snapshots; `--write` writes
default_settings/presets.json only, and prints what it changed.
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
ARCHETYPES = HERE / "preset_weights_archetypes.json"
PROPOSAL = HERE.parent / "_tmp" / "preset_weights_proposal.json"
sys.path.insert(0, str(SOURCE))

# ---------------------------------------------------------------------------
# The assumptions. docs/preset_weights.md says why each is what it is.
# ---------------------------------------------------------------------------

LEVEL = 61
PARTNER_GRADE = 5          # flat stats: the class's 5-star partner
# The signature partner's limit break, by its grade: 5-star and
# 4.5-star partners at 0, 4-star ones at their highest.
PARTNER_LIMIT_BREAK = {5: 0, 4.5: 0, 4: 4}
POTENTIAL_LEVEL = 5        # nodes 5 and 6 (wire 50 and 60), maxed

# The partner a combatant is assumed to wear is
# `game_data.partners.assumed_partner`'s, else the one equipped on the
# maintainer's account.

# Presets that are not their combatant's own Optimizer settings as they
# stand. `settings` overrides fields of them; `set` is a 4-piece set the
# preset assumes worn; `unique_lean` is Maribell's share of her
# shield-scaling build, whose damage only CRate and CDMG move; `new`
# marks a preset the maintainer's settings do not hold yet, whose
# tie-breakers come from `like`.
VARIANTS = {
    "Beryl (Upgrade Deck)": {"settings": {"extra_pct": 100}},
    "Beryl (no Extra DMG)": {"settings": {"extra_pct": 0}},
    "Heidemarie (no Extra DMG)": {"settings": {"extra_pct": 0}},
    "Haru (Line of Justice)": {"set": 20},
    "Khalipe (Line of Justice)": {"set": 20},
    "Nine (Line of Justice)": {"set": 20},
    "Rita (Line of Justice)": {"set": 20},
    "Renoa (Conqueror's Aspect)": {"set": 6},
    "Rin (Conqueror's Aspect)": {"set": 6},
    "Maribell (Shelter Strike DPS)": {"unique_lean": 0.5},
    "Maribell": {"unique_lean": 0.0},
    "Orlea (slight DMG skew)": {
        "settings": {"shielding_healing_weight": 33}},
    "Orlea (healing skew)": {
        "settings": {"shielding_healing_weight": 80}, "new": True,
        "like": "Orlea (slight DMG skew)"},
    # Her tie-breakers are those of a plain ATK DPS. Her own best
    # build's sets are in the stored archetypes; her fragment stats
    # join the averages at the next `--derive`.
    "Anika": {"new": True, "like": "Sereniel"},
}

# The 2-piece a forced 4-piece is paired with where the inventory has no
# such build: the one nearly every best build wears.
PAIRED_TWO_PIECE = 11      # Executioner's Tool

STATS_SHOWN = ["Flat ATK", "ATK%", "Flat DEF", "DEF%", "Flat HP", "HP%",
               "CRate", "CDmg", "Ego", "Extra DMG%", "DoT%"]
MF_KEYS = STATS_SHOWN


class Pseudo:
    """Fragment stats with no set and no main stat: one max roll, or an
    archetype's whole average."""
    set_id = None
    main_stat = None

    def __init__(self, stats):
        self._stats = dict(stats)

    def get_total_stats(self):
        return dict(self._stats)


def combatant_of(preset):
    return preset.split(" (", 1)[0]


def archetype(s):
    """The groups the averages are taken over, by what the settings say
    the combatant does."""
    heal = s.get("shielding_healing_weight", 0)
    split = s.get("atk_def_split", 0)
    if heal >= 50:
        return "healer"
    if heal > 0 and split < 50:
        return "healer, ATK damage"
    if split >= 50:
        return "DEF DPS"
    if s.get("dot_pct", 0) + s.get("fracture_pct", 0) >= 50:
        return "ATK DPS, DoT"
    if s.get("extra_pct", 0) >= 50:
        return "ATK DPS, Extra"
    return "ATK DPS"


class World:
    """The program's data, read once: the optimizer on the newest
    snapshot, the maintainer's settings and presets."""

    def __init__(self):
        os.chdir(SOURCE)
        from optimizer.optimizer import GearOptimizer
        self.opt = GearOptimizer()
        self.snapshot = max(glob.glob("snapshots/memory_fragments_*.json"),
                            key=os.path.getmtime)
        self.opt.load_data(self.snapshot)
        self.by_id = {f.id: f for f in self.opt.fragments}
        read = lambda p: json.load(io.open(p, encoding="utf-8"))
        osm = read("settings/optimizer_settings.json")["characters"]
        self.settings = {s["name_hint"]: s for s in osm.values()}
        self.presets = read("settings/presets.json")["presets"]
        self.glob_settings = read("settings/settings.json")
        real = self.opt._build_char_static
        self.opt._build_char_static = lambda name, level: self.statics(
            name, real)

    # -- the reference combatant --------------------------------------------

    def partner(self, name):
        """(res_id, data) of the partner assumed for `name`."""
        from game_data import PARTNERS
        from game_data.partners import assumed_partner
        rid, partner = assumed_partner(name)
        if rid is not None:
            return rid, partner
        info = self.opt.character_info.get(name)
        rid = info.partner_res_id if info else None
        return rid, PARTNERS.get(rid) if rid else None

    def statics(self, name, real=None):
        """The char-static inputs of `name` in the vacuum."""
        from game_data import FRIENDSHIP_BONUSES, PARTNER_CLASS_STATS
        from game_data.characters import (get_character_by_name,
                                          get_potential_stat_bonus)
        from game_data.partners import get_partner_passive_stats
        build = real or self.opt.__class__._build_char_static.__get__(
            self.opt)
        cs = dict(build(name, LEVEL))
        char = get_character_by_name(name)
        _tier, aff_atk, aff_def, aff_hp = FRIENDSHIP_BONUSES[-1]
        cs.update(affection_atk=aff_atk, affection_def=aff_def,
                  affection_hp=aff_hp)
        for key in [k for k in cs if k.startswith("partner_")]:
            cs[key] = 0
        prid, partner = self.partner(name)
        cls = (partner or {}).get("class") or char.get("class")
        flat = PARTNER_CLASS_STATS[(PARTNER_GRADE, cls)]
        cs.update(partner_flat_atk=flat["atk"], partner_flat_def=flat["def"],
                  partner_flat_hp=flat["hp"])
        if prid:
            for cond, suffix in ((False, ""), (True, "_cond")):
                passive = get_partner_passive_stats(
                    prid, PARTNER_LIMIT_BREAK.get(partner.get("grade"), 0),
                    conditional=cond)
                for stat, key in (("ATK%", "atk_pct"), ("DEF%", "def_pct"),
                                  ("HP%", "hp_pct"), ("CDmg", "cdmg"),
                                  ("Extra DMG%", "extra_dmg"),
                                  ("CRate", "crate"), ("DoT%", "dot"),
                                  ("Ego", "ego")):
                    cs["partner_" + key + suffix] = passive.get(stat, 0)
        for key in ("pot_atk_pct", "pot_def_pct", "pot_hp_pct", "pot_crate",
                    "pot_cdmg"):
            cs[key] = 0
        from game_data import CHARACTERS
        rid = next((r for r, c in CHARACTERS.items()
                    if isinstance(c, dict) and c.get("name") == name), None)
        for node in (50, 60):
            stat, bonus = get_potential_stat_bonus(rid, node,
                                                   POTENTIAL_LEVEL)
            key = {"ATK%": "pot_atk_pct", "DEF%": "pot_def_pct",
                   "HP%": "pot_hp_pct", "CRate": "pot_crate",
                   "CDmg": "pot_cdmg"}.get(stat)
            if key:
                cs[key] += bonus
        # Node 7 taken, whatever the account's own combatant has: its
        # growth is part of what a stat buys.
        from optimizer import core
        from game_data.potential_7 import get_potential_7
        cs["potential_7"] = core.potential_7_effects(get_potential_7(rid))
        return cs

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
    from game_data.sets import SET_STAT_NAME_MAP
    out = defaultdict(float)
    counts = defaultdict(int)
    for piece in gear:
        counts[piece.set_id] += 1
    for sid, n in counts.items():
        info = SETS.get(sid)
        if not info or n < info["pieces"]:
            continue
        stat = info.get("stat", "")
        if info["type"] == "unconditional":
            value = info.get("value", 0)
        elif info["type"] == "conditional" and stat in ("Crit DMG",
                                                        "Crit Rate"):
            value = info.get("value", 0) * shares.get(sid, 0.0)
        else:
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


# ---------------------------------------------------------------------------
# The weights.
# ---------------------------------------------------------------------------

def worths(world, name, s, vector, lean=0.0):
    """{stat: relative gain of one max roll} at the reference build."""
    from game_data import STATS
    from optimizer import core
    sp = core.build_score_precompute(s)
    shares = sp["set_effect_shares"]
    h = sp["heal_share"]
    attribute = world.opt._resolve_attribute(name, s)
    cs = world.statics(name)

    def scored(extra):
        stats = core.compute_build_stats([Pseudo(vector)] + extra, cs, shares)
        return stats, core.compute_score_components([], stats, sp, attribute)
    stats0, (d0, s0) = scored([])
    out = {}
    for info in STATS.values():
        if info[3] <= 0:
            continue
        _st, (d, sv) = scored([Pseudo({info[0]: info[3]})])
        gain = (1 - h) * (d / d0 - 1) if d0 else 0.0
        if h and s0:
            gain += h * (sv / s0 - 1)
        out[info[0]] = gain
    if lean:
        # The build whose damage only crit moves: its gains are the crit
        # multiplier's alone, blended with the ordinary build's.
        cm = core.crit_multiplier(stats0)
        crit = {stat: core.crit_multiplier(dict(
            stats0, **{stat: stats0[stat] + max_roll(stat)})) / cm - 1
            for stat in ("CRate", "CDmg")}
        out = {k: lean * crit.get(k, 0.0) + (1 - lean) * v
               for k, v in out.items()}
    return out, stats0


def max_roll(stat):
    from game_data import STATS
    return next(info[3] for info in STATS.values() if info[0] == stat)


def baseline(s, current):
    """The stat a preset reads 1 on: DEF% for a healer or a DEF scaler,
    or where the preset already reads DEF% 1 over a smaller ATK%."""
    if s.get("shielding_healing_weight", 0) >= 50 \
            or s.get("atk_def_split", 0) >= 50:
        return "DEF%"
    if current.get("DEF%") == 1.0 and current.get("ATK%", 1.0) < 1.0:
        return "DEF%"
    return "ATK%"


def rounded(value):
    return round(value, 2) if value >= 1 else round(value, 3)


def derive_preset(world, stored, preset):
    """(derived weights, reference stats, notes) for one preset."""
    name = combatant_of(preset)
    spec = VARIANTS.get(preset) or {}
    s = dict(world.settings[name], **spec.get("settings", {}))
    current = world.presets.get(preset) or world.presets.get(
        spec.get("like", ""), {})
    vector = dict(stored["averages"][archetype(s)])
    own_sets = stored["sets"].get(name)
    notes = []
    if spec.get("set") and (own_sets is None or not _has_set(
            own_sets, spec["set"])):
        from game_data import SETS
        from optimizer import core
        shares = core.build_score_precompute(s)["set_effect_shares"]
        own_sets = synthetic_sets(spec["set"], shares)
        notes.append("%s x4 assumed with %s x2: no such build in the "
                     "inventory" % (SETS[spec["set"]]["name"],
                                    SETS[PAIRED_TWO_PIECE]["name"]))
    for k, v in (own_sets or {}).items():
        vector[k] = vector.get(k, 0) + v
    gains, stats = worths(world, name, s, vector,
                          spec.get("unique_lean", 0.0))
    unit_stat = baseline(s, current)
    unit = gains[unit_stat] or 1e-12
    out = {}
    for stat in STATS_SHOWN:
        gain = gains.get(stat, 0.0)
        if abs(gain) < 1e-9:
            # The score cannot price it: the preset's own tie-breaker.
            out[stat] = current.get(stat, 0.0)
        else:
            out[stat] = rounded(gain / unit)
    return out, stats, notes


def _has_set(vector, sid):
    from game_data import SETS
    from game_data.sets import SET_STAT_NAME_MAP
    stat = SET_STAT_NAME_MAP.get(SETS[sid].get("stat", ""))
    return vector.get(stat, 0) >= SETS[sid].get("value", 0) * 0.5


def synthetic_sets(sid, shares):
    from game_data import SETS
    from game_data.sets import SET_STAT_NAME_MAP
    out = defaultdict(float)
    for set_id, share in ((sid, shares.get(sid, 0.0)),
                          (PAIRED_TWO_PIECE, 1.0)):
        info = SETS[set_id]
        value = info.get("value", 0) * (
            share if info["type"] == "conditional" else 1.0)
        out[SET_STAT_NAME_MAP.get(info.get("stat", ""))] += value
    return dict(out)


def all_presets(world):
    names = list(world.presets)
    names += [p for p, spec in VARIANTS.items()
              if spec.get("new") and p not in names]
    return names


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
        if "--check" in argv and ARCHETYPES.exists():
            old = json.loads(ARCHETYPES.read_text(encoding="utf-8"))
            report_drift(world, old, fresh)
            old["checked"] = fresh["checked"]
            ARCHETYPES.write_text(json.dumps(old, indent=1, sort_keys=True),
                                  encoding="utf-8")
            print("Recorded the check: %s part %s." % (season, part))
            return
        ARCHETYPES.write_text(json.dumps(fresh, indent=1, sort_keys=True),
                              encoding="utf-8")
        stored = fresh
    proposal = {}
    for preset in all_presets(world):
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
        print("Written into %s" % target)


def report_drift(world, old, fresh):
    """How far the weights move with today's archetypes, per preset."""
    worst = []
    for preset in all_presets(world):
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
