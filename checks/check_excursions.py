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

The Communication Pass is a third: it has no id and no balance, so its
count is the daily allowance less what today has spent. A snapshot that
does not carry the counter has to read as UNKNOWN -- treated as zero
spent it would report a full allowance, which is a number nobody could
tell from a real one.

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

    # The denominator is read off the board, not stated: a type added
    # to the game has to show up once anyone goes through it.
    wide = {ex.BOARD_FIELD: [
        {"res_id": 1, ex.INDEXES_FIELD: "[1,2,3]"},
        {"res_id": 2, ex.INDEXES_FIELD: "[1,2,3,4,5,6,7,8]"},
    ]}
    if ex.type_total(wide) != 8:
        failures.append(
            f"a board reaching index 8 gave a total of "
            f"{ex.type_total(wide)}. Every combatant would be read "
            f"against the wrong denominator and each one would look "
            f"complete."
        )
    if ex.type_total({}) != ex.VISIT_TYPES:
        failures.append("a snapshot with no board did not fall back to "
                        "VISIT_TYPES")

    # The Communication Pass: an allowance less what today has spent.
    for spent, left in ((0, ex.DAILY_PASSES), (1, ex.DAILY_PASSES - 1),
                        (ex.DAILY_PASSES, 0), (ex.DAILY_PASSES + 3, 0)):
        got = ex.passes_left(_town(spent))
        if got != left:
            failures.append(
                f"{spent} visits spent gave {got} passes left, not {left}."
            )
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

    return failures


def _town(spent):
    """A snapshot carrying just the daily visit counter."""
    return {"characters": {"town_data": {
        "day_changeable_data": {"use_town_visit_count": spent}}}}


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
