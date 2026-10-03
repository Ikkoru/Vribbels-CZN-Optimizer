"""Each combatant's Potential 7: node 7's bonus, and the stat check that
gates it.

POTENTIAL_7
===========

res_id -> a tuple of effects, each a dict:

    grants  what the effect raises (below)
    value   how much, in percent; the whole of it once the check passes
    stat    the check's stat, by its Have-at-least name: ATK, DEF, HP,
            Ego, CRate, CDmg, Extra DMG%, DoT%. A tuple is ANY OF, with
            `at` a tuple of the same length beside it. Absent: the
            effect always applies.
    at      the threshold; met at `at` or higher
    per, add, max
            growth past the threshold: +`add` for every `per` of the
            stat above `at`, `max` at most. **Continuous, not stepped**:
            Magna's 324 DEF against 300, +2 per 10, is +4.8 on the
            server, not +4
    start   True where the bonus lands at the start of battle, so the
            sheet a battle's entry states does not carry it (Orlea,
            Tiphera). The score counts it all the same: "allies"
            includes the combatant
    card    what an unpriced effect acts on, for display
    fill    for an any-of check, the stat the Optimizer's Fill buttons
            write (Orlea's DEF): no single minimum stands for "ATK or
            DEF", so the maintainer picks the one her builds go for

`grants`, and where each lands (`docs/game_formulas.md` §1):

    ATK%, DEF%             the inner %, as nodes 5 and 6
    CRate, CDmg, Extra DMG%
                           added to the final stat
    Element%               the combatant's own attribute's damage,
                           beside the fragments' element main stat
    card, event, weakness  not priced: one card's damage, shield or
                           heal; an in-battle trigger; Weakness Damage

**The check reads the value before any Potential 7 bonus**, as the
server's `potential_base_status` does: Rita's +10% ATK at 800 is in her
inner % at 902 ATK and absent at 755, where it would have carried her
past 800. Each line follows the e7bot wiki's text, which the maintainer
checked against the game.
"""

# What the score prices, and where `core.compute_build_stats` puts it.
PRICED = ("ATK%", "DEF%", "CRate", "CDmg", "Extra DMG%", "Element%")
# What it keeps only for the thresholds and the label.
UNPRICED = ("card", "event", "weakness")
GRANTS = PRICED + UNPRICED
# The stats a check can read: the Have-at-least names, whose comparison
# values are the check's own (`core.meets_have_at_least`).
CHECK_STATS = ("ATK", "DEF", "HP", "Ego", "CRate", "CDmg", "Extra DMG%",
               "DoT%")


def _grow(grants, value, stat, at, per, add, most, **more):
    """One effect with growth past its threshold."""
    return dict(grants=grants, value=value, stat=stat, at=at, per=per,
                add=add, max=most, **more)


