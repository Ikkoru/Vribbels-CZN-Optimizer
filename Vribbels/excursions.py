"""How many excursions each combatant has been on.

A snapshot's `char_visits` is the excursion board: one row per
combatant that has been taken on one, and the server sends the board
WHOLE. So a combatant with no row has been on none -- that is a
reading, not a hole to leave blank.

**The count is a list inside a string.** Each row's
`experienced_normal_visit_indexes` holds JSON text, `"[1,2,3,4,5,6,7]"`,
not a list -- reading it the ordinary way gets a string whose `len` is
the number of characters. The count here is how many indexes it names.

What the row does NOT carry is anything else per combatant that moves:
`experienced_visit_order` and `normal_visit_reward_received` were the
same for all 34 rows of the capture this was written against, and
`version` is the row's write counter -- every entity in the payload has
one. Whether the number the game itself shows is this count has not
been read off a screen and compared.
"""

import json

# Where the board lives in a snapshot. Top level, beside the banners:
# it arrives in its own frame carrying no roster and no inventory.
BOARD_FIELD = "char_visits"

# The row field holding the JSON text, and the row's combatant.
INDEXES_FIELD = "experienced_normal_visit_indexes"
RES_ID_FIELD = "res_id"


def counts(raw_data):
    """{res_id: excursions} for every combatant with a row.

    A snapshot with no board, an unreadable row or an unparseable
    index list contributes nothing rather than raising: this feeds a
    panel, and a combatant reading 0 is what "no excursions" looks
    like anyway.
    """
    board = (raw_data or {}).get(BOARD_FIELD)
    if not isinstance(board, list):
        return {}
    out = {}
    for row in board:
        if not isinstance(row, dict):
            continue
        res_id = row.get(RES_ID_FIELD)
        if not isinstance(res_id, int):
            continue
        out[res_id] = _experienced(row.get(INDEXES_FIELD))
    return out


def _experienced(raw):
    """How many visit indexes a row names.

    Accepts the list itself as well as the JSON text the server sends,
    so a payload that stops quoting it keeps working.
    """
    if isinstance(raw, list):
        return len(raw)
    if not isinstance(raw, str):
        return 0
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return 0
    return len(parsed) if isinstance(parsed, list) else 0
