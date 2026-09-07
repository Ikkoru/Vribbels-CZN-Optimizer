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

from ._harness import add_source_to_path

NAME = "checklist readings"

# Any moment will do -- the module windows roll from `now` -- but a
# stated one keeps the cases readable. A Monday 10:00 UTC.
MONDAY_MORNING = 1789380000
HOUR = 3600
DAY = 24 * HOUR


def _snapshot(amounts=(), expiries=(), day_point=None, spent=None,
              coffee=None, rift=()):
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
    if day_point is not None:
        raw["point_entity"] = {"day_point": day_point}
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
    from ui.tabs.checklist_tab import (
        ACTIVITY_FULL, CHAOS_CURRENCY, COFFEE_DONE, COFFEE_TODO,
        columns_for,
        ACTIVITY_CLAIMED, ACTIVITY_UNCLAIMED,
        DELEGATION_CURRENCY, DELEGATION_DONE, DELEGATION_TODO,
        PASS_DAILY_COUNT,
        _last_daily_reset,
        DONE, GREAT_RIFT_OVER, GREAT_RIFT_TARGET, MODULE_ITEM,
        MODULE_WINDOWS, NO_DATA,
        SORTIE_CAP, SORTIE_CURRENCY, TODO, UNKNOWN, _readings,
    )

    failures = []
    now = MONDAY_MORNING

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
    # **A full day is not a claimed day.** `day_point` reads 100 the
    # moment the last activity lands, and the rewards sit there
    # unclaimed -- so the row stays red until the claim is seen.
    full = f"{ACTIVITY_FULL}/{ACTIVITY_FULL}{ACTIVITY_UNCLAIMED}"
    for point, want, state in ((ACTIVITY_FULL, full, TODO),
                               (40, f"40/{ACTIVITY_FULL}"
                                f"{ACTIVITY_UNCLAIMED}", TODO),
                               (None, f"{NO_DATA}/{ACTIVITY_FULL}", UNKNOWN)):
        got = _readings(_snapshot(day_point=point), now)["activity"]
        if got != (want, state):
            failures.append(
                f"a day_point of {point!r} reads {got!r}, not "
                f"{(want, state)!r}. A full day whose rewards are still "
                f"sitting there is work left, not work done.")
    got = _readings(_snapshot(day_point=ACTIVITY_FULL), now,
                    claimed=True)["activity"]
    if got != (ACTIVITY_CLAIMED, DONE):
        failures.append(
            f"a claimed day reads {got!r}, not "
            f"({ACTIVITY_CLAIMED!r}, {DONE!r}).")

    # --- today's coffee, which INVERTS the field it reads --------------
    for possible, want, state in ((True, COFFEE_TODO, TODO),
                                  (False, COFFEE_DONE, DONE),
                                  (None, NO_DATA, UNKNOWN)):
        got = _readings(_snapshot(coffee=possible), now)["coffee"]
        if got != (want, state):
            failures.append(
                f"is_coffee_possible={possible!r} reads {got!r}, not "
                f"{(want, state)!r}. The field is a CAPABILITY: true "
                f"means the coffee is still there to drink, so the row "
                f"says the opposite of what the field does.")

    # --- the Great Rift, and picking the LIVE season ------------------
    # Two seasons, the older carrying the higher score and a higher
    # threshold. The live one is the later WEEK, not the bigger number.
    rift = ((180, 999999, 500000), (193, 120000, 300000))
    got = _readings(_snapshot(rift=rift), now)["seasonal_score"]
    if got != ("120000/300000", TODO):
        failures.append(
            f"the Great Rift row reads {got!r}, not "
            f"('120000/300000', {TODO!r}). Past seasons keep their rows "
            f"and carry higher totals AND different thresholds, so the "
            f"live one is the latest score_week_id.")
    # Over the threshold, the display caps AND says it capped.
    got = _readings(_snapshot(rift=((193, 1396064, 300000),)),
                    now)["seasonal_score"]
    if got != (f"300000{GREAT_RIFT_OVER}/300000", DONE):
        failures.append(
            f"a score past the threshold reads {got!r}, not "
            f"('300000{GREAT_RIFT_OVER}/300000', {DONE!r}). The figure "
            f"runs to seven digits and the row is about clearing the "
            f"threshold, so it caps -- and the sign is what stops a "
            f"capped reading looking like one that landed on the bar.")
    # Landing EXACTLY on it takes no sign, and is still done.
    got = _readings(_snapshot(rift=((193, 300000, 300000),)),
                    now)["seasonal_score"]
    if got != ("300000/300000", DONE):
        failures.append(
            f"a score exactly on the threshold reads {got!r}, not "
            f"('300000/300000', {DONE!r}). Nothing is over, so nothing "
            f"is capped.")
    got = _readings(_snapshot(), now)["seasonal_score"]
    if got != (f"{NO_DATA}/{GREAT_RIFT_TARGET}", UNKNOWN):
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
        got, state = _readings(_snapshot(spent=spent), now)["excursions"]
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
    if out["modules_soon"] != ("1 expiring within 6h!", TODO):
        failures.append(
            f"the tight module row reads {out['modules_soon']!r}, not "
            f"('1 expiring within 6h!', {TODO!r}). The window bounds what "
            f"is COUNTED; the words say how long the last of them has.")
    if out["modules_week"] != ("2 expiring within 3 days", TODO):
        failures.append(
            f"the wide module row reads {out['modules_week']!r}, not "
            f"('2 expiring within 3 days', {TODO!r}). The windows NEST -- "
            f"a copy inside 24 hours is inside seven days -- so the wider "
            f"count includes the tighter one, and its number is the "
            f"furthest out of the two.")

    # Rounded UP, so a copy is never promised time it has spent.
    out = _readings(_snapshot(expiries=(now + 90 * 60,)), now)
    if out["modules_soon"][0] != "1 expiring within 2h!":
        failures.append(
            f"a copy 90 minutes out reads {out['modules_soon'][0]!r}, not "
            f"'1 expiring within 2h!'. Rounding down promises an hour "
            f"that is already spent.")

    # A copy landing exactly ON a boundary is inside it.
    out = _readings(_snapshot(expiries=(soon,)), now)
    if out["modules_soon"][0] != "1 expiring within 24h!":
        failures.append(
            f"a copy expiring exactly 24 hours out reads "
            f"{out['modules_soon'][0]!r}. `within` includes the boundary.")

    # Nothing held: the window's own bound stands in for a longest that
    # does not exist, and both rows are GREEN -- there is nothing to use.
    out = _readings(_snapshot(), now)
    if (out["modules_soon"] != ("0 expiring within 24h!", DONE)
            or out["modules_week"] != ("0 expiring within 7 days", DONE)):
        failures.append(
            f"with no modules held the two rows read "
            f"{out['modules_soon']!r} and {out['modules_week']!r}, not "
            f"zero against the window's own bound, in green.")

    # --- today's Chaos Delegation ------------------------------------
    # No balance to read: the free entry is granted and spent in one
    # transaction, so `amount` is 0 either way and `last_update` is
    # what says whether it went today.
    reset = _last_daily_reset(now)
    for stamp, want, state in ((reset + HOUR, DELEGATION_DONE, DONE),
                               (reset - HOUR, DELEGATION_TODO, TODO),
                               (None, NO_DATA, UNKNOWN)):
        raw = _snapshot()
        if stamp is not None:
            raw.setdefault("characters", {})["currencies"] = {
                str(DELEGATION_CURRENCY): {"last_update": int(stamp)}}
        got = _readings(raw, now)["chaos_delegation"]
        if got != (want, state):
            failures.append(
                f"a delegation stamp of {stamp!r} against a reset of "
                f"{reset!r} reads {got!r}, not {(want, state)!r}. The "
                f"row is whether the currency moved since the day's own "
                f"18:00 UTC boundary.")
    # Exactly ON the boundary counts as today: the reset is when the
    # day begins, not the last moment of the one before.
    raw = _snapshot()
    raw.setdefault("characters", {})["currencies"] = {
        str(DELEGATION_CURRENCY): {"last_update": int(reset)}}
    if _readings(raw, now)["chaos_delegation"] != (DELEGATION_DONE, DONE):
        failures.append(
            "a delegation used exactly at the reset reads as not used. "
            "The reset opens the day it belongs to.")

    # --- the Arkhianon Supply, three ways -----------------------------
    # A DAILY mission is one the pass ISSUED since the day's reset --
    # there is no id list, and one would not survive the season number
    # changing. The denominator is stated: the game issues a mission
    # lazily, so counting the issued rows understates the day.
    reset = _last_daily_reset(now)
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
    if got != (f"1/{PASS_DAILY_COUNT}", TODO):
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
        {"res_id": "season_pass_006", "week_id": 182, "week_exp": 10000,
         "free_reward_rank": 70},
        {"res_id": "season_pass_008", "week_id": 193, "week_exp": 6500,
         "free_reward_rank": 46},
    ]
    for key, want in (("supply_weekly", ("6500/10000", TODO)),
                      ("supply_season", ("46/70", TODO))):
        got = _readings(raw, now)[key]
        if got != want:
            failures.append(
                f"{key} reads {got!r}, not {want!r}. A finished past pass "
                f"is in the same list and sits at its full figure.")
    # The singular field wins where a claim has just sent it.
    raw["season_pass_entity"] = {"week_id": 193, "week_exp": 8000,
                                 "free_reward_rank": 50}
    if _readings(raw, now)["supply_weekly"] != ("8000/10000", TODO):
        failures.append(
            "the singular `season_pass_entity` does not win over the "
            "login's list. A claim sends the one live pass under it, "
            "and that is the fresher reading.")

    # --- the Basin, and which season it reports --------------------
    # Two seasons at once and one figure on screen, so the row takes
    # the LEAST complete: a fresh season beside a finished one is work
    # left, and reporting the finished one would hide it.
    def basin(*seasons):
        raw = _snapshot()
        raw["mission_seasson_entities"] = {
            f"hyperspace_02_{i}": {
                f"content_{i}_{n:02d}": {"score": 1 if n <= done else 0}
                for n in range(1, total + 1)}
            for i, (done, total) in enumerate(seasons)}
        return _readings(raw, now)["basin"]

    got = basin((26, 26))
    if got != ("26/26", DONE):
        failures.append(
            f"a finished Basin season reads {got!r}, not ('26/26', "
            f"{DONE!r}). A scored objective is a done one.")
    got = basin((26, 26), (3, 26))
    if got != ("3/26", TODO):
        failures.append(
            f"with a finished season beside a fresh one the Basin reads "
            f"{got!r}, not ('3/26', {TODO!r}). The row takes the LEAST "
            f"complete, or the season with work left disappears behind "
            f"the one without.")
    got = _readings(_snapshot(), now)["basin"]
    if got != (NO_DATA, UNKNOWN):
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
            "limit_count": cap, "limit_type": limit_type, "sort": 5}}}
        raw["shop_list"] = {product: {"count": count, "reset_time": touched,
                                      "total_count": 5}}
        if month is not None:
            raw["month_start"] = month
        return _readings(raw, now)[key]

    got = shop(0, int(started) + HOUR)
    if got != (f"{cap}/{cap}", TODO):
        failures.append(
            f"a shop row with nothing bought this period reads {got!r}, "
            f"not {cap}/{cap} in red. `count` is the purchases MADE, so "
            f"what is left is the cap less it.")
    got = shop(cap, int(started) + HOUR)
    if got != (f"0/{cap}", DONE):
        failures.append(
            f"a shop row bought out reads {got!r}, not 0 in green.")

    # **The stale tally.** `count` is reset LAZILY -- a row nobody has
    # bought from since the period rolled still carries the previous
    # period's number. Read straight it draws a refilled shop as empty,
    # which is what put 0/20 on a full shelf.
    got = shop(cap, int(started) - HOUR)
    if got != (f"{cap}/{cap}", TODO):
        failures.append(
            f"a row last touched BEFORE the period began reads {got!r}, "
            f"not {cap}/{cap}. Its tally is last period's, so nothing "
            f"has been bought since the shelf refilled.")

    # No `shop_list` AT ALL is a dash: the field never arrived.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {product: {
        "product_link_item_id": 3310006, "product_count": 1,
        "limit_count": cap, "limit_type": "LIMIT_WEEK", "sort": 5}}}
    got = _readings(raw, now)[key]
    if got != (f"{NO_DATA}/{cap}", UNKNOWN):
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
    if got != (f"{cap}/{cap}", TODO):
        failures.append(
            f"a product absent from a shop_list that DID arrive reads "
            f"{got!r}, not {cap}/{cap}. No row means nothing bought.")

    # A MONTHLY product has no boundary without the wire's own
    # `month_start`, so it reads a dash rather than guessing one.
    got = shop(1, now, "LIMIT_MONTH")
    if got != (f"{NO_DATA}/{cap}", UNKNOWN):
        failures.append(
            f"a monthly row with no `month_start` reads {got!r}, not a "
            f"dash. The month rolls at 18:00 UTC on the LAST day, so "
            f"there is no boundary to compute without the wire saying.")
    got = shop(1, now, "LIMIT_MONTH", month=int(now - DAY))
    if got != (f"0/{cap}", DONE):
        failures.append(
            f"a monthly row with `month_start` reads {got!r}, not 0/{cap}.")

    # A product with NO cap is not a row at all: nothing counts down.
    raw = _snapshot()
    raw["shop_res_data"] = {"shop_town": {"town_shop_goods_010": {
        "product_link_item_id": 2000001, "product_count": 4000,
        "limit_count": -1, "limit_type": "NONE", "sort": 14}}}
    if any(key.startswith("shop:") for _t, rows in columns_for(raw)
           for key, _l, _w in rows):
        failures.append(
            "an uncapped product got a Checklist row. There is nothing "
            "to count down and nothing to finish, so it is not a "
            "checklist entry.")

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
