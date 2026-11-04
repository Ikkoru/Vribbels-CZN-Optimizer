"""The Units rows under the Memory Fragments tab's Main Stats add up.

Nothing else reads these figures, so a wrong one is believed: a level
counted twice, a Core spent on a fragment already maxed, a shortfall
rounded down to a run too few. The costs are the shipped table's where
the case says so, and the rest synthetic.
"""

from ._harness import add_source_to_path

NAME = "the Units rows add up"

# Rarity tier 4's shape: Units and Cores to leave each level.
COSTS = {3: [[4, 0], [6, 0], [8, 0], [13, 2]],
         4: [[10, 0], [20, 0], [30, 0], [100, 4], [200, 6]],
         2: [[1, 0], [1, 0], [1, 0]]}


def run():
    add_source_to_path()
    import fragment_costs as fc
    import game_client
    out = []
    for fragments, cores, want, why in (
            ([(4, 0)], 0, 60, "a fragment is paid up to level 3"),
            ([(4, 1), (4, 2)], 0, 80, "only the levels left are paid"),
            ([(4, 3), (4, 5)], 0, 0, "nothing is paid past level 3 without "
             "a Core, nor on a maxed fragment"),
            ([(2, 0)], 0, 3, "a rarity topping out at 3 takes no Core"),
            ([(4, 3)], 10, 300, "ten Cores max a fragment from level 3"),
            ([(4, 0)], 10, 360, "a fragment under 3 can be maxed after it"),
            ([(4, 3), (4, 4), (4, 4)], 12, 400, "the Cores go to the fragment "
             "needing fewest, which maxes the most"),
            ([(3, 3), (4, 3)], 12, 313, "a rarity's own Core cost counts"),
            ([(4, 3), (4, 3)], 14, 400, "what is left short of a whole "
             "fragment still buys a level"),
            ([(4, 3)], 3, 0, "a Core short of a level buys nothing"),
            ([(9, 0)], 5, 0, "a rarity the table lacks costs nothing")):
        got = fc.units_needed(fragments, cores, COSTS)
        if got != want:
            out.append(f"{fragments} with {cores} Cores comes to {got} "
                       f"Units, not {want}: {why}")
    for held, drop, want, why in (
            ({fc.UNITS: 100}, 10, (60, 40, None), "Units over the sum are "
             "spare, and no run is wanted"),
            ({fc.UNITS: 60}, 10, (60, 0, None), "exactly enough is not short"),
            ({fc.UNITS: 0}, 10, (60, -60, 1), "a shortfall of one whole x6 "
             "run is that run"),
            ({fc.UNITS: 0}, 9, (60, -60, 2), "a part of a run is a whole "
             "run: fewer would leave the player short"),
            ({}, None, (60, -60, None), "no figure for a run says no runs")):
        got = tuple(fc.reading([(4, 0)], held, COSTS, drop))
        if got != want:
            out.append(f"holding {held} with drops of {drop} reads {got}, "
                       f"not {want}: {why}")
    spent = fc.reading([(4, 3)], {fc.CORE_OF_MEMORY: 10}, COSTS, None).needed
    if spent != 300:
        out.append("the Cores held were not read: Core of Memory is "
                   f"{fc.CORE_OF_MEMORY}")
    shipped = game_client.known_fragment_costs().get(4) or []
    if len(shipped) != 5 or [cost[1] for cost in shipped[:3]] != [0, 0, 0] \
            or not all(cost[1] for cost in shipped[3:]):
        out.append(f"the shipped Legendary costs read {shipped}: five "
                   f"levels, the first three taking no Core. "
                   f"`game_client.fragment_stats`")
    if not game_client.known_limits().get("unit_drop"):
        out.append("no figure for a Growth - Unit - Difficulty 6 drop: the "
                   "shortfall's row names no runs. "
                   "`game_client.limits`' `unit_drop`")
    return out


FAULTS = [
    ("the floor's levels paid past it", "fragment_costs:units_needed",
     "steps[level:LEVEL_FLOOR]", "steps[level:]",
     "nothing is paid past level 3"),
    ("Cores spent in any order", "fragment_costs:units_needed",
     "    pending.sort(key=lambda left: sum(step[1] for step in left))\n", "",
     "the Cores go to the fragment needing"),
    ("a whole fragment or nothing", "fragment_costs:units_needed",
     "    for left in partly:\n", "    for left in ():\n",
     "short of a whole"),
    ("runs rounded down", "fragment_costs:reading",
     "-(spare // run) if spare < 0", "(-spare // run) if spare < 0",
     "a part of a run is a whole"),
    ("exactly enough read as short", "fragment_costs:reading",
     "if spare < 0 and run", "if spare <= 0 and run",
     "exactly enough is not short"),
    ("Cores in the level costs missed", "game_client:known_fragment_costs",
     "out[int(tier)] = steps", "out[int(tier)] = [[s[0], 0] for s in steps]",
     "the shipped Legendary costs"),
]
