"""Town visits: a list inside a string, a missing row, a derived pass.

Two silent failures, both of which draw a plausible number.

`experienced_normal_visit_indexes` holds JSON TEXT -- `"[1,2,3,4,5,6,7]"`
-- not a list. Read the ordinary way its `len` is 15, the number of
characters, which is a number a reader would accept.

And the board arrives WHOLE: a combatant with no row has been on no
excursion. Treating an absent row as unknown would draw `-` beside
combatants whose count is a real zero, and treating an absent BOARD as
zero would draw 0 for every combatant on a snapshot taken before the
addon stored one. The panel tells those two apart and this pins which
is which.

The Communication Pass is a third: spending one debits nothing, so its
count is the day's allowance less what today has spent. A snapshot that
does not carry the counter has to read as UNKNOWN -- treated as zero
spent it would report a full allowance, which is a number nobody could
tell from a real one. And the allowance is the ACCOUNT's: the town's
base and what the research it holds adds. A constant 5 reads right for
an account holding both research nodes and two passes too many for one
holding neither.

The fourth is the capture end: nothing downstream can show a board the
addon does not save, and `ADDON_TEMPLATE` is a string literal that
`compileall` cannot see.

No Tk and no snapshot -- the shapes are synthesised here.
"""

import ast

from ._harness import add_source_to_path

NAME = "excursions"


def run():
    add_source_to_path()
    import excursions as ex
    from capture.manager import ADDON_TEMPLATE

    failures = []

    row = {"res_id": 1017, ex.INDEXES_FIELD: "[1,2,3,4,5,6,7]"}
    got = ex.counts({ex.BOARD_FIELD: [row]})
    if got != {1017: 7}:
        failures.append(
            f"a row naming seven visits counted {got}, not {{1017: 7}}. The "
            f"field is JSON text, so counting it as a sequence gives its "
            f"character length -- a number that looks like an answer."
        )

    # An absent row on a board that DID arrive is a zero.
    if ex.counts({ex.BOARD_FIELD: [row]}).get(9999, 0) != 0:
        failures.append("a combatant with no row did not read 0")

    # An absent board is not a board of zeroes.
    for empty, what in (({}, "a snapshot with no board"),
                        (None, "no snapshot at all"),
                        ({ex.BOARD_FIELD: None}, "a null board")):
        if ex.counts(empty) != {}:
            failures.append(
                f"{what} produced a board. The panel tells 'no capture yet' "
                f"from 'no excursions' by whether this is empty."
            )

    # Malformed rows are dropped, not raised on: this feeds a panel.
    try:
        ex.counts({ex.BOARD_FIELD: [
            "not a row", {"res_id": "1017"}, {"res_id": 1},
            {"res_id": 2, ex.INDEXES_FIELD: "not json"},
            {"res_id": 3, ex.INDEXES_FIELD: "{}"},
        ]})
    except Exception as e:
        failures.append(
            f"a malformed board raised {type(e).__name__}. It is read while "
            f"drawing a panel, where an exception is a blank tab."
        )

    failures.extend(_totals(ex))
    if ex.experienced({}) != ex.VISIT_TYPES:
        failures.append("a snapshot with no board did not fall back to "
                        "VISIT_TYPES")

    # The Communication Pass: an allowance less what today has spent.
    full = ex.daily_passes({})
    for spent, left in ((0, full), (1, full - 1), (full, 0), (full + 3, 0)):
        got = ex.passes_left(_town(spent))
        if got != left:
            failures.append(
                f"{spent} visits spent gave {got} passes left, not {left}."
            )
    failures.extend(_allowance(ex))
    for missing, what in (({}, "an empty snapshot"),
                          ({"characters": {}}, "no town_data"),
                          (_town("five"), "a non-numeric counter")):
        if ex.passes_left(missing) is not None:
            failures.append(
                f"{what} produced a pass count. Nothing carries the pass "
                f"itself, so a snapshot that does not say has to read as "
                f"unknown rather than as a full allowance."
            )

    # The addon has to save it, or none of the above ever sees data.
    if not _template_saves(ADDON_TEMPLATE, ex.BOARD_FIELD):
        failures.append(
            f"ADDON_TEMPLATE's save_data does not carry {ex.BOARD_FIELD!r}. "
            f"The board would be captured and dropped, and every count "
            f"would read `-` with nothing to say why."
        )

    # The same shape of loss, for the one payload carrying the Great
    # Rift weekly score. Nothing reads it yet, so a snapshot missing it
    # would go unnoticed until somebody came to show it.
    if not _template_saves(ADDON_TEMPLATE, "disaster_boss_rank_entities"):
        failures.append(
            "ADDON_TEMPLATE's save_data does not carry "
            "'disaster_boss_rank_entities'. It is the only thing the game "
            "sends that holds the Great Rift weekly score, and the frame "
            "it arrives in is otherwise dropped whole."
        )
    failures.extend(_one_rank_row_is_merged())

    return failures


def _totals(ex):
    """**The denominator is PER COMBATANT and is not read off the
    board.** It is the game client's count of the combatant's own
    types: one combatant reaching index 8 says nothing about anyone
    else, and a board-wide maximum would put every other combatant
    against a total they cannot reach. Returns complaints."""
    import game_client
    from game_data import from_client
    out = []
    try:
        game_client.use({"excursion_types": {"1": 7, "2": 11}})
        for res_id, want in ((1, "7"), (2, "11"), (3, "7?")):
            if ex.total(res_id) != want:
                out.append(
                    f"combatant {res_id} reads against {ex.total(res_id)}, "
                    f"not {want}. The total is the client's count of that "
                    f"combatant's own types; one nothing lists reads the "
                    f"seven every combatant has, marked as a floor, never "
                    f"as a count.")
        game_client.use(None)
        res_id, count = next(iter(from_client.EXCURSION_TYPES.items()))
        if ex.total(res_id) != str(count):
            out.append(
                f"with no client read, combatant {res_id} reads against "
                f"{ex.total(res_id)}, not the shipped {count}.")
    finally:
        game_client.use(None)
    return out


