"""The stats read out of old debug captures, and the standings the Stats
lists work out from them.

`stats_history.py` runs the capture addon over every old log ONCE, and
decides "once" by the file it writes. Each way that goes wrong is quiet:

* **a reading that never counts as done** reads a year of logs at every
  launch, and says nothing but the same `[OK]`;
* **a log cut off mid-line** -- a capture killed while writing -- must
  not stop the reading, or the file is never written and every launch
  stops at the same place;
* **the addon's own save** writes a snapshot after every frame that
  moves anything, into the folder it is given, unless it is replaced;
* **other players' rows** reach the ranking frames this reads, and no
  name, id or team may reach the file;
* **the field's size** is worked out from subdivision tops, and a
  wrong share turns every `~47,160` under Out of into a plausible lie;
* **a finished Great Rift half's place** is its `last_rank`, and its
  `rank` -- the last one computed while the account was looking --
  reads a little higher and plausible.

No Tk and no captured data needed: the logs are written here.
"""

import gzip
import json
import tempfile
import threading
from pathlib import Path

from ._harness import add_source_to_path

NAME = "stats history reads old captures once"

# Keys a ranking row carries that say WHO. None may reach the file.
IDENTITY = frozenset({"user_id", "name", "display_id", "record_nickname",
                      "business_card", "team1", "team2", "equipped_skins",
                      "char_res_ids", "assault_char_titles"})

LIVE = {"season_id": "disaster_s04", "define_id": "disaster_s04_rank_02",
        "rank": 2481, "rank_id": "disaster_s04_rank_best_2_24",
        "last_rank": 0, "last_rank_id": None, "best_score": 1115731}
FINISHED = {"season_id": "disaster_s04", "define_id": "disaster_s04_rank_01",
            "rank": 3473, "rank_id": "disaster_s04_rank_best_1_24",
            "last_rank": 3502, "last_rank_id": "disaster_s04_rank_best_1_24",
            "best_score": 984946}


def _stage(n, score):
    """One of the Full-Scale Offensive's three stages, as a board row."""
    return {"user_id": 300001105178, "define_id": "remnants_boss_penalty_005",
            "list_id": "remnants_boss_s05_%02d" % n, "best_score": score,
            "star_count": 3, "deployed_heroes": [1056]}


def _stranger(rank, rank_id, best_score):
    return {"rank_list": {
        "rank": rank, "score": best_score * 10 ** 8 + 4 * 10 ** 7,
        "rank_id": rank_id, "clear_time": 1789755803, "turn": 11,
        "list_level": 4, "user_id": 300009999999, "display_id": 111,
        "name": "Stranger", "team1": [{"char_res_id": 1056}]},
        "business_card": {"intro_msg": "hello"}}


def _frames():
    """Server replies, in the order a session would send them."""
    return [
        # Login: the standings of every half, the Sortie's clears, and
        # the Offensive's rank with its three stages.
        [{"res": "ok", "service_server_time": 1790000000,
          "disaster_boss_rank_entities": {"disaster_s04": {
              "disaster_s04_rank_01": FINISHED,
              "disaster_s04_rank_02": dict(LIVE, rank=2600)}},
          "chaos_assault_entity": {"total_clear_count": 40,
                                   "highest_clear_level": 5},
          "remnants_entity": {"define_id": "remnants_boss_penalty_005",
                              "rank": 441, "reward_count": 9},
          "remnants_entities": {"remnants_boss_s05_%02d" % n: _stage(n, score)
                                for n, score in ((1, 1130418), (2, 1060877),
                                                 (3, 1255815))}}],
        # Entering the Offensive: its share of the field.
        [{"res": "ok", "service_server_time": 1790000050,
          "define_id": "remnants_boss_penalty_005", "rank": 441,
          "rank_percent": 0.83, "reward_count": 9, "entities": {}}],
        # Merit Ranking, Master's page and then Bronze's.
        [{"res": "ok", "service_server_time": 1790000100,
          "result_list": [_stranger(1, "disaster_s04_rank_best_2_30",
                                    1635631)],
          "disaster_boss_rank_entity": LIVE, "refresh_id": 394}],
        [{"res": "ok", "service_server_time": 1790000200,
          "result_list": [_stranger(35368, "disaster_s04_rank_best_2_5",
                                    416283)],
          "disaster_boss_rank_entity": LIVE, "refresh_id": 394}],
        _hardcore(740, 1790000300),
    ]


