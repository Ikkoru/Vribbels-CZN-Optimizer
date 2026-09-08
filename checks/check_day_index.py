"""`weekly_reset.day_index` against the numbers the game itself sent.

The wire stamps a day number on anything that happens once a day, and
the Checklist reads today's Activities claim by comparing one of them
against the clock. Getting the epoch or the reset hour wrong shifts
every comparison by a whole day and nothing raises: the row simply
reports the opposite of the truth, and only for part of the day.

So the cases below are OBSERVATIONS, not arithmetic. Each is a
(day number, epoch second) pair read out of a capture, taken from a
`point_reward` reply -- the one message that writes the day number and
carries the server's own clock in the same frame, so the two cannot
drift apart. A pair either side of a boundary pins the hour as well as
the offset.

No Tk and no snapshot needed.
"""

from ._harness import add_source_to_path

NAME = "day index"

# (day number, the server time it was written at, what was happening).
# Straight out of `websocket_debug_*.jsonl`; see the module docstring.
OBSERVED = (
    (1345, 1788741198, "claimed 2026-09-07 00:33 UTC"),
    (1346, 1788812715, "claimed 2026-09-07 20:25 UTC"),
    (1347, 1788896698, "claimed 2026-09-08 19:44 UTC"),
    # A daily record issued by the reset itself, twenty seconds after
    # the boundary -- so this one also says WHERE the boundary is.
    (1347, 1788890420, "daily_achieve_001 issued at the 2026-09-08 reset"),
)

# The last second of day 1346 and the first of day 1347, from the pair
# above. A reset hour an hour out still passes every observation that
# sits mid-day; only a pair straddling the boundary catches it.
BOUNDARY = 1788890400


def run():
    add_source_to_path()
    import weekly_reset

    failures = []
    for day, when, what in OBSERVED:
        got = weekly_reset.day_index(when)
        if got != day:
            failures.append(
                f"day_index({when}) is {got} where the game said {day} "
                f"({what}). Every day-stamped record now compares against "
                f"the wrong day, so the Checklist's Activities row reads "
                f"backwards for part of each day.")

    if weekly_reset.day_index(BOUNDARY - 1) != 1346:
        failures.append(
            f"the second before {BOUNDARY} is day "
            f"{weekly_reset.day_index(BOUNDARY - 1)}, not 1346. The day "
            f"turns over at the wrong hour.")
    if weekly_reset.day_index(BOUNDARY) != 1347:
        failures.append(
            f"{BOUNDARY} itself is day {weekly_reset.day_index(BOUNDARY)}, "
            f"not 1347. The boundary belongs to the day it starts.")

    # The epoch is a day boundary, so it has to agree with the hour the
    # week turns on. Drifting them apart is a one-line edit away.
    if weekly_reset.last_daily_reset(weekly_reset.DAY_EPOCH) \
            != weekly_reset.DAY_EPOCH:
        failures.append(
            f"DAY_EPOCH ({weekly_reset.DAY_EPOCH}) is not itself a "
            f"RESET_HOUR boundary. The two are measurements of the same "
            f"thing and correcting one means correcting the other.")
    return failures