POTENTIAL_7 = {
    1055: (_grow("Element%", 5, "DEF", 300, 10, 2, 10),),        # Adelheid
    1017: (                                                     # Amir
        {"grants": "card", "value": 10, "card": "Metallization"},
        {"grants": "card", "value": 10, "card": "Metallization",
         "stat": "DEF", "at": 300},
    ),
    1012: ({"grants": "ATK%", "value": 10, "stat": "ATK",        # Anika
            "at": 500},),
    30115: (_grow("Element%", 5, "ATK", 600, 20, 2, 10),),       # Arabella
    1040: (                                                     # Beryl
        {"grants": "card", "value": 10, "card": "Opening Found"},
        {"grants": "card", "value": 10, "card": "Charged Shot",
         "stat": "CDmg", "at": 230},
    ),
    1049: (                                                     # Cassius
        {"grants": "event", "value": 0,
         "card": "1 Morale for 1 turn on completing a Quest"},
        {"grants": "event", "value": 0,
         "card": "1 Fortitude for 1 turn on completing a Quest",
         "stat": "HP", "at": 700},
    ),
    1060: (_grow("card", 5, "ATK", 600, 10, 1, 10,               # Chizuru
                 card="Bind cards"),),
    1061: (_grow("Extra DMG%", 4, "CRate", 10, 5, 1, 8),),       # Diana
    30048: (_grow("Element%", 5, "ATK", 600, 20, 2, 10),),       # Fei
    1062: (                                                     # Haru
        {"grants": "card", "value": 10, "card": "Anchor Shot"},
        {"grants": "card", "value": 10, "card": "Anchor Shot",
         "stat": "ATK", "at": 600},
    ),
    30093: (_grow("Element%", 5, "ATK", 600, 20, 2, 10),),       # Heidemarie
    30113: (                                                    # Hilde
        {"grants": "Element%", "value": 7},
        {"grants": "Element%", "value": 8, "stat": "Extra DMG%", "at": 6},
    ),
    1043: (_grow("Extra DMG%", 4, "ATK", 700, 50, 1, 8),),       # Hugo
    1064: (_grow("CDmg", 5, "ATK", 600, 40, 1, 10),),            # Kayron
    1008: (                                                     # Khalipe
        {"grants": "card", "value": 10,
         "card": "Vulture Ejection (damage and shield)"},
        {"grants": "card", "value": 20, "card": "Vulture Ejection (damage)",
         "stat": "ATK", "at": 700},
        {"grants": "card", "value": 20, "card": "Vulture Ejection (shield)",
         "stat": "DEF", "at": 300},
    ),
    1021: (                                                     # Lucas
        {"grants": "card", "value": 5, "card": "Launcher Bullet"},
        {"grants": "card", "value": 5, "card": "Launcher Bullet",
         "stat": "CDmg", "at": 240},
    ),
    1004: (_grow("card", 3, "CRate", 40, 5, 2, 12,               # Luke
                 card="Handgun Bullet"),),
    1010: (_grow("Element%", 5, "DEF", 300, 10, 2, 10),),        # Magna
    1028: (                                                     # Maribell
        {"grants": "card", "value": 5, "card": "Basic and Signature cards"},
        {"grants": "card", "value": 5, "card": "Basic and Signature cards",
         "stat": "HP", "at": 800},
    ),
    1027: (_grow("weakness", 4, "ATK", 600, 50, 1, 8,            # Mei Lin
                 card="Weakness Damage"),),
    1039: (_grow("card", 10, "Ego", 40, 5, 2, 20,                # Mika
                 card="Source of Water (recovery)"),),
    1052: (                                                     # Narja
        {"grants": "card", "value": 10, "card": "Voracity"},
        {"grants": "card", "value": 20, "card": "Predation",
         "stat": "DEF", "at": 300},
    ),
    1003: (                                                     # Nia
        {"grants": "card", "value": 30, "card": "Elasticity (heal)"},
        {"grants": "card", "value": 20, "card": "Elasticity (heal)",
         "stat": "Ego", "at": 70},
    ),
    30047: (_grow("Element%", 5, "DEF", 300, 10, 2, 10),),       # Nine
    30117: (                                                    # Olga
        {"grants": "Element%", "value": 7},
        {"grants": "Element%", "value": 8, "stat": "DoT%", "at": 6},
    ),
    1024: (                                                     # Orlea
        {"grants": "CRate", "value": 6, "stat": ("ATK", "DEF"),
         "at": (700, 300), "start": True, "fill": "DEF"},
    ),
    1050: (                                                     # Owen
        {"grants": "ATK%", "value": 4},
        {"grants": "DEF%", "value": 4},
        {"grants": "ATK%", "value": 4, "stat": "HP", "at": 700},
        {"grants": "DEF%", "value": 4, "stat": "HP", "at": 700},
    ),
    1056: (_grow("card", 10, "ATK", 550, 10, 1, 20,              # Rei
                 card="Predator's Blade"),),
    1041: (                                                     # Renoa
        {"grants": "card", "value": 5, "card": "Dirge Bullet"},
        {"grants": "card", "value": 10, "card": "Dirge Bullet",
         "stat": "CRate", "at": 60},
    ),
    1018: (_grow("CRate", 5, "ATK", 600, 40, 1, 10),),           # Rin
    30097: ({"grants": "ATK%", "value": 10, "stat": "ATK",       # Rita
             "at": 800},),
    1005: (                                                     # Selena
        {"grants": "Element%", "value": 4},
        {"grants": "Element%", "value": 4, "stat": "Extra DMG%", "at": 30},
    ),
    30075: (                                                    # Sereniel
        {"grants": "Element%", "value": 10, "stat": "CRate", "at": 20},
        {"grants": "Element%", "value": 5, "stat": "CRate", "at": 40},
    ),
    1069: (_grow("Element%", 5, "ATK", 600, 20, 1, 10),),        # Tenebria
    30084: ({"grants": "CDmg", "value": 10, "stat": "DEF",       # Tiphera
             "at": 300, "start": True},),
    1009: (                                                     # Tressa
        {"grants": "Element%", "value": 4},
        {"grants": "Element%", "value": 4, "stat": "DoT%", "at": 30},
    ),
    1033: (_grow("card", 5, "ATK", 700, 40, 1, 10,               # Veronica
                 card="Ballista rounds"),),
    1057: (_grow("card", 5, "ATK", 600, 20, 1, 5,                # Yuki
                 card="Flash Slash and Iceberg Cleave"),),
}

