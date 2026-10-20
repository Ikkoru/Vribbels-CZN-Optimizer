"""A story-chapter event's progress: the chapter's episodes cleared.

Such an event -- a Galactic Disaster's prologue, `event_disaster_s05_c0`
-- pays as each episode is cleared and has nothing to claim, so every
reward-counting reader finds nothing and the row shows a deadline only.
Its progress is three things meeting, and each fails quietly:

* **the client's chapter**, `game_client.story_chapters`: the event's
  row names the chapter, the chapter its node key, the key its
  episodes. A node marked `no_use` counted would hold the row short of
  100% for good;
* **the capture's list**, which the login sends under the bare key
  `ids` -- taken only on the reply to the command that asks for it,
  since `ids` is far too generic to trust -- plus each clear after it;
* **the reading**, a percentage rounded DOWN, green at 100% only, and
  nothing at all where a snapshot predates the list: no list is not
  "nothing cleared".

`docs/events.md`, *Story chapters*, has the evidence. No Tk, no
snapshot and no game client needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "story-chapter events"

NOW = 1790800000
EVENT = "event_disaster_s05_c0"
EPISODES = tuple("story_node_01_18_%d" % n for n in range(1, 8))


class _FakeClient:
    """Just enough of `game_client.Client` for `story_chapters`."""

    def __init__(self, tables):
        self.tables = tables

    def rows(self, name):
        return self.tables.get(name, [])


def _client(gc):
    """A client holding the prologue, a main-story chapter that is not
    an event, and a deleted story event over a live one's schedule."""
    nodes = [{"id": episode, "no_use": ""} for episode in EPISODES]
    nodes += [{"id": "story_node_01_18_8", "no_use": "YES"},
              {"id": "story_node_01_01_1", "no_use": "NO"}]
    return _FakeClient({
        gc.STORY_NODE_TABLE: nodes,
        gc.STORY_CHAPTER_TABLE: [
            {"id": "disaster_s05_00",
             "link_story_map_node_key": "story_node_01_18"},
            {"id": "story_chapter_1_01",
             "link_story_map_node_key": "story_node_01_01"},
        ],
        gc.EVENT_TABLE: [
            {"id": "event_149", "type": gc.STORY_EVENT_TYPE,
             "delete_flag": "NO", "multiple_link": "disaster_s05_00",
             "link_event_schedule_id": EVENT},
            {"id": "event_150", "type": "EVENT_DAILY_CHECK",
             "delete_flag": "NO", "multiple_link": "story_chapter_1_01",
             "link_event_schedule_id": "event_not_a_story"},
        ],
    })


def _client_chapters(gc):
    failures = []
    got = gc.story_chapters(_client(gc))
    if got != {EVENT: list(EPISODES)}:
        failures.append(
            f"game_client.story_chapters read {got!r}, not the prologue's "
            f"seven episodes under {EVENT!r} alone. A node marked no_use "
            f"counted holds the row short of 100% for good; an event of "
            f"another type listed gives a login streak a percentage.")
    return failures


def _reading(ct, cleared, *, listed=True):
    raw = {"event_schedules": {"EVENT_SCHEDULE": {EVENT: {
        "schedule_id": EVENT, "start_time": NOW - 86400,
        "end_time": NOW + 86400}}},
        "mission_entities": {}}
    if listed:
        raw[ct.EPISODES_FIELD] = list(EPISODES[:cleared]) + [
            "battle_node_01_01_1"]
    ct.event_totals_onto(raw, NOW, {}, {EVENT: EPISODES})
    window = raw["event_schedules"]["EVENT_SCHEDULE"][EVENT]
    return list(ct.EVENT_READERS["EVENT_SCHEDULE"](raw, EVENT, window, NOW))


