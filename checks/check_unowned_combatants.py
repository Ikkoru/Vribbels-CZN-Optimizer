"""A combatant the account does not have is optimized as one built the
way `optimizer.UNOWNED_AFFINITY` and its neighbours describe.

Nothing else would notice if it were not: the Optimizer still returns
builds for such a combatant, just scored against a bare base -- no
partner, Potential or Affinity -- which ranks its fragments as though
flat stats were worth far more than they are. `docs/game_formulas.md`,
§1, says what is assumed.

A fresh `GearOptimizer` holds no account, so every combatant the game
data has is one it does not have, and this needs no capture.
"""

from ._harness import add_source_to_path

NAME = "a combatant you lack is optimized as built"

# The maintainer's figures, held here as well as in `optimizer.py` on
# purpose: the assertions below read the constants, so without this a
# changed constant would change what they expect along with it.
SPEC = {"UNOWNED_AFFINITY": 20, "UNOWNED_PARTNER_LIMIT_BREAK": 0,
        "UNOWNED_PARTNER_GRADE": 5}


def _class_passive_is_shared():
    """`class_partner_passive` keeps only what every partner of the
    class carries alike, tried on test partners added for the purpose:
    one with an extra stat, one with a different value. The real table
    holds neither yet, so it cannot show a union passing for the shared
    part."""
    from game_data import partners
    cls = "Hunter"
    before = partners.class_partner_passive(cls)
    extra = dict(name="test extra", grade=5, **{"class": cls},
                 stats={stat: (v,) * 5 for stat, v in before.items()}
                 | {"CRate": (5,) * 5})
    other = dict(name="test other", grade=5, **{"class": cls},
                 stats={stat: (v + 1,) * 5 for stat, v in before.items()})
    out = []
    try:
        partners.PARTNERS[-901] = extra
        if partners.class_partner_passive(cls) != before:
            out.append(f"a 5-star {cls} partner with an extra CRate moves "
                       f"the class's shared passive to "
                       f"{partners.class_partner_passive(cls)}, from "
                       f"{before}: one partner's extra is not the class's.")
        partners.PARTNERS[-902] = other
        if partners.class_partner_passive(cls):
            out.append(f"a 5-star {cls} partner carrying the shared stats "
                       f"at other values leaves "
                       f"{partners.class_partner_passive(cls)} shared: a "
                       f"stat the class does not carry alike is not shared.")
    finally:
        partners.PARTNERS.pop(-901, None)
        partners.PARTNERS.pop(-902, None)
    if not before:
        out.append(f"the {cls} 5-star partners share no passive at all, so "
                   f"a combatant named by no SIGNATURE_PARTNERS entry gets "
                   f"nothing from its assumed partner.")
    return out


