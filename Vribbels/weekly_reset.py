"""When the game's week rolls over, and how long is left of it.

Weekly stock -- Loot Certification Cards, Reason -- is spent against
this deadline rather than against an expiry stamped on the item, so
nothing in a snapshot says when it runs out. The clock is the only
source, and it is the same clock for every account.

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
