"""Where the account cannot say, a combatant is optimized with what
`optimizer.UNOWNED_AFFINITY` and its neighbours assume.

Nothing else would notice if it were not: the Optimizer still returns
builds, just scored against a bare base -- no partner, Potential or
Affinity -- which ranks fragments as though flat stats were worth far
more than they are. `docs/game_formulas.md`, §1, says what is assumed:
for a combatant wearing no partner, the assumed partner; for one the
account lacks, that partner, maxed stat nodes, node 7 and Affinity.

A fresh `GearOptimizer` holds no account, so every combatant the game
data has is one it lacks, and this needs no capture.
"""

from ._harness import add_source_to_path

NAME = "a combatant you lack is optimized as built"

# The maintainer's figures, held here as well as in `optimizer.py` on
# purpose: the assertions below read the constants, so without this a
# changed constant would change what they expect along with it.
SPEC = {"UNOWNED_AFFINITY": 20, "ASSUMED_PARTNER_LIMIT_BREAK": 0,
        "ASSUMED_PARTNER_GRADE": 5}


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
                   f"a combatant neither partner table names gets nothing "
                   f"from its assumed partner.")
    return out


def _exception_wins():
    """`assumed_partner` takes `PARTNER_EXCEPTIONS`' partner over
    `SIGNATURE_PARTNERS`'. Tried with an exception added for the
    purpose, since the two tables may agree everywhere they overlap."""
    from game_data import partners
    name = next(n for n in sorted(partners.SIGNATURE_PARTNERS)
                if n not in partners.PARTNER_EXCEPTIONS)
    other = next(p["name"] for p in partners.PARTNERS.values()
                 if isinstance(p, dict) and p.get("grade") == 5
                 and p["name"] != partners.SIGNATURE_PARTNERS[name])
    try:
        partners.PARTNER_EXCEPTIONS[name] = other
        got = partners.assumed_partner(name)[1]
    finally:
        partners.PARTNER_EXCEPTIONS.pop(name, None)
    if not got or got.get("name") != other:
        return [f"with PARTNER_EXCEPTIONS naming {other} for {name}, the "
                f"assumed partner is "
                f"{got.get('name') if got else None}: an exception is the "
                f"pairing to assume over the combatant's own."]
    return []


