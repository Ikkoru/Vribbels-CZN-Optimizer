"""When the game's week rolls over, and how long is left of it.

Weekly stock -- Loot Certification Cards, Reason -- is spent against
this deadline rather than against an expiry stamped on the item, so
nothing in a snapshot says when it runs out. The clock is the only
source, and it is the same clock for every account.

**An item carrying its own `end_time` is not read against this.** A
Command Delegation Module expires fourteen days after it was acquired
and no reset moves that, so the Checklist counts those in rolling
windows from now -- see `ui/tabs/checklist_tab.MODULE_WINDOWS`.

The DAY turns on the same hour, so the daily boundary and the wire's
own day numbering live here too -- see `day_index`.

UTC throughout. The local zone would move the deadline for anyone east
or west of it, and a snapshot carries no timezone of its own.
"""

from datetime import datetime, timedelta, timezone

# Sunday 18:00 UTC, as `datetime.weekday()` numbers the days (Monday
# 0). Both are here rather than inline so that a corrected reset is one
# edit.
RESET_WEEKDAY = 6
RESET_HOUR = 18

DAY = 24 * 3600

# When day 0 began, in epoch seconds: 2022-12-31 18:00 UTC.
#
# The wire counts days from here and stamps the number on anything that
# happens once a day -- `point_entity.day_id`, `attendance_entities`'
# `start_dayid` / `last_dayid`, a free gacha's `last_issued_day_id`.
# The epoch is a day BOUNDARY, so it carries `RESET_HOUR` inside it: a
# corrected reset hour has to move this by the same amount.
DAY_EPOCH = 1672509600


def next_reset(now):
    """The next weekly reset STRICTLY after `now`, in epoch seconds.

    Strictly: standing exactly on a reset, what is left is a whole week
    and not nothing -- the week that just began.
    """
    at = datetime.fromtimestamp(now, timezone.utc)
    reset = (at.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
             + timedelta(days=(RESET_WEEKDAY - at.weekday()) % 7))
    if reset <= at:
        reset += timedelta(days=7)
    return reset.timestamp()


def hours_left(now):
    """Hours from `now` to the next weekly reset. Always positive."""
    return (next_reset(now) - now) / 3600


def last_daily_reset(now):
    """The `RESET_HOUR` boundary at or before `now`, epoch seconds."""
    at = datetime.fromtimestamp(now, timezone.utc).replace(
        hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    stamp = at.timestamp()
    return stamp if stamp <= now else stamp - DAY


def month_bounds(now):
    """(start, end) of the game month `now` falls in, epoch seconds.

    The calendar month shifted onto `RESET_HOUR`: it opens on the
    boundary before the 1st and closes one second before the boundary
    that opens the next. Checked against a capture, which stated
    2026-08-31 18:00 and 2026-09-30 17:59:59 for September.

    DERIVED because the wire's own `month_start` / `month_end` arrive
    with the login and a fresh install has neither -- which left the
    Monthly column with no countdown until the first capture. The wire
    is still preferred where it is there; this answers when it is not.
    """
    at = datetime.fromtimestamp(last_daily_reset(now), timezone.utc)
    # The boundary opens the NEXT calendar day, and that is the day the
    # game counts as today -- so the month is that day's, not the
    # boundary's own.
    today = (at + timedelta(days=1)).date()

    def opens(year, month):
        first = datetime(year, month, 1, RESET_HOUR, tzinfo=timezone.utc)
        return (first - timedelta(days=1)).timestamp()

    following = (today.year + today.month // 12,
                 today.month % 12 + 1)
    return opens(today.year, today.month), opens(*following) - 1


def day_index(now):
    """The wire's day number for `now`.

    Compare a `day_id` against this to tell TODAY's record from a stale
    one. The rows the game stamps a day on are written lazily: nothing
    rolls them at reset, so yesterday's row survives untouched into
    today and only says which day it belongs to.
    """
    return int((now - DAY_EPOCH) // DAY)

