"""Rewrite `missions_id.tsv` from the newest capture that carries missions.

Run after a capture that claimed something:

    python docs/missions_id_dump.py

**A mission's id is a string, not a number** -- `pass_mission_008_01`,
`daily_achieve_004` -- and its leading words say which SET it belongs
to. The dump groups by that, so a set reads as a block, and
`SKIP_FAMILIES` is what keeps the sets nobody tracks out.

**A pass mission's id carries the SEASON, and the season increments.**
`pass_mission_008_01` becomes `pass_mission_009_01` when season 9
opens, and keying the file on the raw id would strand every hand-typed
name on a row nothing writes to again. Rows are keyed on `key`
instead -- the id with its season replaced by `*` -- so one row per
mission survives every season, and `res_id` says which season last
filled it.

The columns this script owns:

| column          | wire field      | what it says                        |
| --------------- | --------------- | ----------------------------------- |
| `key`           | -               | the id with its season as `*`       |
| `res_id`        | `res_id`        | the mission, as last seen           |
| `family`        | -               | the id's leading words              |
| `score`         | `score`         | progress; its scale is per mission  |
| `complete_time` | `complete_time` | **when it was finished**, or blank  |
| `issued_time`   | `issued_time`   | when the game handed it out         |
| `week_id`       | `week_id`       | which week it belongs to            |
| `pass_id`       | `pass_id`       | the season pass, where it is one    |
| `seen`          | -               | the capture the row above came from |

`complete_time` is the useful one: a row carrying it is done. A row
that never carries it is either untouched or of a kind that does not
report completion, and telling those two apart is what the hand-added
columns are for.

The run says how many rows are NEW to the file and names them: a key
it has never held is a set nothing has dumped yet or a season opening,
where the rest of a run is known rows being refreshed in place.

**This script owns those columns and nothing else.** Anything typed to
the right of them is read back and written out again untouched, in the
same order, so a mission named by hand survives the next run. It
refuses to write at all if the header has moved under it, because every
hand-typed cell would shift by the difference.

**A row the current capture does not carry KEEPS what it had**, with
`seen` saying which capture that came from. The file is an accumulating
record: one capture holds the login burst's rows and another holds a
claim's, so blanking what is missing throws away readings the next run
may not get back.

**Two sources, and the newest snapshot is usually not one of them.**
`mission_entities` reaches the wire only on a claim, and the addon's
cache is per-session -- so a session where nothing was claimed writes
no missions at all, and the dump has to reach further back than the
last capture. It takes the newest SNAPSHOT that carries them, and
failing that the newest WebSocket debug log, which holds the frames
whether or not the addon of the day knew to keep them. Finding neither
it leaves the file alone rather than blanking it.
"""

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "Vribbels" / "snapshots"
OUT = Path(__file__).resolve().parent

# The key both sources carry them under, and the columns this script
# owns.
FIELD = "mission_entities"
OWNED = ("key", "res_id", "family", "score", "complete_time", "issued_time",
         "week_id", "pass_id", "seen")

# What replaces a season number in a `key`.
SEASON = "*"

# Families this file does not track. `content_*` are the BASIN OF
# HYPERSPACE's objectives -- they arrive with `hyperspace/get_list`,
# three per stage, and the Checklist reads their tally as the Basin's
# progress rather than naming them one by one. Thirty of them drowned
# the rows worth annotating.
SKIP_FAMILIES = ("content",)

# Written into a file that does not exist yet, and never again -- the
# hand-added columns are read back off the header from then on. They
# are here so a fresh dump says where to type rather than being seven
# columns of wire fields and no invitation.
SEED = ("Name", "Notes")


def family_of(res_id):
    """The id's leading words: `pass_mission_008_01` -> `pass_mission`.

    Split at the first numbered segment rather than at the last
    underscore -- the numbers are the mission WITHIN its set, and how
    many of them an id carries varies between sets.
    """
    parts = []
    for part in res_id.split("_"):
        if part.isdigit():
            break
        parts.append(part)
    return "_".join(parts) or res_id


def key_of(res_id, pass_id):
    """The id with its season generalised: `pass_mission_*_01`.

    The season is not guessed from the id's shape. It is the number the
    row's own `pass_id` carries -- `season_pass_008` -> `008` -- and
    only a segment equal to that is replaced, so a mission whose number
    happens to match its chapter is left alone. A row with no pass keeps
    its id.
    """
    season = str(pass_id or "").rsplit("_", 1)[-1]
    if not season.isdigit():
        return res_id
    return "_".join(SEASON if part == season else part
                    for part in res_id.split("_"))


def _row_values(row):
    """One mission's owned cells, in `OWNED` order after the key."""
    res_id = str(row.get("res_id", ""))
    return (
        res_id,
        family_of(res_id),
        row.get("score", ""),
        row.get("complete_time", ""),
        row.get("issued_time", ""),
        row.get("week_id", ""),
        row.get("pass_id", ""),
    )


