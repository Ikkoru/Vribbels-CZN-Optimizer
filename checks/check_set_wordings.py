"""What the program's own tables decide, against the game client
CHANGING it.

A set's entry in `game_data/sets.py` -- its name, pieces, model and
`bonus` wording -- is the maintainer's and goes over the game's, so it
is never held to the client: `Snowflake of OFM` differs on purpose. A
balance patch that changes a set changes nothing there, though, and the
tooltip would go on stating the old figures. So where the installed
client is a build ahead of the copy the program ships
(`game_data/from_client.py`), each set the patch renamed, re-pieced,
re-valued or reworded is a failure, saying whether it moved only the
figures (the wording wants new figures) or reworded the effect (the
wording wants rewriting); and so is a partner's Ego text, or a Rescue
pool's or shop's name, the patch changed (`client_tables.client_changes`).

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


_LOADED = []


def _tool():
    """`docs/client_tables.py`, which holds the comparisons: loaded once,
    so a fault put into it (`_broken`) is what the run reads."""
    if not _LOADED:
        spec = importlib.util.spec_from_file_location(
            "client_tables", REPO_ROOT / "docs" / "client_tables.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        _LOADED.append(tool)
    return _LOADED[0]


def _broken(name, old, new):
    """The loaded tool's `name` with `old` put as `new`: `faults.py`
    reaches only modules under `Vribbels/`, and the tool is loaded from
    its file."""
    import inspect
    import textwrap
    tool = _tool()
    source = textwrap.dedent(inspect.getsource(getattr(tool, name)))
    if source.count(old) != 1:
        raise LookupError(f"{name} no longer holds {old!r} once")
    exec(compile(source.replace(old, new), tool.__file__, "exec"),
         tool.__dict__)


def _comparisons_report(tool):
    """What the program's tables decide is held to the CLIENT changing,
    never to the client: each change between two copies of the client's
    data speaks up -- a set renamed, its pieces or plain stat moved, its
    figures moved or its words reworded, a partner's Ego text and a
    pool's or shop's name changed -- and an entry that differs from the
    client on purpose says nothing. Returns complaints."""
    out = []
    effects = {6: ("A Set", 4, "+35% Critical Damage of 1-cost cards", "",
                   None),
               9: ("B Set", 2, "+12% Attack", "S_ATK_INC_RATE_OUT", 12)}
    typed = {6: {"name": "Short A", "pieces": 4,
                 "bonus": "+30% Crit DMG to 1-cost Cards"},
             9: {"name": "B Set", "pieces": 2, "stat": "ATK%", "value": 10},
             12: {"name": "Gone Set", "pieces": 2}}
    found = tool.set_problems(effects, typed)
    if found != ["set 12 Gone Set: not in the client"]:
        out.append(f"the sets held to the client read {found}: an entry's "
                   f"own name, wording and value stand, and only a set the "
                   f"client lacks is said (`set_problems`).")
    for what, after, says in (
            ("renamed", {**effects, 9: ("New Name",) + effects[9][1:]},
             "renamed it 'B Set' to 'New Name'"),
            ("given new pieces", {**effects, 9: ("B Set", 4)
                                  + effects[9][2:]}, "pieces moved"),
            ("given a new plain value", {**effects, 9: effects[9][:4]
                                         + (15,)}, "ATK% 12 to ATK% 15"),
            ("moved only in its figures",
             {**effects, 6: ("A Set", 4, "+40% Critical Damage of 1-cost "
                                         "cards", "", None)},
             "only its figures moved"),
            ("reworded", {**effects, 6: ("A Set", 4, "+35% Critical Damage "
                                         "of Attack cards", "", None)},
             "reworded")):
        if says not in " ".join(tool.set_changes(effects, after)):
            out.append(f"a set the client {what} goes unreported "
                       f"(`set_changes` in docs/client_tables.py).")
    if tool.set_changes(effects, effects):
        out.append("an unchanged set is reported as changed.")
    from game_data.client_overlay import hand
    rid = next(r for r, p in hand("PARTNERS").items()
               if isinstance(r, int) and isinstance(p, dict)
               and not p.get("from_client"))
    before = {"ego": {rid: "100% Shield"},
              "names": {"rescue pool general": "Normal Combatant Rescue"}}
    after = {"ego": {rid: "120% Shield"},
             "names": {"rescue pool general": "Standard Rescue"}}
    said = " ".join(tool.word_changes(before, after))
    if "Ego text moved from '100% Shield' to '120% Shield'" not in said \
            or "renamed it 'Normal Combatant Rescue' to 'Standard Rescue'" \
            not in said or tool.word_changes(before, before):
        out.append(f"a partner's Ego text or a pool's name the client "
                   f"changed reads {said!r} (`word_changes`): each is said, "
                   f"and nothing where the client kept them.")
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
        note(f"{line}, so it shows in the game's name and words, and the "
             f"optimizer cannot weigh it")

    install = game_client.find_install()
    if install is None:
        note("no game client installed, so a patch's change to a set and "
             "the node 7s were not looked for")
        return failures
    client = game_client.Client(install)
    if client.archive.build != from_client.BUILD:
        installed = game_client.set_effects(client)
        failures += [f"{line} -- build {client.archive.build}, installed. "
                     f"See whether game_data's own entry still says what "
                     f"you want, then `python docs/client_tables.py --ship`."
                     for line in tool.client_changes(client)
                     + tool.set_problems(installed)]
    to_write = []
    failures += tool.potential_7_problems(client, to_write)
    for line in to_write:
        note(f"{line} -- the combatant's entry is the client's, its node 7 "
             f"still to write")
    failures += tool.node_51_problems(client)
    return failures


def _held_to_names():
    _broken("set_problems", "if set_id not in effects]",
            "if set_id not in effects\n"
            "            or ours.get('name') != effects[set_id][0]]")


def _rename_unsaid():
    _broken("set_changes", "if was[0] != now[0]:", "if False:")


def _value_unsaid():
    _broken("set_changes", "if tuple(was[3:5]) != tuple(now[3:5]):",
            "if False:")


def _ego_unsaid():
    _broken("word_changes", "if old[rid] != new[rid] and isinstance(",
            "if False and isinstance(")


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("an entry held to the client's name", _held_to_names, None, None,
     "the sets held to the client read"),
    ("a client's rename unsaid", _rename_unsaid, None, None,
     "a set the client renamed"),
    ("a client's new plain value unsaid", _value_unsaid, None, None,
     "a set the client given a new plain value"),
    ("a client's new Ego text unsaid", _ego_unsaid, None, None,
     "a partner's Ego text or a pool's name"),
]
