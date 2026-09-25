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

import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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
        ACTIVITY_CLAIMED, ACTIVITY_UNCLAIMED,
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
        UNKNOWN_MORE, FLOOR, FLOOR_SETTLES_AFTER,
        PASS_MISSION_FIELD, _at_ceiling, _event_missions,
        EXPECTED_VALUE, EVENT_KEY_PREFIX, _event_rows,
        SHOP_HEAD_PREFIX, SHOP_TOTAL_PREFIX, shop_head_key,
        currency_earned, currency_rate, shop_period, shop_rates,
        shop_full_cost,
        _event_attendance,
        RATE_RECENT_LABEL, RATE_LONG_LABEL,
        SHOP_RATE_FLOOR, season_estimate, ATTENDANCE_FLOOR, SEASON_ESTIMATE,
        LOCKED_PAGES, shop_pages_open, shop_shut_for_now,
        ChecklistTab, WRITTEN_TOTALS, written_total,
        unsure_ceiling, EVENT_FINISHED_FIELD,
    )
    import checklist_manager

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
    # A shop heading's total is keyed apart from the rows -- it is
    # drawn at a stop of its own rather than in the column of readings
    # -- so it is matched against the headings instead.
    keyed = {key for _title, rows in columns_for(_snapshot())
             for key, _label, widest in rows if widest}
    heads = {SHOP_TOTAL_PREFIX + key
             for _title, rows in columns_for(_snapshot())
             for key, _label, _widest in rows
             if key.startswith(SHOP_HEAD_PREFIX)}
    produced = set(_readings(_snapshot(), now))
    if (produced - keyed - heads) or (keyed - produced):
        failures.append(
            f"the rows reserving a value are {sorted(keyed)} and "
            f"`_readings` produces {sorted(produced)}. A row reserving "
            f"width for a reading that never arrives draws a gap nobody "
            f"can see is empty, and a reading with no row is dropped "
            f"silently.")

    # --- the two currencies, by res_id --------------------------------
    raw = _snapshot(amounts=((CHAOS_CURRENCY, 3), (SORTIE_CURRENCY, 7)))
    out = _readings(raw, now)
    if out["chaos_currency"][0][0] != f"3/{CHAOS_CAP}":
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
    if out["chaos_currency"][0][0] != f"0/{CHAOS_CAP}":
        failures.append(
            f"with nothing held, Chaos Currency reads "
            f"{out['chaos_currency'][0]!r}, not '0/{CHAOS_CAP}'.")

    # --- the Activities claim -----------------------------------------
    # **The reading is the DAY the record carries, not its points.**
    # `point_entity` is rewritten only by the claim, so an earlier
    # `day_id` is a day that was never claimed -- and its `day_point`
    # belongs to that earlier day, which is why a stale 100 must not
    # read as a finished today.
    today = weekly_reset.day_index(now)
    # **The claimed state prints its numbers too**, so that a figure
    # can be checked against the game where a word like `All Claimed`
    # cannot.
    cases = ((today, ACTIVITY_FULL,
              ACTIVITY_CLAIMED % (ACTIVITY_FULL, ACTIVITY_FULL), DONE),
             (today, 20, ACTIVITY_CLAIMED % (20, ACTIVITY_FULL), TODO),
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

    # **A Great Rift row states its threshold only once the week's
    # reward is claimed**, and 0 until then. Taken at its word, that 0
    # is a target every score clears: a week barely started reads done.
    raw = _snapshot()
    raw["disaster_boss_rank_entities"] = {"disaster_s04": {"rank_02": {
        "score_week_id": this_week, "week_total_score": 1200,
        "week_total_score_reward": 0}}}
    got = _readings(raw, now)["seasonal_score"]
    if got != [("1200/300000", TODO)]:
        failures.append(
            f"a Great Rift row whose weekly reward is not yet claimed -- "
            f"`week_total_score_reward` 0 -- reads {got!r}, not "
            f"{[('1200/300000', TODO)]!r}. The 0 is not a threshold; "
            f"the stated one stands in for it.")

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
        want = ([(f"0/{CHAOS_CAP}", DONE)],
                [(f"5/{SORTIE_CAP}", TODO)]) if fresh else (
            [(f"{soon_after}{chaos_full}/{CHAOS_CAP}", TODO)],
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

    # --- the Events block puts what is owed first ---------------------
    # Only two states mean "nothing to do on this row": finished, and a
    # Forced Daily whose day is taken. A settled FLOOR is orange
    # because nothing can PROVE it finished, so it stays with the work;
    # an event nobody has mapped shows a deadline and no reading, which
    # is a question rather than an answer.
    #
    # Within each half the order is by deadline. A wrong comparison
    # here just reorders rows, which nothing else would report.
    reset = weekly_reset.last_daily_reset(now)
    raw = _snapshot()
    raw["event_schedules"] = {
        "EVENT_OVERCLOCK": {"event_overclock_live_13": {
            "start_time": int(now - DAY), "end_time": int(now + DAY)}},
        "EVENT_SCHEDULE": {
            "event_schedule_devil_001": {"start_time": int(now - DAY),
                                         "end_time": int(now + 3 * DAY)},
            "event_summer_01": {"start_time": int(now - DAY),
                                "end_time": int(now + 2 * DAY)}},
        "EVENT_RHYTHM_GAME": {"ds_event_rhythm_game": {
            "start_time": int(now - DAY), "end_time": int(now + 4 * DAY)}},
    }
    raw["overclock_entities"] = {"event_overclock_live_13": {
        "res_id": "event_overclock_live_13", "count": 2,
        "reset_time": int(reset + HOUR)}}
    raw[PASS_MISSION_FIELD] = {
        "event_devil_01_01": {"res_id": "event_devil_01_01",
                              "complete_time": 1},
        "event_summer_1_1_01": {"res_id": "event_summer_1_1_01",
                                "complete_time": 0},
    }
    # Soonest first inside each half: the summer floor ends first, then
    # the event_devil_* floor, then the rhythm event, no reader at
    # all. The Overclock's finished day sorts BELOW all three despite
    # ending soonest of the four -- which is the whole point, and what
    # a plain deadline sort would get wrong.
    want = ["summer_01", "schedule_devil_001", "ds_event_rhythm_game",
            "overclock_live_13"]
    got = [label for title, rows in columns_for(raw, now=now)
           for key, label, _widest in rows
           if key.startswith(EVENT_KEY_PREFIX) and key != EVENT_KEY_PREFIX]
    if got != want:
        failures.append(
            f"the Events block reads {got!r}, not {want!r}. Rows with work "
            f"outstanding come first, by deadline; only a finished event or "
            f"a Forced Daily whose day is taken sinks below them.")

    # --- which mission rows belong to which event --------------------
    # **An event's index is not always in its missions' ids.** The
    # devil event is scheduled as `event_schedule_devil_001` and its
    # missions are `event_devil_<day>_<task>` -- so the normalised key
    # `event_devil_1` matches DAY one and nothing else, and a 21-reward
    # event read `3/3` for a week without anything looking wrong.
    #
    # The stem fixes that and is far too greedy on its own, so these
    # pin both halves: event_devil_* is whole, and the three it
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

    # --- a Forced Daily's LAST day is finished, not refreshing --------
    # Orange says the row comes back tomorrow. On the final day there
    # is no tomorrow, so taking the day's runs ends the event and the
    # row is green like any other finished one. The event's own window
    # says which day that is -- and where there is no window the
    # answer has to be NO, because going green a day early costs the
    # last day's rewards where staying orange costs nothing.
    opens = weekly_reset.last_daily_reset(now)
    full = {"e": {"res_id": "e", "count": 2, "reset_time": int(opens + 60)}}
    for ends, want, why in (
            (int(opens + DAY), DONE, "the day the event ends on"),
            (int(opens + DAY) - 1, DONE, "an event ending inside today"),
            (int(opens + DAY) + 1, CYCLE_DONE, "a day with one still to come"),
            (int(opens + 9 * DAY), CYCLE_DONE, "an event with a week to run"),
            (None, CYCLE_DONE, "an event whose window is missing")):
        window = {} if ends is None else {"end_time": ends}
        got = _event_overclock({"overclock_entities": full}, "e", window, now)
        if got != [("2/2", want)]:
            failures.append(
                f"a full day on {why} reads {got!r}, not "
                f"{[('2/2', want)]!r}. Orange means the rewards come back; "
                f"on the last day they do not, and a row that stays orange "
                f"there never tells the user the event is over.")

    # --- a floor SAYS it is a floor, and only the game lifts it ------
    # A denominator counted off the rows in hand is what has been
    # handed out, not what the event holds, so `20/20` there would be
    # a different claim from `20/20` anywhere else on the tab. The
    # suffix carries that difference, and comes off only where
    # `event_mission_reward_entities` says the event is over.
    #
    # The flag is set by claiming the event's FINAL reward, which is
    # one more reward than its rows -- so a flagged event counts it in
    # both figures. `check_event_shapes` has the rest of that.
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

    unknown = UNKNOWN_MORE
    for held, claimed, finished, want, state, why in (
            (20, 16, None, "16/20" + unknown, FLOOR,
             "a part-claimed event with no completion record"),
            (20, 20, None, "20/20" + unknown, FLOOR,
             "every row in hand claimed, with nothing to say that is all"),
            (20, 20, 0, "20/20" + unknown, FLOOR,
             "a completion record that says NOT finished"),
            (20, 20, EVENT_DONE_VALUE, "21/21", DONE,
             "the game's own word that the event is finished"),
            (20, 16, EVENT_DONE_VALUE, "17/21" + unknown, FLOOR,
             "a finished flag over a tally that is not full")):
        got = _event(held, claimed, finished)
        if got != [(want, state)]:
            failures.append(
                f"{why} reads {got!r}, not {[(want, state)]!r}. A tally "
                f"counted off the rows in hand is a FLOOR and says so with "
                f"{unknown!r}; only {EVENT_DONE_FLAG} == "
                f"{EVENT_DONE_VALUE!r} takes it off and lets the row go "
                f"green.")

    # --- what the family's past instalments held ---------------------
    # A live event's rows are what has been issued so far. Its
    # FINISHED predecessors' are the whole total, and where two of them
    # agree the live row can say how much is still coming instead of
    # reading three of three on its first afternoon.
    #
    # **Two, and agreeing.** One instalment is a number rather than a
    # pattern -- the twenty-four login-streak rows on this account run
    # 7, 10, 14 and 21 days between them -- so a family has to repeat
    # itself before any of this is believed.
    def _family(pasts, held, claimed):
        """(the live event's reading, what got recorded).

        `pasts` is {instalment index: rows it held}, all ended; the
        live instalment holds `held` rows with `claimed` of them taken.
        """
        raw = _snapshot()
        missions, windows = {}, {}
        for index, rows in list(pasts.items()) + [(9, held)]:
            live = index == 9
            windows["event_probe_%d" % index] = {
                "start_time": now - (10 * DAY if live else 90 * DAY),
                "end_time": now + 10 * DAY if live else now - 60 * DAY}
            for at in range(1, rows + 1):
                name = "event_probe_%d_%02d" % (index, at)
                missions[name] = {
                    "res_id": name,
                    "complete_time": 1 if live and at <= claimed else 1}
            if live:
                for at in range(claimed + 1, rows + 1):
                    missions["event_probe_9_%02d" % at]["complete_time"] = 0
        raw[PASS_MISSION_FIELD] = missions
        raw["event_schedules"] = {"EVENT_SCHEDULE": windows}
        manager = checklist_manager.ChecklistManager(
            Path(tempfile.mkdtemp(prefix="checklist_totals_")))
        manager.load()
        stub = SimpleNamespace(
            context=SimpleNamespace(checklist_manager=manager))
        ChecklistTab._recall_event_totals(stub, raw, now)
        return _event_missions(raw, "event_probe_9", {}, now), manager

    got, manager = _family({1: 20, 2: 20}, held=3, claimed=1)
    want = [(EXPECTED_VALUE + "1/20", TODO)]
    if got != want:
        failures.append(
            f"an event whose family held 20 twice reads {got!r}, not "
            f"{want!r}. Three rows issued on day one is what the account "
            f"HAS, and a row saying 1/3 of an event that holds 20 is the "
            f"floor this record exists to replace.")
    if manager.events.get("event_probe") != {"event_probe_1": 20,
                                             "event_probe_2": 20}:
        failures.append(
            f"the finished instalments were recorded as "
            f"{manager.events!r}. The game purges old instalments, so a "
            f"count not written down while the rows are there is gone -- "
            f"that is why every load counts them.")

    for pasts, why in (({1: 20}, "one instalment on record"),
                       ({1: 20, 2: 14}, "two that disagree")):
        got, _manager = _family(pasts, held=3, claimed=1)
        if got != [("1/3" + UNKNOWN_MORE, FLOOR)]:
            failures.append(
                f"with {why} the row reads {got!r}, not the floor. A total "
                f"taken from a family that has not repeated itself is a "
                f"guess wearing a number's clothes.")

    # Nor may a family's history ever shrink a reading: a live event
    # that has issued MORE than its predecessors held is the wire
    # saying so, against a record that only remembers.
    got, _manager = _family({1: 20, 2: 20}, held=25, claimed=25)
    if got != [("25/25" + UNKNOWN_MORE, FLOOR)]:
        failures.append(
            f"an event holding more rows than its family's history reads "
            f"{got!r}. The record is the PAST; where the two disagree the "
            f"rows in hand are the ones that were counted today.")

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

    # --- the seasonal shelf: its own season, and its merged rows ------
    # **A Galactic Disaster season spans four Sortie seasons**, so an
    # `account` boundary taken from the Sortie one reads every
    # purchase before the last three weeks as never made: the shelf
    # full, and the bill for clearing it the whole catalogue. See
    # `shop_stock.SEASON_GROUP_BY_SHOP`.
    season = "disaster_s04"
    long_ago = int(now - 60 * DAY)

    def seasonal(rows, bought=None, sub="shop_disaster_1"):
        """A snapshot holding one disaster season and those products.

        `rows` are `(product id, item, cap, price)` and `bought` is
        `{product id: (count, when)}`.
        """
        raw = _snapshot(rift=((500, 1, 1),))
        raw["disaster_boss_rank_entities"] = {season: {"slot": {
            "score_week_id": 500, "week_total_score": 1,
            "week_total_score_reward": 1}}}
        raw["event_schedules"] = {
            "DISASTER_SEASON": {season: {
                "start_time": int(now - 70 * DAY),
                "end_time": int(now + 14 * DAY)}},
            "ASSAULT_SCHEDULE": {"assault_1_s7": {
                "start_time": int(now - 7 * DAY),
                "end_time": int(now + 14 * DAY)}}}
        raw["shop_res_data"] = {"shop_disaster": {
            product_id: {
                "product_link_item_id": item, "product_count": 1,
                "limit_count": limit, "limit_type": "LIMIT_ACCOUNT",
                "price_count": price, "price_link_item_id": 3920031,
                "sort": index, "link_shop_category_id": "shop_disaster",
                "link_shop_sub_category_id": sub}
            for index, (product_id, item, limit, price) in enumerate(rows)}}
        raw["shop_list"] = {product_id: {"count": count,
                                         "reset_time": when,
                                         "total_count": count}
                            for product_id, (count, when)
                            in (bought or {}).items()}
        return raw

    one = [(f"{season}_02", 3200001, 4, 100)]
    got = _readings(seasonal(one, {f"{season}_02": (4, long_ago)}),
                    now)[f"shop:{season}_02"]
    if got != [("0/4", DONE)]:
        failures.append(
            f"a seasonal shelf bought out two months ago reads {got!r}, "
            f"not 0/4. Its season is still running, so the purchase "
            f"stands -- measured against the SORTIE season instead it "
            f"reads as a shelf nobody has touched.")

    # **Pages merge by the item and the PRICE**, cap summed, and the
    # key carries every product under the row -- `shop_display_rows`.
    # Two pages at 30 are one row of 400; the page asking 120 for the
    # same material is a second row, as it is a second tile in game.
    pages = [(f"{season}_14", 3210001, 200, 30),
             (f"{season}_33", 3210001, 200, 30),
             (f"{season}_59", 3210001, 300, 120)]
    merged = f"shop:{season}_14+{season}_33"
    dearer = f"shop:{season}_59"
    # A purchase of something else, so `shop_list` has ARRIVED: with no
    # rows at all the shelves read a dash, which is a different case.
    untouched = {f"{season}_99": (1, long_ago)}
    said = _readings(seasonal(pages, untouched), now)
    if said.get(merged) != [("400/400", TODO)]:
        failures.append(
            f"two pages selling one item at one price read "
            f"{said.get(merged)!r} under {merged}, not 400/400 as one "
            f"row. The shelves are one shelf to whoever is shopping, "
            f"and their caps add up.")
    if said.get(dearer) != [("300/300", TODO)]:
        failures.append(
            f"the page asking a different price for the same item read "
            f"{said.get(dearer)!r} under {dearer}, not 300/300 of its "
            f"own. A dearer shelf is its own row: merged in, the row "
            f"would count down from a cap nobody can buy at one price.")

    # And what clearing the shelf costs is summed PER PRODUCT, since
    # the rows and the prices do not line up one to one.
    from ui.tabs.checklist_tab import shop_display_rows
    shelf = ("shop_disaster", shop_stock.ALL_SCREENS)
    got = shop_full_cost(shelf, "account", seasonal(pages))
    if got != 200 * 30 + 200 * 30 + 300 * 120:
        failures.append(
            f"clearing the shelf is billed at {got}, not "
            f"{200 * 30 + 200 * 30 + 300 * 120}. Its pages carry their "
            f"own prices, so the cost sums per PRODUCT however the rows "
            f"are drawn.")
    drawn = shop_display_rows(shelf, "account", seasonal(pages))
    if len(drawn) != 2:
        failures.append(
            f"the three pages drew {len(drawn)} rows, not 2, so the "
            f"merge is not happening where the tab reads it.")

    # A page the snapshot cannot read leaves the whole row unread: a
    # partial sum drawn as a total says a row is nearly cleared on the
    # strength of the pages it could see. A `count` that is not a
    # number is what one unreadable page looks like.
    half = _readings(seasonal(pages, {f"{season}_14": ("?", long_ago)}),
                     now).get(merged)
    if half != [(f"{NO_DATA}/400", UNKNOWN)]:
        failures.append(
            f"a merged row with one page unreadable reads {half!r}, not "
            f"a dash over 400.")

    # --- what a season is estimated to pay ----------------------------
    # Hand-counted per season, because the wire carries no achievement
    # reward table at all -- see `SEASON_ESTIMATE`. A season nobody has
    # counted gets no line rather than the last one's figures.
    if season_estimate(season) is None:
        failures.append(
            f"the live season {season} has no estimate, so the seasonal "
            f"shop's tip shows nothing where it should show one.")
    if season_estimate("disaster_s99") is not None:
        failures.append(
            "a season SEASON_ESTIMATE does not name still produced an "
            "estimate. The counts are per season and do not carry over, "
            "so one reused reads as a measurement of the wrong season.")
    # **Every term counts.** A table whose runs or whose fixed rewards
    # stopped reaching the total would still answer, and a figure that
    # is merely plausible is the one nobody checks.
    terms = SEASON_ESTIMATE[season]
    if season_estimate(season) != (sum(terms["fixed"])
                                   + terms["days"] * terms["per_run"]):
        failures.append(
            f"the estimate for {season} is not its own terms added up. "
            f"Every one of them is hand-counted, so one that stopped "
            f"reaching the total would go unnoticed.")

    # --- where a page's own rows land in the merged list --------------
    # Three orders are possible for a row one page adds and another
    # has never had, and only one reads as the shop does: beside the
    # rows it sits beside in game. Page two drops `B` and adds `X`, so
    # `X` belongs above `C` -- the row it precedes on its own page --
    # and `B` stays above `X` rather than sinking under it.
    def two_pages(first, second):
        rows, at = [], 0
        for page, items in (("shop_disaster_1", first),
                            ("shop_disaster_2", second)):
            for item in items:
                at += 1
                rows.append((f"{season}_{at:02d}", 3210000 + item, 5, 30))
        raw = seasonal(rows)
        at = 0
        for page, items in (("shop_disaster_1", first),
                            ("shop_disaster_2", second)):
            for _item in items:
                at += 1
                raw["shop_res_data"]["shop_disaster"][
                    f"{season}_{at:02d}"]["link_shop_sub_category_id"] = page
        return raw

    drawn = shop_display_rows(
        shelf, "account", two_pages([1, 2, 3], [1, 9, 3]))
    got = [group[0][1]["product_link_item_id"] for _key, group in drawn]
    if got != [3210001, 3210002, 3210009, 3210003]:
        failures.append(
            f"a row page two adds between two it shares landed at "
            f"{got}, not [3210001, 3210002, 3210009, 3210003]. It goes "
            f"just above the row it precedes on its OWN page: at the "
            f"end of the list it reads as an afterthought, and above "
            f"the row page two skipped it pushes that one down.")

    # --- which pages are open, and what that colours ------------------
    # The wire names no shop page, so which are open is read off the
    # SORTIE rotations inside the season: the first is the preseason
    # and each one after it opens a page. See `shop_pages_open`. That
    # is the reading for a season `SUPPLY_ROUNDS` does not name, and
    # the test season is one it names, so the table is emptied here
    # and tested on its own below.
    import ui.tabs.checklist_tab as checklist_tab
    supply = checklist_tab.SUPPLY_ROUNDS
    checklist_tab.SUPPLY_ROUNDS = {}
    shelf = ("shop_disaster", shop_stock.ALL_SCREENS)
    # A rotation of ten days and a season of four of them: one
    # preseason and a page each. `now` sits in the second, so one page
    # is open and two are not.
    ROTATION = 10 * DAY
    opens = int(now - 15 * DAY)

    def three_pages(bought=None):
        """One item on three pages, and the schedules that date them."""
        raw = seasonal(
            [(f"{season}_01", 3210001, 10, 30),
             (f"{season}_02", 3210001, 10, 30),
             (f"{season}_03", 3210001, 10, 30)], bought)
        raw["event_schedules"]["DISASTER_SEASON"] = {season: {
            "start_time": opens, "end_time": opens + 4 * ROTATION}}
        raw["event_schedules"]["ASSAULT_SCHEDULE"] = {
            "r%d" % at: {"start_time": opens + at * ROTATION,
                         "end_time": opens + (at + 1) * ROTATION}
            for at in range(4)}
        for at, pid in enumerate((f"{season}_01", f"{season}_02",
                                  f"{season}_03")):
            raw["shop_res_data"]["shop_disaster"][pid][
                "link_shop_sub_category_id"] = "shop_disaster_%d" % (at + 1)
        return raw

    for moment, want, why in (
            (opens + 5 * DAY, set(),
             "its PRESEASON -- a Galactic Disaster's schedule opens "
             "three weeks before its shop does"),
            (now, {"shop_disaster_1"},
             "one rotation past the preseason, so the first page and "
             "no other"),
            (opens + 35 * DAY,
             {"shop_disaster_1", "shop_disaster_2", "shop_disaster_3"},
             "three rotations past the preseason, so all of them")):
        got = shop_pages_open(shelf, "account", three_pages(), moment)
        if got != want:
            failures.append(
                f"{int((moment - opens) / DAY)} days into the season the "
                f"open pages read {sorted(got or ())}, not "
                f"{sorted(want)} -- {why}. The first rotation inside a "
                f"season is its preseason and each one after opens a "
                f"page.")

    # **A row whose whole remainder is on a shut page is ORANGE.** Red
    # says there is something to buy; on such a row there is not, and
    # green would say it was finished when another page is still to
    # come. Pages two and three hold 20 of the 30, and buying out page
    # one leaves exactly that.
    row = f"shop:{season}_01+{season}_02+{season}_03"
    got = _readings(three_pages({f"{season}_01": (10, int(now - DAY))}),
                    now)[row]
    if got != [("20/30", LOCKED_PAGES)]:
        failures.append(
            f"with everything on sale bought and 20 still on unopened "
            f"pages, the row reads {got!r}, not 20/30 in "
            f"{LOCKED_PAGES!r}. There is nothing to buy, so it is not "
            f"red; another page is coming, so it is not green.")
    # One left that CAN be bought and it is red again.
    got = _readings(three_pages({f"{season}_01": (9, int(now - DAY))}),
                    now)[row]
    if got != [("21/30", TODO)]:
        failures.append(
            f"with one still buyable the row reads {got!r}, not 21/30 "
            f"in red. Orange is for a row with nothing left to do "
            f"today, not for one with a shut page anywhere behind it.")

    # --- and the shop closes with its season --------------------------
    # The shelves survive on the wire and the standings go on naming
    # the season live, so nothing else notices it ended.
    raw = three_pages()
    if shop_shut_for_now(shelf, "account", raw, now):
        failures.append(
            "the seasonal shop reads as shut while its season is "
            "running.")
    over = opens + 5 * ROTATION          # past the season's end_time
    if not shop_shut_for_now(shelf, "account", raw, over):
        failures.append(
            "the seasonal shop is still open after its season ended. "
            "Its currency is wiped, so the block would bill a "
            "bought-out catalogue in money nobody has.")
    if not shop_shut_for_now(shelf, "account", raw, opens + 5 * DAY):
        failures.append(
            "the seasonal shop is open during its PRESEASON, where the "
            "game has neither the shop nor the currency.")
    # A snapshot from before the schedules arrived says nothing either
    # way, and a shop that vanished on it would read as a bug.
    bare = three_pages()
    bare.pop("event_schedules")
    if shop_shut_for_now(shelf, "account", bare, now):
        failures.append(
            "the seasonal shop reads as shut on a snapshot carrying no "
            "schedules at all. That is a payload not yet arrived, not "
            "a season that is over.")

    # --- the update notices' Supply rounds, where they are copied in ----
    # They outrank the Sortie seasons: a season whose parts are not one
    # Sortie season long is dated by nothing else. Rounds two and three
    # days in and a third weeks away: at `now` two pages are open, where
    # the Sortie seasons would open one.
    def day_of(moment):
        return time.strftime("%Y-%m-%d", time.gmtime(moment))
    checklist_tab.SUPPLY_ROUNDS = {season: (
        day_of(opens + 2 * DAY), day_of(opens + 3 * DAY),
        day_of(opens + 60 * DAY))}
    try:
        got = shop_pages_open(shelf, "account", three_pages(), now)
    finally:
        checklist_tab.SUPPLY_ROUNDS = supply
    if got != {"shop_disaster_1", "shop_disaster_2"}:
        failures.append(
            f"with Supply rounds copied in for the season, the open pages "
            f"read {sorted(got or ())}, not the first two. The update "
            f"notice's dates outrank the Sortie seasons, which date a "
            f"season whose parts are not one of them long wrongly.")

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

    # --- a shop heading's own total -----------------------------------
    # `<currency held>/<what clearing the ticked products costs>`. The
    # bill is the part that can go quietly wrong: a price read off the
    # wrong field, a cap counted instead of what is left, or an
    # untracked product billed anyway all produce a number that still
    # looks like a number.
    MONEY = 2000031                 # Policy Point
    SHOP = ("shop_town", "none")
    HEAD = SHOP_TOTAL_PREFIX + shop_head_key(SHOP, "weekly")

    def _shop(products, bought=(), held=9999, money=MONEY):
        """A snapshot of one weekly shop and what has been bought."""
        raw = _snapshot(amounts=((money, held),) if money else ())
        raw["shop_res_data"] = {SHOP[0]: {
            pid: {"link_shop_sub_category_id": SHOP[1],
                  "limit_type": "LIMIT_WEEK", "limit_count": cap,
                  "product_link_item_id": 3210002, "product_count": 1,
                  "price_link_item_id": price_of,
                  "price_count": price, "sort": at}
            for at, (pid, cap, price, price_of) in enumerate(products)}}
        # A row per product, `bought` overriding. `shop_list` arriving
        # at all is what tells `shop_stock.remaining` an absent row
        # means a full shelf rather than an unread one.
        raw["shop_list"] = {pid: {"count": 0, "reset_time": now}
                            for pid, _cap, _price, _of in products}
        for pid, count in bought:
            raw["shop_list"][pid] = {"count": count, "reset_time": now}
        return raw

    # Nothing bought: the bill is every cap at its price.
    raw = _shop((("a", 3, 20, MONEY), ("b", 1, 100, MONEY)), held=250)
    got = _readings(raw, now)[HEAD][0]
    if got != ("250/160", DONE):
        failures.append(
            f"a full shelf of 3x20 and 1x100 against 250 held reads "
            f"{got!r}, not ('250/160', {DONE!r}). The bill is what is "
            f"LEFT to buy at its price, and green is being able to "
            f"afford the lot.")

    # Bought down, and short of the money.
    raw = _shop((("a", 3, 20, MONEY), ("b", 1, 100, MONEY)),
                bought=(("a", 2),), held=50)
    got = _readings(raw, now)[HEAD][0]
    if got != ("50/120", TODO):
        failures.append(
            f"with two of three bought and 50 held, the shop reads "
            f"{got!r}, not ('50/120', {TODO!r}). A bill counting the CAP "
            f"rather than the remainder overstates every shop the "
            f"account has shopped at.")

    # An untracked product is not billed.
    raw = _shop((("a", 3, 20, MONEY), ("b", 1, 100, MONEY)), held=250)
    got = _readings(raw, now, tracked=lambda pid: pid != "b")[HEAD][0]
    if got != ("250/60", DONE):
        failures.append(
            f"with one of two products unticked the shop reads {got!r}, "
            f"not ('250/60', {DONE!r}). The row answers for what the "
            f"user tracks, and billing the rest makes it unanswerable.")

    # Two currencies on one shelf: nothing to total.
    raw = _shop((("a", 3, 20, MONEY), ("b", 1, 100, 2000020)))
    if HEAD in _readings(raw, now):
        failures.append(
            "a shop priced in two currencies still produced a total. "
            "Adding prices in different money gives a figure that "
            "cannot be compared with any holding.")

    # No price item at all -- the seasonal supplies are free.
    raw = _shop((("a", 3, 0, None),), money=None)
    if HEAD in _readings(raw, now):
        failures.append(
            "a shop whose products carry no price item still produced a "
            "total. There is no currency to read and nothing to spend.")

    # --- what a shop currency earns -----------------------------------
    # The rate is the part a reader cannot sanity-check: a window taken
    # off the wrong end, a span divided by the wrong number of days, or
    # a figure scaled to a unit it was never measured over all produce
    # a plausible number with nothing beside it to disagree.
    #
    # 10 a day, watched for 100 days.
    steady = [(1000 + n, 10 * n) for n in range(101)]

    rate, covered = currency_rate(steady, 7)
    if (rate, covered) != (10.0, 7):
        failures.append(
            f"a ledger rising 10 a day reads {rate!r} a day over "
            f"{covered!r} days, not 10.0 over 7. The window is taken off "
            f"the NEWEST point backwards; off the oldest it would answer "
            f"about the account's first week forever.")

    # A window longer than the ledger falls back to its whole span, and
    # SAYS so -- that second figure is what marks a scaled-up reading.
    rate, covered = currency_rate(steady, 365)
    if (rate, covered) != (10.0, 100):
        failures.append(
            f"a 365-day window over a 100-day ledger reads {rate!r} over "
            f"{covered!r}, not 10.0 over 100. A window the ledger cannot "
            f"fill has to report what it actually covered, or nothing can "
            f"tell a measured year from an extrapolated one.")

    for points in ([], [(1000, 5)], [(1000, 5), (1000, 9)]):
        if currency_rate(points, 7) != (None, 0):
            failures.append(
                f"{points!r} produced a rate. Fewer than two days apart "
                f"there is no span to divide by, and a rate off one point "
                f"is a division by zero waiting to be a number.")

    # A seed at the account's creation and one reading today: the far
    # end is 100 days back whichever window is asked for, so there is
    # ONE line and it says so.
    seeded = [(1000, 0), (1100, 1000)]
    rows = shop_rates(seeded, "week", 7, "Policy Point")
    want = ((RATE_LONG_LABEL % "week", "70 Policy Point"),)
    if rows != want:
        failures.append(
            f"a ledger of a seed and one reading gives {rows!r}, not "
            f"{want!r}. Both windows land on the same two points -- "
            f"printing that twice presents one measurement as two that "
            f"agree, and calling it `recent` names a window it did not "
            f"use.")

    # A week of daily points beside that seed: the recent line appears
    # and is measured against the nearest day it HAS, eight back, not
    # against the seed three months back.
    recent = [(1000, 0)] + [(1092 + n, 1000 + 200 * n) for n in range(9)]
    rows = shop_rates(recent, "week", 7, "P")
    if len(rows) != 2 or rows[0][0] != RATE_RECENT_LABEL % "week":
        failures.append(
            f"a seed plus eight daily points gives {rows!r}. The recent "
            f"line has to take the NEAREST recorded day to the window it "
            f"wants -- eight days back, not the seed three months back.")
    if len(rows) == 2 and rows[0][1] == rows[1][1]:
        failures.append(
            f"the two lines read the same {rows[0][1]!r} where the recent "
            f"week earned 200 a day against the long run's 10. A pair of "
            f"windows that cannot disagree is one line printed twice.")

    # **Both lines are per ROTATION.** A monthly shop over the same
    # ledger says roughly four times what a weekly one does, because
    # the unit is the shop's period and only the window differs.
    week = shop_rates(steady, "week", 7, "P")[-1][1]
    month = shop_rates(steady, "month", 30, "P")[-1][1]
    if (int(week.split()[0]), int(month.split()[0])) != (70, 300):
        failures.append(
            f"a shop earning 10 a day reads {week!r} weekly and "
            f"{month!r} monthly, not 70 and 300. Both lines are per "
            f"ROTATION of that shop -- a rate per day times the days its "
            f"period runs -- and only the window behind them differs.")

    # And nothing at all below the floor.
    if shop_rates(steady[:SHOP_RATE_FLOOR], "week", 7, "P"):
        failures.append(
            f"a ledger spanning under {SHOP_RATE_FLOOR} days produced a "
            f"rate. What a window that short holds is which content ran "
            f"in it, and a tip has to be worth stopping for.")

    # --- what a full period of a shop costs ---------------------------
    # **The whole cap, bought or not**, which is what separates it from
    # the heading's own reading. Both are a sum over the same products
    # at the same prices, so the only thing that can distinguish them
    # is whether a shelf that has been emptied still counts.
    SHOP = ("shop_town", "none")
    shelf = _shop((("a", 3, 20, MONEY), ("b", 1, 100, MONEY)),
                  bought=(("a", 2),))
    got = shop_full_cost(SHOP, "weekly", shelf)
    if got != 160:
        failures.append(
            f"a shelf of 3x20 and 1x100 costs {got!r} in full, not 160. "
            f"Two of the three having been bought does not make the "
            f"period cheaper -- that is what the heading's own reading "
            f"says, and this one is meant to sit still beside a rate.")
    got = shop_full_cost(SHOP, "weekly", shelf, lambda pid: pid != "b")
    if got != 60:
        failures.append(
            f"with one product unticked the full cost is {got!r}, not 60. "
            f"It answers for what the user tracks, like every other "
            f"figure on that heading.")
    if shop_full_cost(SHOP, "weekly", _snapshot()) != 0:
        failures.append(
            "a shop with no products on the wire costed something.")

    # --- which figure a currency feeds the ledger ---------------------
    wired = {"characters": {"currencies": {"2000031": {
        "amount": 23, "total_amount": 36043, "total_use_amount": 36020}}}}
    if currency_earned(wired, 2000031) != (36043, checklist_manager.FROM_WIRE):
        failures.append(
            f"a currency stating its own lifetime total feeds "
            f"{currency_earned(wired, 2000031)!r} to the ledger, not its "
            f"`total_amount`. Recording the HOLDING would make every "
            f"purchase read as earnings undone.")
    # An item with no lifetime total: what is HELD plus everything ever
    # bought with it. 11005 in hand and 3 x 4000 spent.
    item = {"inventory": {"items": [{"res_id": 3920007, "amount": 11005}]},
            "shop_res_data": {"shop_assault": {
                "p1": {"price_link_item_id": 3920007, "price_count": 4000},
                "p2": {"price_link_item_id": 2000020, "price_count": 99}}},
            "shop_list": {"p1": {"total_count": 3},
                          "p2": {"total_count": 7}}}
    if currency_earned(item, 3920007) != (11005 + 12000,
                                          checklist_manager.FROM_SHOPS):
        failures.append(
            f"an inventory item feeds {currency_earned(item, 3920007)!r}, "
            f"not 23005 from the shops. Nothing on the wire keeps a "
            f"lifetime total for those two, and the holding alone would "
            f"read as an account that has never earned what it spent.")
    if currency_earned({"inventory": {"items": [
            {"res_id": 3920007, "amount": 11005}]}}, 3920007) != (None, None):
        failures.append(
            "an item was recorded with no `shop_list` to account for it. "
            "That payload not having arrived is not the same as nothing "
            "having been bought, and the holding alone puts a total in "
            "the ledger every later reading has to climb back over.")
    if currency_earned({}, 2000031) != (None, None):
        failures.append(
            "a currency the snapshot carries nowhere fed a figure to the "
            "ledger. Never held and not yet captured look the same from "
            "there, and a zero for either is a false floor in the record.")

    # --- how long a shop's period is ----------------------------------
    # A THIRTY-ONE day month, deliberately: the written fallback is
    # thirty, so a reading that ignored the wire would agree with
    # this case and the case would never fail.
    month = {"month_start": 1788199200,
             "month_end": 1788199200 + 31 * DAY - 1}
    if shop_period("monthly", month, now) != ("month", 31):
        failures.append(
            f"a month bounded by the wire reads "
            f"{shop_period('monthly', month, now)!r}, not ('month', 31). "
            f"A month is 28 to 31 days and the wire is the only thing "
            f"that knows which.")
    if shop_period("monthly", {}, now) != ("month", 30):
        failures.append(
            f"a month with no bounds on the wire reads "
            f"{shop_period('monthly', {}, now)!r}, not the written "
            f"fallback. A fresh install has no `month_start` until "
            f"its first capture.")
    if shop_period("weekly", {}, now) != ("week", 7):
        failures.append(
            f"a weekly shop's period reads "
            f"{shop_period('weekly', {}, now)!r}, not ('week', 7).")

    # --- a login streak, which has no stated length -------------------
    # Every reading here is a plausible number if it is wrong. The
    # account's own history holds streaks of 7, 10, 14 and 21 days, so
    # a written-down seven would read `8/7` on the eighth day of a
    # fortnight's run and nothing would look broken.
    WINDOW = {"start_time": 1000, "end_time": now + DAY}

    def _streak(**fields):
        raw = _snapshot()
        raw["attendance_entities"] = [dict({"event_id": "event_143",
                                            "start_time": 2000}, **fields)]
        return _event_attendance(raw, "event_daily_16", WINDOW, now)

    cases = (
        # **Under the floor the ceiling is the FLOOR.** Counting from
        # what is claimed alone read `1/1+?` a day into a new event,
        # which says finished; no login event in the record has ended
        # under seven. See `ATTENDANCE_FLOOR`.
        (dict(current_days=1, received_days=1),
         "1/%d" % ATTENDANCE_FLOOR + UNKNOWN_MORE, CYCLE_DONE),
        # claimed up to date -- orange, the streak may have more days
        (dict(current_days=4, received_days=4),
         "4/%d" % ATTENDANCE_FLOOR + UNKNOWN_MORE, CYCLE_DONE),
        # a day shown up for and not claimed -- red
        (dict(current_days=5, received_days=4),
         "4/%d" % ATTENDANCE_FLOOR + UNKNOWN_MORE, TODO),
        # the game says the streak is over -- green, and the floor mark
        # comes off with it
        (dict(current_days=7, received_days=7, completed=True), "7/7", DONE),
        # **Days shown up for do not raise the ceiling.** Whatever
        # `current_days` says, the ceiling is one past what has been
        # claimed -- a streak has never been caught more than one
        # apart, and fifty-six over seven would be a tally of nothing.
        (dict(current_days=56, received_days=7), "7/8" + UNKNOWN_MORE, TODO),
        # And past the floor the claimed count leads again.
        (dict(current_days=9, received_days=9), "9/9" + UNKNOWN_MORE,
         CYCLE_DONE),
        # no shown-up count at all: nothing says a day is waiting
        (dict(received_days=3),
         "3/%d" % ATTENDANCE_FLOOR + UNKNOWN_MORE, CYCLE_DONE),
    )
    for fields, want, state in cases:
        got = _streak(**fields)
        if got != [(want, state)]:
            failures.append(
                f"a streak reading {fields!r} shows {got!r}, not "
                f"[({want!r}, {state!r})].")

    # --- the one answer the program cannot give -----------------------
    # A row at its own ceiling that the game has not called finished is
    # either finished or waiting for more, and nothing here can say
    # which. So the tab asks the person who can see the game, and
    # remembers the answer against the READING it was given for.
    for segments, want, why in (
            ((("21/21", FLOOR),), (21, 21), "a floor at its ceiling"),
            ((("20/20" + UNKNOWN_MORE, FLOOR),), (20, 20),
             "a floor at its ceiling with the mark still on it"),
            ((("7/7" + UNKNOWN_MORE, CYCLE_DONE),), (7, 7),
             "a streak claimed up to date"),
            ((("24/24", DONE),), None, "an event the game called finished"),
            ((("16/20", FLOOR),), None, "an event with work left"),
            ((("Go drink!", TODO),), None, "a row that is not a tally"),
    ):
        got = unsure_ceiling(segments)
        if got != want:
            failures.append(
                f"{why} answers {got!r} to the Finished? question, not "
                f"{want!r}. The box is offered where the tally is full and "
                f"the GAME has not settled it, and nowhere else.")

    # And the answer stands only for the pair it was given for.
    store = checklist_manager.ChecklistManager(
        Path(tempfile.mkdtemp(prefix="checklist_finished_")))
    store.load()
    stub = SimpleNamespace(
        context=SimpleNamespace(checklist_manager=store),
        _finishable={})
    raw = _snapshot()
    readings = {EVENT_KEY_PREFIX + "probe": (("21/21", FLOOR),
                                             ("Ends in 3 days", LATER))}
    open_rows = ChecklistTab._mark_finished(stub, raw, readings)
    if open_rows.get(EVENT_KEY_PREFIX + "probe") != (21, 21, False):
        failures.append(
            f"an unanswered row came back as "
            f"{open_rows.get(EVENT_KEY_PREFIX + 'probe')!r}, not "
            f"(21, 21, False). The pair is what the answer will be "
            f"remembered against.")

    store.call_finished("probe", 21, 21)
    readings = {EVENT_KEY_PREFIX + "probe": (("21/21", FLOOR),
                                             ("Ends in 3 days", LATER))}
    open_rows = ChecklistTab._mark_finished(stub, raw, readings)
    if readings[EVENT_KEY_PREFIX + "probe"][0] != ("21/21", DONE):
        failures.append(
            f"an answered row still reads "
            f"{readings[EVENT_KEY_PREFIX + 'probe'][0]!r}. A tick is the "
            f"only thing that can settle an event the wire says nothing "
            f"about, so the reading goes green on it.")
    if "probe" not in (raw.get(EVENT_FINISHED_FIELD) or ()):
        failures.append(
            "an answered row did not reach the snapshot, so the sort "
            "cannot see it: the rows are built before these readings are.")

    # **Either figure moving retires the answer**, and not quietly:
    # the record goes, so the row is asked about again from scratch.
    readings = {EVENT_KEY_PREFIX + "probe": (("21/22", FLOOR),
                                             ("Ends in 3 days", LATER))}
    open_rows = ChecklistTab._mark_finished(stub, raw, readings)
    if store.finished or readings[EVENT_KEY_PREFIX + "probe"][0][1] is DONE:
        failures.append(
            f"a reward appearing under an answered row left it answered: "
            f"{store.finished!r}, reading "
            f"{readings[EVENT_KEY_PREFIX + 'probe'][0]!r}. The answer was "
            f"about 21 of 21; 21 of 22 is a different question.")

    # A row that is not on the tab at all is left alone -- its event
    # may simply be over, and a tab with no snapshot behind it would
    # otherwise wipe every answer at once.
    store.call_finished("gone", 5, 5)
    ChecklistTab._mark_finished(stub, raw, {})
    if "gone" not in store.finished:
        failures.append(
            "an answer was forgotten for a row that was not drawn. A "
            "Checklist with no data behind it draws nothing, and that is "
            "not the user changing their mind.")

    # --- a rectangular family states its own size --------------------
    # event_devil_* is the same three tasks each day, ids
    # `event_devil_<day>_<task>`, and the game issues one axis a row
    # at a time and the other all at once -- so a same-second batch
    # spanning the days says both that the shape is a grid and how
    # many days it has. The game's own screen says 21; so does this,
    # and it said so on the event's first afternoon with 12 rows in
    # hand.
    def _grid(pairs, stamps, claimed=0):
        """`pairs` is [(page, index)], `stamps` the issue time of each."""
        raw = _snapshot()
        missions = {}
        for (page, index), stamp in zip(pairs, stamps):
            name = "event_probe_%02d_%02d" % (page, index)
            missions[name] = {"res_id": name, "issued_time": stamp,
                              "complete_time": 1 if len(missions) < claimed
                              else 0}
        raw[PASS_MISSION_FIELD] = missions
        return _event_missions(raw, "event_probe", {}, now)

    # Seven days of three tasks, with only day one's three issued and
    # the first task of every day issued in one batch.
    day_one = [(d, 1) for d in range(1, 8)] + [(1, 2), (1, 3)]
    stamps = [500] * 7 + [600, 700]
    got = _grid(day_one, stamps, claimed=2)
    if got != [("2/21", FLOOR)]:
        failures.append(
            f"a grid with nine of its rows issued reads {got!r}, not "
            f"[('2/21', {FLOOR!r})]. Seven days x three tasks is what the "
            f"batch spanning the days says the event holds, and saying "
            f"2/2 instead is the floor this exists to replace.")

    # A ragged family must NOT be called a grid: its batch varies both
    # indices, which says nothing about a shape.
    got = _grid([(1, 1), (1, 2), (2, 1)], [500, 500, 500], claimed=1)
    if got != [("1/3", FLOOR)]:
        failures.append(
            f"a family whose batch varies both indices reads {got!r}. "
            f"Nothing there says the pages are the same length -- the "
            f"bartender's are 7, 7 and 10.")

    # **The shape is re-derived, never remembered.** An eighth day
    # appearing is an event bigger than it looked, and the row has to
    # say so rather than hold the number it first worked out.
    eight = [(d, 1) for d in range(1, 9)] + [(1, 2), (1, 3)]
    got = _grid(eight, [500] * 8 + [600, 700], claimed=2)
    if got != [("2/24", FLOOR)]:
        failures.append(
            f"a grid that gained a day reads {got!r}, not [('2/24', "
            f"{FLOOR!r})]. Nothing about the shape is written down: it "
            f"comes off the ids in hand every time, so an event that "
            f"turns out longer than it looked corrects itself.")

    # --- a page issued WHOLE is a denominator, not a floor -----------
    # A mission id's middle segment is its page, and a page whose rows
    # all carry one `issued_time` was issued in a single act -- so its
    # count is what it holds. Every page issued that way in the
    # account's table is a ladder of thresholds, and none of the
    # twenty-four that trickle is.
    #
    # **Whole pages do not make the EVENT exact** unless every page is
    # whole: a page still being handed out says the event is not done
    # issuing, and a page nobody has been issued at all is invisible
    # either way -- which is why this never goes green.
    def _paged(pages, claimed):
        """`pages` is {page number: [issued_time per row]}."""
        raw = _snapshot()
        missions = {}
        taken = claimed
        for page, stamps in pages.items():
            for at, stamp in enumerate(stamps, start=1):
                name = "event_paged_%02d_%02d" % (page, at)
                missions[name] = {"res_id": name, "issued_time": stamp,
                                  "complete_time": 1 if taken > 0 else 0}
                taken -= 1
        raw[PASS_MISSION_FIELD] = missions
        return _event_missions(raw, "event_paged", {}, now)

    got = _paged({1: [500, 500, 500, 500, 500, 500, 500]}, claimed=3)
    if got != [("3/7", FLOOR)]:
        failures.append(
            f"a page issued whole reads {got!r}, not [('3/7', {FLOOR!r})]. "
            f"Seven rows sharing one issue stamp is seven rewards stated, "
            f"not seven handed out so far -- and a denominator that is a "
            f"statement does not carry the floor mark.")

    got = _paged({1: [500, 600, 700]}, claimed=3)
    if got != [("3/3" + UNKNOWN_MORE, FLOOR)]:
        failures.append(
            f"a page whose rows trickled in reads {got!r}, not the floor. "
            f"Three rows issued at three different moments is an event "
            f"still handing them out.")

    got = _paged({1: [500, 500, 500], 2: [500, 600]}, claimed=2)
    if got != [("2/5" + UNKNOWN_MORE, FLOOR)]:
        failures.append(
            f"an event with one whole page and one trickling reads "
            f"{got!r}, not the floor. One page being complete says "
            f"nothing about the page beside it.")

    # --- a total written down, and what takes it back ----------------
    # The launch login event hands out seven rewards in a new account's
    # first week and then sits there for a year with `current_days`
    # climbing. Nothing on the wire says seven, so it is WRITTEN DOWN --
    # and written down so that the wire can take it back: a reward past
    # the number disproves it and the row goes back to reading the way
    # every other streak reads.
    def _launch(name, **fields):
        raw = _snapshot()
        raw["attendance_entities"] = [dict({"event_id": "event_1",
                                            "start_time": 2000}, **fields)]
        return _event_attendance(raw, name, WINDOW, now)

    written = WRITTEN_TOTALS.get("event_daily_1")
    if written != 7:
        failures.append(
            f"WRITTEN_TOTALS holds {written!r} for the launch event, and "
            f"the cases below are written against seven.")
    else:
        got = _launch("event_daily_1", current_days=56, received_days=7)
        if got != [("7/7", DONE)]:
            failures.append(
                f"the launch event reads {got!r}, not [('7/7', {DONE!r})]. "
                f"Its seven are all it ever had; counting its days "
                f"instead reports a reward waiting that cannot be "
                f"claimed, in red, for the year the event runs.")
        # **An eighth reward disproves the write-down.** A number typed
        # into the program is a claim about what the wire has not said,
        # and this is the wire saying it.
        got = _launch("event_daily_1", current_days=56, received_days=8)
        if got != [("8/9" + UNKNOWN_MORE, TODO)]:
            failures.append(
                f"an eighth reward left the launch event reading {got!r}. "
                f"Past the written-down total the row has to go back to "
                f"its group's own reading -- otherwise a write-down that "
                f"turns out wrong is wrong on screen for ever.")
        # And it belongs to that event alone.
        got = _launch("event_daily_16", current_days=56, received_days=7)
        if got != [("7/8" + UNKNOWN_MORE, TODO)]:
            failures.append(
                f"a live streak with the same numbers read {got!r}. The "
                f"write-down is keyed on the event, not on the shape of "
                f"its record.")

    # The row is the FIRST one started after the event was: the streak
    # ids are numbered nothing like the schedule's, and a row that
    # began before the window belongs to some earlier event.
    raw = _snapshot()
    raw["attendance_entities"] = [
        {"event_id": "before", "start_time": 500, "received_days": 99,
         "current_days": 99},
        {"event_id": "mine", "start_time": 2000, "received_days": 4,
         "current_days": 4},
        {"event_id": "later", "start_time": 9000, "received_days": 1,
         "current_days": 1},
    ]
    got = _event_attendance(raw, "event_daily_16", WINDOW, now)
    if got != [("4/%d" % ATTENDANCE_FLOOR + UNKNOWN_MORE, CYCLE_DONE)]:
        failures.append(
            f"with three streaks on the account the row reads {got!r}, not "
            f"the first one started after the event's own window opened.")

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
