"""An item held with an expiry is LISTED, not counted.

Every other item in a snapshot is one entry carrying an `amount`. A
period item is one entry per item listing its COPIES, each carrying an
`end_time` and a `count`: three Command Delegation Modules are three
copies of count 1, and 17 Abyssal Cores two copies of 8 and 9. Nothing
in the file states the number held. Reading one of these the ordinary
way gets `amount` of None and reports nothing held, which looks exactly
like owning none; reading the copies without their counts reports 2.

**`expiring` must find one every way a snapshot can say it is held**,
since the Checklist's Expiring Items row lists only what it finds: the
lists of copies, an ordinary holding the client's period table names or
whose name says it is time-limited, and one whose record carries an
expiry of its own.

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

    # A copy standing for several items is that many.
    counted = pi.held({"period_items": [{"res_id": known, "value": [
        {"count": 3, "end_time": 1788710956},
        {"count": 1, "end_time": 1788819739}]}]})
    if len(counted.get(known, ())) != 4:
        failures.append(
            f"a copy of count 3 and one of count 1 came back as "
            f"{counted.get(known)}: a count of 3 is three items, and the "
            f"Delegation Module rows count the list's length.")

    failures.extend(_expiring(pi))
    failures.extend(_modules(pi))
    return failures


def _modules(pi):
    """Every length of Time-Limited Command Delegation Module counts
    together, a length the program has not met among them -- and one
    the shipped client table holds that nobody approved fails here, the
    maintainer's cue to name it in `MODULE_ITEMS` or decide otherwise."""
    failures = []
    names = {7: "Time-Limited Command Delegation Module - 7 Days",
             21: "Time-Limited Command Delegation Module - 21 Days"}
    unmet = 999999910
    inventory = {"period_items": [
        {"res_id": 3920025, "value": [{"count": 1, "end_time": 100}]},
        {"res_id": 3920026, "value": [{"count": 2, "end_time": 300}]},
        {"res_id": 3920027, "value": [{"count": 1, "end_time": 200}]},
        {"res_id": unmet, "value": [{"count": 1, "end_time": 400}]},
        {"res_id": 3920039, "value": [{"count": 5, "end_time": 50}]}]}
    name_of = {3920025: names[7], 3920026: "Time-Limited Command "
               "Delegation Module - 14 Days", 3920027: names[21],
               unmet: "Time-Limited Command Delegation Module - 30 Days",
               3920039: "Abyssal Core (Time-Limited)",
               2000052: "Command Delegation Module"}.get
    got = pi.module_expiries(inventory, name_of)
    if got != [100, 200, 300, 300, 400]:
        failures.append(
            f"the Delegation Module copies read {got}, not [100, 200, 300, "
            f"300, 400]: the 7-, 14- and 21-day modules and one of a length "
            f"the program has not met, counted together, and nothing else.")
    if pi.new_modules(inventory, name_of) != {unmet}:
        failures.append(
            f"the modules nobody approved read "
            f"{sorted(pi.new_modules(inventory, name_of))}, not [{unmet}]")
    if 2000052 in pi.module_items(inventory, name_of):
        failures.append(
            "2000052, a subscription's Command Delegation Module, was "
            "counted as a Time-Limited module: it folds into the currency "
            "the Chaos Delegation row reads")

    shipped = pi.new_modules()
    if shipped:
        from game_data.constants import item_names
        named = item_names()
        failures.append(
            f"the shipped client table holds Delegation Module(s) the "
            f"program has not been told about: "
            f"{', '.join(f'{rid} {named.get(rid)!r}' for rid in sorted(shipped))}"
            f". They are counted with the others in the Checklist's "
            f"Delegation Module rows and the Materials tab. Add them to "
            f"period_items.MODULE_ITEMS to keep that, or treat them "
            f"otherwise.")
    return failures


NOW = 1792884151
SEASON_END = 1797984000
LISTED = 3920039            # Abyssal Core (Time-Limited)
SCHEDULED = 3920033         # Diallos's Radiance (Time-Limited)
NAMED_ONLY = 999999901      # a name with the marker, in no table
OWN_DATE = 999999902        # no table, no marker, a date of its own
PLAIN = 999999903           # an ordinary item, held


