"""The game client's facts written into `game_data`'s own tables.

`game_data.client_sync` rewrites source files the maintainer also edits
by hand, from `docs/client_tables.py --ship` and from a launch, so what
goes wrong goes wrong in the maintainer's own work:

1. **A line nobody marked is rewritten**, and a value the maintainer
   read in game becomes the client's, with nothing to show it changed
   but the diff.
2. **What is marked goes stale**: a block or a `# client` value left at
   the last patch's figures, a unit the client added never arriving, or
   a nameless one arriving as an entry called Unknown.
3. **The file comes back otherwise than it went in**: a CRLF file turned
   LF, so the whole of it shows as changed, or a run that changes
   something the second time it is made.
4. **A pairing lands in the wrong table**: a 4-star's recommended partner
   made a signature one, or a line holding several pairings rewritten
   for one of them.
5. **An entry the client fills whole is asked for the maintainer's
   companions**, its Potential 7 among them, and the launch's data check
   puts that to a player as a problem.
6. **The launch from source ships when it should not**, a read of an
   unreadable build or an older client writing over a newer copy, or
   its notice drops what the tools said.

Held on synthetic tables in a temporary folder: no installed client and
no real table is touched.
"""

import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "the client's facts written into game_data's own tables"

# A combatant table as the hand writes it, CRLF: a hand entry with one
# value marked the client's, a block of the client's, a block whose unit
# the client no longer holds, and a block with its end marker missing.
CHARACTERS_PY = (
    '"""Combatants."""\n'
    "\n"
    "CHARACTERS = {\n"
    "    0: None,  # unequipped\n"
    "    1: {\n"
    '        "name": "Hand",\n'
    '        "grade": 4,\n'
    '        "base_atk": 100,  # client\n'
    '        "node_60": "HP%",  # read in game\n'
    "    },\n"
    "    2: {\n"
    '        "name": "Old",  # client block start\n'
    '        "grade": 5,\n'
    '        "from_client": True,  # client block end\n'
    "    },\n"
    "    3: {\n"
    '        "name": "Gone",  # client block start\n'
    '        "from_client": True,  # client block end\n'
    "    },\n"
    "    6: {\n"
    '        "name": "Broken",  # client block start\n'
    '        "grade": 4,\n'
    "    },\n"
    "}\n"
    "\n"
    "AFTER = 1\n").replace("\n", "\r\n")

# A partner table, LF, with the three line tables beside it: a class
# entry marked the client's, and a pairing line holding two pairings.
PARTNERS_PY = (
    '"""Partners."""\n'
    "\n"
    "PARTNERS = {\n"
    "    10: {\n"
    '        "name": "Hand Partner",\n'
    '        "grade": 5,\n'
    "    },\n"
    "}\n"
    "\n"
    "PARTNER_CLASS_STATS = {\n"
    '    (5, "Striker"):  {"atk": 1, "def": 2, "hp": 3},\n'
    '    (4, "Vanguard"): {"atk": 5, "def": 40, "hp": 95},  # client\n'
    "}\n"
    "\n"
    "SIGNATURE_PARTNERS = {\n"
    '    "Hand Five": "Hand Partner", "Old": "Stale",  # client\n'
    "}\n"
    "\n"
    "PARTNER_EXCEPTIONS = {\n"
    '    "Hand": "Hand Partner",\n'
    "}\n")


def _combatant(name, grade, atk):
    return {"name": name, "grade": grade, "class": "Striker",
            "attribute": "Passion", "base_atk": atk, "base_def": 150,
            "base_hp": 350, "base_crit_rate": 3.0, "base_crit_dmg": 125.0,
            "node_50": "CRate", "node_60": "CDmg",
            "level_gains": {"61": {"atk": 8, "def": 3, "hp": 9},
                            "62": {"atk": 8, "def": 3, "hp": 9}}}


