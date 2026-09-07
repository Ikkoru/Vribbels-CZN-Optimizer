"""When the game rolls over, daily and weekly, and how long is left.

Weekly stock -- Loot Certification Cards, Reason -- is spent against
this deadline rather than against an expiry stamped on the item, so
nothing in a snapshot says when it runs out. The clock is the only
source, and it is the same clock for every account.

**Both boundaries fall at the same hour**, 18:00 UTC; the weekly one is
the Sunday. So they share `RESET_HOUR`, and correcting the game's reset
time is one edit.

UTC throughout. The local zone would move the deadline for anyone east
or west of it, and a snapshot carries no timezone of its own.
"""

from datetime import datetime, timedelta, timezone

# Sunday 18:00 UTC, as `datetime.weekday()` numbers the days (Monday
# 0). Both are here rather than inline so that a corrected reset is one
# edit.
RESET_WEEKDAY = 6
RESET_HOUR = 18


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


def next_daily_reset(now):
    """The next DAILY reset strictly after `now`, in epoch seconds.

    18:00 UTC, the same hour the week turns on. Strictly, for the
    reason `next_reset` is strict: standing exactly on a reset, what is
    left is the whole day that just began.
    """
    at = datetime.fromtimestamp(now, timezone.utc)
    reset = at.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if reset <= at:
        reset += timedelta(days=1)
    return reset.timestamp()
