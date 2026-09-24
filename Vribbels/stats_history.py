"""Standings and lifetime stats: the history a snapshot carries, and the
part of it only old debug captures hold.

The capture keeps the Great Rift's and the Sortie's ranking readings and
the lifetime counters in every snapshot, each carried forward into the
next (`capture/manager.py`, `_seed_from_previous`). Captures taken before
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

What the Stats sheets show is worked out here too, as plain data --
`sortie_seasons` and `rift_halves` -- so it is testable without Tk.
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
VERSION = 1

# A frame is parsed only where its text carries one of these: the keys
# of everything the reading keeps. Every other frame is skipped unread,
# which is what keeps a pass over a year of logs to seconds.
MARKERS = ('"my_rank"', '"result_list"', '"mission_accumulate"',
           '"disaster_boss_rank_entit', '"login_total_count"',
           '"accumulate_condition"', '"achievement_entity"',
           '"chaos_assault_entity"')

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
    sample, and one taken at the same moment is the same sample.
    """
    out = json.loads(json.dumps((history or {}).get(key) or {}))
    for season, value in ((raw or {}).get(key) or {}).items():
        mine = out.setdefault(season, {})
        if key == "chaos_assault_rankings":
            mine["reset_time"] = value.get("reset_time",
                                           mine.get("reset_time"))
            _join(mine.setdefault("readings", []), value.get("readings"))
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
    if not found:
        return None
    number = int(found.group(2))
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
        rank = samples[-1].get("rank")
        if not isinstance(rank, int) or rank < 2:
            continue
        above = SHARES[found[0]]
        if best is None or above > best[0]:
            best = (above, rank)
    return None if best is None else round((best[1] - 1) / best[0])


def sortie_seasons(raw, history):
    """[(season number, latest reading, reset_time)], newest first."""
    seasons = merged(raw, history, "chaos_assault_rankings")
    out = []
    for schedule, season in seasons.items():
        found = re.search(r"_s(\d+)$", schedule)
        readings = season.get("readings") or []
        if found and readings:
            out.append((int(found.group(1)), readings[-1],
                        season.get("reset_time")))
    return sorted(out, key=lambda s: -s[0])


def rift_halves(raw, history):
    """[(season, half, standing, tops)] for every Great Rift half the
    account has a standing in, newest first. `tops` is that half's
    {rank_id: samples}, empty where its ranking was never opened."""
    tops = merged(raw, history, "disaster_boss_rank_tops")
    out = []
    for season_id, halves in ((raw or {}).get(
            "disaster_boss_rank_entities") or {}).items():
        season = re.search(r"_s(\d+)$", season_id)
        for define_id, standing in (halves or {}).items():
            half = re.search(r"_rank_(\d+)$", define_id)
            if season and half and isinstance(standing, dict):
                out.append((int(season.group(1)), int(half.group(1)),
                            standing,
                            tops.get(season_id, {}).get(define_id, {})))
    return sorted(out, key=lambda h: (-h[0], -h[1]))
