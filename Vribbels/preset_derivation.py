"""The shipped Gear Score presets' weights, worked out from the
Optimizer's own score: the method `docs/preset_weights.md` describes,
which `docs/preset_weights.py` runs for the maintainer.

**A weight is what one MAX roll of a stat adds to the score**, divided
by what one max roll of the preset's scaling stat adds: the relative
gain of `(1 - h) * D + h * S`, `core.compute_score_components`'s damage
and shield/heal terms, at a reference build. Max rolls, because the
Gear Score divides every roll by its stat's max roll.

**The reference build is in a vacuum**: the combatant at level 61 with
their class's 5-star partner, their signature partner's passives (a
5-star or 4.5-star one at limit break 0, a 4-star one at its highest),
potential nodes 5 and 6 maxed, node 7 taken and the highest Affection,
wearing their ARCHETYPE's average fragment stats -- the mean of the
fragment stats of every archetype member's best Optimizer build -- and
their own sets. The averages are measured on the maintainer's inventory
and kept in `ARCHETYPES_FILE`, so the weights work out without one: no
inventory is read here.

**What the score cannot price keeps the preset's own weight**: Ego, HP,
and any stat worth exactly nothing to the score -- a tie-breaker the
maintainer sets (Ego and DEF ahead of HP), never a derived value.

**The program re-works the shipped presets itself where the game
client's max rolls are not the ones they were derived with** (`rework`,
the `max_rolls` the archetypes file records): each weight moves by what
the new rolls move its derivation by, so a weight the maintainer set by
hand keeps its own setting. `defaults_sync.presets_follow` hands the
result to a player's presets.
"""

import json
from collections import defaultdict
from pathlib import Path

# The archetypes file, in the bundled defaults (`defaults_sync.
# resolve_defaults_dir`): the averages, each member's sets, and the max
# rolls the shipped presets were derived with.
ARCHETYPES_FILE = "preset_archetypes.json"

# ---------------------------------------------------------------------------
# The assumptions. docs/preset_weights.md says why each is what it is.
# ---------------------------------------------------------------------------

LEVEL = 61
PARTNER_GRADE = 5          # flat stats: the class's 5-star partner
# The signature partner's limit break, by its grade: 5-star and
# 4.5-star partners at 0, 4-star ones at their highest.
PARTNER_LIMIT_BREAK = {5: 0, 4.5: 0, 4: 4}
POTENTIAL_LEVEL = 5        # nodes 5 and 6 (wire 50 and 60), maxed

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


def current_max_rolls():
    """{stat name: its max roll}, as `STATS` holds it now: the game
    client's where it was read (`client_overlay`)."""
    from game_data import STATS
    return {info[0]: info[3] for info in STATS.values() if info[3] > 0}


class Reference:
    """The reference combatants: their Optimizer settings and presets,
    by name, and an optimizer to build their char statics with. An
    optimizer with no inventory loaded builds them alike, every input an
    account carries being set here."""

    def __init__(self, settings, presets, opt=None):
        if opt is None:
            from optimizer.optimizer import GearOptimizer
            opt = GearOptimizer()
        self.opt = opt
        self.settings = settings
        self.presets = presets

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


def worths(ref, name, s, vector, lean=0.0, max_rolls=None):
    """{stat: relative gain of one max roll} at the reference build, the
    max rolls `max_rolls`' ({stat name: roll}, `current_max_rolls`'s
    without)."""
    from optimizer import core
    rolls = max_rolls or current_max_rolls()
    sp = core.build_score_precompute(s)
    shares = sp["set_effect_shares"]
    h = sp["heal_share"]
    attribute = ref.opt._resolve_attribute(name, s)
    cs = ref.statics(name)

    def scored(extra):
        stats = core.compute_build_stats([Pseudo(vector)] + extra, cs, shares)
        return stats, core.compute_score_components([], stats, sp, attribute)
    stats0, (d0, s0) = scored([])
    out = {}
    for stat, roll in rolls.items():
        _st, (d, sv) = scored([Pseudo({stat: roll})])
        gain = (1 - h) * (d / d0 - 1) if d0 else 0.0
        if h and s0:
            gain += h * (sv / s0 - 1)
        out[stat] = gain
    if lean:
        # The build whose damage only crit moves: its gains are the crit
        # multiplier's alone, blended with the ordinary build's.
        cm = core.crit_multiplier(stats0)
        crit = {stat: core.crit_multiplier(dict(
            stats0, **{stat: stats0[stat] + rolls[stat]})) / cm - 1
            for stat in ("CRate", "CDmg")}
        out = {k: lean * crit.get(k, 0.0) + (1 - lean) * v
               for k, v in out.items()}
    return out, stats0


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


