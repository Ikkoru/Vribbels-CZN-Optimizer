"""A synthetic inventory for `check_optimizer_parity`: seeded, so every
run searches the same combos, and built from nothing captured, so the
check runs on a fresh clone.

It is shaped to reach what parity can break on. Each property is
asserted by the check rather than hoped for -- see `PROPERTIES` there:

* **the parallel path** -- more combos than `PARALLEL_MIN_COMBOS`;
* **the in-flight trim** -- more surviving builds than `max_results` x
  10, so both paths cut their survivor lists many times over;
* **exact ties** -- every slot's strongest fragment has a twin with
  another id, so the top builds tie in groups and their order is the
  tie-break's alone;
* **every set type** -- a 4-piece and a 2-piece conditional set and a
  2-piece unconditional one, all selected, with flex slots;
* **element mains** -- Slot V carries the combatant's element, another
  element, and ATK%;
* **Potential 7** -- the combatant has node 7, whose grant rises at
  every 5 CRate past 10, and the fragments' CRate spreads the builds
  across those steps;
* **Have at Least** -- a CRate minimum some builds fail.

Values follow the inventory's own shape -- a Legendary at level 5 has
its main stat at its usual value and four substats from three first
rolls, a fourth added and four upgrades -- but no fragment is copied.
"""

import json
import random

SEED = 20261005
# Diana: Passion, and a Potential 7 that grows with CRate.
COMBATANT = 1061
COMBATANT_NAME = "Diana"
NODE_7 = "[10617001]"
# Fragments a slot offers: its ace, the ace's twin, and the rest drawn.
PER_SLOT = 8
LEVEL = 5
RARITY = 4
# Sets: Spark of Passion (4-piece, conditional), Seth's Scarab (2-piece,
# conditional), Black Wing (2-piece, unconditional), and one not
# selected.
SPARK, SCARAB, WING, OTHER = 18, 10, 9, 23
DRAWN_SETS = (SPARK, SPARK, SCARAB, SCARAB, WING, OTHER)
# Each slot's main stats, at a level-5 Legendary's usual value. The
# first is the ace's.
MAINS = {
    1: (("S_ATK_INC_ADD_OUT", 22.0),),
    2: (("S_DEF_INC_ADD_OUT", 22.0),),
    3: (("S_HP_INC_ADD_OUT", 36.65),),
    4: (("S_ATK_INC_RATE_OUT", 25.0), ("S_CRI_INC_ADD", 27.0),
        ("S_CRI_DMG_RATE_INC_ADD", 40.8)),
    5: (("S_RED_DMG_RATE_INC_ADD", 16.0), ("S_BLUE_DMG_RATE_INC_ADD", 16.0),
        ("S_ATK_INC_RATE_OUT", 25.0)),
    6: (("S_ATK_INC_RATE_OUT", 25.0), ("S_DEF_INC_RATE_OUT", 25.0)),
}
# Substats a fragment may roll, and the range of one roll of each.
SUBSTATS = {
    "S_ATK_INC_ADD_OUT": (5.0, 8.0), "S_ATK_INC_RATE_OUT": (0.8, 1.3),
    "S_ADDI_ATK_DMG_RATE_INC_ADD": (2.7, 3.4),
    "S_DEF_INC_ADD_OUT": (3.0, 5.0), "S_DEF_INC_RATE_OUT": (0.8, 1.3),
    "S_HP_INC_ADD_OUT": (10.0, 12.0), "S_HP_INC_RATE_OUT": (0.8, 1.3),
    "S_CRI_INC_ADD": (1.2, 2.0), "S_CRI_DMG_RATE_INC_ADD": (2.4, 4.0),
    "S_CHARGING_POWER_INC_ADD": (2.0, 5.0),
}
# What an ace rolls: its upgrades go to ATK%, and its one CRate roll
# leaves the aces' build in Potential 7's first step, so builds that
# trade an ace for CRate climb past it and builds that trade CRate
# away fall below it.
ACE_SUBSTATS = ("S_ATK_INC_RATE_OUT", "S_CRI_INC_ADD",
                "S_CRI_DMG_RATE_INC_ADD", "S_ADDI_ATK_DMG_RATE_INC_ADD")
FIRST_ID = 900_000_000

# The run the check makes against it.
SETTINGS = {
    "sets_selected": [SPARK, SCARAB, WING],
    "max_flex_slots": 2,
    "set_effect_pcts": {str(SPARK): 100, str(SCARAB): 50},
    "extra_pct": 40,
    "have_at_least": {"CRate": 8},
    "max_results": 100,
    "top_percent": 100,
    "optimize_for_level": 60,
}


def _roll(rng, stat):
    low, high = SUBSTATS[stat]
    return round(rng.uniform(low, high), 1)


def _fragment(rng, ident, slot, set_id, main, substats, upgrades):
    """One fragment as the capture files it: `stat_list` holds the
    main stat, then three first rolls (type 1), a fourth substat added
    (type 2), and each upgrade (type 3) on the substat it went to."""
    stats = [{"slot": 0, "stat": main[0], "type": 0, "value": main[1]}]
    for place, stat in enumerate(substats, start=1):
        stats.append({"slot": place, "stat": stat,
                      "type": 1 if place < 4 else 2,
                      "value": _roll(rng, stat)})
    for place in upgrades:
        stat = substats[place - 1]
        stats.append({"slot": place, "stat": stat, "type": 3,
                      "value": _roll(rng, stat)})
    return {"id": ident, "res_id": int("11%d%d%03d" % (slot, RARITY, set_id)),
            "char_res_id": 0, "level": LEVEL, "lock": 0,
            "stat_list": stats}


def _level_60_exp():
    """The least experience the level table reads as 60."""
    from optimizer.optimizer import get_level_from_exp
    low, high = 0, 10_000_000
    while low < high:
        middle = (low + high) // 2
        if get_level_from_exp(middle) >= 60:
            high = middle
        else:
            low = middle + 1
    return low


def build():
    """The synthetic snapshot, as the dict a capture writes."""
    rng = random.Random(SEED)
    items, ident = [], FIRST_ID
    for slot in sorted(MAINS):
        ace_main = MAINS[slot][0]
        ace = _fragment(rng, ident, slot, SPARK, ace_main, ACE_SUBSTATS,
                        (1, 1, 1, 2))
        twin = dict(ace, id=ident + 1)
        items += [ace, twin]
        ident += 2
        for drawn, set_id in enumerate(DRAWN_SETS[:PER_SLOT - 2]):
            # Mains in turn rather than drawn, so every one a slot has
            # is on offer whatever the stream gives the rest.
            main = MAINS[slot][drawn % len(MAINS[slot])]
            pool = [s for s in SUBSTATS if s != main[0]]
            substats = rng.sample(pool, 4)
            upgrades = [rng.randint(1, 4) for _ in range(4)]
            items.append(_fragment(rng, ident, slot, set_id, main,
                                   substats, upgrades))
            ident += 1
    combatant = {"res_id": COMBATANT, "exp": _level_60_exp(), "ascend": 5,
                 "limit_break": 0, "friendship_reward_index": 1,
                 "partner_id": 0, "potential_node_ids": NODE_7}
    return {"capture_time": "parity fixture",
            "inventory": {"piece_items": items},
            "characters": {"characters": [combatant]}}


def write(path):
    """Write the fixture to `path`, for `GearOptimizer.load_data`."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build(), f)
    return path
