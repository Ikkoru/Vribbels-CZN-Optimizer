"""What the capture keeps as HISTORY, and what it must never keep.

Four records a snapshot carries for a reader that will chart them:

* **the lifetime counters, the Achievements screen and the daily
  tasks**, merged by id -- and what each counter COUNTS, which the wire
  names only when a counter moves and never at login, so a login that
  washed it out would lose it for good;
* **the Great Rift's subdivision tops**, one sample per change, from
  pages of twenty OTHER players each;
* **the Sortie's standings**, a season per schedule, since the game
  keeps only the current season and the one before;
* **the Full-Scale Offensive's standing**, a season per Offensive,
  since the login's table holds only the one running -- with its share
  of the field, which only entering the Offensive states.

The last three and the counters' meanings are carried from one capture
to the next through the newest snapshot, so a session that does not
see them again cannot write them away. And the ranking pages are other
players' rows: **no name, id, profile or team may reach a snapshot** --
a failure there is silent in the worst way, since nothing downstream
would ever look.

Shapes from `websocket_debug_20260924_152901.jsonl`. No Tk and no
snapshot needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture keeps history, never other players"

# Keys a ranking row carries that say WHO. None may reach a snapshot.
IDENTITY = frozenset({"user_id", "name", "display_id", "record_nickname",
                      "business_card", "team1", "team2", "equipped_skins",
                      "char_res_ids", "assault_char_titles"})


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


def _addon_class():
    from capture.manager import ADDON_TEMPLATE
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     ITEM_NAMES={}, KNOWN_UNIT_IDS=set(), REGION_ROUTES={})
    return namespace["Addon"]


def _stranger(rank, rank_id, score_record):
    """One row of a Great Rift ranking page, identity and all."""
    return {"rank_list": {
        "rank": rank, "score": score_record, "rank_id": rank_id,
        "clear_time": 1789755803, "turn": 11, "list_level": 4,
        "user_id": 300009999999, "display_id": 111, "name": "Stranger",
        "team1": [{"char_res_id": 1056}], "team2": [{"char_res_id": 1057}]},
        "business_card": {"intro_msg": "hello"},
        "equipped_skins": {"1056": "1056_01"}}


MINE = {"season_id": "disaster_s04", "define_id": "disaster_s04_rank_02",
        "rank": 2474, "rank_id": "disaster_s04_rank_best_2_24",
        "best_score": 1115731}


def _keys(value, found):
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(key)
            _keys(inner, found)
    elif isinstance(value, list):
        for inner in value:
            _keys(inner, found)
    return found


def run():
    add_source_to_path()
    Addon = _addon_class()
    failures = []
    folder = Path(tempfile.mkdtemp(prefix="capture_history_"))
    addon = Addon(folder, log_callback=lambda *a, **k: None)

    # --- the lifetime tables, and what each counter counts -----------
    addon.websocket_message(_Flow([{
        "res": "ok",
        "mission_accumulate": [
            {"res_id": "ac_collection_003", "score": 182120591},
            {"res_id": "ac_collection_033", "score": 334}],
        "achievements": [{"res_id": "ingame_027", "score": 49,
                          "complete_time": 0}],
        "daily_achieve": [{"res_id": "daily_achieve_001", "score": 1,
                           "version": 314}]}]))
    addon.websocket_message(_Flow([{
        "res": "ok", "mission_condition": {"condition": {
            "accumulate_condition": [{"res_id": "ac_collection_003",
                                      "score": 182250591,
                                      "condition_type": "GET_ITEM__ID"}],
            "achievement": [{"res_id": "collection_027", "score": 335,
                             "condition_type": "LOGIN"}]}}}]))
    # A claim on the Achievements screen answers with its one row.
    addon.websocket_message(_Flow([{
        "res": "ok", "achievement_entity": {
            "res_id": "ingame_027", "score": 50,
            "complete_time": 1789611094}}]))
    # And the next login sends every counter again, without its type.
    addon.websocket_message(_Flow([{
        "res": "ok", "login_total_count": 335,
        "mission_accumulate": [
            {"res_id": "ac_collection_003", "score": 182260591},
            {"res_id": "ac_collection_033", "score": 335}]}]))
    counters = addon.lifetime.get("mission_accumulate", {})
    if counters.get("ac_collection_003", {}).get("condition_type") != \
            "GET_ITEM__ID":
        failures.append(
            f"ac_collection_003 reads "
            f"{counters.get('ac_collection_003')!r} after a login. What a "
            f"counter counts arrives only when it moves, and the login's "
            f"rows never carry it -- a login that replaces the row washes "
            f"the meaning out for good.")
    if counters.get("ac_collection_003", {}).get("score") != 182260591:
        failures.append("the login's newer score did not win.")
    achievements = addon.lifetime.get("achievements", {})
    if achievements.get("ingame_027", {}).get("complete_time") != 1789611094:
        failures.append(
            "an Achievements claim's one row did not reach the table; it "
            "answers under `achievement_entity`, singular.")
    if achievements.get("collection_027", {}).get("score") != 335:
        failures.append(
            "a score moved by `mission_condition` did not reach the "
            "achievement it names.")

    # --- the Great Rift's subdivision tops ------------------------------
    # The session's server, as a connection's SNI names it. Every
    # ranking sample below must carry it: the two servers rank
    # different players, and `shared_facts` keeps them apart by it.
    addon._note_region("global")
    page = [_stranger(1, "disaster_s04_rank_best_2_30", 163563143483397),
            _stranger(2, "disaster_s04_rank_best_2_30", 163000043483397)]
    addon.websocket_message(_Flow([{
        "res": "ok", "result_list": page, "disaster_boss_rank_entity": MINE,
        "refresh_id": 394, "max_rank": 100,
        "service_server_time": 1790260736}]))
    # The same board again, and then a new leader.
    addon.websocket_message(_Flow([{
        "res": "ok", "result_list": page, "disaster_boss_rank_entity": MINE,
        "refresh_id": 394, "service_server_time": 1790260743}]))
    addon.websocket_message(_Flow([{
        "res": "ok", "result_list": [
            _stranger(1, "disaster_s04_rank_best_2_30", 164000043000000)],
        "disaster_boss_rank_entity": MINE, "refresh_id": 395,
        "service_server_time": 1790300000}]))
    samples = (addon.rift_tops.get("disaster_s04", {})
               .get("disaster_s04_rank_02", {})
               .get("disaster_s04_rank_best_2_30", []))
    if [s.get("best_score") for s in samples] != [1635631, 1640000]:
        failures.append(
            f"Master I's top reads {samples!r}. Each subdivision keeps its "
            f"TOP row, one sample per change: the second page was the same "
            f"board and must add nothing, the third a new leader. The best "
            f"score is the record divided by 10**8.")

    # --- the Sortie's standings, a season per schedule ------------------
    for tab, schedule, rank in (("ongoing", "assault_1_s7", 739),
                                ("complete", "assault_1_s6", 1914)):
        addon.websocket_message(_Flow([{
            "res": "ok", "tab": tab, "schedule_id": schedule, "page": 1,
            "reset_time": 1790726400, "refresh_id": 1122,
            "total_count": 19552,
            "my_rank": {"rank": rank, "score": 45512},
            "rank_list": [{"rank": 1, "score": 65084, "clear_time_sec": 2629,
                           "penalty_level": 30, "user_id": 300009999999,
                           "name": "Stranger", "business_card": {},
                           "char_res_ids": [30117]}],
            "chaos_assault_rank_entity": {"rank": rank, "last_rank": 0},
            "service_server_time": 1790262663}]))
    # A later page carries the same standing and no rank 1.
    addon.websocket_message(_Flow([{
        "res": "ok", "tab": "ongoing", "schedule_id": "assault_1_s7",
        "page": 2, "total_count": 19552,
        "my_rank": {"rank": 739, "score": 45512},
        "rank_list": [{"rank": 21, "score": 60000}]}]))
    seasons = addon.sortie_rankings
    got = {s: [(r.get("rank"), r.get("top_score")) for r in
               seasons.get(s, {}).get("readings", [])]
           for s in ("assault_1_s7", "assault_1_s6")}
    if got != {"assault_1_s7": [(739, 65084)],
               "assault_1_s6": [(1914, 65084)]}:
        failures.append(
            f"the Sortie standings read {got!r}. Both tabs are kept, a "
            f"season each, from the first page only -- the one holding "
            f"rank 1; a later page has no top to give.")
    stamps = {s.get("region") for s in samples} | {
        r.get("region") for season in seasons.values()
        for r in season.get("readings", [])}
    if stamps != {"global"}:
        failures.append(
            f"ranking samples carry the servers {sorted(map(str, stamps))}, "
            f"not the session's own. A field size or a division's top "
            f"is a fact about one server, and a sample without its "
            f"server cannot be shared without guessing which.")

    # --- the Full-Scale Offensive, a season per Offensive ------------------
    def stage(n, score):
        return {"user_id": 300001105178, "list_id": "remnants_boss_s05_%02d" % n,
                "define_id": "remnants_boss_penalty_005",
                "best_score": score, "star_count": 3}
    login = {"res": "ok", "service_server_time": 1790000000,
             "remnants_entity": {"define_id": "remnants_boss_penalty_005",
                                 "rank": 441, "reward_count": 9},
             "remnants_entities": {"remnants_boss_s05_%02d" % n:
                                   stage(n, 1000000 + n) for n in (1, 2, 3)}}
    addon.websocket_message(_Flow([login]))
    # Entering the Offensive: the same rank, and its share of the field.
    addon.websocket_message(_Flow([{
        "res": "ok", "define_id": "remnants_boss_penalty_005", "rank": 441,
        "rank_percent": 0.83, "reward_count": 9,
        "service_server_time": 1790000100,
        "entities": {"remnants_boss_s05_01": stage(1, 1200000)}}]))
    # A later login with the rank unmoved, then one with it moved.
    addon.websocket_message(_Flow([dict(login, service_server_time=1790000200,
                                        remnants_entities={})]))
    moved = dict(login, service_server_time=1790000300, remnants_entities={},
                 remnants_entity=dict(login["remnants_entity"], rank=460))
    addon.websocket_message(_Flow([moved]))
    season = addon.remnants_rankings.get("remnants_boss_penalty_005", {})
    got = [(r.get("rank"), r.get("rank_percent"), r.get("score"))
           for r in season.get("readings", [])]
    want = [(441, None, 3000006), (441, 0.83, 3200005), (460, None, 3200005)]
    if got != want:
        failures.append(
            f"the Offensive's readings are {got}, not {want}. Entering it "
            f"adds the share of the field; a login that finds the rank "
            f"unmoved carries that share and adds nothing, and one that "
            f"finds it moved leaves the share unknown. The score is the "
            f"stages' best scores summed, each as last read.")
    stamps = {r.get("region") for r in season.get("readings", [])}
    if stamps != {"global"}:
        failures.append(
            f"the Offensive's readings carry the servers "
            f"{sorted(map(str, stamps))}, not the session's own. The "
            f"field its rank implies is one server's.")

    # --- saved, and carried into the next capture ------------------------
    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    for field, shape in (("mission_accumulate", list),
                         ("achievements", list), ("daily_achieve", list),
                         ("login_total_count", int),
                         ("disaster_boss_rank_tops", dict),
                         ("chaos_assault_rankings", dict),
                         ("remnants_rankings", dict)):
        if not isinstance(saved.get(field), shape) or not saved.get(field):
            failures.append(
                f"a saved snapshot's {field} is {saved.get(field)!r}. A "
                f"field the addon never writes is invisible to "
                f"everything downstream.")
    leaked = _keys({"tops": saved.get("disaster_boss_rank_tops"),
                    "sortie": saved.get("chaos_assault_rankings")},
                   set()) & IDENTITY
    if leaked:
        failures.append(
            f"another player's {sorted(leaked)!r} reached the snapshot. A "
            f"ranking page is twenty strangers; only the numbers are kept.")

    again = Addon(folder, log_callback=lambda *a, **k: None)
    if again.rift_tops != addon.rift_tops or \
            again.sortie_rankings != addon.sortie_rankings or \
            again.remnants_rankings != addon.remnants_rankings:
        failures.append(
            "the ranking history did not carry into the next capture. The "
            "game keeps two Sortie seasons and nothing older, the login "
            "holds only the Offensive running, and a Great Rift top is "
            "read once per visit to its screen; a capture that starts "
            "empty writes the history away at its first save.")
    again.websocket_message(_Flow([{
        "res": "ok", "mission_accumulate": [
            {"res_id": "ac_collection_003", "score": 182300000}]}]))
    if again.lifetime.get("mission_accumulate", {}).get(
            "ac_collection_003", {}).get("condition_type") != "GET_ITEM__ID":
        failures.append(
            "what ac_collection_003 counts did not survive a restart. It "
            "was learned from one `mission_condition` and the wire will "
            "not repeat it until the counter moves again.")
    return failures