def _readings(ct):
    failures = []
    for cleared, want in ((0, [("0%", ct.TODO)]), (2, [("28%", ct.TODO)]),
                          (4, [("57%", ct.TODO)]), (7, [("100%", ct.DONE)])):
        got = _reading(ct, cleared)
        if got != want:
            failures.append(
                f"a story chapter with {cleared} of 7 episodes cleared read "
                f"{got!r}, not {want!r}. The game shows its Progress as the "
                f"episodes cleared, in percent; rounded up, a chapter one "
                f"episode short of a long one would read 100% in green.")
    got = _reading(ct, 0, listed=False)
    if got:
        failures.append(
            f"a snapshot with no episode list read {got!r} for the story "
            f"chapter, where it should show the deadline alone. A snapshot "
            f"taken before the capture kept the list has cleared nothing "
            f"as far as it can say, which is not 0%.")
    return failures


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


def _capture(folder):
    from capture.manager import ADDON_TEMPLATE
    from .check_capture_history import addon_tables
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(addon_tables())
    addon = namespace["Addon"](Path(folder),
                               log_callback=lambda *a, **k: None)

    def ask(qid, inner, **params):
        addon.websocket_message(_Flow([{
            "cmd": "story_system", "qid": qid,
            "params": dict(params, cmd=inner)}], from_client=True))

    failures = []
    # `ids` answering something else is not the list.
    addon.websocket_message(_Flow([{"cmd": "mail", "qid": 9,
                                    "params": {"cmd": "get_list"}}],
                                  from_client=True))
    addon.websocket_message(_Flow([{"res": "ok", "ids": ["mail_1"],
                                    "qid": 9}]))
    if addon.episodes:
        failures.append(
            f"a reply carrying `ids` to another command left the addon "
            f"holding {sorted(addon.episodes)!r} as cleared episodes. The "
            f"key is generic; only the episode list's own command says "
            f"what it is.")
    ask(11, "get_completed_episode_ids")
    addon.websocket_message(_Flow([{"res": "ok", "qid": 11,
                                    "ids": list(EPISODES[:4])}]))
    ask(12, "complete_episode", res_id=EPISODES[4], replay=False)
    addon.websocket_message(_Flow([{"res": "ok", "qid": 12, "result": {
        "res_id": EPISODES[4], "is_clear": True}}]))
    if addon.episodes != set(EPISODES[:5]):
        failures.append(
            f"after the login's list of four and one clear the addon holds "
            f"{sorted(addon.episodes)!r}, not the chapter's first five. "
            f"The Checklist's story-chapter row then reads what the login "
            f"said until the next one.")
    addon.inventory_data = {"items": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    if saved.get("completed_episode_ids") != sorted(EPISODES[:5]):
        failures.append(
            f"the snapshot's completed_episode_ids is "
            f"{saved.get('completed_episode_ids')!r}: the addon kept the "
            f"episodes and the save dropped them, so no reader sees them.")
    return failures


def run():
    add_source_to_path()
    import game_client as gc
    from ui.tabs import checklist_tab as ct

    failures = _client_chapters(gc) + _readings(ct)
    with tempfile.TemporaryDirectory() as folder:
        failures += _capture(folder)
    return failures


FAULTS = [
    ("an unused node counted", "game_client:story_chapters",
     "if (row.get(STORY_NODE_UNUSED[0]) != STORY_NODE_UNUSED[1]\n"
     "                and \"_\" in node):",
     "if \"_\" in node:",
     "no_use counted"),
    ("rounded to nearest", "ui.tabs.checklist_tab:_story_progress",
     "100 * done // len(episodes)", "round(100 * done / len(episodes))",
     "rounded up"),
    ("no list read as none cleared", "ui.tabs.checklist_tab:_story_progress",
     "if not episodes or not isinstance(cleared, list):",
     "cleared = cleared or []\n    if not episodes:",
     "which is not 0%"),
    ("any `ids` taken", "capture.manager:ADDON_TEMPLATE",
     "if (asked == EPISODES_LISTED\n", "if (True\n",
     "only the episode list's own command"),
    ("a clear not added", "capture.manager:ADDON_TEMPLATE",
     "self.episodes.add(str(cleared[\"res_id\"]))", "pass",
     "not the chapter's first five"),
]
