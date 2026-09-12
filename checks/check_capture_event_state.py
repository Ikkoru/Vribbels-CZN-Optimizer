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