def derive_preset(ref, stored, preset, max_rolls=None):
    """(derived weights, reference stats, notes) for one preset."""
    name = combatant_of(preset)
    spec = VARIANTS.get(preset) or {}
    s = dict(ref.settings[name], **spec.get("settings", {}))
    current = ref.presets.get(preset) or ref.presets.get(
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
    gains, stats = worths(ref, name, s, vector,
                          spec.get("unique_lean", 0.0), max_rolls)
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


def all_presets(presets):
    names = list(presets)
    names += [p for p, spec in VARIANTS.items()
              if spec.get("new") and p not in names]
    return names


# ---------------------------------------------------------------------------
# Re-working the shipped presets for the game client's max rolls.
# ---------------------------------------------------------------------------

def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_archetypes(defaults_dir):
    """The bundled archetypes file, or None where it does not read."""
    return _read(Path(defaults_dir) / ARCHETYPES_FILE)


def shipped_reference(defaults_dir):
    """(Reference over the bundled defaults, stored archetypes), or None
    where a file is missing or does not read."""
    defaults_dir = Path(defaults_dir)
    presets = (_read(defaults_dir / "presets.json") or {}).get("presets")
    chars = (_read(defaults_dir / "optimizer_settings.json")
             or {}).get("characters")
    stored = read_archetypes(defaults_dir)
    if not isinstance(presets, dict) or not isinstance(chars, dict) \
            or not stored or "averages" not in stored:
        return None
    settings = {s.get("name_hint"): s for s in chars.values()
                if isinstance(s, dict) and s.get("name_hint")}
    return Reference(settings, presets), stored


def rolls_moved(stored, rolls=None):
    """Whether `rolls` (the current max rolls without) differ from those
    the shipped presets were derived with. False where the archetypes
    file records none."""
    basis = (stored or {}).get("max_rolls")
    if not isinstance(basis, dict) or not basis:
        return False
    rolls = rolls or current_max_rolls()
    return any(abs(float(basis.get(stat, roll)) - roll) > 1e-9
               for stat, roll in rolls.items())


def rework(defaults_dir, rolls=None):
    """{preset: weights}: the shipped presets for `rolls` (the current
    max rolls without), or None where those are the ones the presets
    were derived with, or the defaults cannot be read.

    Each weight is the shipped one plus what the new rolls move its
    derivation by, never below 0: a weight the derivation does not
    reproduce -- one the maintainer set by hand -- keeps its own
    setting, and moves only by what the rolls change."""
    found = shipped_reference(defaults_dir)
    if found is None:
        return None
    ref, stored = found
    rolls = rolls or current_max_rolls()
    if not rolls_moved(stored, rolls):
        return None
    basis = {stat: float(stored["max_rolls"].get(stat, roll))
             for stat, roll in rolls.items()}
    out = {}
    for preset, shipped in ref.presets.items():
        if combatant_of(preset) not in ref.settings \
                or not isinstance(shipped, dict):
            continue
        before, _s, _n = derive_preset(ref, stored, preset, basis)
        after, _s, _n = derive_preset(ref, stored, preset, rolls)
        out[preset] = {
            stat: rounded(max(0.0, float(shipped.get(stat, before[stat]))
                              + after[stat] - before[stat]))
            for stat in STATS_SHOWN}
    return out
