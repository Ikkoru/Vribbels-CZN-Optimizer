"""Items held with an expiry, read out of a snapshot.

**A period item is not counted, it is listed.** Where an ordinary item
is one entry carrying an `amount`, a period item is one entry per ITEM
whose `value` lists its COPIES, each with its own `end_time` and a
`count`. Three Command Delegation Modules picked up on three days are
three copies of count 1; a Galactic Disaster season's 17 Abyssal Cores
are two copies, one per way they arrived (`SHOP` 8, `SYSTEM` 9), both
ending with the season. So the number held is the copies' counts added
up, one level deeper than a reader expects, and nothing states it.

`end_time` is epoch SECONDS, UTC. The game shows a local time, so a
reading taken off the screen is the maintainer's offset away from what
is stored -- which is why the formatting below converts rather than
printing the stored value.

**`expiring` finds them every way a snapshot can say one is held**,
since a held item it misses is one the Checklist says nothing about:
the lists of copies, and any ordinary holding the game client's period
table names, whose name says it is time-limited, or whose record
carries an expiry of its own. See `expiring`.

No Tk and no managers: this takes snapshot dicts and returns data,
which is what lets it be exercised without a window.
"""

import re
from datetime import datetime, timezone

import game_client
import item_amounts
import schedules
from game_data.constants import PERIOD_ITEMS, item_names

# How a moment is written for the user. Local time, because that is
# what the game showed them.
WHEN_FORMAT = "%Y-%m-%d %H:%M:%S"

# Where a snapshot lists items as COPIES, each list shaped as
# `inventory.period_items` is. The two `period_currencies` have only
# ever arrived empty; read the same way, a currency the game puts on a
# clock is found with no edit.
COPY_LISTS = (("inventory", "period_items"),
              ("inventory", "period_currencies"),
              ("characters", "period_currencies"))

# The fields a record could carry its own expiry under: a copy's
# `end_time`, and the wire's other spelling for one, which its other
# timed records use (`issued_limit_entities`, `shop_list`).
EXPIRY_FIELDS = ("end_time", "expire_time")

# What marks a time-limited item in its name, in every spelling the
# client has used: `Abyssal Core (Time-Limited)`, `Core of Potential
# [Time-Limited]`, `Time-Limited Command Delegation Module - 14 Days`.
TIME_LIMITED = re.compile(
    r"[(\[]\s*time[- ]limited\s*[)\]]|^\s*time[- ]limited\b", re.I)


def held(inventory):
    """{res_id: [expiry, ...]} for every period item in a snapshot, one
    expiry per item held: a copy of count 3 is three.

    Expiries are epoch seconds, sorted soonest first. An entry with no
    `end_time` is skipped rather than counted as never expiring: the
    field is the only thing that makes one of these a period item, and
    a copy without one is a shape this does not understand.
    """
    out = {}
    for entry in (inventory or {}).get("period_items") or []:
        res_id = entry.get("res_id") if isinstance(entry, dict) else None
        if res_id is None:
            continue
        for end, count in _copies(entry):
            out.setdefault(res_id, []).extend([end] * count)
    return {res_id: sorted(times) for res_id, times in out.items()}


def expiring(raw, now=None, name_of=None):
    """{res_id: (how many are held, the soonest expiry or None)} for
    every item a snapshot holds that the game will delete.

    Three ways in, each a check on the others, since an item read none
    of them is one the user is never told about:

    - **Listed as copies** (`COPY_LISTS`), each with its expiry. Exact.
    - **An ordinary holding** (`item_amounts.held`) the game client's
      period table lists (`game_client.known_period_items`), or whose
      name carries the marker (`TIME_LIMITED`). Such a record states
      an amount and no expiry, so its date is its own record's
      (`EXPIRY_FIELDS`) where it carries one, else the end of the
      schedule the table links it to (`event_schedules`), else None.
    - **An ordinary holding whose record carries an expiry of its own**,
      whatever its name and whether or not any table lists it.

    A copy already past its expiry is gone in the game, however old the
    snapshot, and is left out; an item with nothing left is not held.

    `now` is epoch seconds, defaulting to the real clock. `name_of` maps
    a res_id to its name, `game_data.constants.item_names` by default.
    """
    now = datetime.now(tz=timezone.utc).timestamp() if now is None else now
    if name_of is None:
        name_of = item_names().get
    found = {}
    for path in COPY_LISTS:
        node = raw or {}
        for step in path:
            node = node.get(step) if isinstance(node, dict) else None
        for entry in node if isinstance(node, list) else ():
            res_id = _res_id(entry.get("res_id")) \
                if isinstance(entry, dict) else None
            if res_id is None:
                continue
            for end, count in _copies(entry):
                if end > now:
                    count_was, soonest = found.get(res_id, (0, None))
                    found[res_id] = (count_was + count,
                                     end if soonest is None
                                     else min(soonest, end))

    rules = game_client.known_period_items()
    own = _own_expiries(raw)
    for res_id, amount in item_amounts.held(raw).items():
        if (res_id in found or not isinstance(amount, int) or amount <= 0
                or not (res_id in rules or res_id in own
                        or TIME_LIMITED.search(name_of(res_id) or ""))):
            continue
        end = own.get(res_id) or _schedule_end(raw, rules.get(res_id))
        if end is not None and end <= now:
            continue
        found[res_id] = (amount, end)
    return found


