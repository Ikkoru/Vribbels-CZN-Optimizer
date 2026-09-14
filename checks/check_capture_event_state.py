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
    # No capture has ever caught one, so all three are accepted: the
    # plural list, a `result_`-prefixed list (which is how an Overclock
    # run answers) and a bare singular record (which is how a Bartender
    # story answers). Whichever it turns out to be, the row lands.
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
        "res": "ok", "qid": 39, "completed": False, "event_id": "event_143",
        "message": "", "received_days_before": 6, "received_days_after": 7,
        "reward_list": [{"count": 1, "res_id": 2000023}],
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

    # --- and both reach the snapshot as LISTS -----------------------
    # The shape the wire uses and the shape every snapshot on disk
    # already carries, so `_event_finished` and `_event_attendance`
    # read old captures and new ones the same way.
    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    for field in ("attendance_entities", "event_mission_reward_entities"):
        rows = saved.get(field)
        if not isinstance(rows, list) or not rows:
            failures.append(
                f"a saved snapshot's {field} is {rows!r}. The Checklist "
                f"reads a list of rows; a field the addon never writes is "
                f"invisible to everything downstream.")
    return failures
