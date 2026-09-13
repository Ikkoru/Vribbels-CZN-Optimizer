"""What the Checklist rows read off a snapshot.

Every one of these fails by printing a plausible number. A currency
read under the wrong res_id reports 0, which is what an empty stock
also reports; a module counted against the wrong deadline reports a
smaller figure, not an error; and the passes-left reading is a
subtraction from an allowance, so an off-by-one is a number that still
looks like a number.

The two module rows NEST -- a copy inside 24 hours is inside seven
days -- which is the opposite of the Materials tab's buckets, where a
copy falls in one window only. Reversing that by accident leaves both
rows populated and neither obviously wrong.

Driven from a built snapshot with the clock passed in, so nothing here
depends on captured data or on the hour it runs at.

No Tk and no snapshot needed.
"""

from datetime import datetime

from ._harness import add_source_to_path

NAME = "checklist readings"

# Any moment will do -- the module windows roll from `now` -- but a
# stated one keeps the cases readable. A Monday 10:00 UTC.
MONDAY_MORNING = 1789380000
HOUR = 3600
DAY = 24 * HOUR


def _snapshot(amounts=(), expiries=(), day_point=None, spent=None,
              coffee=None, rift=(), day_id=None):
    """A snapshot holding exactly what a case needs and nothing else."""
    characters = {}
    if amounts:
        characters["currencies"] = {str(res_id): {"amount": amount}
                                    for res_id, amount in amounts}
    day = {}
    if spent is not None:
        day["use_town_visit_count"] = spent
    if coffee is not None:
        day["is_coffee_possible"] = coffee
    if day:
        characters["town_data"] = {"day_changeable_data": day}
    raw = {"inventory": {"period_items": [
        {"res_id": 3920026,
         "value": [{"end_time": end} for end in expiries]}]}}
    if characters:
        raw["characters"] = characters
    if day_point is not None or day_id is not None:
        raw["point_entity"] = {"day_point": day_point, "day_id": day_id}
    if rift:
        raw["disaster_boss_rank_entities"] = {
            f"season_{i}": {f"slot_{i}": {
                "score_week_id": week, "week_total_score": score,
                "week_total_score_reward": target}}
            for i, (week, score, target) in enumerate(rift)}
    return raw


