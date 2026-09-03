"""An item held with an expiry is LISTED, not counted.

Every other item in a snapshot is one entry carrying an `amount`. A
period item is one entry per COPY carrying an `end_time`, so three
Command Delegation Modules are three entries of count 1 and nothing in
the file states the number three. Reading one of these the ordinary way
gets `amount` of None and reports nothing held, which looks exactly
like owning none.

The times are epoch SECONDS in UTC and the game shows them local, so a
reading taken off the screen is the user's offset away from the stored
value. That conversion is the other thing worth pinning: it is
invisible until someone in a different offset reads a wrong hour.

No Tk and no snapshot needed -- the shapes are synthesised here.
"""

from ._harness import add_source_to_path

NAME = "period items"


def run():
    add_source_to_path()
    import period_items as pi
    from game_data.constants import PERIOD_ITEMS

    failures = []
    known = next(iter(PERIOD_ITEMS))

    # Three copies, out of order, one of them malformed.
    inventory = {"period_items": [
        {"res_id": known, "value": [
            {"id": str(known), "type": "SYSTEM", "count": 1,
             "end_time": 1788819739},
            {"id": str(known), "type": "SYSTEM", "count": 1,
             "end_time": 1788710956},
            {"id": str(known), "type": "SYSTEM", "count": 1},
        ]},
    ]}
    held = pi.held(inventory)
    if held.get(known) != [1788710956, 1788819739]:
        failures.append(
            f"three entries, one without an end_time, came back as "
            f"{held.get(known)}. The count is the number of entries that "
            f"HAVE one, soonest first -- a copy with no expiry is a shape "
            f"this does not understand, not one that never expires."
        )

    for shape in ({}, {"period_items": None}, {"period_items": []},
                  {"period_items": [{"value": []}]}):
        if pi.held(shape) != {}:
            failures.append(f"{shape} should hold nothing, got {pi.held(shape)}")

    # The stored time is UTC; the line shows it local.
    lines = pi.describe(known, [1788710956], now=1788710956 - 3600)
    if len(lines) != 2 or not lines[0].endswith(": 1"):
        failures.append(f"one copy described as {lines}, expected a count "
                        f"line and one expiry")
    elif "1h 0m" not in lines[1]:
        failures.append(
            f"an expiry an hour away reads {lines[1]!r}. `now` is epoch "
            f"seconds and the difference is what the remaining figure is "
            f"built from."
        )
    else:
        from datetime import datetime, timezone
        want = datetime.fromtimestamp(1788710956, tz=timezone.utc).astimezone()
        if f"{want:%Y-%m-%d %H:%M:%S}" not in lines[1]:
            failures.append(
                f"the expiry line {lines[1]!r} does not carry the LOCAL "
                f"time {want:%Y-%m-%d %H:%M:%S}. The game shows local and "
                f"the snapshot stores UTC."
            )

    if pi.describe(-1, [1788710956]) != []:
        failures.append("an id no table names should describe as nothing "
                        "rather than being given a title")
    if pi.describe(known, []) != []:
        failures.append("no copies should describe as nothing")

    for seconds, want in ((0, "expired"), (-5, "expired"), (60, "1m"),
                          (3600 + 120, "1h 2m"), (86400 * 2 + 3600, "2d 1h")):
        got = pi.remaining(seconds)
        if got != want:
            failures.append(f"remaining({seconds}) is {got!r}, not {want!r}")

    return failures
