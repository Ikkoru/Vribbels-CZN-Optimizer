"""Town visits: which excursion types a combatant has seen, and the
passes left to run more today.

A snapshot's `char_visits` is the excursion board: one row per
combatant that has been taken on one, and the server sends the board
WHOLE. So a combatant with no row has seen none -- that is a reading,
not a hole to leave blank.

**The count is a list inside a string.** Each row's
`experienced_normal_visit_indexes` holds JSON text, `"[1,2,3,4,5,6,7]"`,
not a list -- reading it the ordinary way gets a string whose `len` is
the number of characters. The count here is how many indexes it names,
which is how many of the visit TYPES that combatant has been through.

Nothing else in a row is a count: `experienced_visit_order` and
`normal_visit_reward_received` were the same for all 34 rows of the
capture this was written against, and `version` is the row's write
counter -- every entity in the payload carries one.

**The Communication Pass has no id and no balance.** Spending one
debits nothing anywhere. What a snapshot carries is how many visits
have been SPENT today, and the count the game shows is the daily
allowance less that.
"""

import json

# Where the board lives in a snapshot. Top level, beside the banners:
# it arrives in its own frame carrying no roster and no inventory.
BOARD_FIELD = "char_visits"

# The row field holding the JSON text, and the row's combatant.
INDEXES_FIELD = "experienced_normal_visit_indexes"
RES_ID_FIELD = "res_id"

# How many normal visit types the game has, where no board says
# otherwise. The board itself is the better answer and `type_total`
# reads it; this is what a snapshot with no board falls back to.
VISIT_TYPES = 7

# Communication Passes granted per day, and where the day's spending
# is kept. The allowance is the game's own number; the counter beside
# it agrees with the visit board's visited flags in every snapshot,
# and resets at `town_visit_reset_time`.
DAILY_PASSES = 5
SPENT_PATH = ("characters", "town_data", "day_changeable_data",
              "use_town_visit_count")


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


def type_total(raw_data):
    """How many normal visit types the board knows of.

    The largest index any combatant has experienced, which is the
    denominator every combatant is read against. Taken off the board
    rather than stated so that a type added to the game shows up the
    moment anyone goes through it; `VISIT_TYPES` is the fallback for a
    snapshot carrying no board at all.
    """
    board = (raw_data or {}).get(BOARD_FIELD)
    seen = 0
    for row in board if isinstance(board, list) else ():
        if isinstance(row, dict):
            seen = max(seen, _highest(row.get(INDEXES_FIELD)))
    return seen or VISIT_TYPES


def passes_left(raw_data):
    """Communication Passes left today, or None if nothing says.

    `DAILY_PASSES - use_town_visit_count`. The pass is not an item and
    not a currency: spending one debits no id anywhere, so this is the
    only reading of it a snapshot allows.
    """
    node = raw_data or {}
    for key in SPENT_PATH:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if not isinstance(node, int) or isinstance(node, bool):
        return None
    return max(0, DAILY_PASSES - node)


def _highest(raw):
    """The largest index a row names, or 0."""
    indexes = _parsed(raw)
    return max(indexes) if indexes and all(
        isinstance(i, int) for i in indexes) else 0


def _experienced(raw):
    """How many visit indexes a row names."""
    return len(_parsed(raw))


def _parsed(raw):
    """A row's index list, or [].

    Accepts the list itself as well as the JSON text the server sends,
    so a payload that stops quoting it keeps working.
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []
