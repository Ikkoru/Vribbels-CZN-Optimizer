"""The Galactic Disaster tab reads its pages right, end to end.

Three parts, each wrong without a sound:

* **The client reader** (`game_client.disaster_challenges`). A meta-
  achievement taken for an ordinary one would be written out as a
  requirement the player has no single thing to do for; a gate read as
  no gate shows a Part 3 achievement as open; a list built off the wrong
  rows puts the wrong items in a tip.
* **The capture** (`Addon._note_challenges`, `Addon._note_event`). The
  login sends the table whole and nothing after it but claims and moved
  scores: a claim or a move not folded in leaves the tab on the login's
  reading all session, and a progress report's `complete_time` of 0
  copied over a claim unclaims it. A run's codex finds not kept leave a
  tip listing what was found an hour ago. An Event's leaving not heard
  leaves its rows lit on the next spot.
* **The model** (`disaster_challenges.board`). What counts as done --
  claimed, a score at its target, or every child of a meta done -- and
  what is locked, by when, decides every number on the tab. A row lit
  off its Event sends the player looking for a button that is not there.

No Tk, no snapshot and no client needed: the cases are synthetic.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "Galactic Disaster challenge pages"

DAY = 24 * 3600
START = 1_800_000_000          # the season's schedule opening
SEASON = "disaster_s09"


# ----------------------------------------------------------- the reader

class _FakeClient:
    """Just enough of `game_client.Client` for `disaster_challenges`."""

    def __init__(self, tables, text):
        self.archive = type("A", (), {"files": {
            f"db/{name}.db": None for name in tables}})()
        self._tables, self._text = tables, text

    def rows(self, name):
        return self._tables[name]

    def text(self):
        return self._text


def _row(rid, page, sort, **extra):
    row = {"id": rid, "main_category": page, "sort": str(sort),
           "achievement_type": "name", "count": "1",
           "desc": f"disaster_achievement@desc@{rid}",
           "schedule_link_condition_schedule_id": "none",
           "link_disaster_achievement_id": "[]", "condition_type": "X",
           "opt_1_multiple_link": "[]",
           "link_disaster_achievement_info_id": "none"}
    row.update(extra)
    return row


def _option(rid, event, order, words):
    """An Event option's row, with its button's `words` in `CLIENT_TEXT`
    under its own id."""
    CLIENT_TEXT[f"encounter_option@simple_flavor_text@{rid}"] = words
    return {"id": rid, "link_encounter_id": event, "order": str(order),
            "simple_flavor_text":
                f"encounter_option@simple_flavor_text@{rid}",
            "success_link_encounter_option_eff_id": f"{rid}_o"}


CLIENT_TEXT = {
    "disaster_achievement@desc@disaster_s09_101":
        "Clear <#6AA5E2>Stage 1</>",
    "disaster_achievement@desc@disaster_s09_203":
        "Obtain legendary equipment Hammer",
    "disaster_achievement@desc@disaster_s09_204":
        "Check [Diary] in Unidentified Area [Long Road] with Nine",
    "char_base@name@1001": "Nine", "char_base@name@1002": "Diary",
    "char_base@name@1003": "Lon",
    "achievement_category_disaster_collection": "Mission Records",
    "monster@name@m1": "Wolf", "monster@name@m2": "Hidden",
    "relic@name@eq_a": "Hammer", "relic@name@eq_b": "Other season's",
    "encounter@name@uk_a": "Long Road", "encounter@name@uk_c": "Elsewhere",
    "moves_1": "Event Encounter: [Into It]",
    "moves_2": "Event Encounter: [Further In]",
}
CLIENT_TABLES = {
    "disaster_achievement(s08)@disaster_achievement": [
        _row("disaster_s08_101", "disaster_collection", 1)],
    "disaster_achievement(s09)@disaster_achievement": [
        _row("disaster_s09_001", "score", 1),
        _row("disaster_s09_126", "internal", 1),
        _row("disaster_s09_101", "disaster_collection", 2),
        _row("disaster_s09_102", "disaster_collection", 1,
             schedule_link_condition_schedule_id="event_disaster_009_chapter_2"),
        _row("disaster_s09_103", "disaster_collection", 3,
             achievement_type="group",
             link_disaster_achievement_id="[disaster_s09_101,disaster_s09_102]",
             count="2"),
        _row("disaster_s09_104", "disaster_collection", 4,
             condition_type="DISASTER_ACHIEVEMENT_CLEAR_ALL__ID",
             opt_1_multiple_link="[disaster_s09_101]"),
        _row("disaster_s09_105", "disaster_battle", 1,
             link_disaster_achievement_info_id="achieve_info_s09_105"),
        _row("disaster_s09_106", "disaster_ingame", 1,
             link_disaster_achievement_info_id="achieve_info_s09_106"),
        _row("disaster_s09_010", "penalty", 1, achievement_type="default",
             schedule_link_condition_schedule_id="event_disaster_009_penalty_2"),
        # Five ways to an Event: an option, a step reached by the second
        # way on, Equipment an option pays, an inspected object, and an
        # Event entered.
        _row("disaster_s09_201", "disaster_ingame", 2,
             condition_type="ENCOUNTER_CHOICE__ID",
             opt_1_multiple_link="[uk_a_s2]"),
        _row("disaster_s09_202", "disaster_ingame", 3,
             condition_type="ENTER_ENCOUNTER__ID",
             opt_1_multiple_link="[uk_a-2]"),
        _row("disaster_s09_203", "disaster_ingame", 4,
             condition_type="GET_EQUIPMENT__ID",
             opt_1_multiple_link="[eq_a]"),
        _row("disaster_s09_204", "disaster_ingame", 5,
             condition_type="ENCOUNTER_CHOICE__ID",
             opt_1_multiple_link="[i_uk_s1]"),
        _row("disaster_s09_205", "disaster_ingame", 6,
             condition_type="ENTER_ENCOUNTER__ID",
             opt_1_multiple_link="[uk_b]"),
    ],
    "encounter(disaster)@encounter": [
        {"id": "uk_a", "name": "encounter@name@uk_a"},
        {"id": "uk_a-1", "name": "encounter@name@uk_a"},
        {"id": "uk_a-2", "name": "encounter@name@uk_a"},
        {"id": "uk_b", "name": "encounter@name@uk_a"},
        {"id": "uk_c", "name": "encounter@name@uk_c"}],
    "encounter(disaster)@encounter_option": [
        _option("uk_a_s4", "uk_a", 4, "Walk on"),
        _option("uk_a_s2", "uk_a", 2, "Threaten them"),
        _option("uk_a_s1", "uk_a", 1, "Go in"),
        _option("uk_a-2_s1", "uk_a-2", 1, "Take it")],
    "encounter(interactor)@encounter_option": [
        {"id": "i_uk_s1", "link_encounter_id": "none", "order": "1",
         "simple_flavor_text": "none",
         "success_link_encounter_option_eff_id": "i_uk_s1_o"}],
    "encounter(disaster)@encounter_option_eff": [
        {"id": "uk_a_s1_o", "overview_eff_desc": "moves_1"},
        {"id": "uk_a_s4_o", "overview_eff_desc": "moves_2"},
        {"id": "uk_a-2_s1_o", "reward1_multiple_link": "get_eq_a"}],
    "encounter_reward(planet)@encounter_reward": [
        {"id": "get_eq_a", "reward_multiple_link": "eq_a"}],
    "event_disaster@event_disaster": [
        {"id": SEASON, "new_link_relic_id": "[eq_a,eq_b]"}],
    # A combatant named in the words, one no player can use, and one
    # whose name is only the start of a word there.
    "char_base@char_base": [
        {"id": "1001", "char_use_playable": "YES"},
        {"id": "1002", "char_use_playable": "NO"},
        {"id": "1003", "char_use_playable": "YES"}],
    "char_base@char_combatant": [
        {"id": "1001"}, {"id": "1002"}, {"id": "1003"}],
    "disaster_achievement(s07)@disaster_achievement": [
        _row("disaster_s07_101", "disaster_collection", 1)],
    "disaster_constant_meta@disaster_constant_meta": [
        {"id": "open_story_3", "value": "42"},
        {"id": "open_penalty_2", "value": "28"}],
    "condition_schedule@condition_schedule": [
        {"id": "event_disaster_009_chapter_2",
         "condition_type": "EVENT_DISASTER_STORY__ID_CHAPTER",
         "opt_2": "[3]", "opt_2_multiple_link": "[]"},
        {"id": "event_disaster_009_penalty_2",
         "condition_type": "EVENT_DISASTER_PENALTY__ID_ID",
         "opt_2": "[]", "opt_2_multiple_link": "[disaster_s09_penalty_02]"}],
    "disaster_achievement_info@disaster_achievement_info": [
        {"id": "achieve_info_s09_105",
         "collection_type": "COLLECTION_TYPE_CHAOS",
         "collection_type_multiple_link": "chaos_14_02",
         "link_extra_tag_id": "none"},
        {"id": "achieve_info_s09_106",
         "collection_type": "COLLECTION_TYPE_CHAOS",
         "collection_type_multiple_link": "chaos_14_01",
         "link_extra_tag_id": "ds09"}],
    "chaos_collection@chaos_collection": [
        {"id": "chaos_14_02", "collection_type": "MONSTER",
         "chaos_multiple_key": "chaos_14_monster"},
        {"id": "chaos_14_01", "collection_type": "RELIC",
         "chaos_multiple_key": "chaos_14_relic"}],
    "chaos_collection_monster@chaos_collection_monster": [
        {"id": "chaos_14_monster_01", "max_count": "4", "hide": "NO",
         "info_desc_2": "monster@name@m1"},
        {"id": "chaos_14_monster_02", "max_count": "1", "hide": "YES",
         "info_desc_2": "monster@name@m2"},
        {"id": "chaos_13_monster_01", "max_count": "1", "hide": "NO",
         "info_desc_2": "monster@name@m3"}],
    "chaos_collection_relic@chaos_collection_relic": [
        {"id": "chaos_14_relic_01", "link_relic_id": "eq_a",
         "info_desc_2": "relic@name@eq_a"},
        {"id": "chaos_14_relic_02", "link_relic_id": "eq_b",
         "info_desc_2": "relic@name@eq_b"}],
    "relic(disaster)@relic": [
        {"id": "eq_a", "link_extra_tag_id": "[ds09]"},
        {"id": "eq_b", "link_extra_tag_id": "[ds08]"}],
}


def _reader_failures():
    import game_client
    out = []
    read = game_client.disaster_challenges(
        _FakeClient(CLIENT_TABLES, CLIENT_TEXT))
    if set(read) != {"disaster_s08", SEASON}:
        out.append(f"the reader kept seasons {sorted(read)}, not the "
                   f"{game_client.CHALLENGE_SEASONS_KEPT} newest by number "
                   f"(disaster_s08 and {SEASON}): the shipped table carries "
                   f"every past season, or loses the live one")
    season = read.get(SEASON) or {}
    by_id = {a["id"]: a for a in season.get("achievements") or ()}
    if "disaster_s09_001" in by_id or "disaster_s09_126" in by_id:
        out.append("the reader kept a Weekly Progress or Display Case row "
                   "as a challenge page's achievement")
    for rid, kind in (("disaster_s09_101", "named"),
                      ("disaster_s09_103", "meta"),
                      ("disaster_s09_104", "meta"),
                      ("disaster_s09_010", "generic")):
        if (by_id.get(rid) or {}).get("kind") != kind:
            out.append(f"{rid} read as {(by_id.get(rid) or {}).get('kind')!r}, "
                       f"not {kind!r}: a meta-achievement taken for an "
                       f"ordinary one is written out as a requirement")
    if (by_id.get("disaster_s09_104") or {}).get("children") \
            != ["disaster_s09_101"]:
        out.append("a clear-all achievement's children were not read off "
                   "its opt_1_multiple_link")
    if (by_id.get("disaster_s09_101") or {}).get("text") != "Clear Stage 1":
        out.append("an achievement's words kept the game's markup")
    gates = season.get("gates") or {}
    if gates != {"event_disaster_009_chapter_2": 42,
                 "event_disaster_009_penalty_2": 28}:
        out.append(f"the gates read as {gates}: a story chapter's opens on "
                   f"its open_story_<n> and a Nebula Distortion boss's on "
                   f"its open_penalty_<n>")
    monsters = ((season.get("lists") or {}).get("achieve_info_s09_105")
                or {}).get("items")
    if monsters != [["chaos_14_monster_01", "Wolf", 4, None]]:
        out.append(f"a codex page's list read as {monsters}: its items are "
                   f"the page key's rows, hidden ones left out, each with "
                   f"its kill count")
    relics = ((season.get("lists") or {}).get("achieve_info_s09_106")
              or {}).get("items")
    if relics != [["chaos_14_relic_01", "Hammer", 1, None]]:
        out.append(f"a tagged list read as {relics}: only the relics "
                   f"carrying the info row's tag belong in it")
    if (season.get("pages") or {}).get("disaster_collection") \
            != "Mission Records":
        out.append("a page's title was not read off the client's text")
    for rid, events, options, why in (
            ("disaster_s09_201", ["uk_a"], ["Threaten them"],
             "an option's row gives its Event and its button's words"),
            ("disaster_s09_202", ["uk_a"], ["Walk on"],
             "step n is reached by the nth option moving the Event on, in "
             "their order, and a step's Event is the one it moves on from"),
            ("disaster_s09_203", ["uk_a"], ["Take it"],
             "Equipment is tied to the options whose effect pays it, through "
             "encounter_reward"),
            ("disaster_s09_204", ["uk_a", "uk_b"], [],
             "an interactor links no Event, so every Event of the name its "
             "words give is its Event"),
            ("disaster_s09_205", ["uk_b"], [],
             "an Event entered has no option to pick")):
        got = by_id.get(rid) or {}
        if (got.get("events"), got.get("options")) != (events, options):
            out.append(f"{rid} read Events {got.get('events')} and options "
                       f"{got.get('options')}, not {events} and {options}: "
                       f"{why}. The row lights on the wrong spot, or names "
                       f"the wrong button")
    if (by_id.get("disaster_s09_203") or {}).get("equipment") != ["Hammer"]:
        out.append(f"the Equipment named by disaster_s09_203 read "
                   f"{(by_id.get('disaster_s09_203') or {}).get('equipment')}: "
                   f"a name in the words stays uncoloured")
    if (by_id.get("disaster_s09_101") or {}).get("events") != []:
        out.append("a row no Event serves reads as served by one")
    named = (by_id.get("disaster_s09_204") or {}).get("combatants")
    if named != ["Nine"]:
        out.append(f"the combatants named by disaster_s09_204 read {named}, "
                   f"not ['Nine']: a name is whole words, and a character no "
                   f"player can use is no combatant to colour")
    return out


def _shipped_failures():
    """Every shipped season's rows reach the tab's Events: a client whose
    tables moved would leave them dark with nothing to say so."""
    from game_data import from_client
    out = []
    held = getattr(from_client, "DISASTER_CHALLENGES", {})
    for season, tables in sorted(held.items()):
        rows = [a for a in tables["achievements"] if a["kind"] == "named"]
        dark = [a["id"] for a in rows if "Unidentified Area [" in a["text"]
                and not a.get("events")]
        if dark:
            out.append(f"{season}'s {dark} name an Unidentified Area and "
                       f"carry no Event: they never light. Is "
                       f"`from_client.py` shipped from the reader that fills "
                       f"`events`? `python docs/client_tables.py --ship`")
        if not any(a.get("options") for a in rows):
            out.append(f"{season} carries no option's words on any row")
        if not any(a.get("equipment") for a in rows):
            out.append(f"{season} carries no Equipment name on any row")
        if not any(a.get("combatants") for a in rows):
            out.append(f"{season} carries no combatant name on any row")
    return out


# ---------------------------------------------------------- the capture

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


def _addon():
    import capture.manager as manager
    from .check_capture_history import addon_tables
    namespace = {}
    exec(compile(manager.ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"),
         namespace)
    namespace.update(addon_tables())
    return namespace["Addon"](Path(tempfile.mkdtemp()),
                              log_callback=lambda *a, **k: None)


def _capture_failures():
    out = []
    addon = _addon()
    send = lambda reply: addon.websocket_message(  # noqa: E731
        _Flow([dict(reply, res="ok")]))
    send({"disaster_achievement_entities": {SEASON: {
        "disaster_s09_101": {"res_id": "disaster_s09_101", "score": 1,
                             "complete_time": 500},
        "disaster_s09_105": {"res_id": "disaster_s09_105", "score": 0,
                             "complete_time": 0}}}})
    held = (addon.disaster_achievements or {}).get(SEASON) or {}
    if set(held) != {"disaster_s09_101", "disaster_s09_105"}:
        out.append(f"after a login carrying two challenge rows the capture "
                   f"holds {sorted(held)}")
    # A progress report: a score moved, `complete_time` 0, the season as
    # `group_id` -- on a row the login had, a claimed one, and a new one.
    send({"mission_condition": {"condition": {"disaster_achievement": [
        {"res_id": "disaster_s09_105", "group_id": SEASON, "score": 1,
         "complete_time": 0},
        {"res_id": "disaster_s09_101", "group_id": SEASON, "score": 1,
         "complete_time": 0},
        {"res_id": "disaster_s09_106", "group_id": SEASON, "score": 1,
         "issued_time": 900, "complete_time": 0}]}}})
    held = (addon.disaster_achievements or {}).get(SEASON) or {}
    if (held.get("disaster_s09_105") or {}).get("score") != 1:
        out.append("a moved score in a reply's mission_condition did not "
                   "reach its row: the tab reads the login's score until the "
                   "next login")
    if "disaster_s09_106" not in held:
        out.append("a row first issued by a move (mission_condition) was "
                   "dropped: an achievement begun in the session stays "
                   "unstarted on the tab")
    if (held.get("disaster_s09_101") or {}).get("complete_time") != 500:
        out.append("a progress report's complete_time of 0 unclaimed a "
                   "claimed row: the tab then shows a reward waiting that "
                   "was taken")
    send({"achievement_entities": [
        {"res_id": "disaster_s09_105", "season_id": SEASON, "score": 1,
         "complete_time": 777}]})
    held = (addon.disaster_achievements or {}).get(SEASON) or {}
    if (held.get("disaster_s09_105") or {}).get("complete_time") != 777:
        out.append("a claim's achievement_entities did not reach its row: "
                   "the reward reads as waiting until the next login")
    # Two Chaos runs, each killing two of one monster: each reply states
    # the run's own count so far, a level or three down, and the reply
    # closing the run states none. The codex then sends both whole.
    send({"chaos_archive_entities": {"chaos_14_02": {
        "res_id": "chaos_14_02",
        "collection": {"chaos_14_monster_01": 1}}}})
    qid = [100]

    def ask(command, reply):
        qid[0] += 1
        cmd, _, inner = command.partition("/")
        addon.websocket_message(_Flow(
            [{"cmd": cmd, "qid": qid[0], "params": {"cmd": inner}}],
            from_client=True))
        send(dict(reply, qid=qid[0]))

    def archive(kills):
        return {"actions": [{"chaos_complete_archive": {
            "monster_resid": {"chaos_14_monster_01": kills},
            "encounter_resid": {}}}],
            "result": {"actions": [{"disaster_complete_archive": {
                "disaster_card_resid": {"disaster_s09_memory_01": 1}}}]}}

    for run in (1, 2):
        ask("disaster/enter_disaster_chaos_stage", {})
        ask("battle/battle_start", archive(1))
        ask("battle/battle_start", archive(2))
        if run == 1:
            ask("stage/clear_stage", {"return_info": {}})
    if (addon.chaos_run_finds.get("chaos_14_monster_01"),
            addon.chaos_run_open.get("chaos_14_monster_01")) != (2, 2):
        out.append(f"after one finished run and one open, each killing two, "
                   f"the capture holds finished {addon.chaos_run_finds} and "
                   f"open {addon.chaos_run_open}: a run's archive counts that "
                   f"run alone, so the finished runs add up and the open "
                   f"one stays apart")
    ask("stage/clear_stage", {"return_info": {}})
    if addon.chaos_run_finds.get("chaos_14_monster_01") != 4 \
            or addon.chaos_run_open:
        out.append(f"two finished runs of two kills each add up to "
                   f"{addon.chaos_run_finds.get('chaos_14_monster_01')}, "
                   f"not 4: the next login's codex counts both")
    if addon.chaos_run_finds.get("disaster_s09_memory_01") != 2:
        out.append("a season collection's finds were not kept with the "
                   "codex's")
    ask("disaster/enter_disaster_chaos_stage", {})
    ask("battle/battle_start", archive(1))
    send({"chaos_archive_entities": {"chaos_14_02": {
        "res_id": "chaos_14_02",
        "collection": {"chaos_14_monster_01": 4}}}})
    if "chaos_14_monster_01" in addon.chaos_run_finds \
            or "disaster_s09_memory_01" not in addon.chaos_run_finds:
        out.append("a whole codex did not replace the finished runs' codex "
                   "finds, or took the season collection's with them")
    if addon.chaos_run_open.get("chaos_14_monster_01") != 1:
        out.append("a whole codex dropped the open run's finds: the codex "
                   "takes a run in only at its end")
    # Stepping on an Event, moving on to its step, leaving it; the
    # marker saying each, and only each, and a fight leaving it standing.
    said = []
    addon.log_callback = lambda line, *a, **k: said.append(line)
    event = lambda name: {"spot_info": {"enc_info": {"id": name}}}  # noqa: E731
    for command, reply, want in (
            ("stage/enter_spot", event("uk_a"), "uk_a"),
            ("encounter/get_info", {"result": {"info": {"id": "uk_a"}}},
             "uk_a"),
            ("encounter/next_encounter", {"result": {"info": {"id": "uk_a-1"}}},
             "uk_a-1"),
            ("battle/battle_start", {}, "uk_a-1"),
            ("encounter/exit_encounter", {"result": {"step": 7}}, None),
            ("stage/enter_spot", {"spot_info": {"spot_type": "BATTLE"}}, None),
            ("encounter/get_info", {"result": {"info": {"id": "uk_b"}}},
             "uk_b"),
            ("stage/clear_stage", {"return_info": {}}, None)):
        ask(command, reply)
        if addon.chaos_event != want:
            out.append(f"after {command} the capture says the player stands "
                       f"on {addon.chaos_event!r}, not {want!r}: the row "
                       f"lights on the wrong spot, or stays lit off it")
    told = [line for line in said if line.startswith("[SYNC] event")]
    if told != ["[SYNC] event uk_a", "[SYNC] event uk_a-1", "[SYNC] event ",
                "[SYNC] event uk_b", "[SYNC] event "]:
        out.append(f"the capture said {told} of those moves: once for each "
                   f"change, or the app is not told, or redraws for nothing")
    addon.log_callback = lambda *a, **k: None
    # Saved and seeded: a capture that starts without a login keeps them.
    addon.inventory_data = {"piece_items": []}
    addon.character_data = {"characters": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    for key in ("disaster_achievement_entities", "chaos_archive_entities",
                "chaos_run_finds"):
        if not saved.get(key):
            out.append(f"the snapshot carries no {key}: the tab reads "
                       f"nothing of it")
    import capture.manager as manager
    from .check_capture_history import addon_tables
    namespace = {}
    exec(compile(manager.ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"),
         namespace)
    namespace.update(addon_tables())
    again = namespace["Addon"](Path(addon.output_dir),
                               log_callback=lambda *a, **k: None)
    if ((again.disaster_achievements or {}).get(SEASON) or {}) != (
            (addon.disaster_achievements or {}).get(SEASON) or {}):
        out.append("a capture's next start did not seed the challenge rows "
                   "from the last snapshot: one written before the login's "
                   "table arrives holds none")
    return out


def _marker_failures():
    """The reader takes the addon's Event marker for the app: consumed,
    with its timing off, and nothing said where nothing moved."""
    from types import SimpleNamespace
    import capture.manager as manager
    held = manager.CaptureManager.__new__(manager.CaptureManager)
    held.chaos_event = None
    moves, shown = [], []
    held.event_update_callback = lambda: moves.append(held.chaos_event)
    held._log_line = lambda line, *a: shown.append(line)
    for name in ("status_callback", "live_update_callback",
                 "gacha_update_callback", "region_callback"):
        setattr(held, name, None)
    held._debug_mode = True
    held.log_callback = lambda *a, **k: None
    held.proxy_process = SimpleNamespace(poll=lambda: 0, stdout=[
        f"{manager.EVENT_MARKER} uk_a{manager.LAG_MARKER}1.0,2.0,3.0]\n",
        f"{manager.EVENT_MARKER} uk_a\n",
        f"{manager.EVENT_MARKER} uk_a-1\n",
        f"{manager.EVENT_MARKER} \n",
        f"{manager.EVENT_MARKER} uk_b\n"])
    held._read_proxy_output()
    out = []
    if moves != ["uk_a", "uk_a-1", None, "uk_b", None]:
        out.append(f"the reader told the app of {moves}: each Event, a "
                   f"leaving as None, and None when the proxy ends. The row "
                   f"stays dark, or stays lit after the capture has stopped")
    if shown:
        out.append(f"the Event marker reached the Capture Log: {shown}")
    return out


# ------------------------------------------------------------ the model

def _achievement(rid, page, kind="named", count=1, gate=None, children=(),
                 listed=None, text=None, events=(), options=(), equipment=(),
                 combatants=()):
    return {"id": rid, "page": page, "sort": 0, "kind": kind, "count": count,
            "text": text or rid, "gate": gate, "children": list(children),
            "list": listed, "events": list(events), "options": list(options),
            "equipment": list(equipment), "combatants": list(combatants)}


CHALLENGES = {SEASON: {
    "pages": {"disaster_collection": "Mission Records"},
    "gates": {"part2": 42, "boss2": 28},
    "achievements": [
        # Mission Records: a score short of its target, one at it, one
        # claimed, a meta whose children are all done (and so a reward
        # waiting), and three locked ones -- Part 2, a boss, undated.
        _achievement("a1", "disaster_collection", count=10),
        _achievement("a2", "disaster_collection", count=10),
        _achievement("a3", "disaster_collection"),
        _achievement("m1", "disaster_collection", kind="meta",
                     children=("a2", "a3")),
        _achievement("l1", "disaster_collection", gate="part2"),
        _achievement("l2", "disaster_collection", gate="boss2"),
        _achievement("l3", "disaster_collection", gate="nowhere"),
        # Battle Report: one list achievement.
        _achievement("b1", "disaster_battle", listed="info_b1"),
        # Annihilation Reward: one named, done and claimed; an unnamed
        # one done and not claimed.
        _achievement("p1", "penalty"),
        _achievement("g1", "penalty", kind="generic"),
        # Chaos Investigation: gated by Part 2, but with a row on the
        # wire -- the gate is open. Then one done on an Event, and one
        # done on two others.
        _achievement("c1", "disaster_ingame", gate="part2"),
        _achievement("e1", "disaster_ingame", events=("uk_a",),
                     options=("Take it",), equipment=("Hammer",),
                     combatants=("Nine",),
                     text="Obtain equipment Hammer with Nine"),
        _achievement("e2", "disaster_ingame", events=("uk_b", "uk_c")),
    ],
    "lists": {"info_b1": {"kind": "chaos", "collection": "chaos_14_02",
                          "items": [["i1", "Wolf", 4, None],
                                    ["i2", "Bat", 1, None],
                                    ["i3", "Owl", 1, None],
                                    ["i4", "Later", 1, "part2"]]}},
}}
CONSTANTS = {"unlock_disaster_shop_1": 21, "unlock_disaster_shop_2": 42,
             "unlock_disaster_shop_3": 63}
NOW = START + 26 * DAY - 3600          # in part 1, boss 2 two days off


def _raw(wire=None):
    return {
        "event_schedules": {"DISASTER_SEASON": {SEASON: {
            "start_time": START, "end_time": START + 84 * DAY}}},
        "disaster_achievement_entities": {SEASON: wire or {
            "a1": {"score": 4, "complete_time": 0},
            "a2": {"score": 10, "complete_time": 0},
            "a3": {"score": 1, "complete_time": 9},
            "p1": {"score": 1, "complete_time": 9},
            "g1": {"score": 1, "complete_time": 0},
            "c1": {"score": 0, "complete_time": 0}}},
        "chaos_archive_entities": {"chaos_14_02": {
            "collection": {"i1": 1, "i2": 1}}},
        # The codex's 1, two kills in finished runs and one in the open
        # one: the four the codex wants.
        "chaos_run_finds": {"i1": 2},
        "chaos_run_open": {"i1": 1},
    }


def _model_failures():
    import disaster_challenges as dc
    out = []
    board = dc.board(_raw(), NOW, CHALLENGES, CONSTANTS)
    pages = {page.page: page for page in board.pages}
    records = pages.get("disaster_collection")
    if records is None:
        return out + [f"Mission Records missing from the board: {board}"]
    if (records.done, records.total) != (3, 7):
        out.append(f"Mission Records counts {records.done}/{records.total}, "
                   f"not 3/7: a score at its target, a claim and a meta whose "
                   f"children are done are each done, and the locked ones "
                   f"count in the total")
    if not records.unclaimed:
        out.append("a page whose meta-achievement is done and not claimed "
                   "reads no reward waiting: a meta's row is issued only "
                   "when it is claimed, so its children say it is done")
    if [row.id for row in records.rows] != ["a1"]:
        out.append(f"Mission Records lists {[r.id for r in records.rows]}, "
                   f"not just a1: done ones, metas and locked ones are not "
                   f"requirements to write out")
    if records.locked != ("1 achievement (in 2d)", "1 Part 2 achievement",
                          "1 locked achievement"):
        out.append(f"the locked lines read {records.locked}: a boss's opens "
                   f"in days, a Supply round's is its Part, one the client "
                   f"does not date is undated -- soonest first")
    if dc.finished(records):
        out.append("a page with achievements left reads finished")
    annihilation = pages.get("penalty")
    if annihilation is None or (annihilation.done, annihilation.total) \
            != (1, 1):
        out.append(f"Annihilation Reward reads {annihilation}: the unnamed "
                   f"ones stay out of its count")
    elif not (dc.finished(annihilation) and annihilation.unclaimed):
        out.append("a finished page with an unnamed reward waiting does not "
                   "say so: its count would not blink")
    investigation = pages.get("disaster_ingame")
    if investigation is None or "c1" not in [r.id for r in investigation.rows]:
        out.append("an achievement with a row on the wire was taken as "
                   "still locked by its gate")

    def lit(event):
        page = {p.page: p for p in dc.board(
            _raw(), NOW, CHALLENGES, CONSTANTS, event=event).pages}
        return [r.id for r in page["disaster_ingame"].rows if r.lit]

    for event, want, why in (
            (None, [], "no Event stood on lights nothing"),
            ("uk_a", ["e1"], "its Event lights a row"),
            ("uk_a-1", ["e1"], "a step of an Event is that Event's spot"),
            ("uk_c", ["e2"], "any of a row's Events lights it"),
            ("uk_z", [], "an Event the rows name nowhere lights nothing")):
        if lit(event) != want:
            out.append(f"standing on {event!r} lights {lit(event)}, not "
                       f"{want}: {why}")
    shown = {r.id: r for r in investigation.rows}.get("e1")
    if shown is None or (shown.options, shown.equipment, shown.combatants) \
            != (("Take it",), ("Hammer",), ("Nine",)):
        out.append(f"a row reads {shown}: its button's words and its "
                   f"Equipment and combatant names show whether or not the "
                   f"player is on its Event")
    battle = pages.get("disaster_battle")
    tip = battle.rows[0].tip if battle and battle.rows else None
    if tip != ("Owl", "+1 more in a later part"):
        out.append(f"the list's tip reads {tip}: the codex's count, the "
                   f"finished runs' and the open run's add up, a monster at "
                   f"its kill count is done, and one opening later is "
                   f"counted, not named")
    later = dc.board(_raw(), START + 43 * DAY, CHALLENGES, CONSTANTS)
    records = {p.page: p for p in later.pages}["disaster_collection"]
    if "l1" not in [row.id for row in records.rows]:
        out.append("an achievement whose gate's day has passed is still "
                   "shown as locked")
    bare = _raw()
    del bare["chaos_archive_entities"], bare["chaos_run_finds"], \
        bare["chaos_run_open"]
    battle = {p.page: p for p in dc.board(
        bare, NOW, CHALLENGES, CONSTANTS).pages}["disaster_battle"]
    if battle.rows[0].tip != (dc.TIP_UNREAD,):
        out.append("a list with no codex captured tips every item as "
                   "missing rather than saying none was read")
    for raw, why, want in (
            ({}, "no season running", dc.NO_SEASON),
            (dict(_raw(), disaster_achievement_entities=None),
             "no challenge table captured", dc.NO_CAPTURE)):
        note = dc.board(raw, NOW, CHALLENGES, CONSTANTS).note
        if note != want:
            out.append(f"with {why} the tab says {note!r}")
    note = dc.board(_raw(), NOW, {}, CONSTANTS).note
    if note != dc.NO_CLIENT % SEASON:
        out.append(f"a season the client does not list reads {note!r}")
    return out


def run():
    add_source_to_path()
    return _reader_failures() + _shipped_failures() + _capture_failures() \
        + _marker_failures() + _model_failures()


def _strip_shipped_events():
    """A fault: `from_client.py` shipped before its rows had Events."""
    add_source_to_path()
    from game_data import from_client
    for held in from_client.DISASTER_CHALLENGES.values():
        for achievement in held["achievements"]:
            achievement["events"] = []


FAULTS = [
    ("a clear-all achievement read as ordinary", "game_client:disaster_challenges",
     'kind = ("meta" if row.get("condition_type") == CHALLENGE_CLEAR_ALL',
     'kind = ("meta" if False', "disaster_s09_104 read as"),
    ("every season kept", "game_client:disaster_challenges",
     "[-CHALLENGE_SEASONS_KEPT:]", "", "the reader kept seasons"),
    ("a boss's gate undated", "game_client:disaster_challenges",
     'cell.rpartition("_")[2]', "cell", "the gates read as"),
    ("a list's tag ignored", "game_client:_challenge_list",
     "if tagged is not None and row.get(\"link_relic_id\") not in tagged:",
     "if False:", "a tagged list read as"),
    ("a progress report unclaims", "capture.manager:ADDON_TEMPLATE",
     '            if row.get("complete_time"):\n'
     '                held["complete_time"] = row["complete_time"]\n'
     '            held.setdefault("complete_time", 0)\n'
     '            held.setdefault("season_id", season)',
     '            held["complete_time"] = row.get("complete_time", 0)\n'
     '            held.setdefault("season_id", season)',
     "unclaimed a claimed row"),
    ("a claim ignored", "capture.manager:ADDON_TEMPLATE",
     '        claimed = data.get("achievement_entities")',
     "        claimed = None", "a claim's achievement_entities"),
    ("a run's archives ignored", "capture.manager:ADDON_TEMPLATE",
     "        self._run_finds(data, found, RUN_FINDS_DEPTH)", "",
     "after one finished run and one open"),
    ("the codex leaves stale finds", "capture.manager:ADDON_TEMPLATE",
     '            self._drop_run_finds("chaos_")', "            pass",
     "a whole codex did not replace"),
    ("finished runs kept at their highest, not added",
     "capture.manager:ADDON_TEMPLATE",
     "                self.chaos_run_finds.get(item, 0) + count)",
     "                max(self.chaos_run_finds.get(item, 0), count))",
     "add up to"),
    ("a run's close not ending it", "capture.manager:ADDON_TEMPLATE",
     "        if asked == CHAOS_CLOSES:\n            self._bank_run()", "",
     "add up to"),
    ("the codex dropping the open run", "capture.manager:ADDON_TEMPLATE",
     "                                if not item.startswith(prefix)}\n",
     "                                if not item.startswith(prefix)}\n"
     "        self.chaos_run_open = {}\n",
     "dropped the open run's finds"),
    ("not seeded from the last snapshot", "capture.manager:ADDON_TEMPLATE",
     '        held = previous.get("disaster_achievement_entities")\n'
     '        if isinstance(held, dict):\n'
     '            self.disaster_achievements = held',
     "", "did not seed the challenge rows"),
    ("a meta's children not consulted", "disaster_challenges:_Reading.done",
     'if not answer and achievement.get("kind") == "meta" and children',
     'if False', "Mission Records counts"),
    ("a score at its target not done", "disaster_challenges:_Reading.done",
     'row["score"] >= (achievement.get("count") or 1))',
     'row["score"] > (achievement.get("count") or 1))',
     "Mission Records counts"),
    ("the unnamed ones counted", "disaster_challenges:board",
     'counted = [a for a in listed if a.get("kind") != "generic"]',
     "counted = listed", "Annihilation Reward reads"),
    ("an unnamed reward not heard", "disaster_challenges:board",
     "                for a in listed),",
     "                for a in counted),",
     "an unnamed reward waiting"),
    ("a Part read as a countdown", "disaster_challenges:_locked_lines",
     "elif day in parts:", "elif False:", "the locked lines read"),
    ("the open run not counted", "disaster_challenges:_tip",
     "_number(run.get(item_id)) for run in runs)",
     "_number(run.get(item_id)) for run in runs[:1])",
     "the list's tip reads"),
    ("the codex's own count left out", "disaster_challenges:_tip",
     "count = _number(have.get(item_id)) + sum(",
     "count = 0 * _number(have.get(item_id)) + sum(",
     "the list's tip reads"),
    ("a wire row does not open a gate", "disaster_challenges:_Reading.open",
     "            or self.row(achievement) is not None", "",
     "taken as still locked"),
    ("options in the table's order, not the game's",
     "game_client:_challenge_events",
     'r.get("link_encounter_id") or "", _figure(r.get("order")) or 0)):',
     'r.get("link_encounter_id") or "", 0)):', "disaster_s09_202 read"),
    ("a step's Event left as the step", "game_client:_challenge_event",
     'event, _, step = link.partition("-")\n            where.append(event)',
     'event, _, step = link.partition("-")\n            where.append(link)',
     "disaster_s09_202 read"),
    ("an award not traced", "game_client:_challenge_events",
     "awards.setdefault(paid, []).append(row[\"id\"])", "pass",
     "disaster_s09_203 read"),
    ("an interactor's Event not read off the words",
     "game_client:_challenge_event", "if not where and named:", "if False:",
     "disaster_s09_204 read"),
    ("Equipment names not looked for", "game_client:_equipment_named",
     "if name and name in words", "if False", "the Equipment named by"),
    ("a combatant's name found inside a word",
     "game_client:disaster_challenges",
     'r"\\b%s\\b" % re.escape(name), words)',
     're.escape(name), words)', "the combatants named by"),
    ("a character no player can use taken for a combatant",
     "game_client:_combatant_names",
     'if row.get("char_use_playable") == "YES"', "", "the combatants named by"),
    ("combatant names dropped from a row", "disaster_challenges:board",
     'tuple(a.get("combatants") or ()))', "())", "a row reads"),
    ("no row given its Events", "game_client:_challenge_event",
     'return sorted(set(where)), options', 'return [], options',
     "disaster_s09_201 read"),
    ("the shipped table without Events", _strip_shipped_events, None, None,
     "carry no Event"),
    ("a step not on its Event's spot", "disaster_challenges:board",
     'here = (event or "").partition("-")[0]', 'here = event or ""',
     "lights []"),
    ("a leaving not heard", "capture.manager:ADDON_TEMPLATE",
     "        elif asked == EVENT_LEAVES or asked == CHAOS_CLOSES \\\\\n",
     "        elif asked == CHAOS_CLOSES \\\\\n", "after encounter/exit_encounter"),
    ("a step moved on to not heard", "capture.manager:ADDON_TEMPLATE",
     'EVENT_SAYS = ("encounter/get_info", "encounter/next_encounter")',
     'EVENT_SAYS = ("encounter/get_info",)',
     "after encounter/next_encounter"),
    ("the marker shown in the log, not read",
     "capture.manager:CaptureManager._read_proxy_output",
     "                if EVENT_MARKER in line:", "                if False:",
     "the reader told the app of"),
    ("a dead proxy leaving the row lit",
     "capture.manager:CaptureManager._read_proxy_output",
     "            self._set_chaos_event(None)\n", "",
     "the reader told the app of"),
    ("every reply said, moved or not", "capture.manager:ADDON_TEMPLATE",
     "        if event != self.chaos_event:\n            self.chaos_event = event\n"
     '            self.log_callback("%s %s" % (EVENT_MARKER, event or ""))',
     "        self.chaos_event = event\n"
     '        self.log_callback("%s %s" % (EVENT_MARKER, event or ""))',
     "the capture said"),
]
