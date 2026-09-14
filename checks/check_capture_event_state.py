"""Two event records that only ever arrive whole, merged row by row.

`attendance_entities` and `event_mission_reward_entities` have both
been seen ONLY in the login burst, as a full list. So a reader that
assigns the list wholesale looks right on every capture ever taken --
and is wrong the first time a claim answers with just the row it
changed, which is what a claim does everywhere else on this wire.

That failure is silent in the worst way: a Daily Check-in claim would
leave the Checklist reading yesterday's count until the next login, and
an event's completion flag would arrive as a one-row list that wiped
every other event's.

The second half is the completion flag itself. `event_achieve_state`
is the only thing on the wire that says an event is FINISHED rather
than how much of it has been handed out, so it has to reach the
snapshot -- a field the addon drops is invisible to every check that
reads snapshots, because none of them will ever see it.

No Tk and no snapshot needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "event state merges row by row"

# One login's worth, trimmed to what the readers use. Two streaks and
# two completion records, so a one-row follow-up has something to lose.
LOGIN = {
    "res": "ok",
    "attendance_entities": [
        {"event_id": "event_1", "start_time": 100, "received_days": 7},
        {"event_id": "event_143", "start_time": 200, "received_days": 3},
    ],
    "event_mission_reward_entities": [
        {"res_id": "event_stock_1", "event_achieve_state": 1,
         "reward_step": 0, "version": 0},
        {"res_id": "event_bartender_1", "event_achieve_state": 0,
         "reward_step": 3, "version": 2},
    ],
}


class _Message:
    def __init__(self, payload, from_client=False):
        self.from_client = from_client
        self.is_text = True
        self.text = json.dumps(payload)
        self.content = self.text.encode()


class _Flow:
    def __init__(self, payload, from_client=False):
        self.websocket = type(
            "W", (), {"messages": [_Message(payload, from_client)]})()


def _rows(addon, field):
    """What `field` would be written to a snapshot, keyed by its id."""
    key = "event_id" if field == "attendance_entities" else "res_id"
    store = (addon.attendance if field == "attendance_entities"
             else addon.event_rewards)
    return {str(row[key]): row for row in store.values()}


def run():
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     ITEM_NAMES={}, KNOWN_UNIT_IDS=set(), REGION_ROUTES={})
    Addon = namespace["Addon"]

    failures = []
    addon = Addon(Path(tempfile.mkdtemp()), log_callback=lambda *a, **k: None)
    addon.websocket_message(_Flow([LOGIN]))

    for field, count in (("attendance_entities", 2),
                         ("event_mission_reward_entities", 2)):
        held = _rows(addon, field)
        if len(held) != count:
            failures.append(
                f"after a login carrying {count} {field} rows the addon "
                f"holds {len(held)}. The login list is where both of these "
                f"start; nothing else sends them in full.")

    # --- the shapes a claim could answer in -------------------------
    # Four are accepted: the plural list, a `result_`-prefixed list
    # (which is how an Overclock run answers), a bare singular record,
    # and -- the one a capture has since caught -- a bare `entity`.
    # Whichever a given claim uses, the row lands.
    claims = (
        ("attendance_entities",
         {"attendance_entities": [
             {"event_id": "event_143", "start_time": 200,
              "received_days": 4}]}),
        ("result_attendance_entities",
         {"result_attendance_entities": [
             {"event_id": "event_143", "start_time": 200,
              "received_days": 5}]}),
        ("attendance_entity",
         {"attendance_entity": {"event_id": "event_143", "start_time": 200,
                                "received_days": 6}}),
    )
    for at, (shape, payload) in enumerate(claims, start=4):
        addon.websocket_message(_Flow([dict(payload, res="ok")]))
        held = _rows(addon, "attendance_entities")
        if held.get("event_143", {}).get("received_days") != at:
            failures.append(
                f"a claim answering under {shape!r} left event_143 at "
                f"{held.get('event_143', {}).get('received_days')!r}, not "
                f"{at}. The Checklist then shows the streak it had at "
                f"login until the next one.")
        if "event_1" not in held:
            failures.append(
                f"a one-row {shape!r} payload REPLACED the whole streak "
                f"list -- event_1 is gone. A partial list has to merge by "
                f"event, or a claim wipes every other row.")
            return failures

    # --- the completion flag, the same three ways -------------------
    for shape, payload, want in (
        ("event_mission_reward_entities",
         {"event_mission_reward_entities": [
             {"res_id": "event_bartender_1", "event_achieve_state": 1}]}, 1),
        ("event_mission_reward_entity",
         {"event_mission_reward_entity":
          {"res_id": "event_bartender_1", "event_achieve_state": 0}}, 0),
        ("result_event_mission_reward_entities",
         {"result_event_mission_reward_entities": [
             {"res_id": "event_bartender_1", "event_achieve_state": 1}]}, 1),
    ):
        addon.websocket_message(_Flow([dict(payload, res="ok")]))
        held = _rows(addon, "event_mission_reward_entities")
        got = held.get("event_bartender_1", {}).get("event_achieve_state")
        if got != want:
            failures.append(
                f"a completion record arriving under {shape!r} left the "
                f"Bartender at {got!r}, not {want!r}.")
        if "event_stock_1" not in held:
            failures.append(
                f"a one-row {shape!r} payload replaced every other event's "
                f"completion record.")
            return failures

    # --- the shape a Daily Check-in claim REALLY answers in ----------
    # It carries no record at all: the event, the streak before, the
    # streak after and whether that finished it. Captured from
    # `websocket_debug_20260913_202036.jsonl`, qid 39.
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 39, "completed": True, "event_id": "event_143",
        "message": "", "received_days_before": 6, "received_days_after": 7,
        "reward_list": [{"count": 3, "res_id": 2000023}],
    }]))
    held = _rows(addon, "attendance_entities")
    if held.get("event_143", {}).get("received_days") != 7:
        failures.append(
            f"the real claim reply left event_143 at "
            f"{held.get('event_143', {}).get('received_days')!r}, not 7. It "
            f"names no entity, so the cached row has to be patched from "
            f"`received_days_after` or the streak never moves until the "
            f"next login.")
    if held.get("event_1", {}).get("received_days") != 7:
        failures.append(
            "claiming one streak's reward changed another streak's row.")

    # --- a doubled Simulation run's row arrives NESTED ---------------
    # Under the stage reply's `return_info`, not at the top level --
    # which is why the Overclock row sat at its login value all session
    # while the doubled rewards paid out beside it. Shape from the same
    # capture, qid 58.
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 9,
        "overclock_entities": {"event_overclock_live_13": {
            "res_id": "event_overclock_live_13", "count": 2,
            "reset_time": 1789236863, "total_count": 10}}}]))
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 58, "return_info": {
            "result_reward_drop_overclock": {"currency": {}},
            "result_overclock_entities": [{
                "res_id": "event_overclock_live_13", "count": 1,
                "reset_time": 1789327354, "total_count": 11}]}}]))
    row = (addon.overclock or {}).get("event_overclock_live_13") or {}
    if (row.get("count"), row.get("total_count")) != (1, 11):
        failures.append(
            f"after a doubled run the Overclock row reads count="
            f"{row.get('count')!r} total={row.get('total_count')!r}, not "
            f"1 and 11. `result_overclock_entities` rides under "
            f"`return_info`, and read only at the top level it never "
            f"arrives -- the row keeps the login's tally all session.")

    # --- an event reward claim answers under a BARE `entities` -------
    # Not `mission_entities`, not `event_mission_entities`. Without it
    # a reward claimed during the session reads unclaimed, and a row
    # the claim issued is missing from the denominator as well.
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 91, "entities": [
            {"res_id": "event_bartender_1_01_04", "complete_time": 1789328267,
             "issued_time": 1789328079, "score": 1, "version": 1}]}]))
    if addon.missions.get("event_bartender_1_01_04", {}).get(
            "complete_time") != 1789328267:
        failures.append(
            "an event reward claim's own row did not reach the mission "
            "cache. It arrives under the bare key `entities`, so a handler "
            "watching only `mission_entities` leaves the Checklist showing "
            "the tally it had at login.")

    # **`entities` is not always missions.** The Full-Scale Offensive's
    # board arrives under the same key, as a dict keyed by `list_id`.
    # Taking that as missions would put three boss rows into the tally
    # every event row is counted from.
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 48, "entities": {
            "remnants_boss_s05_01": {"list_id": "remnants_boss_s05_01",
                                     "star_count": 3, "best_score": 1130418}}}]))
    if any(str(key).startswith("remnants") for key in addon.missions):
        failures.append(
            "the Full-Scale Offensive board was merged into the mission "
            "cache. It shares the key `entities` with a reward claim and "
            "is a dict of `list_id` rows, so the guard is a LIST of rows "
            "carrying `res_id` and `complete_time`.")

    # --- the SINGULAR of a collection is the row that changed --------
    # Finishing a summer puzzle answers with `event_summer_set_entity`,
    # one row, under its own key rather than inside the plural the
    # login sends. Read only in the plural, the set's `complete_time`
    # stays 0 until the next login -- the snapshot then shows an
    # unfinished puzzle beside the reward it has just paid for.
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 35,
        "event_summer_set_entities": {
            "event_summer_01_01": {"res_id": "event_summer_01_01",
                                   "complete_time": 1786910660},
            "event_summer_01_03": {"res_id": "event_summer_01_03",
                                   "complete_time": 0}}}]))
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 43,
        "event_summer_set_entity": {"res_id": "event_summer_01_03",
                                    "complete_time": 1789347146}}]))
    sets = addon.event_defines.get("event_summer_set_entities") or {}
    if sets.get("event_summer_01_03", {}).get("complete_time") != 1789347146:
        failures.append(
            f"the finished set reads "
            f"{sets.get('event_summer_01_03', {}).get('complete_time')!r}, "
            f"not 1789347146. A one-row reply arrives under the SINGULAR "
            f"key and has to be folded into the collection the login "
            f"sends.")
    if sets.get("event_summer_01_01", {}).get("complete_time") != 1786910660:
        failures.append(
            "folding in the one changed set lost the others.")
    stray = [key for key in addon.event_defines if key.endswith("_entity")
             and key.endswith("_set_entity")]
    if stray:
        failures.append(
            f"the singular key {stray!r} was kept as well. It is the same "
            f"collection under another name, and a second copy is one more "
            f"thing for a reader to pick the wrong one of.")

    # --- the completion flag's REAL shape: a bare `entity` ----------
    # `mission / reward_event_limit` -- the claim of the final reward
    # that unlocks only after every other -- answers under `entity`,
    # the same key a Combatant Trial claim uses for a different row.
    # Captured from `websocket_debug_20260914_195103.jsonl`, qid 100.
    #
    # Put back to UNFINISHED first, which is what the cases above left
    # it at the end of: without that this reads 1 whatever the addon
    # does with `entity`, and the case cannot fail.
    addon.websocket_message(_Flow([{
        "res": "ok", "event_mission_reward_entities": [
            {"res_id": "event_bartender_1", "event_achieve_state": 0}]}]))
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 100,
        "item_result": {"items": {"9700001": {
            "doc": {"res_id": 9700001, "amount": 1}, "diff": 1}}},
        "entity": {"user_id": 1, "res_id": "event_bartender_1",
                   "event_achieve_state": 1},
    }]))
    held = _rows(addon, "event_mission_reward_entities")
    if held.get("event_bartender_1", {}).get("event_achieve_state") != 1:
        failures.append(
            f"the real completion reply left the Bartender at "
            f"{held.get('event_bartender_1', {}).get('event_achieve_state')!r}"
            f", not 1. `entity` is the key that claim answers under, and "
            f"dropping it leaves an event the wire has called finished "
            f"reading as a floor for as long as it runs.")
    if "event_stock_1" not in held:
        failures.append(
            "the one-row `entity` reply replaced every other event's "
            "completion record.")

    # **A bare `entity` is not always one of these.** A Combatant Trial
    # claim answers under the same key with a different row, and taking
    # it would put a trial slot in the completion table under whatever
    # id it happens to carry. The flag is what tells them apart.
    before = set(_rows(addon, "event_mission_reward_entities"))
    addon.websocket_message(_Flow([{
        "res": "ok", "qid": 101,
        "entity": {"res_id": "not_an_event",
                   "event_combatant_trial_slot_id": "slot_1"},
    }]))
    stray = set(_rows(addon, "event_mission_reward_entities")) - before
    if stray:
        failures.append(
            f"a trial claim's `entity` landed in the completion table as "
            f"{sorted(stray)!r}. Only a row carrying `event_achieve_state` "
            f"belongs there.")

    # --- `completed` survives the login that follows ----------------
    # It is the only thing that says a streak has ENDED rather than
    # been claimed for today: streak lengths vary by event -- one
    # account's history holds runs of 7, 10, 14 and 21 days -- and a
    # finished record is identical to a claimed-today one.
    addon.websocket_message(_Flow([{
        "res": "ok", "attendance_entities": [
            {"event_id": "event_143", "start_time": 200,
             "current_days": 7, "received_days": 7}]}]))
    held = _rows(addon, "attendance_entities")
    if not held.get("event_143", {}).get("completed"):
        failures.append(
            "the login after a streak finished dropped `completed`. The "
            "row it sends is identical to a streak claimed for today, so "
            "letting it win loses the only answer there is -- and the "
            "next login sends the same row again.")

    # --- what the monthly pass expires at ---------------------------
    # `issued_limit_entities` rides the login burst beside the stage
    # limits. `subscription_1.expire_time` is the only thing on the
    # wire that says how long the daily gift keeps coming.
    addon.websocket_message(_Flow([{
        "res": "ok", "issued_limit_entities": {"subscription_1": {
            "res_id": "subscription_1", "expire_time": 1797962400,
            "count": 14, "vi1": 1353}}}]))
    if (addon.issued_limits.get("subscription_1") or {}).get(
            "expire_time") != 1797962400:
        failures.append(
            "the login's `issued_limit_entities` did not reach the addon. "
            "Nothing else on the wire dates the monthly pass.")

    # --- and both reach the snapshot as LISTS -----------------------
    # The shape the wire uses and the shape every snapshot on disk
    # already carries, so `_event_finished` and `_event_attendance`
    # read old captures and new ones the same way.
    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    # **Each in the shape the WIRE sends it in**, which is what lets
    # the readers treat an old capture and a new one the same way: the
    # two event records as lists, the limit tables keyed by res_id.
    for field, shape in (("attendance_entities", list),
                         ("event_mission_reward_entities", list),
                         ("issued_limit_entities", dict)):
        rows = saved.get(field)
        if not isinstance(rows, shape) or not rows:
            failures.append(
                f"a saved snapshot's {field} is {rows!r}, not a "
                f"{shape.__name__} with rows in it. A field the addon "
                f"never writes is invisible to everything downstream.")
    return failures