def run():
    add_source_to_path()
    from optimizer import core, optimizer as mod
    from game_data import CHARACTERS, get_friendship_bonus
    from game_data.characters import POTENTIAL_NODES, get_potential_stat_bonus
    from game_data.constants import PARTNER_EXP_TABLE
    from game_data.partners import (
        SIGNATURE_PARTNERS, class_partner_passive, get_partner_passive_stats,
        get_partner_stats, signature_partner)
    from game_data.potential_7 import get_potential_7

    opt = mod.GearOptimizer()
    names = {data["name"]: rid for rid, data in CHARACTERS.items()
             if isinstance(data, dict) and data.get("name")}
    cap = PARTNER_EXP_TABLE[-1][1]
    top = {node.wire: node.max_level for node in POTENTIAL_NODES}
    keys = [key for _stat, key in mod.PARTNER_STAT_KEYS]
    out = [f"optimizer.{name} is {getattr(mod, name)!r}; the maintainer "
           f"asked for {want!r}." for name, want in SPEC.items()
           if getattr(mod, name) != want]
    out.extend(_class_passive_is_shared())

    def static(name):
        return opt._build_char_static(name, 60)

    def passive_of(cs, suffix=""):
        return {key: cs["partner_" + key + suffix] for key in keys}

    def as_keys(stats):
        return {key: stats.get(stat, 0) for stat, key in mod.PARTNER_STAT_KEYS}

    for name in sorted(SIGNATURE_PARTNERS):
        if signature_partner(name)[0] is None:
            out.append(f"SIGNATURE_PARTNERS names {SIGNATURE_PARTNERS[name]!r} "
                       f"for {name}, which partners.py does not have: "
                       f"{name} falls back to the class's shared passive.")

    named = next((n for n in sorted(SIGNATURE_PARTNERS) if n in names), None)
    if named is not None:
        cs = static(named)
        pid, _partner = signature_partner(named)
        lb = mod.UNOWNED_PARTNER_LIMIT_BREAK
        flats = get_partner_stats(pid, cap)
        got = (cs["partner_flat_atk"], cs["partner_flat_def"],
               cs["partner_flat_hp"], passive_of(cs), passive_of(cs, "_cond"))
        want = (flats["atk"], flats["def"], flats["hp"],
                as_keys(get_partner_passive_stats(pid, lb)),
                as_keys(get_partner_passive_stats(pid, lb, conditional=True)))
        if got != want:
            out.append(f"{named}, not owned, carries partner flats and "
                       f"passive {got}, not {SIGNATURE_PARTNERS[named]}'s at "
                       f"level {cap} and limit break {lb}: {want}. See "
                       f"`GearOptimizer._assume_unowned`.")

    plain = next((n for n in sorted(names) if n not in SIGNATURE_PARTNERS),
                 None)
    if plain is not None:
        cs = static(plain)
        cls = CHARACTERS[names[plain]].get("class")
        shared = as_keys(class_partner_passive(cls))
        if (passive_of(cs) != shared or any(passive_of(cs, "_cond").values())
                or not any(shared.values()) or not cs["partner_flat_hp"]):
            out.append(f"{plain}, not owned and named by no "
                       f"SIGNATURE_PARTNERS entry, carries passive "
                       f"{passive_of(cs)} and conditional "
                       f"{passive_of(cs, '_cond')}, not the {cls} 5-star "
                       f"partners' shared {shared} and nothing conditional.")

    for name, rid in sorted(names.items()):
        cs = static(name)
        if (cs["affection_atk"], cs["affection_def"], cs["affection_hp"]) \
                != tuple(get_friendship_bonus(mod.UNOWNED_AFFINITY)):
            out.append(f"{name}, not owned, has Affinity bonus "
                       f"{(cs['affection_atk'], cs['affection_def'], cs['affection_hp'])}, "
                       f"not Affinity {mod.UNOWNED_AFFINITY}'s.")
            break
        nodes = {}
        for node in (50, 60):
            stat, bonus = get_potential_stat_bonus(rid, node, top[node])
            if stat:
                nodes[stat] = nodes.get(stat, 0) + bonus
        pots = {"ATK%": "pot_atk_pct", "DEF%": "pot_def_pct",
                "HP%": "pot_hp_pct", "CRate": "pot_crate",
                "CDmg": "pot_cdmg"}
        if any(cs[key] != nodes.get(stat, 0) for stat, key in pots.items()):
            out.append(f"{name}, not owned, has Potential nodes 5 and 6 at "
                       f"{ {k: cs[k] for k in pots.values()} }, not at their "
                       f"maximum: {nodes}.")
            break

    # Node 7 at its full effect: no check, growth at the cap. Read on a
    # combatant whose node 7 grows, which is where the two can differ.
    growing = next((n for n, rid in sorted(names.items())
                    if any(e.get("per") for e in get_potential_7(rid))), None)
    if growing is not None:
        effects = core.potential_7_effects(get_potential_7(names[growing]))
        want = tuple((g, v + (most if per else 0), (), None, None, None)
                     for g, v, _c, per, _a, most in effects)
        got = static(growing)["potential_7"]
        if got != want:
            out.append(f"{growing}, not owned, has node 7 as {got}, not at "
                       f"its full effect {want}: every check passed and "
                       f"its growth at the cap (`core.potential_7_full`).")
        check = core.potential_7_check(0, 0, 0, 0, 0, 0, 0, 0)
        full = core.potential_7_bonus(got, check)
        if not full or any(v <= 0 for v in full.values()):
            out.append(f"{growing}, not owned, gets {full} from node 7 on a "
                       f"build with no stats at all: its node 7 must not "
                       f"wait for a check.")
    return out
