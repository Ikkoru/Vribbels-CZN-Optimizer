"""The potential tree: ten nodes, two numberings, one list.

`POTENTIAL_NODES` carries the display order, the game's numbering, the
wire's numbering, the maxima and the descriptions. Four things there
fail quietly:

* **The two numberings disagree.** Node 5.2 is `52` on the wire and node
  6 is `60`; a `shown` and a `wire` that drift apart put one node's
  level under another's name, and every line still reads like a line.
* **The maximum is summed, not stated.** `POTENTIAL_MAX_TOTAL` is what
  the Combatants tab's `Nodes` column counts against, so a wrong max
  level anywhere makes every combatant's reading wrong by the same
  amount -- which looks consistent.
* **Only two nodes carry a stat.** A third marked `stat` would send
  `get_potential_stat` looking for a stat no character names and draw
  `(?)` for the whole roster.
* **A per-character override keyed by the wrong res_id** silently does
  nothing: the node just reads its ordinary description.

No Tk: the tables are all this needs. The three RENDERED shapes are
checked in `check_tabs_build`, which has a built panel to read them off.
"""

from ._harness import add_source_to_path

NAME = "potential nodes"

# The wire numbers, in the display order, from `docs/game_formulas.md`
# §1. Restated here on purpose: this is the copy that would catch the
# table being edited into disagreeing with the doc.
WIRE_ORDER = (10, 20, 30, 31, 40, 50, 51, 52, 60, 70)
STAT_NODES = (50, 60)
MAX_TOTAL = 45


def run():
    add_source_to_path()
    from game_data import POTENTIAL_MAX_TOTAL, POTENTIAL_NODES
    from game_data.characters import (
        CHARACTERS, POTENTIAL_NODE_OVERRIDES, get_potential_node_does,
    )

    failures = []

    wires = tuple(node.wire for node in POTENTIAL_NODES)
    if wires != WIRE_ORDER:
        failures.append(
            f"POTENTIAL_NODES runs {wires}, not {WIRE_ORDER}. The wire "
            f"numbers are what a snapshot keys its levels by, so a node "
            f"out of place shows one node's level under another's name."
        )

    shown = [node.shown for node in POTENTIAL_NODES]
    if len(set(shown)) != len(shown):
        failures.append(f"two nodes are both shown as one of {shown}")

    # The game's number and the wire's are related but not equal, and
    # the relation is what a reader is most likely to "fix".
    for node in POTENTIAL_NODES:
        expect = node.shown.replace(".", "")
        if node.wire != int(expect + "0" * (2 - len(expect))):
            failures.append(
                f"node {node.shown} is wire {node.wire}, which is not what "
                f"its own name encodes. See docs/game_formulas.md §1."
            )

    if POTENTIAL_MAX_TOTAL != MAX_TOTAL:
        failures.append(
            f"the tree's levels sum to {POTENTIAL_MAX_TOTAL}, not "
            f"{MAX_TOTAL}. Every `Nodes` reading is counted against it, so "
            f"they would all be wrong by the same amount and look right."
        )

    stat = tuple(node.wire for node in POTENTIAL_NODES if node.stat)
    if stat != STAT_NODES:
        failures.append(
            f"{stat} are marked as stat nodes, not {STAT_NODES}. Only "
            f"those two name a stat on a CHARACTERS entry; another one "
            f"would draw `(?)` for every combatant."
        )

    # A stat node states no description of its own -- it reads its stat
    # instead -- and every other node needs one to say what it does.
    for node in POTENTIAL_NODES:
        if node.stat and node.does:
            failures.append(
                f"node {node.shown} is a stat node and also states "
                f"{node.does!r}. The stat is read per character and would "
                f"overwrite it."
            )

    for res_id, overrides in POTENTIAL_NODE_OVERRIDES.items():
        if res_id not in CHARACTERS:
            failures.append(
                f"POTENTIAL_NODE_OVERRIDES names res_id {res_id}, which is "
                f"not a character. Its wording would never be reached."
            )
        for wire in overrides:
            if wire not in wires:
                failures.append(
                    f"res_id {res_id} overrides node {wire}, which is not "
                    f"in the tree."
                )
            node = next((n for n in POTENTIAL_NODES if n.wire == wire), None)
            if node is not None and node.stat:
                failures.append(
                    f"res_id {res_id} overrides the wording of stat node "
                    f"{wire}, whose line is built from its stat instead."
                )
            if node is not None:
                got = get_potential_node_does(res_id, node)
                if got != overrides[wire]:
                    failures.append(
                        f"res_id {res_id} node {wire} reads {got!r}, not its "
                        f"override {overrides[wire]!r}"
                    )

    return failures
