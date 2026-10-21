"""Town visits: which excursion types a combatant has seen, and the
passes left to run more today.

A snapshot's `char_visits` is the excursion board: one row per
combatant that has been taken on one, and the server sends the board
WHOLE. So a combatant with no row has seen none -- that is a reading,
not a hole to leave blank.

**A row states no maximum.** The total printed beside it is the game
client's -- `total` -- because nothing on the wire says how many types
a given combatant has.

**The count is a list inside a string.** Each row's
`experienced_normal_visit_indexes` holds JSON text, `"[1,2,3,4,5,6,7]"`,
not a list -- reading it the ordinary way gets a string whose `len` is
the number of characters. The count here is how many indexes it names,
which is how many of the visit TYPES that combatant has been through.

Nothing else in a row is a count: `experienced_visit_order` and
`normal_visit_reward_received` were the same for every row of the
capture this was written against, and `version` is the row's write
counter -- every entity in the payload carries one.

**The Communication Pass is never debited.** The client gives it an
item, 2000006 (`currency_define`'s `town_visit_ticket`), but spending
one moves nothing: that item's balance sits where the account started
it however many are spent. What a snapshot carries is how many visits
have been SPENT today, and the count the game shows is the day's
allowance less that.

**The allowance is per account**: the town's base and what its
research adds, at the levels the account holds.
"""

import json

import game_client

# Where the board lives in a snapshot. Top level, beside the banners:
# it arrives in its own frame carrying no roster and no inventory.
BOARD_FIELD = "char_visits"

# The row field holding the JSON text, and the row's combatant.
INDEXES_FIELD = "experienced_normal_visit_indexes"
RES_ID_FIELD = "res_id"

# The fewest normal visit types any combatant has, and what
# `experienced` falls back to.
VISIT_TYPES = 7

# What the total reads for a combatant neither this machine's client
# nor the shipped table lists: a release newer than both. The floor
# every combatant has, marked as one.
UNKNOWN_TOTAL = "%d?" % VISIT_TYPES

# The Communication Passes a day grants before town research, and
# {research node: what it adds at level 1, 2, ...}: an account holding
# both nodes has the 5 the Excursion and Counseling buttons count down
# from. The client's figures stand ahead of these
# (`game_client.known_limits`' `visit_tickets` and `visit_research`);
# these are for a player without the client, and
# `checklist_tab.limit_mismatches` says when the two part.
VISIT_TICKETS = 3
VISIT_RESEARCH = {"126": [1], "149": [1]}
# Where the account's research levels are kept, by node, and where the
# day's spending is. The counter agrees with the visit board's visited
# flags in every snapshot, and resets at `town_visit_reset_time`.
RESEARCH_PATH = ("characters", "town_data", "town_research_level_map")
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


def total(res_id):
    """What to print after the slash for one combatant: how many
    Excursion types it has.

    PER COMBATANT, and off the game client (`game_client.visit_types`):
    nothing in a snapshot states a maximum, and the totals differ --
    most combatants have seven, a few ten or eleven.
    """
    count = game_client.visit_types(res_id)
    return str(count) if count else UNKNOWN_TOTAL


def experienced(raw_data):
    """The highest index the WHOLE board names, or `VISIT_TYPES`.

    Not a denominator: it says how far the game's own numbering has
    been seen to run, which is a different question from what any one
    combatant is working towards. Kept because it is the only reading
    of the type list a snapshot allows at all.
    """
    board = (raw_data or {}).get(BOARD_FIELD)
    seen = 0
    for row in board if isinstance(board, list) else ():
        if isinstance(row, dict):
            seen = max(seen, _highest(row.get(INDEXES_FIELD)))
    return seen or VISIT_TYPES


def daily_passes(raw_data):
    """The Communication Passes a day grants this account: the base,
    and what each research node it holds adds at its level.

    A snapshot without the research map reads the most a day can grant,
    every node at its top level. The map comes in the same block as the
    day's counter, so a snapshot short of it has no count to set against
    it either.
    """
    stated = game_client.known_limits()
    base = stated.get("visit_tickets")
    research = stated.get("visit_research")
    base = base if _is_count(base) else VISIT_TICKETS
    research = research if isinstance(research, dict) and research \
        else VISIT_RESEARCH
    held = _dig(raw_data, RESEARCH_PATH)
    total = base
    for node, figures in research.items():
        level = held.get(node) if isinstance(held, dict) else len(figures)
        if _is_count(level) and level > 0 and figures:
            total += figures[min(level, len(figures)) - 1]
    return total


def passes_left(raw_data):
    """Communication Passes left today, or None if nothing says.

    `daily_passes - use_town_visit_count`. Spending a pass debits
    nothing, so this is the only reading of it a snapshot allows.
    """
    spent = _dig(raw_data, SPENT_PATH)
    if not _is_count(spent):
        return None
    return max(0, daily_passes(raw_data) - spent)


def _dig(raw_data, path):
    """The value at `path` in a snapshot, or None."""
    node = raw_data or {}
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _is_count(value):
    """Whether a snapshot's value is a whole number, not a flag."""
    return isinstance(value, int) and not isinstance(value, bool)


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
