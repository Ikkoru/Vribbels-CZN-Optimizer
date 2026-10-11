"""The Memory Fragment sets' wordings against the game client's.

A set's `bonus` in `game_data/sets.py` is the maintainer's own short
wording of the game's text, and a balance patch that changes a set's
figures changes nothing there: the tooltip goes on stating the old
ones. So every wording is held to the game's figures, as of the copy
the program ships (`game_data/from_client.py`), and where the installed
client is a build ahead, to that too -- naming each set the patch
touched, and whether it moved only the figures (the wording wants new
figures) or reworded the effect (the wording wants rewriting).

A set with no wording of its own, or none in `sets.py` at all, shows
the game's words, and each is noted so the maintainer can write one.

Where a client is installed, its node 7s are held to
`game_data/potential_7.py`, and its node 7 and 5.1 texts to their
data, `TEXT_FIXES` applied (`python docs/client_tables.py --audit`
gives the same lines). Each is a FAILURE, not a note: a patch that
rewrites a node's effect, or the text a fix corrects, has to be seen
the run after it lands -- the fix may now be wrong, or the server may
be doing something none of the program's readings has shown.
"""

import importlib.util

from ._harness import REPO_ROOT, add_source_to_path, note

NAME = "set wordings and Potentials 7 and 5.1 against the game client"


def _tool():
    """`docs/client_tables.py`, which holds the comparisons."""
    spec = importlib.util.spec_from_file_location(
        "client_tables", REPO_ROOT / "docs" / "client_tables.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def _comparisons_report(tool):
    """Each comparison speaks up about a fault put into a copy of the
    data: a wording's figure, a plain set's value, a reworded effect and
    one whose figures alone moved. Returns complaints."""
    from game_data import SETS
    out = []
    effects = {6: ("A Set", 4, "+35% Critical Damage of 1-cost cards", "",
                   None),
               9: ("B Set", 2, "+12% Attack", "S_ATK_INC_RATE_OUT", 12)}
    saved = {k: SETS.get(k) for k in effects}
    try:
        SETS[6] = {"name": "A Set", "pieces": 4,
                   "bonus": "+30% Crit DMG to 1-cost Cards"}
        SETS[9] = {"name": "B Set", "pieces": 2, "stat": "ATK%",
                   "value": 10}
        found = " ".join(tool.set_problems(effects))
        if "states [1 30]" not in found:
            out.append("a wording stating 30 where the game states 35 "
                       "goes unreported. See `set_problems` in "
                       "docs/client_tables.py.")
        if "ATK% 10 here, ATK% 12" not in found:
            out.append("a plain set's value unlike the client's goes "
                       "unreported.")
    finally:
        for key, entry in saved.items():
            if entry is None:
                SETS.pop(key, None)
            else:
                SETS[key] = entry
    moved = {**effects, 6: ("A Set", 4, "+40% Critical Damage of 1-cost "
                            "cards", "", None)}
    reworded = {**effects, 6: ("A Set", 4, "+35% Critical Damage of Attack "
                               "cards", "", None)}
    if "only its figures moved" not in " ".join(
            tool.set_changes(effects, moved)):
        out.append("a set whose figures alone moved is not told apart. See "
                   "`set_changes` in docs/client_tables.py.")
    if "reworded" not in " ".join(tool.set_changes(effects, reworded)):
        out.append("a reworded set goes unreported.")
    if tool.set_changes(effects, effects):
        out.append("an unchanged set is reported as changed.")
    return out


def _fallback_shows_the_game():
    """A set with no wording of its own shows the client's words, and
    one with a wording shows that; a set with no entry at all goes by
    the client's name, which leads back to its id. Returns complaints."""
    from game_data import SETS, from_client, set_bonus
    from game_data.sets import set_name, set_named
    out = []
    set_id = next(iter(from_client.SET_EFFECTS))
    entry = SETS.get(set_id)
    try:
        SETS[set_id] = dict(entry or {}, bonus="Short")
        if set_bonus(set_id) != "Short":
            out.append("a set's own wording is not what `set_bonus` "
                       "shows.")
        SETS[set_id].pop("bonus")
        if set_bonus(set_id) != from_client.SET_EFFECTS[set_id][2]:
            out.append("a set with no wording of its own does not show the "
                       "game's. See `set_bonus` in game_data/sets.py.")
        del SETS[set_id]
        theirs = from_client.SET_EFFECTS[set_id][0]
        if set_name(set_id) != theirs or set_named(theirs) != set_id:
            out.append(f"a set with no entry is named {set_name(set_id)!r}, "
                       f"not the client's {theirs!r}, or that name does not "
                       f"lead back to set {set_id}. See `set_name` and "
                       f"`set_named` in game_data/sets.py.")
        if set_name(999999) != "999999" or set_named("999999") != 999999:
            out.append("a set nothing names does not go by its number.")
    finally:
        if entry is None:
            SETS.pop(set_id, None)
        else:
            SETS[set_id] = entry
    return out


def run():
    add_source_to_path()
    import game_client
    from game_data import SETS, from_client
    tool = _tool()
    failures = _comparisons_report(tool) + _fallback_shows_the_game()

    shipped = from_client.SET_EFFECTS
    failures += [f"{line} -- the shipped copy of the game's text. Make "
                 f"game_data/sets.py agree."
                 for line in tool.set_problems(shipped)]
    for set_id, entry in sorted(SETS.items()):
        if not entry.get("bonus") and set_id in shipped:
            note(f"set {set_id} {entry.get('name')} has no wording of its "
                 f"own, so the game's shows: {shipped[set_id][2]!r}")
    for line in tool.unlisted_sets(shipped):
        note(f"{line}, so it shows by number, in the game's words")

    install = game_client.find_install()
    if install is None:
        note("no game client installed, so a patch's change to a set and "
             "the node 7s were not looked for")
        return failures
    client = game_client.Client(install)
    if client.archive.build != from_client.BUILD:
        installed = game_client.set_effects(client)
        failures += [f"{line} -- build {client.archive.build}, installed. "
                     f"Make game_data/sets.py agree, then `python "
                     f"docs/client_tables.py --ship`."
                     for line in tool.set_changes(shipped, installed)
                     + tool.set_problems(installed)]
    failures += tool.potential_7_problems(client)
    failures += tool.node_51_problems(client)
    return failures
