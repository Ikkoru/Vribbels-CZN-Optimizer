"""When each of the game's contents opened, and when it closes.

`event_schedules` is one group per kind of content, each holding every
instance the account has seen with a `start_time` and an `end_time`:

    {"ASSAULT_SCHEDULE":   {"assault_1_s6":     {start, end}},
     "HYPER_SPACE_SEASON": {"hyperspace_02_16": {start, end}},
     "SEASON_PASS":        {"season_pass_008":  {start, end}}, ...}

**Nothing else dates any of them.** A Sortie product's cap is
`LIMIT_ACCOUNT`, which never refreshes -- what actually refreshes it is
the season ending, and the season's end is only here. The same goes for
the Basin, the pass, the seasonal event and the Chaos Matrix, whose
lengths the Checklist used to guess at in its labels.

Past instances stay in the table, so `live` is what picks the one that
is running: `start_time <= now <= end_time`. Where two overlap the one
ending SOONEST wins -- that is the deadline a checklist is about.

**A never-ending window is not a deadline.** The permanent banners and
subscriptions carry an `end_time` in 2099, and counting down to it
would print a five-digit number of days, so anything past
`FOREVER_DAYS` reads as no deadline at all.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

FIELD = "event_schedules"

# Past this many days out, a window is permanent rather than pending.
# The game's own "never" is 2099, so anything in years is one.
FOREVER_DAYS = 365

HOUR = 3600
DAY = 24 * HOUR


def groups(raw_data):
    """{group: {id: window}} from a snapshot."""
    out = (raw_data or {}).get(FIELD)
    return out if isinstance(out, dict) else {}


def live(group, raw_data, now):
    """(id, window) for the instance running now, or (None, None).

    The one ending SOONEST where several overlap, since that is the
    deadline. A window ending past `FOREVER_DAYS` is not a deadline and
    is skipped.
    """
    best = None
    for name, window in groups(raw_data).get(group, {}).items():
        if not isinstance(window, dict):
            continue
        start, end = window.get("start_time"), window.get("end_time")
        if not _is_time(start) or not _is_time(end):
            continue
        if not start <= now <= end:
            continue
        if end - now > FOREVER_DAYS * DAY:
            continue
        if best is None or end < best[1]["end_time"]:
            best = (name, window)
    return best if best else (None, None)


def all_live(group, raw_data, now):
    """[(id, window)] for every instance of `group` running now.

    Soonest deadline first. `live` answers a different question -- ONE
    instance, for a row that counts down to a single date -- and a
    group can run several at once: three events under `EVENT_SCHEDULE`
    overlapped in one capture, and listing one of them would have left
    two out of a list whose whole point is to be complete.
    """
    found = []
    for name, window in groups(raw_data).get(group, {}).items():
        if not isinstance(window, dict):
            continue
        start, end = window.get("start_time"), window.get("end_time")
        if not _is_time(start) or not _is_time(end):
            continue
        if start <= now <= end and end - now <= FOREVER_DAYS * DAY:
            found.append((end, name, window))
    return [(name, window) for _end, name, window in sorted(found)]


def season_start(group, raw_data, now):
    """When the season a tally belongs to began, or None.

    The LATEST instance already under way, which is not the same
    question `live` answers: between one season and the next there is
    no running instance, and the shelves still hold what the season
    just ended left on them. Falling back to the last one to have
    started keeps those readings; taking the live one would blank them
    for the gap.
    """
    best = None
    for window in groups(raw_data).get(group, {}).values():
        if not isinstance(window, dict):
            continue
        start = window.get("start_time")
        if _is_time(start) and start <= now and (best is None or start > best):
            best = start
    return best


def remaining(group, raw_data, now):
    """How long the live instance of `group` has, in seconds, or None."""
    _name, window = live(group, raw_data, now)
    return None if window is None else max(0, window["end_time"] - now)


def countdown(seconds):
    """`22 days`, `1 day`, `23h`, `44m`, or `over`.

    Days down to the hour, hours down to the minute: the point of the
    line is whether something has to be done today, and a seconds
    figure on a three-week season is noise. Rounded DOWN, so nothing is
    promised time it does not have.
    """
    if seconds is None:
        return None
    if seconds <= 0:
        return "over"
    if seconds >= DAY:
        days = int(seconds // DAY)
        return "1 day" if days == 1 else "%d days" % days
    if seconds >= HOUR:
        return "%dh" % int(seconds // HOUR)
    return "%dm" % max(1, int(seconds // 60))


def _is_time(value):
    """True for something comparable against an epoch second."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