def run():
    add_source_to_path()
    import excursions
    import weekly_reset
    from ui.tabs.checklist_tab import (
        ACTIVITY_FULL, CHAOS_CURRENCY, COFFEE_DONE, COFFEE_TODO,
        columns_for,
        ACTIVITY_CLAIMED, ACTIVITY_PARTIAL, ACTIVITY_UNCLAIMED,
        DELEGATION_CURRENCY, DELEGATION_DONE, DELEGATION_TODO,
        ENDS_IN, LATER, SOON, WARN,
        PASS_DAILY_COUNT, PERIOD_LENGTHS,
        _period_band, _period_left, _period_words,
        DONE, GREAT_RIFT_OVER, GREAT_RIFT_TARGET, MODULE_ITEM,
        MODULE_WINDOWS, NO_DATA,
        SORTIE_CAP, SORTIE_CURRENCY, TODO, UNKNOWN, _readings,
        CHAOS_CAP, CHAOS_WEEKLY_GRANT, SORTIE_WEEKLY_GRANT,
        CYCLE_DONE, OVERCLOCK_USES, OVERCLOCK_SHAPE_SIGHTINGS,
        _event_overclock,
        EVENT_DONE_FIELD, EVENT_DONE_FLAG, EVENT_DONE_VALUE,
        EVENT_TOTAL_UNKNOWN, FLOOR, FLOOR_SETTLES_AFTER,
        PASS_MISSION_FIELD, _at_ceiling, _event_missions,
        EXPECTED_VALUE, _event_rows,
    )

    failures = []
    now = MONDAY_MORNING
    # Every weekly case is written against the week `now` falls
    # in: a literal number would go stale the moment the clock
    # passed it, and the cases would then all test the STALE path.
    this_week = weekly_reset.week_index(now)

    # --- the two windows the cases are written against ----------------
    if len(MODULE_WINDOWS) != 2 or (MODULE_WINDOWS[0][0]
                                    >= MODULE_WINDOWS[1][0]):  # noqa: E129
        failures.append(
            f"MODULE_WINDOWS is {MODULE_WINDOWS!r}. The cases below read "
            f"two windows, the tighter first, and the nesting they check "
            f"only means something in that shape.")
        return failures
    soon = now + MODULE_WINDOWS[0][0]
    week = now + MODULE_WINDOWS[1][0]

    # --- every keyed reading belongs to a row, and vice versa ---------
    keyed = {key for _title, rows in columns_for(_snapshot())
             for key, _label, widest in rows if widest}
    produced = set(_readings(_snapshot(), now))
    if produced != keyed:
        failures.append(
            f"the rows reserving a value are {sorted(keyed)} and "
            f"`_readings` produces {sorted(produced)}. A row reserving "
            f"width for a reading that never arrives draws a gap nobody "
            f"can see is empty, and a reading with no row is dropped "
            f"silently.")

    # --- the two currencies, by res_id --------------------------------
    raw = _snapshot(amounts=((CHAOS_CURRENCY, 3), (SORTIE_CURRENCY, 7)))
    out = _readings(raw, now)
    if out["chaos_currency"][0][0] != "3":
        failures.append(
            f"Chaos Currency reads {out['chaos_currency'][0]!r} where the "
            f"snapshot holds 3 of {CHAOS_CURRENCY}. A wrong res_id reads "
            f"0, which is what an empty stock reads.")
    if out["sortie_currency"][0][0] != f"7/{SORTIE_CAP}":
        failures.append(
            f"Sortie Currency reads {out['sortie_currency'][0]!r}, not "
            f"'7/{SORTIE_CAP}', from 7 of {SORTIE_CURRENCY}.")

    # An id held nowhere reads 0 rather than raising.
    out = _readings(_snapshot(), now)
    if out["chaos_currency"][0][0] != "0":
        failures.append(
            f"with nothing held, Chaos Currency reads "
            f"{out['chaos_currency'][0]!r}, not '0'.")

    # --- the Activities claim -----------------------------------------
    # **The reading is the DAY the record carries, not its points.**
    # `point_entity` is rewritten only by the claim, so an earlier
    # `day_id` is a day that was never claimed -- and its `day_point`
    # belongs to that earlier day, which is why a stale 100 must not
    # read as a finished today.
    today = weekly_reset.day_index(now)
    cases = ((today, ACTIVITY_FULL, ACTIVITY_CLAIMED, DONE),
             (today, 20, ACTIVITY_PARTIAL % (20, ACTIVITY_FULL), TODO),
             (today - 1, ACTIVITY_FULL, ACTIVITY_UNCLAIMED, TODO),
             (today - 400, 20, ACTIVITY_UNCLAIMED, TODO),
             (None, ACTIVITY_FULL, NO_DATA, UNKNOWN),
             (today, None, NO_DATA, UNKNOWN))
    for day_id, point, want, state in cases:
        got = _readings(_snapshot(day_id=day_id, day_point=point),
                        now)["activity"]
        if got != [(want, state)]:
            failures.append(
                f"a day_id of {day_id!r} against today's {today} with "
                f"{point!r} points reads {got!r}, not {(want, state)!r}. "
                f"Only a record stamped with TODAY is a claim that "
                f"happened today.")

    # --- an event row counts what is DONE, never what is left --------
    # **Both directions print a plausible number**, and the wrong one
    # is worst where the two agree: a full cap and an empty one both
    # read `2/2` if the numerator is flipped, and `2/2` is what every
    # other row on the tab uses for finished.
    #
    # An Overclock event is GENERIC -- its runs come back tomorrow --
    # so a finished cycle is orange and never green.
    reset = weekly_reset.last_daily_reset(now)
    for taken, want, state in ((2, "2/2", CYCLE_DONE),
                               (1, "1/2", TODO),
                               (0, "0/2", TODO)):
        raw = _snapshot()
        raw["overclock_entities"] = {"e": {"res_id": "e", "count": taken,
                                           "reset_time": int(reset + HOUR)}}
        got = _event_overclock(raw, "e", {}, now)
        if got != [(want, state)]:
            failures.append(
                f"{taken} of {OVERCLOCK_USES} doubled runs taken reads "
                f"{got!r}, not {[(want, state)]!r}. The numerator is what "
                f"has been DONE, like every other row, and a finished "
                f"cycle is orange because the runs come back tomorrow.")
    # A count stamped before the reset is yesterday's: none taken today.
    raw = _snapshot()
    raw["overclock_entities"] = {"e": {"res_id": "e", "count": 2,
                                       "reset_time": int(reset - HOUR)}}
    got = _event_overclock(raw, "e", {}, now)
    if got != [("0/2", TODO)]:
        failures.append(
            f"an Overclock count stamped before the reset reads {got!r}, "
            f"not [('0/2', {TODO!r})]. It is yesterday's tally, and the "
            f"day's runs have come back.")

    # --- the cap comes off the ENDED events, not a written-down two --
    # The game runs Overclock at six a day as well as two, and every
    # event it has ever run is still in `overclock_entities` carrying
    # its own `count`. Reading the live one's cap out of those is what
    # stops a six-shape event's third run from clamping to `2/2` and
    # calling a day with three runs left finished.
    #
    # A shape has to RECUR. One row's `count` can be a day the event
    # ended part-way through, which was never anybody's cap.
    def _overclock(live, siblings):
        raw = _snapshot()
        rows = {"e": {"res_id": "e", "count": live,
                      "reset_time": int(reset + HOUR)}}
        for at, count in enumerate(siblings):
            rows["old%d" % at] = {"res_id": "old%d" % at, "count": count,
                                  "reset_time": int(reset - 30 * 24 * HOUR)}
        raw["overclock_entities"] = rows
        return _event_overclock(raw, "e", {}, now)

    for live, siblings, want, state, why in (
            (3, (6, 6, 2, 2), "3/6", TODO,
             "three of a six-shape event's runs"),
            (6, (6, 6, 2, 2), "6/6", CYCLE_DONE,
             "a six-shape event's whole day"),
            (2, (6, 6, 2, 2), "2/2", CYCLE_DONE,
             "a two-shape event's whole day, with sixes also on file"),
            (1, (6, 6, 2, 2, 1), "1/2", TODO,
             "a lone `1` left by an event that ended mid-day"),
            (2, (), "2/2", CYCLE_DONE,
             "an account with no Overclock history at all")):
        got = _overclock(live, siblings)
        if got != [(want, state)]:
            failures.append(
                f"{why} reads {got!r}, not {[(want, state)]!r}. The cap is "
                f"the smallest shape at least {OVERCLOCK_SHAPE_SIGHTINGS} "
                f"ended events share that still fits today's count; "
                f"{OVERCLOCK_USES} is only the floor where none does.")

    # --- a week that has rolled brings its rows back ------------------
    # **Weekly records are written lazily, exactly like the daily
    # ones.** Nothing zeroes them at the reset, so last week's full
    # score, EXP and clear total survive into a week with nothing done
    # in it -- and every one of those rows read as FINISHED on the
    # Monday morning that first showed it.
    #
    # The stamp beside each is what says which week it is. These read
    # a full record twice, once stamped this week and once last, and
    # the two must differ.
    for stamp, want_full in ((this_week, True), (this_week - 1, False)):
        raw = _snapshot()
        raw["season_pass_entities"] = [
            {"res_id": "season_pass_008", "week_id": stamp,
             "week_exp": 10000, "free_reward_rank": 60,
             "end_time": now + 30 * DAY, "start_time": now - 30 * DAY}]
        raw["disaster_entities"] = [
            {"res_id": "disaster_s04", "week_id": stamp,
             "week_clear_score": 8000}]
        raw["disaster_boss_rank_entities"] = {"disaster_s04": {"rank_01": {
            "score_week_id": stamp, "week_total_score": 742054,
            "week_total_score_reward": 300000}}}
        out = _readings(raw, now)
        for key, full, empty in (
                ("supply_weekly", "10000/10000", "0/10000"),
                ("chaos_progress", "8000/8000", "0/8000"),
                ("seasonal_score", "300000+/300000", "0/300000")):
            want = (full, DONE) if want_full else (empty, TODO)
            if out[key] != [want]:
                failures.append(
                    f"a record stamped week {stamp} against this week's "
                    f"{this_week} reads {out[key]!r} for {key}, not "
                    f"{[want]!r}. A weekly record is not zeroed at the "
                    f"reset, so its `week_id` is the only thing that says "
                    f"whether the figure beside it is this week's.")

    # A record with NO stamp is read at face value: nothing about it
    # can say otherwise, and blanking it would lose a live reading.
    raw = _snapshot()
    raw["disaster_entities"] = [{"res_id": "d", "week_clear_score": 8000}]
    if _readings(raw, now)["chaos_progress"] != [("8000/8000", DONE)]:
        failures.append(
            "an unstamped weekly record was not read at face value. "
            "Nothing about it can say which week it belongs to, and "
            "refusing it blanks a row that may be perfectly current.")

    # --- a weekly ALLOWANCE is topped up, not zeroed ------------------
    # The two spendable currencies gain at the reset ON TOP of what was
    # left, and the game applies that lazily -- so a record the week
    # has rolled past holds a leftover and not a stock. The row then
    # shows what the week's rule says to EXPECT, marked as such,
    # because 60 Aether buys either with no limit and the real figure
    # can only be higher.
    opened = weekly_reset.last_weekly_reset(now)
    soon_after = EXPECTED_VALUE
    chaos_full = min(CHAOS_WEEKLY_GRANT, CHAOS_CAP)
    reason_full = min(5 + SORTIE_WEEKLY_GRANT, SORTIE_CAP)
    for touched, fresh in ((opened + HOUR, True), (opened - HOUR, False)):
        raw = _snapshot()
        raw["characters"] = {"currencies": {
            str(CHAOS_CURRENCY): {"amount": 0, "last_update": int(touched)},
            str(SORTIE_CURRENCY): {"amount": 5, "last_update": int(touched)}}}
        out = _readings(raw, now)
        want = ([("0", DONE)], [(f"5/{SORTIE_CAP}", TODO)]) if fresh else (
            [(f"{soon_after}{chaos_full}", TODO)],
            [(f"{soon_after}{reason_full}/{SORTIE_CAP}", TODO)])
        for key, wanted in (("chaos_currency", want[0]),
                            ("sortie_currency", want[1])):
            if out[key] != wanted:
                failures.append(
                    f"a currency last written {'after' if fresh else 'before'}"
                    f" the week opened reads {out[key]!r} for {key}, not "
                    f"{wanted!r}. Read after the reset it is a reading; read "
                    f"before, the row owes the week's grant and is marked as "
                    f"worked out rather than read.")

    # **The cap is hard**, tested in game: no amount of buying takes a
    # holding past it, so the top-up stops there rather than running
    # over. Reason one short of its ceiling gains one, not three.
    raw = _snapshot()
    raw["characters"] = {"currencies": {
        str(SORTIE_CURRENCY): {"amount": SORTIE_CAP - 1,
                               "last_update": int(opened - HOUR)}}}
    got = _readings(raw, now)["sortie_currency"]
    want = [(f"{soon_after}{SORTIE_CAP}/{SORTIE_CAP}", TODO)]
    if got != want:
        failures.append(
            f"a holding one short of the cap reads {got!r}, not {want!r}. "
            f"The week's grant stops at the cap.")

    # --- which mission rows belong to which event --------------------
    # **An event's index is not always in its missions' ids.** The
    # devil event is scheduled as `event_schedule_devil_001` and its
    # missions are `event_devil_<day>_<task>` -- so the normalised key
    # `event_devil_1` matches DAY one and nothing else, and a 21-reward
    # event read `3/3` for a week without anything looking wrong.
    #
    # The stem fixes that and is far too greedy on its own, so these
    # pin both halves: the devil is whole, and the three families it
    # would otherwise swallow are untouched.
    def _rows(schedules, mission_ids):
        raw = _snapshot()
        raw["event_schedules"] = {"EVENT_SCHEDULE": {
            name: {"schedule_id": name} for name in schedules}}
        raw[PASS_MISSION_FIELD] = {
            res_id: {"res_id": res_id, "complete_time": 0}
            for res_id in mission_ids}
        return raw

    devil = ["event_devil_%02d_%02d" % (day, task)
             for day in range(1, 8) for task in range(1, 4)]
    cases = (
        ("event_schedule_devil_001", ("event_schedule_devil_001",), devil, 21,
         "its own index collides with its first DAY, so the key alone "
         "takes day one and drops the other six"),
        ("event_bartender_01", ("event_bartender_01",),
         ["event_bartender_1_01_%02d" % n for n in range(1, 8)], 7,
         "an ordinary family repeats the event index and must be "
         "unaffected"),
        ("event_schedule_policy_005",
         ("event_schedule_policy_004", "event_schedule_policy_005"),
         ["event_policy_4_1", "event_policy_4_2", "event_policy_5_1"], 1,
         "a PAST instalment shares the stem and is still in "
         "event_schedules, so its rows belong to it"),
        ("event_schedule_chaos_mission_5", ("event_schedule_chaos_mission_5",),
         ["event_chaos_assault_1_1", "event_chaos_assault_spt_1_1"], 0,
         "its stem `event_chaos` is the opening of another family's "
         "name entirely"),
        ("event_2", ("event_2",), devil + ["event_summer_1_1_1"], 0,
         "its stem is the bare word `event`, which every event mission "
         "on the account starts with"),
    )
    for name, schedules, mission_ids, want, why in cases:
        got = len(_event_rows(_rows(schedules, mission_ids), name))
        if got != want:
            failures.append(
                f"{name} takes {got} of {len(mission_ids)} mission rows, not "
                f"{want}: {why}. The stem is tried only where the full key "
                f"already matched something, and never over rows another "
                f"schedule's key claims.")

    # --- a floor SAYS it is a floor, and only the game lifts it ------
    # A denominator counted off the rows in hand is what has been
    # handed out, not what the event holds, so `20/20` there would be
    # a different claim from `20/20` anywhere else on the tab. The
    # suffix carries that difference, and comes off only where
    # `event_mission_reward_entities` says the event is over.
    def _event(rows_held, claimed, finished):
        raw = _snapshot()
        raw[PASS_MISSION_FIELD] = {
            "event_probe_%02d" % at: {
                "res_id": "event_probe_%02d" % at,
                "complete_time": 1 if at <= claimed else 0}
            for at in range(1, rows_held + 1)}
        if finished is not None:
            raw[EVENT_DONE_FIELD] = [{"res_id": "event_probe",
                                      EVENT_DONE_FLAG: finished}]
        return _event_missions(raw, "event_probe", {}, now)

    unknown = EVENT_TOTAL_UNKNOWN
    for held, claimed, finished, want, state, why in (
            (20, 16, None, "16/20" + unknown, FLOOR,
             "a part-claimed event with no completion record"),
            (20, 20, None, "20/20" + unknown, FLOOR,
             "every row in hand claimed, with nothing to say that is all"),
            (20, 20, 0, "20/20" + unknown, FLOOR,
             "a completion record that says NOT finished"),
            (20, 20, EVENT_DONE_VALUE, "20/20", DONE,
             "the game's own word that the event is finished"),
            (20, 16, EVENT_DONE_VALUE, "16/20" + unknown, FLOOR,
             "a finished flag over a tally that is not full")):
        got = _event(held, claimed, finished)
        if got != [(want, state)]:
            failures.append(
                f"{why} reads {got!r}, not {[(want, state)]!r}. A tally "
                f"counted off the rows in hand is a FLOOR and says so with "
                f"{unknown!r}; only {EVENT_DONE_FLAG} == "
                f"{EVENT_DONE_VALUE!r} takes it off and lets the row go "
                f"green.")

    # The suffix must not stop a floor settling to orange, which is the
    # whole answer for an event nothing can prove finished.
    for words, want in (("20/20" + unknown, True), ("16/20" + unknown, False),
                        ("20/20", True), ("16/20", False)):
        if _at_ceiling(words) is not want:
            failures.append(
                f"_at_ceiling({words!r}) is {_at_ceiling(words)!r}, not "
                f"{want!r}. A floor at its ceiling is what settles to "
                f"orange after {FLOOR_SETTLES_AFTER // 3600}h, and "
                f"{unknown!r} must not hide that.")

    # --- a DAY that has rolled brings its rows back ------------------
    # The town's daily block carries no date of its own but does carry
    # `town_visit_reset_time`, the moment the game granted the day. A
    # block stamped before the last reset is a finished day's, and its
    # coffee and its passes have both come back -- which is what makes
    # the rows right with no capture running, the clock moving where
    # the snapshot cannot.
    reset = weekly_reset.last_daily_reset(now)
    for stamp, label, coffee_want, passes_want in (
            (reset + HOUR, "written since the reset", COFFEE_DONE, "0/5"),
            (reset - HOUR, "written before it", COFFEE_TODO, "5/5")):
        raw = _snapshot(coffee=False, spent=5)
        raw["characters"]["town_data"]["day_changeable_data"][
            "town_visit_reset_time"] = int(stamp)
        out = _readings(raw, now)
        if out["coffee"][0][0] != coffee_want:
            failures.append(
                f"with the day block {label} the coffee reads "
                f"{out['coffee'][0][0]!r}, not {coffee_want!r}. A drunk "
                f"coffee comes back at the reset whether or not a capture "
                f"is running to say so.")
        if out["excursions"][0][0] != passes_want:
            failures.append(
                f"with the day block {label} the passes read "
                f"{out['excursions'][0][0]!r}, not {passes_want!r}.")

    # ...and with no stamp at all, the CAPTURE's own time stands in.
    raw = _snapshot(coffee=False, spent=5)
    raw["capture_time"] = datetime.fromtimestamp(reset - HOUR).isoformat()
    if _readings(raw, now)["coffee"][0][0] != COFFEE_TODO:
        failures.append(
            "a snapshot written before the last reset still reads its "
            "coffee as drunk. Without the block's own stamp the capture "
            "time is what dates it.")

    # --- today's coffee, which INVERTS the field it reads --------------
    for possible, want, state in ((True, COFFEE_TODO, TODO),
                                  (False, COFFEE_DONE, DONE),
                                  (None, NO_DATA, UNKNOWN)):
        got = _readings(_snapshot(coffee=possible), now)["coffee"]
        if got != [(want, state)]:
            failures.append(
                f"is_coffee_possible={possible!r} reads {got!r}, not "
                f"{(want, state)!r}. The field is a CAPABILITY: true "
                f"means the coffee is still there to drink, so the row "
                f"says the opposite of what the field does.")

    # --- the Great Rift, and picking the LIVE season ------------------
    # Two seasons, the older carrying the higher score and a higher
    # threshold. The live one is the later WEEK, not the bigger number.
    rift = ((this_week - 13, 999999, 500000),
            (this_week, 120000, 300000))
    got = _readings(_snapshot(rift=rift), now)["seasonal_score"]
    if got != [("120000/300000", TODO)]:
        failures.append(
            f"the Great Rift row reads {got!r}, not "
            f"('120000/300000', {TODO!r}). Past seasons keep their rows "
            f"and carry higher totals AND different thresholds, so the "
            f"live one is the latest score_week_id.")
    # Over the threshold, the display caps AND says it capped.
    got = _readings(_snapshot(rift=((this_week, 1396064, 300000),)),
                    now)["seasonal_score"]
    if got != [(f"300000{GREAT_RIFT_OVER}/300000", DONE)]:
        failures.append(
            f"a score past the threshold reads {got!r}, not "
            f"('300000{GREAT_RIFT_OVER}/300000', {DONE!r}). The figure "
            f"runs to seven digits and the row is about clearing the "
            f"threshold, so it caps -- and the sign is what stops a "
            f"capped reading looking like one that landed on the bar.")
    # Landing EXACTLY on it takes no sign, and is still done.
    got = _readings(_snapshot(rift=((this_week, 300000, 300000),)),
                    now)["seasonal_score"]
    if got != [("300000/300000", DONE)]:
        failures.append(
            f"a score exactly on the threshold reads {got!r}, not "
            f"('300000/300000', {DONE!r}). Nothing is over, so nothing "
            f"is capped.")
    got = _readings(_snapshot(), now)["seasonal_score"]
    if got != [(f"{NO_DATA}/{GREAT_RIFT_TARGET}", UNKNOWN)]:
        failures.append(
            f"with no standings the Great Rift row reads {got!r}, not "
            f"a dash against the stand-in threshold.")

    # --- passes left today --------------------------------------------
    allowance = excursions.DAILY_PASSES
    for spent, want in ((0, f"{allowance}/{allowance}"),
                        (2, f"{allowance - 2}/{allowance}"),
                        (allowance, f"0/{allowance}"),
                        (None, f"{NO_DATA}/{allowance}")):
        # Green only where every pass is spent: a pass left over is an
        # excursion not taken.
        (got, state), = _readings(_snapshot(spent=spent),
                                  now)["excursions"]
        want_state = (UNKNOWN if spent is None
                      else DONE if spent >= allowance else TODO)
        if state != want_state:
            failures.append(
                f"{spent!r} passes spent is drawn {state!r}, not "
                f"{want_state!r}. A pass left over is an excursion not "
                f"taken, which is the row's whole message.")
        if got != want:
            failures.append(
                f"{spent!r} passes spent reads {got!r}, not {want!r}. The "
                f"reading is the allowance less what was spent, so an "
                f"off-by-one is still a plausible number.")

    # --- the modules, and the nesting ---------------------------------
    # One copy in each of: inside the tight window, between the two, and
    # past both. So the first row is 1 and the second 2.
    # One copy 6 hours out, one 3 days out, one past both windows. The
    # tight row counts 1 and says SIX hours -- the number in the words
    # is the longest a counted copy has left, not the window.
    raw = _snapshot(expiries=(now + 6 * HOUR, now + 3 * DAY, week + DAY))
    out = _readings(raw, now)
    if out["modules_soon"] != [("1 expiring within 6h!", TODO)]:
        failures.append(
            f"the tight module row reads {out['modules_soon']!r}, not "
            f"('1 expiring within 6h!', {TODO!r}). The window bounds what "
            f"is COUNTED; the words say how long the last of them has.")
    if out["modules_week"] != [("2 expiring within 3 days", TODO)]:
        failures.append(
            f"the wide module row reads {out['modules_week']!r}, not "
            f"('2 expiring within 3 days', {TODO!r}). The windows NEST -- "
            f"a copy inside 24 hours is inside seven days -- so the wider "
            f"count includes the tighter one, and its number is the "
            f"furthest out of the two.")

    # Rounded UP, so a copy is never promised time it has spent.
    out = _readings(_snapshot(expiries=(now + 90 * 60,)), now)
    if out["modules_soon"][0][0] != "1 expiring within 2h!":
        failures.append(
            f"a copy 90 minutes out reads {out['modules_soon'][0]!r}, not "
            f"'1 expiring within 2h!'. Rounding down promises an hour "
            f"that is already spent.")

    # A copy landing exactly ON a boundary is inside it.
    out = _readings(_snapshot(expiries=(soon,)), now)
    if out["modules_soon"][0][0] != "1 expiring within 24h!":
        failures.append(
            f"a copy expiring exactly 24 hours out reads "
            f"{out['modules_soon'][0]!r}. `within` includes the boundary.")

    # Nothing held: the window's own bound stands in for a longest that
    # does not exist, and both rows are GREEN -- there is nothing to use.
    out = _readings(_snapshot(), now)
    if (out["modules_soon"] != [("0 expiring within 24h!", DONE)]
            or out["modules_week"] != [("0 expiring within 7 days", DONE)]):
        failures.append(
            f"with no modules held the two rows read "
            f"{out['modules_soon']!r} and {out['modules_week']!r}, not "
            f"zero against the window's own bound, in green.")

    # --- today's Chaos Delegation ------------------------------------
    # **Holding the free entry is the reading.** `last_update` alone
    # cannot answer it: the entry is granted lazily at the first login
    # after the reset, and the grant stamps that field exactly as
    # spending it does -- the third case below is that grant, and a
    # reading off the stamp calls it a run that never happened.
    reset = weekly_reset.last_daily_reset(now)
    cases = (
        # (held, stamp, reading, state, what it is)
        (0, reset + HOUR, DELEGATION_DONE, DONE, "spent since the reset"),
        (1, reset + HOUR, DELEGATION_TODO, TODO, "granted, not yet run"),
        (1, reset - HOUR, DELEGATION_TODO, TODO, "held from before"),
        (0, reset - HOUR, DELEGATION_TODO, TODO,
         "empty and stale: the grant has not happened yet"),
        # Exactly ON the boundary counts as today: the reset is when
        # the day begins, not the last moment of the one before.
        (0, reset, DELEGATION_DONE, DONE, "spent exactly at the reset"),
        (None, None, NO_DATA, UNKNOWN, "no currency row at all"),
    )
    for held, stamp, want, state, what in cases:
        raw = _snapshot()
        if held is not None:
            raw.setdefault("characters", {})["currencies"] = {
                str(DELEGATION_CURRENCY): {"amount": held,
                                           "last_update": int(stamp)}}
        got = _readings(raw, now)["chaos_delegation"]
        if got != [(want, state)]:
            failures.append(
                f"a delegation balance of {held!r} {what} reads {got!r}, "
                f"not {(want, state)!r}. An entry in hand is a run still "
                f"to do; an empty balance is a run taken only if it was "
                f"written since the day's own 18:00 UTC boundary.")

    # --- the Arkhianon Supply, three ways -----------------------------
    # A DAILY mission is one the pass ISSUED since the day's reset --
    # there is no id list, and one would not survive the season number
    # changing. The denominator is stated: the game issues a mission
    # lazily, so counting the issued rows understates the day.
    reset = weekly_reset.last_daily_reset(now)
    raw = _snapshot()
    raw["mission_entities"] = {
        # Two issued today, one of them claimed.
        "pass_mission_008_01": {"issued_time": int(reset + HOUR),
                                "complete_time": int(reset + 2 * HOUR)},
        "pass_mission_008_02": {"issued_time": int(reset + HOUR),
                                "complete_time": 0},
        # Issued YESTERDAY and claimed: last day's, not this one's.
        "pass_mission_008_03": {"issued_time": int(reset - HOUR),
                                "complete_time": int(reset - HOUR)},
        # Not a pass mission at all.
        "content_01_01_01": {"issued_time": int(reset + HOUR),
                             "complete_time": int(reset + HOUR)},
    }
    got = _readings(raw, now)["supply_daily"]
    if got != [(f"1/{PASS_DAILY_COUNT}", TODO)]:
        failures.append(
            f"the daily Arkhianon row reads {got!r}, not "
            f"1/{PASS_DAILY_COUNT} in red. It counts pass missions "
            f"ISSUED since the day's reset and CLAIMED -- yesterday's, "
            f"and anything that is not a pass mission, are not it.")

    # The pass's own record comes in two shapes, and past passes sit at
    # their full 70 and 10000 -- so the wrong one reads as a finished
    # week. The live one is the latest `week_id`.
    raw = _snapshot()
    raw["season_pass_entities"] = [
        {"res_id": "season_pass_006", "week_id": this_week - 11,
         "week_exp": 10000, "free_reward_rank": 70},
        {"res_id": "season_pass_008", "week_id": this_week,
         "week_exp": 6500, "free_reward_rank": 46},
    ]
    for key, want in (("supply_weekly", [("6500/10000", TODO)]),
                      ("supply_season", [("46/70", TODO)])):
        got = _readings(raw, now)[key]
        if got != want:
            failures.append(
                f"{key} reads {got!r}, not {want!r}. A finished past pass "
                f"is in the same list and sits at its full figure.")
    # The singular field wins where a claim has just sent it.
    raw["season_pass_entity"] = {"week_id": this_week, "week_exp": 8000,
                                 "free_reward_rank": 50}
    if _readings(raw, now)["supply_weekly"] != [("8000/10000", TODO)]:
        failures.append(
            "the singular `season_pass_entity` does not win over the "
            "login's list. A claim sends the one live pass under it, "
            "and that is the fresher reading.")

    # --- the Basin, and which season it reports --------------------
    # Two seasons at once and one figure on screen, so the row takes
    # the LEAST complete: a fresh season beside a finished one is work
    # left, and reporting the finished one would hide it.
    def basin(*seasons, claimed=None):
        raw = _snapshot()
        raw["mission_seasson_entities"] = {
            f"hyperspace_02_{i}": {
                f"content_{i}_{n:02d}": {"score": 1 if n <= done else 0}
                for n in range(1, total + 1)}
            for i, (done, total) in enumerate(seasons)}
        if claimed is not None:
            raw["reward_entities"] = [
                {"res_id": f"hyperspace_02_{len(seasons) - 1}",
                 "count": claimed}]
        return _readings(raw, now)["basin"]

    # **Scored is not claimed.** Every objective can be done with every
    # star reward still sitting there, and that is a trip to the game
    # still owed -- so the row is green only once they are taken.
    got = basin((26, 26), claimed=26)
    if got != [("26/26", DONE)]:
        failures.append(
            f"a Basin season scored and CLAIMED reads {got!r}, not "
            f"('26/26', {DONE!r}).")
    got = basin((26, 26), claimed=0)
    if got != [("26/26", TODO)]:
        failures.append(
            f"a Basin season scored with nothing claimed reads {got!r}, "
            f"not ('26/26', {TODO!r}). `reward_entities` carries no row "
            f"until the first claim, so an absent one is none taken -- "
            f"and a finished-looking row hides the rewards.")
    got = basin((26, 26))
    if got != [("26/26", TODO)]:
        failures.append(
            f"a Basin season with no reward record at all reads {got!r}, "
            f"not ('26/26', {TODO!r}).")
    got = basin((26, 26), (3, 26), claimed=3)
    if got != [("3/26", TODO)]:
        failures.append(
            f"with a finished season beside a fresh one the Basin reads "
            f"{got!r}, not ('3/26', {TODO!r}). The row takes the LIVE "
            f"season, or the one with work left disappears behind the "
            f"one without.")
    got = _readings(_snapshot(), now)["basin"]
    if got != [(NO_DATA, UNKNOWN)]:
        failures.append(
            f"with no Basin data the row reads {got!r}, not a dash.")

    # --- the shop sub-rows, and the STALE tally -----------------------
    # Built from a snapshot carrying a shop DEFINITION, since that is
    # where the cap and the period now come from.
    import shop_stock
    product, cap = "town_shop_goods_005", 1
    key = "shop:" + product
    started = shop_stock.period_start("weekly", {}, now)

    def shop(count, touched, limit_type="LIMIT_WEEK", month=None):
        raw = _snapshot()
        raw["shop_res_data"] = {"shop_town": {product: {
            "product_link_item_id": 3310006, "product_count": 1,
            "limit_count": cap, "limit_type": limit_type, "sort": 5,
        "link_shop_sub_category_id": "none"}}}
        raw["shop_list"] = {product: {"count": count, "reset_time": touched,
                                      "total_count": 5}}
        if month is not None:
            raw["month_start"] = month
        return _readings(raw, now)[key]

    got = shop(0, int(started) + HOUR)
    if got != [(f"{cap}/{cap}", TODO)]:
        failures.append(
            f"a shop row with nothing bought this period reads {got!r}, "
            f"not {cap}/{cap} in red. `count` is the purchases MADE, so "
            f"what is left is the cap less it.")
    got = shop(cap, int(started) + HOUR)
    if got != [(f"0/{cap}", DONE)]:
        failures.append(
            f"a shop row bought out reads {got!r}, not 0 in green.")

    # **The stale tally.** `count` is reset LAZILY -- a row nobody has
    # bought from since the period rolled still carries the previous
    # period's number. Read straight it draws a refilled shop as empty,
    # which is what put 0/20 on a full shelf.
    got = shop(cap, int(started) - HOUR)
    if got != [(f"{cap}/{cap}", TODO)]:
        failures.append(
            f"a row last touched BEFORE the period began reads {got!r}, "
            f"not {cap}/{cap}. Its tally is last period's, so nothing "
            f"has been bought since the shelf refilled.")

    # No `shop_list` AT ALL is a dash: the field never arrived.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {product: {
        "product_link_item_id": 3310006, "product_count": 1,
        "limit_count": cap, "limit_type": "LIMIT_WEEK", "sort": 5,
        "link_shop_sub_category_id": "none"}}}
    got = _readings(raw, now)[key]
    if got != [(f"{NO_DATA}/{cap}", UNKNOWN)]:
        failures.append(
            f"with no shop_list the row reads {got!r}, not a dash. A "
            f"snapshot that never carried the field and a shop with "
            f"nothing left are different answers.")

    # **A shop_list that arrived WITHOUT this product is a full shelf.**
    # A row appears only once something has been bought from it, so an
    # absent one says nothing has -- and reading it as unknown drew a
    # dash beside every product the account has never touched.
    raw["shop_list"] = {"town_shop_goods_099": {"count": 1,
                                                "reset_time": int(now)}}
    got = _readings(raw, now)[key]
    if got != [(f"{cap}/{cap}", TODO)]:
        failures.append(
            f"a product absent from a shop_list that DID arrive reads "
            f"{got!r}, not {cap}/{cap}. No row means nothing bought.")

    # A MONTHLY product has no boundary without the wire's own
    # `month_start`, so it reads a dash rather than guessing one.
    got = shop(1, now, "LIMIT_MONTH")
    if got != [(f"{NO_DATA}/{cap}", UNKNOWN)]:
        failures.append(
            f"a monthly row with no `month_start` reads {got!r}, not a "
            f"dash. The month rolls at 18:00 UTC on the LAST day, so "
            f"there is no boundary to compute without the wire saying.")
    got = shop(1, now, "LIMIT_MONTH", month=int(now - DAY))
    if got != [(f"0/{cap}", DONE)]:
        failures.append(
            f"a monthly row with `month_start` reads {got!r}, not 0/{cap}.")

    # --- each column heading's own countdown ---------------------------
    # The period splits into four EQUAL parts and the colour says which
    # one is running. A band computed off the wrong length reads as a
    # plausible colour, which is why the shares are checked rather than
    # the words alone.
    day = PERIOD_LENGTHS["Daily"]
    reset = weekly_reset.last_daily_reset(now)
    for spent, band in ((0.1, "period_full"), (0.4, "period_most"),
                        (0.6, "period_some"), (0.9, "period_last")):
        at = reset + spent * day
        left, length = _period_left("Daily", {}, at)
        if length != day:
            failures.append(
                f"the Daily period is {length!r} long, not {day}.")
        elif _period_band(left, length) != band:
            failures.append(
                f"{spent:.0%} through the day the heading is drawn "
                f"{_period_band(left, length)!r}, not {band!r}. The "
                f"period splits into four equal parts, the first green "
                f"and the last red.")

    # Hours under a day, days above it, rounded DOWN so nothing is
    # promised time it does not have.
    for left, want in ((90 * 60, "1h left"), (23.9 * HOUR, "23h left"),
                       (DAY, "1d left"), (5.9 * DAY, "5d left")):
        if _period_words(left) != want:
            failures.append(
                f"{left}s left reads {_period_words(left)!r}, not "
                f"{want!r}.")

    # A MONTH is not a fixed length, so its bounds come off the wire --
    # and are DERIVED where a snapshot carries neither, which is every
    # fresh install. **The two have to agree**: a Monthly column that
    # counted to one date before the first capture and another after it
    # would move under the user, and only one of the two can be right.
    derived = _period_left("Monthly", {}, now)
    if derived == (None, None):
        failures.append(
            "the Monthly heading has no countdown without `month_start` "
            "and `month_end`. A fresh install has neither, and the month "
            "is the calendar one on the reset hour -- so it computes.")
    # The bounds the WIRE stated for September 2026, straight out of a
    # capture. An OBSERVATION, so the derivation is checked against the
    # game rather than against itself.
    inside = 1788899000                       # 2026-09-09, mid-month
    if weekly_reset.month_bounds(inside) != (1788199200, 1790791199):
        failures.append(
            f"for a moment inside September 2026 the month derives as "
            f"{weekly_reset.month_bounds(inside)!r}, where the wire "
            f"stated (1788199200, 1790791199) -- 08-31 18:00 UTC to "
            f"09-30 17:59:59. The month is the calendar one shifted onto "
            f"the reset hour, and a derivation that disagrees would move "
            f"the Monthly column on the first capture.")
    raw = {"month_start": int(now - DAY), "month_end": int(now + 3 * DAY)}
    left, length = _period_left("Monthly", raw, now)
    if (left, length) != (3 * DAY, 4 * DAY):
        failures.append(
            f"a month bounded on the wire reads ({left!r}, {length!r}), "
            f"not ({3 * DAY}, {4 * DAY}).")

    # --- a mid-login snapshot keeps its rows --------------------------
    # A capture saves as soon as the inventory arrives, dozens of frames
    # before the shop payloads do, so the session's FIRST snapshot has
    # no `shop_res_data` at all. Without the remembered definitions the
    # whole shop half of the tab vanishes the moment a capture starts.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {"town_shop_goods_001": {
        "product_link_item_id": 3310006, "product_count": 1,
        "limit_count": 1, "limit_type": "LIMIT_WEEK", "sort": 1,
        "link_shop_sub_category_id": "none"}}}
    definitions = raw["shop_res_data"]
    full = sum(len(rows) for _t, rows in columns_for(raw, None, now))
    partial = _snapshot()
    bare = sum(len(rows) for _t, rows in columns_for(partial, None, now))
    held = sum(len(rows) for _t, rows in
               columns_for(partial, None, now, definitions))
    if not bare < full:
        failures.append(
            f"a snapshot with no shop_res_data builds {bare} rows against "
            f"{full} with it, so this case proves nothing -- the shop "
            f"rows are not coming from the definitions any more.")
    elif held != full:
        failures.append(
            f"a mid-login snapshot with the definitions remembered builds "
            f"{held} rows, not the {full} a full one does. A capture's "
            f"first save has no shops in it, and the tab must not empty "
            f"itself until the next one.")

    # --- ticking, and where an untracked product sits -----------------
    # An untracked product sinks to the BOTTOM of its own shop and the
    # tracked ones keep the shop's order. It does not leave the tab:
    # the shop still sells it, and a row that vanished reads as a bug.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {
        f"town_shop_goods_{n:03d}": {
            "product_link_item_id": 3310006, "product_count": 1,
            "limit_count": 1, "limit_type": "LIMIT_WEEK", "sort": n,
            "link_shop_sub_category_id": "none"}
        for n in (1, 2, 3)}}
    weekly = dict(columns_for(raw))["Weekly"]
    order = [key for key, _l, _w in weekly if key.startswith("shop:")]
    if order != ["shop:town_shop_goods_001", "shop:town_shop_goods_002",
                 "shop:town_shop_goods_003"]:
        failures.append(
            f"with nothing filtered the shop rows read {order!r}, not the "
            f"shop's own `sort` order.")
    untracked = {"town_shop_goods_001"}
    order = [key for key, _l, _w in
             dict(columns_for(raw, lambda p: p not in untracked))["Weekly"]
             if key.startswith("shop:")]
    if order != ["shop:town_shop_goods_002", "shop:town_shop_goods_003",
                 "shop:town_shop_goods_001"]:
        failures.append(
            f"with the first product untracked the rows read {order!r}. An "
            f"untracked one sinks to the BOTTOM of its shop and the rest "
            f"keep their order -- ticking one must move that one only.")

    # A product with NO cap is not a row at all: nothing counts down.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {"town_shop_goods_010": {
        "product_link_item_id": 2000001, "product_count": 4000,
        "limit_count": -1, "limit_type": "NONE", "sort": 14,
        "link_shop_sub_category_id": "none"}}}
    if any(key.startswith("shop:") for _t, rows in columns_for(raw)
           for key, _l, _w in rows):
        failures.append(
            "an uncapped product got a Checklist row. There is nothing "
            "to count down and nothing to finish, so it is not a "
            "checklist entry.")

    # --- a value and a countdown are SEPARATE segments -----------------
    # They answer different questions -- is the work done, and how long
    # is left -- so they colour apart. Written as one string they could
    # only take one colour between them.
    raw = _snapshot()
    raw["season_pass_entities"] = [{"res_id": "season_pass_008",
                                    "week_id": this_week,
                                    "week_exp": 6500,
                                    "free_reward_rank": 46}]
    raw["event_schedules"] = {"SEASON_PASS": {"season_pass_008": {
        "start_time": int(now - DAY), "end_time": int(now + 5 * DAY)}}}
    got = _readings(raw, now)["supply_season"]
    if len(got) != 2 or got[0] != ("46/70", TODO):
        failures.append(
            f"a row with a value AND a deadline reads {got!r}. The two "
            f"are separate segments: one says whether the work is done "
            f"and the other how long is left, and one string could take "
            f"only one colour between them.")
    elif not got[1][0].startswith(ENDS_IN) or got[1][1] != LATER:
        failures.append(
            f"the countdown segment reads {got[1]!r}, not `{ENDS_IN}5 "
            f"days` in {LATER!r}. Over three days out is the calm band.")

    # The three bands, by how long is left.
    for hours, state in ((6, SOON), (40, WARN), (200, LATER)):
        raw["event_schedules"]["SEASON_PASS"]["season_pass_008"][
            "end_time"] = int(now + hours * HOUR)
        got = _readings(raw, now)["supply_season"][1]
        if got[1] != state:
            failures.append(
                f"{hours}h left is drawn {got[1]!r}, not {state!r}. Under "
                f"a day is urgent, one to three days is the Materials "
                f"tab's warning, past that is calm.")

    # A row with NO other reading takes the time alone -- the dash is a
    # stand-in for a reading, not one.
    raw = _snapshot()
    raw["event_schedules"] = {"ZERO_REWARD_LIST": {"zero_orb_4": {
        "start_time": int(now - DAY), "end_time": int(now + 5 * DAY)}}}
    got = _readings(raw, now)["matrix"]
    if len(got) != 1 or not got[0][0].startswith(ENDS_IN):
        failures.append(
            f"a row whose only reading is a deadline reads {got!r}, not "
            f"the time alone. A dash beside it would be a stand-in "
            f"presented as an answer.")

    # --- the ids the rows read ----------------------------------------
    # **Against the NAME, not against the constant.** Every assertion
    # above reads the id out of the same module it is testing, so
    # changing it changes the expectation with it and the case passes.
    # The tables are the second copy that closes that.
    from game_data.constants import NAMED_MATERIALS, PERIOD_ITEMS
    for res_id, want in ((CHAOS_CURRENCY, "Loot Certification Card"),
                         (SORTIE_CURRENCY, "Reason")):
        named = NAMED_MATERIALS.get(res_id)
        got = named[0] if named else None
        if got != want:
            failures.append(
                f"the Checklist reads {res_id} for {want!r}, which "
                f"NAMED_MATERIALS calls {got!r}. A row pointed at the "
                f"wrong id reads 0, the same as an empty stock.")

    if MODULE_ITEM not in PERIOD_ITEMS:
        failures.append(
            f"the Checklist counts copies of {MODULE_ITEM}, which is not "
            f"in PERIOD_ITEMS. Only a period item has copies to count, so "
            f"both module rows would read 0 forever.")

    return failures