# Node 7 as it stood before a balance patch rewrote it: res_id -> ((the
# first second the new one was live, UTC, the effects before it), ...),
# oldest first. The Optimizer scores today's only; this is what a sheet
# the server stated before the patch is held to, since the readings
# keep sheets from both sides of it (`base_stats_store.formula_gaps`).
POTENTIAL_7_BEFORE = {
    30075: ((1790730000, (                          # Sereniel, to 2026-09-30
        {"grants": "card", "value": 10, "card": "Homing Laser",
         "stat": "CRate", "at": 30},
        {"grants": "card", "value": 5, "card": "Homing Laser",
         "stat": "CRate", "at": 60},
    )),),
}


def get_potential_7(res_id: int, when=None) -> tuple:
    """The combatant's Potential 7 effects; empty where none is known.

    `when`, an epoch second, asks for the ones live then: a sheet read
    before a patch rewrote a node 7 is held to the one it was read
    under (`POTENTIAL_7_BEFORE`).
    """
    if when is not None:
        for until, effects in POTENTIAL_7_BEFORE.get(res_id, ()):
            if when < until:
                return effects
    return POTENTIAL_7.get(res_id, ())


def priced_in_full(res_id: int) -> bool:
    """Whether the score prices every effect of the combatant's
    Potential 7. Meeting its checks is then the score's own business,
    and a Have-at-least minimum for them only hides the builds that
    miss one."""
    effects = get_potential_7(res_id)
    return bool(effects) and all(e.get("grants") in PRICED
                                 for e in effects)


def conditions(effect: dict) -> tuple:
    """((stat, threshold), ...), any one of which meets the check; empty
    for an effect that always applies."""
    stat = effect.get("stat")
    if stat is None:
        return ()
    if isinstance(stat, tuple):
        return tuple(zip(stat, effect.get("at") or ()))
    return ((stat, effect.get("at")),)


def _filled_condition(effect: dict):
    """The one (stat, threshold) the Optimizer's Fill buttons write: the
    check's own, or an any-of check's `fill` one; None where there is
    no such one."""
    conds = conditions(effect)
    if len(conds) > 1:
        conds = tuple(c for c in conds if c[0] == effect.get("fill"))
    return conds[0] if len(conds) == 1 else None


def switch_on_at(effect: dict):
    """(stat, the least value of it that earns any of `effect`): its
    threshold. None as for `full_at`."""
    return _filled_condition(effect)


def full_at(effect: dict):
    """(stat, the least value of it that earns `effect` in full): the
    threshold, or where the growth past it stops. An any-of check
    answers with its `fill` stat's threshold; None for an effect with
    no check, or an any-of one with no `fill`."""
    found = _filled_condition(effect)
    if found is None:
        return None
    stat, at = found
    if effect.get("per"):
        return stat, at + effect["per"] * effect["max"] / effect["add"]
    return stat, at


def potential_7_minimums(res_id: int) -> dict:
    """{Have-at-least stat: the least value that earns every effect of
    the combatant's Potential 7 in full}."""
    out = {}
    for effect in get_potential_7(res_id):
        full = full_at(effect)
        if full is None:
            continue
        stat, least = full
        out[stat] = max(out.get(stat, 0), least)
    return out


def potential_7_switch_ons(res_id: int) -> dict:
    """{Have-at-least stat: the least value that earns any part of the
    combatant's Potential 7 that checks it} -- the lowest threshold on
    each stat, where `potential_7_minimums` takes the highest top."""
    out = {}
    for effect in get_potential_7(res_id):
        found = switch_on_at(effect)
        if found is None:
            continue
        stat, at = found
        out[stat] = min(out.get(stat, at), at)
    return out


# What the Combatants tab's node-7 line says a Potential 7 raises.
_LABELS = {"ATK%": "ATK%", "DEF%": "DEF%", "CRate": "Crit%",
           "CDmg": "CDMG%", "Extra DMG%": "Extra%", "card": "Card",
           "event": "Quest", "weakness": "Weakness"}


def potential_7_label(res_id: int, attribute: str = "") -> str:
    """A few words for what the combatant's Potential 7 raises: `Void%`,
    `ATK%, DEF%`, `Card`. Empty where none is known."""
    seen = []
    for effect in get_potential_7(res_id):
        grants = effect["grants"]
        if grants == "Element%":
            word = f"{attribute}%" if attribute else "Element%"
        else:
            word = _LABELS.get(grants, grants)
        if effect.get("start"):
            word = f"Team {word}"
        if word not in seen:
            seen.append(word)
    return ", ".join(seen)