FACTS = {
    "combatants": {
        1: _combatant("Hand", 4, 999),
        2: _combatant("Old", 5, 470),
        4: _combatant("New", 4, 440),
        5: {**_combatant("", 5, 1), "name": None},
        7: _combatant("Newer", 5, 480),
        "Other": _combatant("Other", 5, 1),
    },
    "partners": {
        10: {"name": "Hand Partner", "grade": 5, "class": "Striker",
             "level_60": {"atk": 155, "def": 5, "hp": 144}},
        11: {"name": "New Partner", "grade": 4.5, "class": "Medic",
             "passive_name": "Mending", "ego_name": "Mend", "ego_cost": 2,
             "stats": {"HP%": [10, 12, 14, 16, 18]},
             "passive_lines": [[f"Increase Health by {n}%." for n in
                                (10, 12, 14, 16, 18)]],
             "level_60": {"atk": 5, "def": 44, "hp": 105}},
        12: {"name": "Vanguard Partner", "grade": 4, "class": "Vanguard",
             "level_60": {"atk": 5, "def": 41, "hp": 95}},
    },
    "recommended": {2: 10, 4: 11, 1: 11, 7: 10},
}


def _run_sync(folder):
    from game_data import client_sync
    (folder / "characters.py").write_bytes(CHARACTERS_PY.encode("utf-8"))
    (folder / "partners.py").write_bytes(PARTNERS_PY.encode("utf-8"))
    return client_sync.sync(FACTS, folder=folder)


def _entries(folder):
    from game_data import client_sync
    texts = {name: (folder / name).read_bytes().decode("utf-8")
             for name in ("characters.py", "partners.py")}
    return {table: client_sync._held(texts[name], table) for name, table in
            (("characters.py", "CHARACTERS"), ("partners.py", "PARTNERS"),
             ("partners.py", "PARTNER_CLASS_STATS"),
             ("partners.py", "SIGNATURE_PARTNERS"),
             ("partners.py", "PARTNER_EXCEPTIONS"))}, texts


