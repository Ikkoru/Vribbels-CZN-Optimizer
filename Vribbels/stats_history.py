"""Standings and lifetime stats: the history a snapshot carries, and the
part of it only old debug captures hold.

The capture keeps the Great Rift's, the Sortie's and the Full-Scale
Offensive's ranking readings and the lifetime counters in every
snapshot, each carried forward into the next (`capture/manager.py`,
`_seed_from_previous`). Captures taken before
it did have them only in their debug logs. **Those are read out ONCE**,
into `settings/stats_history.json`, by the capture addon's own code --
exec'd from its template the way the checks run it -- so what is read
out of an old log is exactly what a live capture would have kept.

**Once is decided by the file, not by a date.** It records the
`VERSION` of the reading that wrote it: a file missing, unreadable, of
another kind or an older version is read again at the next launch, and
anything else is left alone. A version rather than the app's release
date, because what matters is whether THIS reading has been done -- a
reading that learns a new field bumps `VERSION` and runs once more.

In `settings/`, not beside the captures: the snapshots folder is the one
that gets tidied, and the logs this reads may be gone by the next time
anything wanted them. Only the frames that can carry what is kept are
parsed at all -- see `MARKERS` -- so a pass is mostly the archive's own
decompression.

What the Stats lists show is worked out here too, as plain data --
`sortie_table`, `rift_table` and `offensive_table` -- so it is testable
without Tk.
"""

import gzip
import io
import json
import re
import tempfile
import threading
import zlib
from pathlib import Path

FILE_NAME = "stats_history.json"
KIND = "vribbels stats history"
# What the reading reads. Bump it and the next launch reads every log
# again, which is how a newly kept field reaches the captures before it.
VERSION = 2

# A frame is parsed only where its text carries one of these: the keys
# of everything the reading keeps. Every other frame is skipped unread,
# which is what keeps a pass over a year of logs to seconds.
MARKERS = ('"my_rank"', '"result_list"', '"mission_accumulate"',
           '"disaster_boss_rank_entit', '"login_total_count"',
           '"accumulate_condition"', '"achievement_entity"',
           '"chaos_assault_entity"', '"remnants_entit', '"rank_percent"')


# The Great Rift's thirty subdivisions, by the number that ends a
# `rank_id`: (division, tier, the share of the field it reaches down
# to). The shares are the game's own, as its Merit Ranking states them.
DIVISIONS = ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master")
TIERS = ("V", "IV", "III", "II", "I")
SHARES = (1.00, 0.95, 0.90, 0.85, 0.80,           # Bronze V .. I
          0.75, 0.70, 0.65, 0.60, 0.55,           # Silver
          0.50, 0.48, 0.44, 0.40, 0.34,           # Gold
          0.26, 0.24, 0.22, 0.19, 0.15,           # Platinum
          0.10, 0.09, 0.08, 0.07, 0.05,           # Diamond
          0.02, 0.015, 0.01, 0.005, 0.001)        # Master
RANK_ID = re.compile(r"_rank_best_(\d+)_(\d+)$")

# Each Great Rift part's codename, by (season, part) -- `(4, 2)` is
# `disaster_s04_rank_02`, the list's `4 p2` -- written in by hand:
# nothing on the wire names one. Every part has its own, and a part not
# here shows `RIFT_UNNAMED`.
RIFT_CODENAMES = {
    (1, 1): "Mochi",
    (1, 2): "Haku",
    (2, 1): "Hands",
    (2, 2): "Lion?",
    (3, 1): "3 Heroes",
    (3, 2): "Fingers",
    (4, 1): "Tardigrade",
    (4, 2): "Anis <3",
}
RIFT_UNNAMED = "TBD"