def run():
    add_source_to_path()
    from optimizer import core, optimizer as mod
    from models import CharacterInfo
    from game_data import CHARACTERS, get_friendship_bonus, partners
    from game_data.characters import POTENTIAL_NODES, get_potential_stat_bonus
    from game_data.constants import PARTNER_EXP_TABLE
    from game_data.potential_7 import get_potential_7

    opt = mod.GearOptimizer()
    names = {data["name"]: rid for rid, data in CHARACTERS.items()
             if isinstance(data, dict) and data.get("name")}
    cap = PARTNER_EXP_TABLE[-1][1]
    lb = mod.ASSUMED_PARTNER_LIMIT_BREAK
    top = {node.wire: node.max_level for node in POTENTIAL_NODES}
    keys = [key for _stat, key in mod.PARTNER_STAT_KEYS]
    out = [f"optimizer.{name} is {getattr(mod, name)!r}; the maintainer "
           f"asked for {want!r}." for name, want in SPEC.items()
           if getattr(mod, name) != want]
    out.extend(_class_passive_is_shared())
    out.extend(_exception_wins())

    unnamed = sorted(set(names) - set(partners.SIGNATURE_PARTNERS)
                     - set(partners.PARTNER_EXCEPTIONS))
    if unnamed:
        out.append(f"neither SIGNATURE_PARTNERS nor PARTNER_EXCEPTIONS "
                   f"names a partner for {unnamed}: they fall back to "
                   f"their class's shared passive, which is for a program "
                   f"not yet updated. Add each one's pairing in "
                   f"game_data/partners.py -- a 5-star's release partner "
                   f"to the first, anyone else to the second.")

    def passive_of(cs, suffix=""):
        return {key: cs["partner_" + key + suffix] for key in keys}

    def as_keys(stats):
        return {key: stats.get(stat, 0) for stat, key in mod.PARTNER_STAT_KEYS}

    def partner_of(cs):
        return (cs["partner_flat_atk"], cs["partner_flat_def"],
                cs["partner_flat_hp"], passive_of(cs), passive_of(cs, "_cond"))

    def assumed_for(name):
        pid, _partner = partners.assumed_partner(name)
        flats = partners.get_partner_stats(pid, cap)
        return (flats["atk"], flats["def"], flats["hp"],
                as_keys(partners.get_partner_passive_stats(pid, lb)),
                as_keys(partners.get_partner_passive_stats(
                    pid, lb, conditional=True)))

    # Lacked: one an exception names, one only its own entry names.
    for pick in (next((n for n in sorted(partners.PARTNER_EXCEPTIONS)
                       if n in names), None),
                 next((n for n in sorted(partners.SIGNATURE_PARTNERS)
                       if n in names
                       and n not in partners.PARTNER_EXCEPTIONS), None)):
        if pick is None:
            continue
        got, want = partner_of(opt._build_char_static(pick, 60)), \
            assumed_for(pick)
        if got != want:
            out.append(f"{pick}, not owned, carries partner flats and "
                       f"passive {got}, not "
                       f"{partners.assumed_partner(pick)[1]['name']}'s at "
                       f"level {cap} and limit break {lb}: {want}. See "
                       f"`GearOptimizer._assume_partner`.")

    # Owned, wearing no partner: the same assumption, and nothing else
    # of the account's own replaced.
    owned = sorted(names)[0]
    opt.character_info[owned] = CharacterInfo(
        res_id=names[owned], name=owned, friendship_bonus=(1, 2, 3))
    try:
        cs = opt._build_char_static(owned, 60)
    finally:
        opt.character_info.pop(owned)
    if partner_of(cs) != assumed_for(owned) or (
            cs["affection_atk"], cs["affection_def"],
            cs["affection_hp"]) != (1, 2, 3) or cs["pot_atk_pct"] \
            or cs["pot_def_pct"] or cs["pot_hp_pct"] or cs["potential_7"]:
        out.append(f"{owned}, owned and wearing no partner, carries "
                   f"partner {partner_of(cs)} and Affinity "
                   f"{(cs['affection_atk'], cs['affection_def'], cs['affection_hp'])}"
                   f": the assumed partner, {assumed_for(owned)}, with the "
                   f"account's own Affinity (1, 2, 3) and no Potential.")

    # Named by neither table: the class's 5-star flats and shared passive.
    plain = sorted(names)[-1]
    saved = (partners.SIGNATURE_PARTNERS.pop(plain, None),
             partners.PARTNER_EXCEPTIONS.pop(plain, None))
    try:
        cs = opt._build_char_static(plain, 60)
    finally:
        for table, value in zip((partners.SIGNATURE_PARTNERS,
                                 partners.PARTNER_EXCEPTIONS), saved):
            if value is not None:
                table[plain] = value
    cls = CHARACTERS[names[plain]].get("class")
    shared = as_keys(partners.class_partner_passive(cls))
    flats = partners.class_partner_stats(cls, mod.ASSUMED_PARTNER_GRADE, cap)
    if partner_of(cs) != (flats["atk"], flats["def"], flats["hp"], shared,
                          as_keys({})):
        out.append(f"{plain}, named by neither partner table, carries "
                   f"{partner_of(cs)}, not the {cls} 5-star partners' "
                   f"flats {flats} and shared passive {shared}, with "
                   f"nothing conditional.")

    for name, rid in sorted(names.items()):
        cs = opt._build_char_static(name, 60)
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
        # Node 7 taken, and left to the build as for anyone: the score
        # works out its check and growth.
        want = core.potential_7_effects(get_potential_7(rid))
        if cs["potential_7"] != want:
            out.append(f"{name}, not owned, has node 7 as "
                       f"{cs['potential_7']}, not taken as the score works "
                       f"it out: {want}.")
            break
    return out