def _written(folder):
    """What the sync wrote. Returns complaints."""
    from game_data import client_sync
    out = []
    try:
        said, changed = _run_sync(folder)
    except client_sync.SyncError as exc:
        return [f"the sync would write a table wrong, so wrote nothing: "
                f"{exc}"]
    held, texts = _entries(folder)
    chars = held["CHARACTERS"]
    if chars[1].get("base_atk") != 999:
        out.append(f"a hand entry's `# client` value reads "
                   f"{chars[1].get('base_atk')}, not the client's 999: what "
                   f"is marked is the tool's to keep current.")
    unmarked = ['        "name": "Hand",', '        "grade": 4,',
                '        "node_60": "HP%",  # read in game']
    lines = texts["characters.py"].split("\r\n")
    if any(line not in lines for line in unmarked):
        out.append("a line of the hand entry nobody marked was rewritten: "
                   "an unmarked value is the maintainer's, whatever the "
                   "client says.")
    if chars[2] != client_sync.combatant_entry(FACTS["combatants"][2]):
        out.append(f"a block of the client's reads {chars[2]}, not the "
                   f"client's entry: a block is the tool's whole.")
    if chars.get(3, {}).get("name") != "Gone" or not any(
            "no longer holds" in line for line in said):
        out.append("a block whose unit the client no longer holds was "
                   "dropped, or dropped without a word: it is left as it "
                   "was and said.")
    if chars.get(6) != {"name": "Broken", "grade": 4} or not any(
            "without its pair" in line for line in said):
        out.append("a block missing its end marker was touched, or left "
                   "without a word.")
    if chars.get(4, {}).get("name") != "New" or not chars[4].get(
            client_sync.FROM_CLIENT):
        out.append(f"a unit the table lacks arrived as {chars.get(4)}, not "
                   f"a block of the client's marked from_client.")
    if 5 in chars or any(isinstance(e, dict) and e.get("name") == "Unknown"
                         for e in chars.values()):
        out.append("a unit the client has no name for yet was added: an "
                   "entry called Unknown would stand for every one.")
    if "Other" in chars:
        out.append("a fact under a key that is no res_id was added.")
    if "\nAFTER = 1" not in texts["characters.py"].replace("\r\n", "\n"):
        out.append("what follows the table was lost.")
    stats = held["PARTNER_CLASS_STATS"]
    if stats.get((4.5, "Medic")) != {"atk": 5, "def": 44, "hp": 105} \
            or stats.get((4, "Vanguard")) != {"atk": 5, "def": 41, "hp": 95} \
            or stats.get((5, "Striker")) != {"atk": 1, "def": 2, "hp": 3}:
        out.append(f"PARTNER_CLASS_STATS reads {stats}: a new class added, "
                   f"the marked one the client's, the unmarked one left.")
    partners = held["PARTNERS"]
    if partners.get(11, {}).get("values") != {"v1": (10, 12, 14, 16, 18)} \
            or partners[11].get("passive_desc") != "Increase Health by {v1}%.":
        out.append(f"a new partner's passive reads "
                   f"{partners.get(11, {}).get('passive_desc')!r} with "
                   f"{partners.get(11, {}).get('values')}: drawn from the "
                   f"client's lines, a figure that moves with the level a "
                   f"placeholder.")
    sig, exc = held["SIGNATURE_PARTNERS"], held["PARTNER_EXCEPTIONS"]
    if sig.get("Newer") != "Hand Partner" or "New" in sig:
        out.append(f"SIGNATURE_PARTNERS reads {sig}: a 5-star's recommended "
                   f"partner is its signature one, and nobody else's.")
    if exc.get("New") != "New Partner" or exc.get("Hand") != "Hand Partner":
        out.append(f"PARTNER_EXCEPTIONS reads {exc}: a new 4-star takes its "
                   f"recommended partner, and a pairing of the maintainer's "
                   f"stays.")
    if sig.get("Old") != "Stale" or sig.get("Hand Five") != "Hand Partner" \
            or not any("shares its line" in line for line in said):
        out.append("a `# client` line holding two pairings was rewritten "
                   "for one, or left without a word: the rewrite is the "
                   "whole line.")
    # The endings each file came with, and untouched lines as they were.
    raw = (folder / "characters.py").read_bytes()
    if raw.count(b"\n") != raw.count(b"\r\n"):
        out.append("characters.py came back with lines of another ending "
                   "than its own CRLF: the whole file shows as changed.")
    if b"\r" in (folder / "partners.py").read_bytes():
        out.append("partners.py, LF, came back with CRLF lines.")
    again, changed_again = client_sync.sync(FACTS, folder=folder)
    if changed_again:
        out.append(f"a second run changed {sorted(changed_again)} again: "
                   f"{[line for line in again if 'left' not in line]}.")
    marks = client_sync.marked("CHARACTERS", folder)
    if set(marks) != {1} or set(marks[1]) != {"base_atk"}:
        out.append(f"marked() reads {marks}: the hand entry's base_atk, "
                   f"and no block.")
    if (4, "Vanguard") not in client_sync.marked("PARTNER_CLASS_STATS",
                                                 folder):
        out.append("marked() does not name the class entry marked the "
                   "client's.")
    return out


def _companions():
    """The data check asks an entry of the client's for no Potential 7.
    Returns complaints."""
    import game_data_validator as validator
    from game_data import client_overlay
    table = client_overlay.hand("CHARACTERS")
    probe = {"name": "Probe Client", "grade": 5, "attribute": "Passion",
             "class": "Striker", "base_atk": 470, "base_def": 155,
             "base_hp": 376, "base_crit_rate": 3.0, "base_crit_dmg": 125.0,
             "node_50": "CRate", "node_60": "CDmg", "from_client": True}
    table[999901] = probe
    problems = []
    try:
        validator._check_potential_7(problems)
    finally:
        table.pop(999901, None)
    if any("999901" in line for line in problems):
        return [f"the data check asks an entry of the client's for its "
                f"Potential 7: {[p for p in problems if '999901' in p]}. "
                f"Shown at launch, a player is told of a problem only the "
                f"maintainer can fix."]
    return []