# Division tops no capture here holds, by (server, season, part): when
# they were read, where, and each division's top score in the list's
# order, Master's first -- None where the source does not say.
#
# **A `FINAL` stands over any reading of its tops**: a reading is taken
# while a part runs, and the final is its last word. The rest are
# readings like the capture's own, dated in UTC, and the list shows
# whichever of the two was read later. A part here on the account's
# server gets a column like a shipped one.
FINAL = "final"
OFFICIAL_S1 = ("Official "
               "https://page.onstove.com/chaoszeronightmare/en/view/12183147")
# The site keeps each division's top hundred on both servers, as the
# game's own rows; only each list's first score is taken, never who.
CZNMETADECKS = "https://cznmetadecks.com/meta?define=%s, Leaderboard"
RIFT_RECORDED_TOPS = {
    ("global", 1, 1): (FINAL, OFFICIAL_S1, (1728670,)),           # Mochi
    ("global", 1, 2): (FINAL, OFFICIAL_S1, (1536416,)),           # Haku
    ("asia", 1, 2): (FINAL, OFFICIAL_S1, (1567592,)),             # Haku
    ("global", 2, 1): ("2026-03-18 00:49:48",
                       CZNMETADECKS % "disaster_s02_rank_01",
                       (1397969, 1047250, 736926, 525751, 269900, 110312)),
    ("asia", 2, 1): ("2026-03-18 00:40:38",
                     CZNMETADECKS % "disaster_s02_rank_01",
                     (1424292, 1112343, 796263, 578230, 334351, 139225)),
    ("global", 2, 2): ("2026-04-08 00:51:08",
                       CZNMETADECKS % "disaster_s02_rank_02",
                       (1497905, 894228, 601625, 402653, 188373, 71744)),
    ("asia", 2, 2): ("2026-04-08 00:40:30",
                     CZNMETADECKS % "disaster_s02_rank_02",
                     (1497830, 965349, 647991, 486669, 243747, 85894)),
    ("global", 3, 1): ("2026-06-17 00:50:28",
                       CZNMETADECKS % "disaster_s03_rank_01",
                       (1675662, 1354972, 978677, 699163, 404741, 161035)),
    ("asia", 3, 1): ("2026-06-17 00:41:00",
                     CZNMETADECKS % "disaster_s03_rank_01",
                     (1659034, 1410271, 1009865, 745441, 435893, 214147)),
    ("global", 3, 2): ("2026-07-08 00:50:57",
                       CZNMETADECKS % "disaster_s03_rank_02",
                       (1477426, 1123095, 876418, 583861, 381375, 206278)),
    ("asia", 3, 2): ("2026-07-08 00:39:34",
                     CZNMETADECKS % "disaster_s03_rank_02",
                     (1463021, 1179361, 931392, 635757, 419411, 249431)),
    ("global", 4, 1): ("2026-09-08 23:45:20",
                       CZNMETADECKS % "disaster_s04_rank_01",
                       (1588505, 1167835, 870728, 608926, 417017, 182427)),
    ("asia", 4, 1): ("2026-09-08 23:52:59",
                     CZNMETADECKS % "disaster_s04_rank_01",
                     (1588974, 1274196, 984909, 710213, 454282, 284966)),
    ("global", 4, 2): ("2026-09-23 06:47:46",
                       CZNMETADECKS % "disaster_s04_rank_02",
                       (1635631, 1217377, 1015317, 645125, 417038, 177955)),
    ("asia", 4, 2): ("2026-09-23 02:14:27",
                     CZNMETADECKS % "disaster_s04_rank_02",
                     (1636166, 1285444, 1080181, 788671, 443000, 300118)),
}

# The lists' rows, top to bottom. The Great Rift's start with the
# part's codename and end with every division's top score, Master's
# first -- see `rift_table` for why a division's is its subdivision I's.
SORTIE_ROWS = ("Top%", "Top #", "Out of", "Score", "Top score")
RIFT_ROWS = ("Codename", "Top% apx.", "Top% official", "Top #", "Out of",
             "Score") + tuple(
    "Top %s I" % division for division in reversed(DIVISIONS))