def _allowance(ex):
    """The day's passes are the base and the research the account
    holds, the client's figures ahead of the module's. Returns
    complaints."""
    import game_client
    out = []
    real = game_client.known_limits
    try:
        # The module's own figures, nothing stated by any client.
        game_client.known_limits = lambda: {}
        base = ex.VISIT_TICKETS
        nodes = sorted(ex.VISIT_RESEARCH)
        top = base + sum(f[-1] for f in ex.VISIT_RESEARCH.values())
        for levels, want, what in (
                ({node: 1 for node in nodes}, base + sum(
                    ex.VISIT_RESEARCH[n][0] for n in nodes), "every node"),
                ({}, base, "no research"),
                ({nodes[0]: 1}, base + ex.VISIT_RESEARCH[nodes[0]][0],
                 "one node"),
                (None, top, "no research map")):
            got = ex.daily_passes(_town(0, levels))
            if got != want:
                out.append(
                    f"an account with {what} researched is granted {got} "
                    f"passes a day, not {want}. The allowance is the town's "
                    f"base and what each research node it holds adds; a "
                    f"snapshot with no map reads the most a day can grant.")
        # The client's figures stand ahead, and a level past a node's
        # listed ones reads its top one.
        game_client.known_limits = lambda: {
            "visit_tickets": 2, "visit_research": {"901": [1, 3]}}
        for levels, want in (({"901": 2, nodes[0]: 1}, 5),
                             ({"901": 4}, 5), ({"901": 1}, 3)):
            got = ex.daily_passes(_town(0, levels))
            if got != want:
                out.append(
                    f"with the client stating a base of 2 and node 901 "
                    f"adding 1 then 3, research {levels} grants {got} "
                    f"passes, not {want}: the client's figures are the "
                    f"whole answer where it states them, and a level past "
                    f"a node's listed ones reads its top one.")
        got = ex.passes_left(_town(1, {"901": 1}))
        if got != 2:
            out.append(f"one pass spent of the client's 3 leaves {got}, "
                       f"not 2: what is left counts down from the "
                       f"account's own allowance.")
    finally:
        game_client.known_limits = real
    return out


def _one_rank_row_is_merged():
    """A run's reply updates its rank's row among the standings.

    The whole standings arrive only when the Great Rift's screen lists
    them; a run, and a claim, send the one rank's row as
    `disaster_boss_rank_entity`. Dropped, the score a run just set
    waits for the list to be opened again, and the Checklist reads last
    week's row as nothing done this week. Merged, it must replace only
    its own slot.
    """
    import tempfile
    from pathlib import Path
    from .check_capture_rewards import _build_addon

    out = []
    old = {"score_week_id": 194, "week_total_score": 1115731}
    other = {"score_week_id": 193, "week_total_score": 1396064}
    new = {"season_id": "disaster_s04", "define_id": "disaster_s04_rank_02",
           "score_week_id": 195, "week_total_score": 1102801}
    with tempfile.TemporaryDirectory() as tmp:
        addon = _build_addon(Path(tmp), [])
        addon._handle_server_payload({
            "res": "ok", "qid": 1, "disaster_boss_rank_entities": {
                "disaster_s04": {"disaster_s04_rank_01": other,
                                 "disaster_s04_rank_02": old}}}, 100)
        addon._handle_server_payload({
            "res": "ok", "qid": 2, "disaster_boss_rank_entity": new}, 100)
        ranks = addon.disaster_ranks or {}
    season = ranks.get("disaster_s04") or {}
    if season.get("disaster_s04_rank_02") != new:
        out.append(
            f"a run's reply carrying one Great Rift rank's row left that "
            f"rank at {season.get('disaster_s04_rank_02')!r}. The new "
            f"score waits for the standings to be listed again, and the "
            f"Checklist reads this week's runs as none.")
    if season.get("disaster_s04_rank_01") != other:
        out.append("merging one Great Rift rank's row lost the other "
                   "rank's row beside it.")
    return out


def _town(spent, research=None):
    """A snapshot carrying the daily visit counter, and the research
    levels where `research` is given."""
    town = {"day_changeable_data": {"use_town_visit_count": spent}}
    if research is not None:
        town["town_research_level_map"] = research
    return {"characters": {"town_data": town}}


def _template_saves(source, field):
    """True when the addon's `save_data` dict has `field` as a key."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "save_data" not in names or not isinstance(node.value, ast.Dict):
            continue
        return any(isinstance(k, ast.Constant) and k.value == field
                   for k in node.value.keys)
    return False


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a fixed allowance", "excursions:daily_passes",
     "    return total", "    return VISIT_TICKETS + 2",
     "what each research node it holds adds"),
    ("the research map ignored", "excursions:daily_passes",
     "level = held.get(node) if isinstance(held, dict) else len(figures)",
     "level = len(figures)", "what each research node it holds adds"),
    ("the module's base over the client's", "excursions:daily_passes",
     "base = base if _is_count(base) else VISIT_TICKETS",
     "base = VISIT_TICKETS", "the client's figures are the whole answer"),
    ("a level past the listed ones dropped", "excursions:daily_passes",
     "figures[min(level, len(figures)) - 1]",
     "(figures[level - 1] if level <= len(figures) else 0)",
     "reads its top one"),
    ("spent counted down from a fixed 5", "excursions:passes_left",
     "max(0, daily_passes(raw_data) - spent)", "max(0, 5 - spent)",
     "the account's own allowance"),
]