def _level_terms():
    """A combatant's steps to 61 and 62 are written as the hand entries
    state them: nothing where their own class's curve holds them, a
    `level_curve` naming the one other pair whose curve does, else the
    steps. Returns complaints."""
    from game_data import client_sync
    from game_data.characters import LEVEL_BONUS_BY_CLASS

    def steps(atk, def_, hp):
        return {level: {"atk": atk, "def": def_, "hp": hp}
                for level in (61, 62)}

    fact = {"name": "Probe", "grade": 5, "class": "Striker",
            "attribute": "Justice"}
    lone = [pair for pair, curve in LEVEL_BONUS_BY_CLASS.items()
            if sum(c == curve for c in LEVEL_BONUS_BY_CLASS.values()) == 1
            and pair != ("Striker", 5)][0]
    shared = [pair for pair, curve in LEVEL_BONUS_BY_CLASS.items()
              if pair[1] == 4 and LEVEL_BONUS_BY_CLASS.get(("Striker", 4)) == curve
              and pair != ("Striker", 4)]
    out = []
    for gains, want, why in (
            (LEVEL_BONUS_BY_CLASS[("Striker", 5)], {},
             "their own class and grade's curve"),
            (LEVEL_BONUS_BY_CLASS[lone], {"level_curve": lone},
             "one other pair's curve"),
            (steps(99, 1, 1), {"level_gains": steps(99, 1, 1)},
             "steps no curve holds"),
            (LEVEL_BONUS_BY_CLASS[("Striker", 4)] if shared else None,
             {"level_gains": LEVEL_BONUS_BY_CLASS[("Striker", 4)]}
             if shared else None,
             "a curve several pairs share")):
        if gains is None:
            continue
        entry = client_sync.combatant_entry(dict(fact, level_gains=gains))
        got = {k: entry[k] for k in client_sync.LEVEL_FIELDS if k in entry}
        if got != want:
            out.append(f"a combatant on {why} is written with {got}, not "
                       f"{want}: the hand entries name a curve only where "
                       f"it is another class's, and the steps only where no "
                       f"one curve holds them (`client_sync._level_terms`).")
    return out


def _notice():
    """When a launch from source ships, and what it tells the maintainer
    (`czn_optimizer_gui.ship_wanted`, `client_tool_lines`,
    `client_parts_text`). Returns complaints."""
    import czn_optimizer_gui as gui
    out = []
    for args, want, why in (
            ((126, 126, 88), True, "a newer build, read at that build"),
            ((126, None, 88), False, "a newer build this launch could not "
                                     "read"),
            ((126, 120, 88), False, "a newer build, the facts in use an "
                                    "earlier one's"),
            ((88, 88, 88), False, "the build already shipped"),
            ((80, 80, 88), False, "a client older than the shipped copy"),
            ((None, None, 88), False, "no build to read")):
        if gui.ship_wanted(*args) != want:
            out.append(f"with {why} (installed, read, shipped = {args}) a "
                       f"launch {'does not ship' if want else 'ships'}: "
                       f"only a read of a newer build writes the copy.")
    lines = gui.client_tool_lines(
        "--audit", "set 30: in the client\nbuild 126: 1 disagreement(s)\n"
        "\n", "", 0)
    if lines != ["set 30: in the client"]:
        out.append(f"the audit's lines read {lines}: its summary line says "
                   f"nothing the notice needs.")
    failed = gui.client_tool_lines("--ship", "nothing written: x\n",
                                   "Traceback\nSyncError: x\n", 1)
    if not failed or "stopped: SyncError: x" not in failed[-1]:
        out.append(f"a run that failed reads {failed}: the notice says it "
                   f"stopped, and why.")
    text = gui.client_parts_text(
        126, ["characters.py: CHARACTERS[30134] Rossweisse added"],
        ["Checklist ACTIVITY_FULL: 100 here, 120 in the client"]
        + [f"line {n}" for n in range(gui.CLIENT_PARTS_LINES + 3)],
        ["ACTIVITY_FULL: 100 here, 120 in the client",
         "SUPPLY_ROUNDS['disaster_s05']: (...) here, (...) in the client"])
    for want, why in (
            (gui.CLIENT_PARTS_SHIPPED % 126, "what --ship wrote, by build"),
            ("Rossweisse added", "what --ship wrote"),
            (gui.CLIENT_PARTS_AUDIT, "the audit's section"),
            ("... and 4 more", "a long section cut, the rest counted"),
            ("SUPPLY_ROUNDS", "a snapshot's maximum the audit cannot name")):
        if want not in (text or ""):
            out.append(f"the notice lacks {why} ({want!r}): {text!r}")
    if (text or "").count("ACTIVITY_FULL") != 1:
        out.append("a maximum both the audit and the snapshot name is said "
                   "twice.")
    if gui.client_parts_text(None, [], [], []) is not None:
        out.append("with nothing parting, a launch still raises the notice.")
    return out