# An Offensive is three stages; the list gives each its own score row.
OFFENSIVE_STAGES = 3
OFFENSIVE_ROWS = ("Top%", "Top #", "Out of", "Total") + tuple(
    "Score %d" % n for n in range(1, OFFENSIVE_STAGES + 1))


def path_in(settings_dir):
    return Path(settings_dir) / FILE_NAME


def load(settings_dir):
    """The file's contents, or None where there is no usable one."""
    try:
        data = json.loads(path_in(settings_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") != KIND:
        return None
    return data


def is_current(settings_dir):
    """Whether the logs have been read by this version of the reading."""
    data = load(settings_dir)
    return data is not None and data.get("version") == VERSION


def _addon(folder):
    """The capture addon, from its template, on an output folder of
    `folder` -- which must be empty, or it seeds itself from the newest
    snapshot there -- and saving nothing into it."""
    from capture.manager import ADDON_TEMPLATE
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     ITEM_NAMES={}, KNOWN_UNIT_IDS=set(), REGION_ROUTES={})
    addon = namespace["Addon"](Path(folder),
                               log_callback=lambda *a, **k: None)
    # **NOT optional.** Left alone, the addon writes a snapshot into its
    # folder after every frame that moves anything. Pinned by
    # `check_stats_history`.
    addon._save_data = lambda *a, **k: None
    return addon


class _Message:
    def __init__(self, text):
        self.text, self.is_text, self.from_client = text, True, False
        self.content = text.encode("utf-8")


class _Flow:
    def __init__(self, text):
        self.websocket = type("W", (), {"messages": [_Message(text)]})()


def _logs(snapshots_dir):
    """(name, text stream) for every debug log, oldest first, once each."""
    from capture import archive
    seen = set()
    for name, handle in archive.stream_members(snapshots_dir,
                                               "websocket_debug_"):
        if name not in seen:
            seen.add(name)
            yield name, io.TextIOWrapper(handle, encoding="utf-8",
                                         errors="replace")
    for path in sorted(Path(snapshots_dir).glob("websocket_debug_*.jsonl.gz")):
        name = archive.member_name(path)
        if name not in seen:
            seen.add(name)
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                yield path.name, fh


def read_logs(snapshots_dir):
    """Everything the old logs hold that a snapshot would keep.

    Also what no snapshot keeps as history: the account's own Great
    Rift standing and Sortie standing at every login, as one sample per
    change -- a snapshot holds only the latest of each.

    A log that ends inside a line -- a capture killed mid-write, or the
    one a running capture is still writing -- keeps what came before
    the break and is named under `cut_short`. Raising instead would
    leave the file unwritten, and every launch would try again and stop
    at the same place.
    """
    standings, sortie, logs, cut_short = {}, [], [], []
    with tempfile.TemporaryDirectory(prefix="stats_") as scratch:
        addon = _addon(scratch)
        for name, fh in _logs(snapshots_dir):
            logs.append(name)
            try:
                for line in fh:
                    _read_line(addon, line, standings, sortie)
            except (EOFError, OSError, zlib.error):
                cut_short.append(name)
    return {"kind": KIND, "version": VERSION, "logs": logs,
            "cut_short": cut_short,
            "disaster_boss_rank_tops": addon.rift_tops,
            "chaos_assault_rankings": addon.sortie_rankings,
            "remnants_rankings": addon.remnants_rankings,
            "disaster_boss_rank_standings": standings,
            "chaos_assault_standings": sortie,
            "mission_accumulate":
                list(addon.lifetime.get("mission_accumulate", {}).values()),
            "login_total_count": addon.login_total_count}


def _read_line(addon, line, standings, sortie):
    """Feed one debug-log line to the addon, if it can carry anything
    kept, and note the standings it leaves."""
    if '"server_to_client"' not in line[:300] or not any(
            marker in line for marker in MARKERS):
        return
    try:
        data = json.loads(line).get("data")
    except ValueError:
        return
    addon.websocket_message(_Flow(json.dumps(data)))
    rows = data if isinstance(data, list) else [data]
    at = next((r.get("service_server_time") for r in rows
               if isinstance(r, dict) and r.get("service_server_time")),
              None)
    _note_standings(addon.disaster_ranks, at, standings)
    entity = next((r.get("chaos_assault_entity") for r in rows
                   if isinstance(r, dict) and isinstance(
                       r.get("chaos_assault_entity"), dict)), None)
    if entity:
        sample = {"read_at": at,
                  "total_clear_count": entity.get("total_clear_count"),
                  "highest_clear_level": entity.get("highest_clear_level")}
        if not sortie or {k: v for k, v in sortie[-1].items()
                          if k != "read_at"} != {
                k: v for k, v in sample.items() if k != "read_at"}:
            sortie.append(sample)


def _note_standings(ranks, at, standings):
    """One sample per change of each half's own standing."""
    for season, halves in (ranks or {}).items():
        for half, row in (halves or {}).items() if isinstance(
                halves, dict) else ():
            if not isinstance(row, dict):
                continue
            sample = {"read_at": at, "rank": row.get("rank"),
                      "rank_id": row.get("rank_id"),
                      "best_score": row.get("best_score")}
            history = standings.setdefault(season, {}).setdefault(half, [])
            if not history or [history[-1].get(k) for k in
                               ("rank", "rank_id", "best_score")] != [
                    sample[k] for k in ("rank", "rank_id", "best_score")]:
                history.append(sample)


def write(settings_dir, data):
    """Write the file through a temp copy, so a half-written one never
    stands where a whole one did."""
    path = path_in(settings_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def read_in_background(snapshots_dir, settings_dir, say, done,
                       wait_for=None):
    """Read the old logs on a thread of their own, if they want reading.

    `wait_for` is a thread to let finish first: the archiver rewrites the
    archive this reads. `done()` is called from the thread when the file
    has been written, and must only set a flag. Nothing here may raise
    into the caller -- a thread that dies of an exception takes the
    report with it -- so anything unforeseen is said instead.
    Returns the thread, or None where the file is current.
    """
    if is_current(settings_dir):
        return None

    def work():
        try:
            if wait_for is not None:
                wait_for.join()
            data = read_logs(snapshots_dir)
            write(settings_dir, data)
        except Exception as exc:                              # noqa: BLE001
            say("[X] Reading old captures for stats stopped on %s: %s"
                % (type(exc).__name__, exc))
            return
        cut = (", %d of them cut short" % len(data["cut_short"])
               if data["cut_short"] else "")
        say("[OK] Stats read from %d old debug capture(s)%s."
            % (len(data["logs"]), cut))
        done()

    thread = threading.Thread(target=work, name="stats-history", daemon=True)
    thread.start()
    return thread


# ------------------------------------------------------------ readings

def merged(raw, history, key):
    """The snapshot's history under `key` joined with the file's.

    Rankings are {season: ...} tables of readings; a reading is one
    sample, and one taken at the same moment is the same sample. Beside
    its readings a season holds values the snapshot's copy of wins --
    the Sortie's `reset_time`, the Offensive's stage scores.
    """
    out = json.loads(json.dumps((history or {}).get(key) or {}))
    for season, value in ((raw or {}).get(key) or {}).items():
        mine = out.setdefault(season, {})
        if key in ("chaos_assault_rankings", "remnants_rankings"):
            for field, held in (value or {}).items():
                if field == "readings":
                    _join(mine.setdefault("readings", []), held)
                elif isinstance(held, dict):
                    mine.setdefault(field, {}).update(held)
                elif held is not None:
                    mine[field] = held
        else:
            for half, subdivisions in (value or {}).items():
                held = mine.setdefault(half, {})
                for rank_id, samples in (subdivisions or {}).items():
                    _join(held.setdefault(rank_id, []), samples)
    return out


def _join(into, samples):
    """Add `samples` not already in `into`, oldest first."""
    seen = {s.get("read_at") for s in into}
    into.extend(s for s in samples or () if s.get("read_at") not in seen)
    into.sort(key=lambda s: s.get("read_at") or 0)


def subdivision(rank_id):
    """(number, 'Diamond II', share reached) for a Great Rift `rank_id`,
    or None where it is not on the thirty-step scale."""
    found = RANK_ID.search(str(rank_id or ""))
    return numbered(int(found.group(2))) if found else None


def numbered(number):
    """`subdivision` for the subdivision's number, 1 to 30."""
    if not 1 <= number <= len(SHARES):
        return None
    division = DIVISIONS[(number - 1) // len(TIERS)]
    tier = TIERS[(number - 1) % len(TIERS)]
    return number, "%s %s" % (division, tier), SHARES[number - 1]


def field_size(tops):
    """How many accounts are ranked, from one half's subdivision tops.

    A subdivision's top row stands one below everyone above it, and
    everyone above it is the share the subdivision ABOVE reaches down to
    -- so the lowest subdivision read gives the field most precisely.
    None where no subdivision below the very top has been read.
    """
    best = None
    for rank_id, samples in (tops or {}).items():
        found = subdivision(rank_id)
        if not found or not samples or found[0] >= len(SHARES):
            continue
        # The latest sample that HAS a rank: a recorded top carries
        # only its score.
        rank = next((s.get("rank") for s in reversed(samples)
                     if isinstance(s.get("rank"), int)), None)
        if rank is None or rank < 2:
            continue
        above = SHARES[found[0]]
        if best is None or above > best[0]:
            best = (above, rank)
    return None if best is None else round((best[1] - 1) / best[0])


def sortie_seasons(raw, history, shipped=None):
    """[(season number, latest reading, reset_time)], newest first.

    `shipped` is the program's own game facts (`shared_facts.py`). A
    season the account never read that they hold for its server comes
    as a reading of the field alone: no rank or score of its own. A
    season it did read keeps its own reading whole, so its share of the
    field is always of one moment."""
    seasons = merged(raw, history, "chaos_assault_rankings")
    out, read = [], set()
    for schedule, season in seasons.items():
        found = re.search(r"_s(\d+)$", schedule)
        readings = season.get("readings") or []
        if found and readings:
            out.append((int(found.group(1)), readings[-1],
                        season.get("reset_time")))
            read.add(schedule)
    for schedule, field in _shipped_fields(raw, shipped, "SORTIE").items():
        found = re.search(r"_s(\d+)$", schedule)
        if found and schedule not in read:
            out.append((int(found.group(1)),
                        {"total_count": field["players"],
                         "top_score": field.get("top_score")}, None))
    return sorted(out, key=lambda s: -s[0])


def _shipped_fields(raw, shipped, kind):
    """{season: field} of one shared kind, by its name in
    `shared_facts`, for the account's server. The module is imported
    only where something is shipped."""
    if not shipped:
        return {}
    import shared_facts
    return shared_facts.fields_for(shipped, getattr(shared_facts, kind),
                                   (raw or {}).get("detected_region"))


def rift_halves(raw, history, shipped=None):
    """[(season, half, standing, tops)] for every Great Rift half known
    on the account's server, newest first: one it has a standing in,
    one it read or the program ships tops of, and one with a recorded
    top (`RIFT_RECORDED_TOPS`). `standing` is empty for a half the
    account did not play, and `tops` is the half's {rank_id: samples},
    empty where nothing about its divisions is known.

    `shipped` is the program's own game facts (`shared_facts.py`), on
    the account's server only."""
    tops = merged(raw, history, "disaster_boss_rank_tops")
    region = (raw or {}).get("detected_region")
    if shipped:
        import shared_facts
        tops = shared_facts.tops_with(tops, shipped, region)
    _join_recorded(tops, region)
    out, seen = [], set()
    for season_id, halves in ((raw or {}).get(
            "disaster_boss_rank_entities") or {}).items():
        season = re.search(r"_s(\d+)$", season_id)
        for define_id, standing in (halves or {}).items():
            half = re.search(r"_rank_(\d+)$", define_id)
            if season and half and isinstance(standing, dict):
                out.append((int(season.group(1)), int(half.group(1)),
                            standing,
                            tops.get(season_id, {}).get(define_id, {})))
                seen.add((season_id, define_id))
    # A half with tops and no standing -- one the account only read the
    # ranking of, or one the program ships -- is a column of the field's
    # figures alone.
    for season_id, halves in tops.items():
        season = re.search(r"_s(\d+)$", str(season_id))
        for define_id, subdivisions in (halves.items() if isinstance(
                halves, dict) else ()):
            half = re.search(r"_rank_(\d+)$", str(define_id))
            if (season and half and subdivisions
                    and (season_id, define_id) not in seen):
                out.append((int(season.group(1)), int(half.group(1)), {},
                            subdivisions))
    # And a part with only a recorded final on the account's server.
    listed = {(h[0], h[1]) for h in out}
    out += [(season, half, {}, {})
            for (server, season, half) in RIFT_RECORDED_TOPS
            if server == region and (season, half) not in listed]
    return sorted(out, key=lambda h: (-h[0], -h[1]))


def _division_ids(season, half):
    """Each division's subdivision I's `rank_id`, in the list's order."""
    return ["disaster_s%02d_rank_best_%d_%d" % (season, half, number)
            for number in range(len(SHARES), 0, -len(TIERS))]


def _join_recorded(tops, region):
    """Join `region`'s recorded READINGS into `tops` as samples of their
    division tops, oldest first, so a list's latest sample is whichever
    of a capture's and a record's was read later. Finals are not joined:
    `rift_table` puts them over everything."""
    import calendar
    import time
    for (server, season, half), (read, _source, scores) in \
            RIFT_RECORDED_TOPS.items():
        if server != region or read == FINAL:
            continue
        at = calendar.timegm(time.strptime(read, "%Y-%m-%d %H:%M:%S"))
        held = tops.setdefault("disaster_s%02d" % season, {}).setdefault(
            "disaster_s%02d_rank_%02d" % (season, half), {})
        for rank_id, score in zip(_division_ids(season, half), scores):
            samples = held.setdefault(rank_id, [])
            if score is not None and at not in {x.get("read_at")
                                                for x in samples}:
                samples.append({"best_score": score, "read_at": at})
                samples.sort(key=lambda x: x.get("read_at") or 0)


# ------------------------------------------------------------- the lists
#
# Each table is (row labels, [(column heading, [cell, ...]), ...]), the
# newest column first. A cell is text, or None where nothing was read.

def _count(value):
    return value if isinstance(value, int) and value > 0 else None


def _thousands(value):
    return format(value, ",") if isinstance(value, int) else None


def _share_of(rank, field):
    return "%.1f%%" % (100.0 * rank / field) if rank and field else None


def sortie_table(raw, history, shipped=None):
    """The Sortie list: a column per season. A finished season's rank is
    its final one where Previous Sortie Ranking was opened after it
    ended, and the last one read during it otherwise. `shipped` as
    `sortie_seasons` takes it."""
    columns = []
    for number, reading, _reset in sortie_seasons(raw, history, shipped):
        rank = _count(reading.get("rank"))
        field = _count(reading.get("total_count"))
        columns.append((str(number), [
            _share_of(rank, field), _thousands(rank), _thousands(field),
            _thousands(reading.get("score")),
            _thousands(reading.get("top_score"))]))
    return SORTIE_ROWS, columns


def _top_of(tops, number):
    """The best score heading subdivision `number`'s list, as read last."""
    for rank_id, samples in (tops or {}).items():
        found = subdivision(rank_id)
        if found and found[0] == number and samples:
            return _thousands(samples[-1].get("best_score"))
    return None


def rift_table(raw, history, shipped=None):
    """The Great Rift list: a column per half, `4 p2` for season 4's
    second. `shipped` as `rift_halves` takes it.

    **A division's list starts at its subdivision I**, and the game lists
    a hundred places of each -- so the top score it shows for a division
    is subdivision I's, and no other subdivision's top is ever sent. The
    last rows are those, a division each, Master's first.

    A finished half's place is its `last_rank`, which is 0 while a half
    runs and set when it ends: read as the placing it finished on.
    `rank` on a finished half is the last one computed while the account
    was looking, and sits a little higher. The share of the field is
    worked out only where that half's division tops were read.
    """
    halves = rift_halves(raw, history, shipped)
    region = (raw or {}).get("detected_region")
    # Each division's subdivision I, Master's first: 30, 25, .. 5.
    tops_of = range(len(SHARES), 0, -len(TIERS))
    columns = []
    for season, half, standing, tops in halves:
        division_tops = [_top_of(tops, number) for number in tops_of]
        read, _source, scores = RIFT_RECORDED_TOPS.get(
            (region, season, half), (None, None, ()))
        if read == FINAL:
            for n, score in enumerate(scores):
                if score is not None:
                    division_tops[n] = _thousands(score)
        finished = bool(standing.get("last_rank_id"))
        rank = (_count(standing.get("last_rank")) if finished else None) \
            or _count(standing.get("rank"))
        found = subdivision(standing.get("last_rank_id")
                            or standing.get("rank_id"))
        field = field_size(tops)
        columns.append(("%d p%d" % (season, half), [
            RIFT_CODENAMES.get((season, half), RIFT_UNNAMED),
            _share_of(rank, field),
            "%g%%" % (found[2] * 100) if found else None,
            _thousands(rank),
            "~" + format(int(round(field, -1)), ",") if field else None,
            _thousands(standing.get("best_score"))] + division_tops))
    return RIFT_ROWS, columns


def offensive_table(raw, history, shipped=None):
    """The Full-Scale Offensive list: a column per Offensive, numbered as
    the game numbers them. The field is the rank over `rank_percent`,
    which the game states to two decimals -- so it is given to the
    hundred. The total is the stages' best scores summed, and each
    stage's follows it, in the order of their ids.

    `shipped` is the program's own game facts (`shared_facts.py`). An
    Offensive the account never read that they hold for its server is a
    column of the field alone, and one whose last reading states no
    percentage takes its field from them."""
    fields = _shipped_fields(raw, shipped, "OFFENSIVE")
    columns, read = [], set()
    for define_id, season in merged(raw, history,
                                    "remnants_rankings").items():
        found = re.search(r"(\d+)$", str(define_id))
        readings = season.get("readings") or []
        if not found or not readings:
            continue
        read.add(str(define_id))
        last = readings[-1]
        rank = _count(last.get("rank"))
        percent = last.get("rank_percent")
        if not isinstance(percent, (int, float)) or percent <= 0:
            percent = None
        held = season.get("stages") or {}
        stages = [held[stage] for stage in sorted(held)
                  if isinstance(held[stage], int)]
        scores = (stages + [None] * OFFENSIVE_STAGES)[:OFFENSIVE_STAGES]
        field = (int(round(rank * 100.0 / percent, -2)) if rank and percent
                 else (fields.get(str(define_id)) or {}).get("players"))
        columns.append((int(found.group(1)), [
            "%g%%" % percent if percent else None,
            _thousands(rank),
            "~" + format(field, ",") if field else None,
            _thousands(sum(stages)) if stages else None]
            + [_thousands(score) for score in scores]))
    for define_id, field in fields.items():
        found = re.search(r"(\d+)$", define_id)
        if found and define_id not in read:
            columns.append((int(found.group(1)), [
                None, None, "~" + format(field["players"], ","), None]
                + [None] * OFFENSIVE_STAGES))
    columns.sort(key=lambda c: -c[0])
    return OFFENSIVE_ROWS, [(str(n), cells) for n, cells in columns]