def _expiring(pi):
    """Each way in, alone, and what must stay out."""
    failures = []
    names = {NAMED_ONLY: "Mystery Core (Time-Limited)",
             OWN_DATE: "Odd Thing", PLAIN: "Plain Core"}
    raw = {
        "inventory": {
            "period_items": [{"res_id": LISTED, "value": [
                {"type": "SHOP", "count": 8, "end_time": SEASON_END},
                {"type": "SYSTEM", "count": 9, "end_time": SEASON_END},
                # Gone in the game, however old the snapshot.
                {"type": "SYSTEM", "count": 5, "end_time": NOW - 60}]},
                {"res_id": 3920045, "value": [
                    {"count": 2, "end_time": NOW - 60}]}],
            "period_currencies": [{"res_id": 3920046, "amount": 4,
                                   "end_time": NOW + 3600}],
            "items": [{"res_id": SCHEDULED, "amount": 2},
                      {"res_id": NAMED_ONLY, "amount": 1},
                      {"res_id": OWN_DATE, "amount": 6,
                       "end_time": NOW + 7200},
                      {"res_id": PLAIN, "amount": 9},
                      {"res_id": 3920034, "amount": 0}],
        },
        "event_schedules": {"DISASTER_SEASON": {"disaster_s05": {
            "start_time": NOW - 86400, "end_time": SEASON_END}}},
    }
    found = pi.expiring(raw, NOW, names.get)
    want = {
        LISTED: ((17, SEASON_END),
                 "listed copies: their counts added up, the one already "
                 "past its expiry left out"),
        3920046: ((4, NOW + 3600),
                  "a `period_currencies` record carrying its own expiry"),
        SCHEDULED: ((2, SEASON_END),
                    "an ordinary holding the client's period table links to "
                    "a schedule, dated by that schedule's end"),
        NAMED_ONLY: ((1, None),
                     "an ordinary holding whose name carries the marker, "
                     "with no date anything states"),
        OWN_DATE: ((6, NOW + 7200),
                   "an ordinary holding whose record carries an expiry"),
    }
    for res_id, (pair, why) in want.items():
        if found.get(res_id) != pair:
            failures.append(f"{why}: read {found.get(res_id)}, not {pair}")
    for res_id, why in ((3920045, "an item whose every copy has expired"),
                        (PLAIN, "an ordinary item with no expiry"),
                        (3920034, "a period item held at 0")):
        if res_id in found:
            failures.append(f"{why} was listed as expiring: {found[res_id]}")

    for name, bare in (("Abyssal Core (Time-Limited)", "Abyssal Core"),
                       ("Core of Potential [Time-Limited]",
                        "Core of Potential"),
                       ("Time-Limited Command Delegation Module - 14 Days",
                        "Command Delegation Module - 14 Days")):
        if pi.bare_name(name) != bare:
            failures.append(f"{name!r} bared to {pi.bare_name(name)!r}, "
                            f"not {bare!r}")
    return failures


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a copy's count ignored",
     "period_items:held",
     "out.setdefault(res_id, []).extend([end] * count)",
     "out.setdefault(res_id, []).append(end)",
     "a count of 3 is three items"),
    ("expired copies kept",
     "period_items:expiring",
     "if end > now:",
     "if True:",
     "already past its expiry"),
    ("the name not read",
     "period_items:expiring",
     'or TIME_LIMITED.search(name_of(res_id) or ""))):',
     "or False)):",
     "whose name carries the marker"),
    ("the schedule link not followed",
     "period_items:expiring",
     "end = own.get(res_id) or _schedule_end(raw, rules.get(res_id))",
     "end = own.get(res_id)",
     "dated by that schedule's end"),
    ("an ordinary record's own expiry not read",
     "period_items:expiring",
     "or not (res_id in rules or res_id in own",
     "or not (res_id in rules",
     "whose record carries an expiry"),
    ("a module length the program has not met left out",
     "period_items:module_items",
     "return frozenset(MODULE_ITEMS) | frozenset(",
     "return frozenset(MODULE_ITEMS) or frozenset(",
     "has not met, counted together"),
    ("a subscription's module counted",
     "period_items:module_items",
     "if (rules.get(res_id) or (\"\",))[0] != NOT_A_MODULE_CLOCK",
     "if True",
     "subscription's Command Delegation Module"),
    ("an unapproved module in the shipped table",
     "period_items:MODULE_ITEMS",
     "MODULE_ITEMS = (3920025, 3920026, 3920027)",
     "MODULE_ITEMS = (3920026,)",
     "has not been told about"),
]