def bare_name(name):
    """An item's name without its time-limited marker (`TIME_LIMITED`):
    `Abyssal Core`, `Command Delegation Module - 14 Days`."""
    return " ".join(TIME_LIMITED.sub(" ", name or "").split())


def describe(res_id, expiries, now=None):
    """User-facing lines for one period item: a count, then each expiry.

    `now` is epoch seconds, defaulting to the real clock -- passed in
    by the check, which cannot depend on what time it runs at.

    Returns [] for an id no table names, rather than inventing a title
    for a number.
    """
    named = PERIOD_ITEMS.get(res_id)
    if named is None or not expiries:
        return []
    name = named[0]
    now = datetime.now(tz=timezone.utc).timestamp() if now is None else now
    lines = [f"{name}: {len(expiries)}"]
    for end in expiries:
        when = datetime.fromtimestamp(end, tz=timezone.utc).astimezone()
        lines.append(f"    expires {when:{WHEN_FORMAT}}"
                     f"  ({remaining(end - now)})")
    return lines


def remaining(seconds):
    """`2d 4h`, `4h 12m`, `12m`, or `expired`.

    Two units and never three: the point of the line is whether a copy
    needs using today, and a seconds figure on a fourteen-day timer is
    noise.
    """
    if seconds <= 0:
        return "expired"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _copies(entry):
    """[(expiry, how many)] for one listed entry's copies.

    A copy's `count` is how many items it stands for, 1 where it says
    nothing; one stating 0 or less holds none. **An entry with no copy
    list that carries an expiry itself is one copy** of its own `count`
    or `amount`: the shape a `period_currencies` row would most likely
    take, none having arrived yet to say.
    """
    copies = entry.get("value")
    if not isinstance(copies, list):
        copies = [entry] if _expiry(entry) else []
    out = []
    for copy in copies:
        end = _expiry(copy) if isinstance(copy, dict) else None
        if end is None:
            continue
        count = copy.get("count", copy.get("amount", 1))
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            count = 1
        if count >= 1:
            out.append((end, int(count)))
    return out


def _expiry(record):
    """A record's own expiry in epoch seconds (`EXPIRY_FIELDS`), or
    None; 0, which the game writes for none, is none."""
    for field in EXPIRY_FIELDS:
        value = record.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and value > 0:
            return int(value)
    return None


def _own_expiries(raw):
    """{res_id: expiry} for every ordinary holding whose record carries
    one: the item list's entries and the currency table's records."""
    out = {}
    inventory = (raw or {}).get("inventory") or {}
    records = list(inventory.get("items") or []) if isinstance(
        inventory, dict) else []
    currencies = ((raw or {}).get("characters") or {}).get("currencies")
    if isinstance(currencies, dict):
        records += list(currencies.values())
    for record in records:
        if not isinstance(record, dict):
            continue
        res_id, end = _res_id(record.get("res_id")), _expiry(record)
        if res_id is not None and end is not None:
            out[res_id] = end
    return out


def _schedule_end(raw, rule):
    """When the schedule a period rule links to ends, or None: the rule
    names none, or the snapshot's `event_schedules` does not hold it."""
    schedule = rule[2] if isinstance(rule, (list, tuple)) \
        and len(rule) == 3 else None
    if not schedule:
        return None
    for windows in schedules.groups(raw).values():
        window = windows.get(schedule) if isinstance(windows, dict) else None
        if isinstance(window, dict):
            end = window.get("end_time")
            if isinstance(end, (int, float)) and end > 0:
                return int(end)
    return None


def _res_id(value):
    """A res_id as the int every table keys on, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else None