def _collect(payload, into):
    """Fold every `mission_entities` under `payload` into `into`.

    The key arrives nested at a depth that differs between the two
    sources, and in two SHAPES: a snapshot holds the addon's cache,
    already keyed by res_id, while the wire sends a plain list. Later
    rows win, which is what makes a claim's `complete_time` override
    the login burst's bare score for the same mission.
    """
    if isinstance(payload, dict):
        for field, value in payload.items():
            if field == FIELD:
                rows = value.values() if isinstance(value, dict) else value
                for row in rows or ():
                    if not isinstance(row, dict) or not row.get("res_id"):
                        continue
                    res_id = str(row["res_id"])
                    if family_of(res_id) in SKIP_FAMILIES:
                        continue
                    into[key_of(res_id, row.get("pass_id"))] = _row_values(row)
            else:
                _collect(value, into)
    elif isinstance(payload, list):
        for value in payload:
            _collect(value, into)


def from_snapshots():
    """(name, rows) from the newest snapshot that carries missions."""
    for path in sorted(SNAPSHOTS.glob("memory_fragments_*.json"),
                       reverse=True):
        rows = {}
        _collect(json.loads(path.read_text(encoding="utf-8")), rows)
        if rows:
            return path.name, rows
    return None, {}


def from_debug_logs():
    """(name, rows) from the newest debug log that carries missions.

    One JSON record per line, and a line that will not parse is skipped
    rather than stopping the read: a log can be cut off mid-write by
    the capture ending.

    **Both spellings.** Captures are written `.jsonl.gz` now -- one
    gzip member per line, so it still reads a line at a time -- and the
    plain `.jsonl` ones taken before that are still on disk. Sorting
    the two together works because the timestamp is in the stem.
    """
    logs = (list(SNAPSHOTS.glob("websocket_debug_*.jsonl"))
            + list(SNAPSHOTS.glob("websocket_debug_*.jsonl.gz")))
    for path in sorted(logs, key=lambda p: p.name, reverse=True):
        rows = {}
        opener = (gzip.open if path.suffix == ".gz" else open)
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if FIELD not in line:
                    continue
                try:
                    _collect(json.loads(line), rows)
                except ValueError:
                    continue
        if rows:
            return path.name, rows
    return None, {}


def read_existing(path):
    """(user columns, {key: their cells}, {key: its owned cells}).

    The third is what lets a row the current capture does not carry keep
    what the last one gave it.
    """
    if not path.exists():
        return [], {}, {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [], {}, {}
    header = lines[0].split("\t")
    if header[:len(OWNED)] != list(OWNED):
        raise SystemExit(
            f"{path.name} starts with columns {header[:len(OWNED)]}, not "
            f"{list(OWNED)}. Rewriting it would move every hand-typed cell "
            f"into a neighbouring column. Reconcile the header first."
        )
    extra = header[len(OWNED):]
    kept, before = {}, {}
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        if not cells[0].strip():
            continue
        tail = cells[len(OWNED):]
        kept[cells[0]] = tail + [""] * (len(extra) - len(tail))
        owned = cells[1:len(OWNED)]
        before[cells[0]] = owned + [""] * (len(OWNED) - 1 - len(owned))
    return extra, kept, before


def few(values, limit=10):
    """`values` as one line, cut short so a first run stays readable."""
    shown = ", ".join(str(value) for value in values[:limit])
    over = len(values) - limit
    return shown + (f", +{over} more" if over > 0 else "")


def main():
    source, rows = from_snapshots()
    if not rows:
        source, rows = from_debug_logs()
    if not rows:
        raise SystemExit(
            "no snapshot and no debug log in Vribbels/snapshots/ carries "
            f"`{FIELD}`. Capture with something claimed; the file on disk "
            "is left as it is."
        )

    path = OUT / "missions_id.tsv"
    extra, kept, before = read_existing(path)
    if not path.exists():
        extra = list(SEED)
    # By set, then by key inside it, so a set reads as a block rather
    # than being scattered by one alphabetical order over everything.
    order = sorted(set(rows) | set(kept),
                   key=lambda k: (rows[k][1] if k in rows else family_of(k),
                                  k))
    # **A mission this capture did not carry KEEPS what it had**, and
    # `seen` says which capture that was. The file accumulates: one
    # capture holds the login burst's rows and another holds a claim's,
    # so blanking what is absent throws away a reading nothing else
    # will supply.
    blank = [""] * (len(OWNED) - 1)
    gone = []
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join(list(OWNED) + extra) + "\n")
        for key in order:
            values = rows.get(key)
            if values is None:
                values = before.get(key) or blank
                gone.append(key)
            else:
                values = list(values) + [source]
            tail = kept.get(key, [""] * len(extra))
            handle.write("\t".join(str(cell) for cell in
                                   [key, *values, *tail]) + "\n")

    # **New rows are the point of a run.** A mission key the file has
    # never held is either a set nothing has dumped yet or a season
    # opening, and both want looking at -- where the rest of the run is
    # a file of known rows being refreshed in place.
    fresh = [key for key in order if key not in kept]
    families = sorted({row[1] for row in rows.values()})
    print(f"from {source}")
    print(f"{path.name}: {len(order)} rows, {len(extra)} hand-added columns"
          + (f", {len(gone)} kept from an earlier capture" if gone else ""))
    print(f"  {len(fresh)} new row(s)" + (f": {few(fresh)}" if fresh else ""))
    print("  sets: " + ", ".join(
        f"{family} x{sum(1 for r in rows.values() if r[1] == family)}"
        for family in families))


if __name__ == "__main__":
    main()