def _hardcore(rank, at):
    """A Hardcore Rankings page, rank 1 and all."""
    return [{"res": "ok", "tab": "ongoing", "schedule_id": "assault_1_s7",
             "page": 1, "reset_time": 1790726400, "refresh_id": 1122,
             "total_count": 19607, "my_rank": {"rank": rank, "score": 45512},
             "rank_list": [{"rank": 1, "score": 65084,
                            "clear_time_sec": 2629, "penalty_level": 30,
                            "user_id": 300009999999, "name": "Stranger",
                            "char_res_ids": [30117]}],
             "service_server_time": at}]


def _line(data):
    return json.dumps({"ts": "2026-09-24T15:29:23", "direction":
                       "server_to_client", "keys": [], "size": 1,
                       "data": data}) + "\n"


def _write_log(path, frames, cut=False):
    """A debug log as the capture writes one: a gzip member per line.
    `cut` ends it halfway through a last member, as a capture killed
    mid-write does."""
    with open(path, "wb") as fh:
        for data in frames:
            fh.write(gzip.compress(_line(data).encode("utf-8")))
        if cut:
            tail = gzip.compress(_line({"res": "ok", "my_rank": {}})
                                 .encode("utf-8"))
            fh.write(tail[:len(tail) // 2])


def _keys(value, found):
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(key)
            _keys(inner, found)
    elif isinstance(value, list):
        for inner in value:
            _keys(inner, found)
    return found


def _readings(sh):
    """The pure readings: subdivisions, the field, the joins."""
    out = []
    if len(sh.SHARES) != 30 or sh.SHARES[0] != 1.0 \
            or sh.SHARES[-1] != 0.001 \
            or any(a <= b for a, b in zip(sh.SHARES, sh.SHARES[1:])):
        out.append(f"SHARES is not thirty shares falling from 100% to "
                   f"0.1%: {sh.SHARES}. Every subdivision's `top N%` and "
                   f"the field's size are read off it.")
    for rank_id, want, why in (
            ("disaster_s04_rank_best_2_1", (1, "Bronze V", 1.0), ""),
            ("disaster_s04_rank_best_2_24", (24, "Diamond II", 0.07), ""),
            ("disaster_s04_rank_best_1_30", (30, "Master I", 0.001), ""),
            ("disaster_s04_rank_best_2_31", None,
             " There are thirty subdivisions."),
            ("disaster_s01_h1_4", None,
             " Season 1's ids are on another scale.")):
        got = sh.subdivision(rank_id)
        if got != want:
            out.append(f"subdivision({rank_id!r}) reads {got}, not "
                       f"{want}.{why}")
    tops = {"disaster_s04_rank_best_2_30": [{"rank": 1}],
            "disaster_s04_rank_best_2_25": [{"rank": 941}],
            "disaster_s04_rank_best_2_5": [{"rank": 35368}]}
    for held, want in ((tops, 47156),
                       ({k: v for k, v in tops.items()
                         if not k.endswith("_5")}, 47000),
                       ({"disaster_s04_rank_best_2_30": [{"rank": 1}]},
                        None)):
        got = sh.field_size(held)
        if got != want:
            out.append(
                f"field_size over {sorted(held)} reads {got}, not {want}. "
                f"A subdivision's top row stands one below the share of "
                f"the subdivision ABOVE it, and the lowest one read gives "
                f"the field most exactly; Master I's top says nothing.")
    raw = {"chaos_assault_rankings": {"assault_1_s7": {
        "reset_time": 2, "readings": [{"read_at": 5, "rank": 700},
                                      {"read_at": 9, "rank": 690}]}}}
    history = {"chaos_assault_rankings": {
        "assault_1_s7": {"reset_time": 1, "readings": [
            {"read_at": 1, "rank": 900}, {"read_at": 5, "rank": 700}]},
        "assault_1_s6": {"reset_time": 0, "readings": [
            {"read_at": 0, "rank": 1914}]},
        "assault_1_s5": {"reset_time": 0, "readings": []}}}
    joined = sh.merged(raw, history, "chaos_assault_rankings")
    ranks = [r["rank"] for r in joined["assault_1_s7"]["readings"]]
    if ranks != [900, 700, 690] or joined["assault_1_s7"]["reset_time"] != 2:
        out.append(f"the snapshot's Sortie readings joined with the file's "
                   f"read {ranks}: one taken at the same moment is the same "
                   f"reading, and the lot runs oldest first.")
    if history["chaos_assault_rankings"]["assault_1_s7"]["readings"][-1] \
            != {"read_at": 5, "rank": 700}:
        out.append("merged() changed the history it was handed; the "
                   "tab keeps that dict and joins it again on every load.")
    seasons = [s[0] for s in sh.sortie_seasons(raw, history)]
    if seasons != [7, 6]:
        out.append(f"sortie_seasons reads seasons {seasons}: newest first, "
                   f"and a season with no reading is not one.")
    halves = sh.rift_halves({"disaster_boss_rank_entities": {
        "disaster_s03": {"disaster_s03_rank_02": {}},
        "disaster_s04": {"disaster_s04_rank_01": {},
                         "disaster_s04_rank_02": {}}}}, None)
    order = [(h[0], h[1]) for h in halves]
    if order != [(4, 2), (4, 1), (3, 2)]:
        out.append(f"rift_halves reads {order}; newest first.")
    return out


def _tables(sh):
    """What the lists say, where the arithmetic shows: each column's
    cells, top to bottom, and the columns newest first."""
    out = []
    top = {"read_at": 1}
    raw = {
        "disaster_boss_rank_entities": {"disaster_s04": {
            "disaster_s04_rank_01": FINISHED,
            "disaster_s04_rank_02": LIVE}},
        "disaster_boss_rank_tops": {"disaster_s04": {"disaster_s04_rank_02": {
            "disaster_s04_rank_best_2_30": [dict(top, rank=1,
                                                 best_score=1635631)],
            "disaster_s04_rank_best_2_25": [dict(top, rank=941,
                                                 best_score=1219348)],
            "disaster_s04_rank_best_2_5": [dict(top, rank=35368,
                                                best_score=416283)]}}},
        "chaos_assault_rankings": {
            "assault_1_s6": {"readings": [{
                "tab": "complete", "rank": 1914, "total_count": 24684,
                "score": 42343, "top_score": 66265, "read_at": 2}]},
            "assault_1_s7": {"readings": [{
                "tab": "ongoing", "rank": 740, "total_count": 19607,
                "score": 45512, "top_score": 65084, "read_at": 3}]}},
        "remnants_rankings": {
            "remnants_boss_penalty_004": {"readings": [
                {"rank": 900, "rank_percent": None, "read_at": 4}]},
            "remnants_boss_penalty_005": {
                "stages": {"a": 1130418, "b": 1060877, "c": 1255815},
                "readings": [{"rank": 441, "rank_percent": 0.83,
                              "read_at": 5}]}}}
    for name, table, rows, columns, why in (
            ("Sortie", sh.sortie_table, sh.SORTIE_ROWS,
             [("7", ["3.8%", "740", "19,607", "45,512", "65,084"]),
              ("6", ["7.8%", "1,914", "24,684", "42,343", "66,265"])],
             "the share of the field is the rank over total_count"),
            ("Great Rift", sh.rift_table, sh.RIFT_ROWS,
             [("4 p2", ["Test Part", "5.3%", "7%", "2,481", "~47,160",
                        "1,115,731", "1,635,631", "1,219,348", None,
                        None, None, "416,283"]),
              ("4 p1", [sh.RIFT_UNNAMED, None, "7%", "3,502", None,
                        "984,946"] + [None] * 6)],
             "each part opens on its own codename, or TBD; a finished "
             "half's place is its last_rank, the running one's its rank "
             "against the field Bronze's top gives; then each division's "
             "top, Master's first, as its subdivision I -- no other "
             "subdivision's top is ever sent"),
            ("Full-Scale Offensive", sh.offensive_table, sh.OFFENSIVE_ROWS,
             [("5", ["0.83%", "441", "~53,100", "3,447,110",
                     "1,130,418", "1,060,877", "1,255,815"]),
              ("4", [None, "900", None, None, None, None, None])],
             "the field is the rank over rank_percent, to the hundred, the "
             "total the stages' best scores summed, and each stage's in "
             "the order of their ids")):
        # Codenames of the check's own -- one part named, its season's
        # other part not -- so the maintainer's own cannot move what
        # this expects.
        saved = sh.RIFT_CODENAMES
        sh.RIFT_CODENAMES = {(4, 2): "Test Part"}
        try:
            got = table(raw, None)
        finally:
            sh.RIFT_CODENAMES = saved
        if got != (rows, columns):
            out.append(f"the {name} list reads {got}, not {(rows, columns)}: "
                       f"{why}.")
        empty = table({}, None)
        if empty != (empty[0], []) or len(empty[0]) != len(rows):
            out.append(f"the {name} list with nothing read reads {empty}; "
                       f"its rows and no columns.")
    return out


def _reading(sh):
    """read_logs over written logs: what it keeps, what it drops, and a
    log cut short."""
    out = []
    folder = Path(tempfile.mkdtemp(prefix="stats_logs_"))
    try:
        whole = folder / "websocket_debug_20260101_000000.jsonl.gz"
        cut = folder / "websocket_debug_20260102_000000.jsonl.gz"
        _write_log(whole, _frames())
        # A later session's page, then the break.
        _write_log(cut, [_hardcore(730, 1790090000)], cut=True)
        data = sh.read_logs(folder)
        if data.get("cut_short") != [cut.name] \
                or data.get("logs") != [whole.name, cut.name]:
            out.append(
                f"reading one whole log and one cut off mid-line gives "
                f"logs {data.get('logs')} and cut_short "
                f"{data.get('cut_short')}. A cut log keeps what came "
                f"before the break; raising instead leaves the file "
                f"unwritten, and every launch stops at the same place.")
        tops = (data.get("disaster_boss_rank_tops", {}).get("disaster_s04", {})
                .get("disaster_s04_rank_02", {}))
        if sorted(tops) != ["disaster_s04_rank_best_2_30",
                            "disaster_s04_rank_best_2_5"]:
            out.append(f"the Merit Ranking pages left tops {sorted(tops)}; "
                       f"each page's subdivision keeps its top row.")
        readings = (data.get("chaos_assault_rankings", {})
                    .get("assault_1_s7", {}).get("readings") or [])
        got = [(r.get("rank"), r.get("total_count"), r.get("top_score"))
               for r in readings]
        if got != [(740, 19607, 65084), (730, 19607, 65084)]:
            out.append(f"the Hardcore Rankings pages left {got}: one "
                       f"reading from the whole log, and the cut log's, "
                       f"which came before its break.")
        samples = (data.get("disaster_boss_rank_standings", {})
                   .get("disaster_s04", {}).get("disaster_s04_rank_02", []))
        if [s.get("rank") for s in samples] != [2600, 2481]:
            out.append(
                f"the running half's standing reads "
                f"{[s.get('rank') for s in samples]} across the log: one "
                f"sample per change, the login's and then the ranking "
                f"page's. A snapshot holds only the latest.")
        clears = data.get("chaos_assault_standings") or []
        if len(clears) != 1 or clears[0].get("total_clear_count") != 40:
            out.append(f"the Sortie's clears read {clears}; the same count "
                       f"at every login is one sample.")
        offensive = (data.get("remnants_rankings", {})
                     .get("remnants_boss_penalty_005", {}))
        got = [(r.get("rank"), r.get("rank_percent"), r.get("score"))
               for r in offensive.get("readings", [])]
        if got != [(441, None, 3447110), (441, 0.83, 3447110)]:
            out.append(f"the Offensive's readings from the log are {got}: "
                       f"the login's rank, then entering it adds the share "
                       f"of the field. MARKERS must let both frames "
                       f"through.")
        leaked = _keys(data, set()) & IDENTITY
        if leaked:
            out.append(f"the stats file would carry {sorted(leaked)} -- "
                       f"other players' identity, read off the ranking "
                       f"pages. Nothing downstream would ever notice.")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    return out


def _addon_saves_nothing(sh):
    """The addon's save is replaced. It would otherwise write a
    snapshot into the folder it is given after the first frame that
    moves anything -- the line that stops it reads as a stray."""
    folder = Path(tempfile.mkdtemp(prefix="stats_addon_"))
    try:
        addon = sh._addon(folder)
        addon.inventory_data = {"info_item_piece": [{"id": 1}]}
        addon.websocket_message(sh._Flow(json.dumps(_frames()[0])))
        written = sorted(p.name for p in folder.iterdir())
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    if written:
        return [f"the addon stats_history runs wrote {written} into its "
                f"folder. `_addon` replaces its `_save_data`, and that line "
                f"looks removable."]
    return []


def _once(sh):
    """The file decides whether the logs are read: missing, broken, of
    another kind or an older version reads them; current does not."""
    out = []
    settings = Path(tempfile.mkdtemp(prefix="stats_settings_"))
    logs = Path(tempfile.mkdtemp(prefix="stats_logs_"))
    try:
        path = sh.path_in(settings)
        for state, text in (("missing", None), ("broken", "{not json"),
                            ("of another kind", json.dumps({"kind": "x"})),
                            ("an older version", json.dumps(
                                {"kind": sh.KIND, "version": sh.VERSION - 1}))):
            if text is not None:
                path.write_text(text, encoding="utf-8")
            if sh.is_current(settings):
                out.append(f"a stats file {state} counts as current: the "
                           f"old logs would never be read.")
        if path.exists():
            path.unlink()
        _write_log(logs / "websocket_debug_20260101_000000.jsonl.gz",
                   _frames())
        said, finished = [], threading.Event()
        thread = sh.read_in_background(logs, settings, said.append,
                                       finished.set)
        if thread is None:
            out.append("with no stats file the old logs were not read.")
            return out
        thread.join(30)
        if not finished.is_set() or not sh.is_current(settings) \
                or not said or not said[-1].startswith("[OK]"):
            out.append(f"the reading said {said} and left the file "
                       f"current: {sh.is_current(settings)}.")
        if list(settings.glob("*.tmp")):
            out.append("the reading left its temp file beside the stats "
                       "file.")
        again = sh.read_in_background(logs, settings, said.append,
                                      finished.set)
        if again is not None:
            again.join(30)
            out.append("with a current stats file the logs were read "
                       "again: every launch pays for a year of logs.")
        # Nothing may raise out of the thread: a thread that dies of an
        # exception takes its report with it.
        path.unlink()
        said.clear()
        finished.clear()
        real = sh.read_logs

        def broken(_folder):
            raise ValueError("a log nobody expected")
        sh.read_logs = broken
        try:
            thread = sh.read_in_background(logs, settings, said.append,
                                           finished.set)
            thread.join(30)
        finally:
            sh.read_logs = real
        if finished.is_set() or path.exists() or not said \
                or not said[-1].startswith("[X]"):
            out.append(f"a reading that raised said {said}, called done: "
                       f"{finished.is_set()}, wrote the file: "
                       f"{path.exists()}. It must say it stopped, and "
                       f"leave the file for the next launch to write.")
    finally:
        import shutil
        shutil.rmtree(settings, ignore_errors=True)
        shutil.rmtree(logs, ignore_errors=True)
    return out


def run():
    add_source_to_path()
    import stats_history as sh
    failures = []
    failures.extend(_readings(sh))
    failures.extend(_tables(sh))
    failures.extend(_reading(sh))
    failures.extend(_addon_saves_nothing(sh))
    failures.extend(_once(sh))
    return failures
