"""What levelling the Memory Fragments held would cost in Units.

Two things are paid for: every fragment up to `LEVEL_FLOOR`, which takes
Units and Particles of Memory alone, and then as many fragments as the
Cores of Memory held can take to their top level. Particles are not
counted: the sum is about Units.

**The Cores go where they max the most fragments**: fragments needing
the fewest first, which is the ones already furthest along. What is left
short of a whole fragment goes on single levels, so the Cores are used
up as far as any level can take them.

`game_client.known_fragment_costs` gives the costs and
`known_limits()["unit_drop"]` what a run pays. No Tk and no managers:
this takes data and returns data.
"""

from collections import namedtuple

LEVEL_FLOOR = 3
# The x6 multiplier: a run of Growth - Unit is this many drops.
RUN_DROPS = 6
UNITS = 2000001
CORE_OF_MEMORY = 3200002

# `needed`: the Units the sum comes to. `spare`: the Units held less
# that, negative where short. `runs`: the x6 runs covering a shortfall,
# None with none, or with no figure for what a run pays.
Reading = namedtuple("Reading", "needed spare runs")


def units_needed(fragments, cores, costs):
    """The Units the sum comes to for `fragments`, (rarity tier, level)
    pairs, with `cores` Cores of Memory to spend. A rarity `costs` does
    not list costs nothing."""
    total, pending = 0, []
    for tier, level in fragments:
        steps = costs.get(tier) or []
        total += sum(step[0] for step in steps[level:LEVEL_FLOOR])
        left = steps[max(level, LEVEL_FLOOR):]
        if left:
            pending.append(left)
    pending.sort(key=lambda left: sum(step[1] for step in left))
    partly = []
    for left in pending:
        need = sum(step[1] for step in left)
        if need <= cores:
            cores -= need
            total += sum(step[0] for step in left)
        else:
            partly.append(left)
    for left in partly:
        for units, need in left:
            if need > cores:
                break
            cores -= need
            total += units
    return total


def reading(fragments, held, costs, unit_drop):
    """A `Reading` of `fragments` against `held`, {res_id: amount}.
    `unit_drop` is what one drop of a run pays, or None."""
    needed = units_needed(fragments, held.get(CORE_OF_MEMORY, 0), costs)
    spare = held.get(UNITS, 0) - needed
    run = (unit_drop or 0) * RUN_DROPS
    return Reading(needed, spare, -(spare // run) if spare < 0 and run
                   else None)