def run():
    add_source_to_path()
    with tempfile.TemporaryDirectory() as tmp:
        failures = _written(Path(tmp))
    return failures + _companions() + _level_terms() + _notice()


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a class's own curve written as steps", "game_data.client_sync:_level_terms",
     "if not gains or LEVEL_BONUS_BY_CLASS.get((cls, grade)) == gains:",
     "if not gains:", "their own class and grade's curve"),
    ("another class's curve written as steps",
     "game_data.client_sync:_level_terms",
     'return {"level_curve": pairs[0]}', 'return {"level_gains": gains}',
     "one other pair's curve"),
    ("an unmarked value rewritten", "game_data.client_sync:_sync_entries",
     "if not any(comments.get(line) == CLIENT for line in span):\n"
     "                continue",
     "if False:\n                continue",
     "nobody marked was rewritten"),
    ("a block left stale", "game_data.client_sync:_sync_entries",
     "if _bare(lines[first - 1:last]) != new:", "if False:",
     "would write a table wrong"),
    ("a new unit not added", "game_data.client_sync:_sync_entries",
     "added = [key for key in sorted(whole) if key not in held]",
     "added = []", "a unit the table lacks"),
    ("a nameless unit added", "game_data.client_sync:sync",
     "                  if str(k).isdigit() and isinstance(v, dict) "
     "and v.get(\"name\")}",
     "                  if str(k).isdigit() and isinstance(v, dict)}",
     "no name for yet"),
    ("a file's endings changed", "game_data.client_sync:_apply",
     "out[first - 1:last] = [line + newline for line in new]",
     "out[first - 1:last] = [line + \"\\n\" for line in new]",
     "another ending"),
    ("a shared line rewritten", "game_data.client_sync:_sync_lines",
     "or starts.count(key_node.lineno) > 1:", "or False:",
     "rewritten for one"),
    ("a 4-star paired as a signature", "game_data.client_sync:pairings",
     "if grade == 5:", "if True:", "and nobody else's"),
    ("a broken block rewritten", "game_data.client_sync:_block",
     'return "broken" if start or end or inner else False',
     "return False", "missing its end marker"),
    ("the client's block asked for a node 7",
     "game_data_validator:_check_potential_7",
     '                and not data.get("from_client"):', ":",
     "asks an entry of the client's"),
    ("a read of another build shipped", "czn_optimizer_gui:ship_wanted",
     "read_build == build", "True", "only a read of a newer build"),
    ("an older client shipped over a newer copy",
     "czn_optimizer_gui:ship_wanted", "build > (shipped_build or 0)", "True",
     "only a read of a newer build"),
    ("a failed run said nothing", "czn_optimizer_gui:client_tool_lines",
     "if returncode:", "if False:", "it stopped, and why"),
    ("the snapshot's maximums said twice",
     "czn_optimizer_gui:client_parts_text",
     'if f"Checklist {line}" not in heard]', "]", "is said twice"),
]
