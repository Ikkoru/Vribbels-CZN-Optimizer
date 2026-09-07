"""What the Checklist rows read off a snapshot.

Every one of these fails by printing a plausible number. A currency
read under the wrong res_id reports 0, which is what an empty stock
also reports; a module counted against the wrong deadline reports a
smaller figure, not an error; and the passes-left reading is a
subtraction from an allowance, so an off-by-one is a number that still
looks like a number.

The two module rows NEST -- a copy expiring before today's reset also
expires before the week's -- which is the opposite of the Materials
tab's buckets, where a copy falls in one window only. Reversing that
by accident leaves both rows populated and neither obviously wrong.

Driven from a built snapshot with the clock passed in, so nothing here
depends on captured data or on the hour it runs at.

No Tk and no snapshot needed.
"""

from ._harness import add_source_to_path

NAME = "checklist readings"

# A Monday 10:00:00 UTC. The daily reset after it is that day's 18:00
# and the weekly one is the coming Sunday; the run confirms both before
# using them, so a corrected reset hour fails here rather than silently
# re-aiming every case.
MONDAY_MORNING = 1789380000
HOUR = 3600
DAY = 24 * HOUR


def _snapshot(amounts=(), expiries=(), day_point=None, spent=None):
    """A snapshot holding exactly what a case needs and nothing else."""
    characters = {}
    if amounts:
        characters["currencies"] = {str(res_id): {"amount": amount}
                                    for res_id, amount in amounts}
    if spent is not None:
        characters["town_data"] = {
            "day_changeable_data": {"use_town_visit_count": spent}}
    raw = {"inventory": {"period_items": [
        {"res_id": 3920026,
         "value": [{"end_time": end} for end in expiries]}]}}
    if characters:
        raw["characters"] = characters
    if day_point is not None:
        raw["point_entity"] = {"day_point": day_point}
    return raw


def run():
    add_source_to_path()
    import weekly_reset
    import excursions
    from ui.tabs.checklist_tab import (
        CHAOS_CURRENCY, COLUMNS, MODULE_ITEM, SORTIE_CAP, SORTIE_CURRENCY,
        ACTIVITY_FULL, NO_DATA, _readings,
    )
    from datetime import datetime, timezone

    failures = []
    now = MONDAY_MORNING

    # --- the clock the cases are written against ----------------------
    at = datetime.fromtimestamp(now, timezone.utc)
    if (at.weekday(), at.hour, at.minute) != (0, 10, 0):
        failures.append(
            f"MONDAY_MORNING is {at.isoformat()}, not a Monday 10:00 UTC. "
            f"Every case below is an offset from it.")
        return failures
    today = weekly_reset.next_daily_reset(now)
    week = weekly_reset.next_reset(now)
    if not now < today < week:
        failures.append(
            f"the daily reset ({today}) does not fall between now ({now}) "
            f"and the weekly one ({week}), so the nesting these cases "
            f"check cannot be read.")
        return failures

    # --- every keyed reading belongs to a row, and vice versa ---------
    keyed = {key for _title, rows in COLUMNS
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
    if out["chaos_currency"][0] != "3":
        failures.append(
            f"Chaos Currency reads {out['chaos_currency'][0]!r} where the "
            f"snapshot holds 3 of {CHAOS_CURRENCY}. A wrong res_id reads "
            f"0, which is what an empty stock reads.")
    if out["sortie_currency"][0] != f"7/{SORTIE_CAP}":
        failures.append(
            f"Sortie Currency reads {out['sortie_currency'][0]!r}, not "
            f"'7/{SORTIE_CAP}', from 7 of {SORTIE_CURRENCY}.")

    # An id held nowhere reads 0 rather than raising.
    out = _readings(_snapshot(), now)
    if out["chaos_currency"][0] != "0":
        failures.append(
            f"with nothing held, Chaos Currency reads "
            f"{out['chaos_currency'][0]!r}, not '0'.")

    # --- the day's activity, and its colour ---------------------------
    for point, want, alert in ((ACTIVITY_FULL, f"{ACTIVITY_FULL}/"
                                f"{ACTIVITY_FULL}", False),
                               (40, f"40/{ACTIVITY_FULL}", True),
                               (None, f"{NO_DATA}/{ACTIVITY_FULL}", False)):
        got = _readings(_snapshot(day_point=point), now)["activity"]
        if got != (want, alert):
            failures.append(
                f"a day_point of {point!r} reads {got!r}, not "
                f"{(want, alert)!r}. The colour is the whole of what that "
                f"row says, and a full day drawn red is as wrong as a "
                f"short one drawn plain.")

    # --- passes left today --------------------------------------------
    allowance = excursions.DAILY_PASSES
    for spent, want in ((0, f"{allowance}/{allowance}"),
                        (2, f"{allowance - 2}/{allowance}"),
                        (allowance, f"0/{allowance}"),
                        (None, f"{NO_DATA}/{allowance}")):
        got = _readings(_snapshot(spent=spent), now)["excursions"][0]
        if got != want:
            failures.append(
                f"{spent!r} passes spent reads {got!r}, not {want!r}. The "
                f"reading is the allowance less what was spent, so an "
                f"off-by-one is still a plausible number.")

    # --- the modules, and the nesting ---------------------------------
    # One copy in each of: before today's reset, between the two resets,
    # and after the week's. So `today` is 1 and `week` is 2.
    raw = _snapshot(expiries=(today - HOUR, week - HOUR, week + DAY))
    out = _readings(raw, now)
    if out["modules_today"][0] != "1 expiring today!":
        failures.append(
            f"the module row for today reads "
            f"{out['modules_today'][0]!r}, not '1 expiring today!'. One "
            f"of the three copies falls before {today}.")
    if out["modules_week"][0] != "2 expiring this week":
        failures.append(
            f"the module row for the week reads "
            f"{out['modules_week'][0]!r}, not '2 expiring this week'. The "
            f"windows NEST -- a copy expiring before today's reset also "
            f"expires before the week's -- so the week's count includes "
            f"the day's.")
    if not out["modules_today"][1]:
        failures.append(
            "a copy expiring today is not drawn in the alert colour. The "
            "row's own words end in an exclamation mark; without the "
            "colour it reads like every other row.")

    # A copy landing exactly ON a deadline is inside it: the reset is
    # when the item stops being spendable, not the last moment it is.
    out = _readings(_snapshot(expiries=(today,)), now)
    if out["modules_today"][0] != "1 expiring today!":
        failures.append(
            f"a copy expiring exactly at the daily reset reads "
            f"{out['modules_today'][0]!r}. It expires AT the deadline, so "
            f"it is inside the window, not past it.")

    # Nothing held is 0 in both rows, and neither is coloured.
    out = _readings(_snapshot(), now)
    if (out["modules_today"] != ("0 expiring today!", False)
            or out["modules_week"] != ("0 expiring this week", False)):
        failures.append(
            f"with no modules held the two rows read "
            f"{out['modules_today']!r} and {out['modules_week']!r}, not "
            f"zero and unalerted.")

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
