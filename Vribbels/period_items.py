"""Items held with an expiry, read out of a snapshot.

**A period item is not counted, it is listed.** Where an ordinary item
is one entry carrying an `amount`, a period item is one entry PER COPY
carrying an `end_time` -- three Command Delegation Modules are three
entries of count 1, expiring at three different moments. So the number
held is the number of entries, and nothing in the snapshot states it.

`end_time` is epoch SECONDS, UTC. The game shows a local time, so a
reading taken off the screen is the maintainer's offset away from what
is stored -- which is why the formatting below converts rather than
printing the stored value.

No Tk and no managers: this takes the snapshot's inventory dict and
returns data, which is what lets it be exercised without a window.
"""

from datetime import datetime, timezone

from game_data.constants import PERIOD_ITEMS

# How a moment is written for the user. Local time, because that is
# what the game showed them.
WHEN_FORMAT = "%Y-%m-%d %H:%M:%S"


def held(inventory):
    """{res_id: [expiry, ...]} for every period item in a snapshot.

    Expiries are epoch seconds, sorted soonest first. An entry with no
    `end_time` is skipped rather than counted as never expiring: the
    field is the only thing that makes one of these a period item, and
    a copy without one is a shape this does not understand.
    """
    out = {}
    for entry in (inventory or {}).get("period_items") or []:
        res_id = entry.get("res_id")
        if res_id is None:
            continue
        for copy in entry.get("value") or []:
            end = copy.get("end_time")
            if isinstance(end, (int, float)) and end > 0:
                out.setdefault(res_id, []).append(int(end))
    return {res_id: sorted(times) for res_id, times in out.items()}


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
