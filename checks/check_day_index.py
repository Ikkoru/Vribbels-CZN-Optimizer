"""`weekly_reset.day_index` and `week_index` against the game's own.

The wire stamps a day number on anything that happens once a day and a
week number on anything that resets weekly, and the Checklist reads
both by comparing them against the clock. Getting the epoch or the
reset hour wrong shifts every comparison by a whole period and nothing
raises: the row simply reports the opposite of the truth, and only for
part of the period.

So the cases below are OBSERVATIONS, not arithmetic. Each day case is
a (day number, epoch second) pair read out of a capture, taken from a
`point_reward` reply -- the one message that writes the day number and
carries the server's own clock in the same frame, so the two cannot
drift apart. A pair either side of a boundary pins the hour as well as
the offset.

The week cases are the same idea one period up: a `week_id` the login
burst stamped on a record, against the capture's own server time.

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

# (week number, a server time inside it, where the number came from).
# The login burst stamps `week_id` on the season pass's record, on a
# disaster season's row and on the Great Rift standings, and all three
# agreed in every capture -- so one number per capture is enough.
OBSERVED_WEEKS = (
    (193, 1789131623, "season_pass_008 / disaster_s04 at the 09-11 login"),
    (193, 1789232707, "the same three at the 09-12 login"),
    # Taken 1h37m after the weekly reset, with the records still
    # stamped 193: the DERIVED week has to be 194 by then, which is
    # exactly what makes those records readable as last week's.
    (194, 1789328267, "the 09-13 login, after the Sunday 18:00 reset"),
)

# The last second of week 193 and the first of week 194. `next_reset`
# computes this boundary from the weekday and `week_index` from the day
# number; they are two routes to one instant and must not drift.
WEEK_BOUNDARY = 1789322400


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

    # --- the week number, the same way --------------------------------
    for week, when, what in OBSERVED_WEEKS:
        got = weekly_reset.week_index(when)
        if got != week:
            failures.append(
                f"week_index({when}) is {got} where the game said {week} "
                f"({what}). Every weekly record now compares against the "
                f"wrong week, so last week's full score reads as this "
                f"week's and the row says the work is done.")

    if weekly_reset.week_index(WEEK_BOUNDARY - 1) != 193:
        failures.append(
            f"the second before {WEEK_BOUNDARY} is week "
            f"{weekly_reset.week_index(WEEK_BOUNDARY - 1)}, not 193. The "
            f"week turns over in the wrong place.")
    if weekly_reset.week_index(WEEK_BOUNDARY) != 194:
        failures.append(
            f"{WEEK_BOUNDARY} itself is week "
            f"{weekly_reset.week_index(WEEK_BOUNDARY)}, not 194. The "
            f"boundary belongs to the week it starts.")

    # **Two routes to one instant.** `next_reset` works from the
    # weekday and `week_index` from the day number; a corrected
    # `RESET_WEEKDAY` has to move both or the rows disagree with the
    # countdown beside them.
    for when in (BOUNDARY, WEEK_BOUNDARY, 1789131623, 1786000000):
        opened = weekly_reset.last_weekly_reset(when)
        if weekly_reset.week_index(opened) != weekly_reset.week_index(when):
            failures.append(
                f"the week containing {when} opened at {opened}, which "
                f"week_index calls week "
                f"{weekly_reset.week_index(opened)} against "
                f"{weekly_reset.week_index(when)}. `next_reset` and "
                f"`week_index` have drifted apart.")
        if weekly_reset.week_index(opened - 1) != \
                weekly_reset.week_index(when) - 1:
            failures.append(
                f"the second before {when}'s own week opened is still "
                f"week {weekly_reset.week_index(opened - 1)}. The two "
                f"routes put the boundary in different places.")
    return failures
