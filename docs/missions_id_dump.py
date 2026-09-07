"""Rewrite `missions_id.tsv` from the newest capture that carries missions.

Run after a capture that claimed something:

    python docs/missions_id_dump.py

**A mission's id is a string, not a number** -- `content_01_01_01`,
`pass_mission_008_01` -- and its leading words say which SET it belongs
to. The dump groups by that, so a set reads as a block.

The columns this script owns:

| column          | wire field      | what it says                        |
| --------------- | --------------- | ----------------------------------- |
| `res_id`        | `res_id`        | the mission                         |
| `family`        | -               | the id's leading words              |
| `score`         | `score`         | progress; its scale is per mission  |
| `complete_time` | `complete_time` | **when it was finished**, or blank  |
| `issued_time`   | `issued_time`   | when the game handed it out         |
| `week_id`       | `week_id`       | which week it belongs to            |
| `pass_id`       | `pass_id`       | the season pass, where it is one    |

`complete_time` is the useful one: a row carrying it is done. A row
that never carries it is either untouched or of a kind that does not
report completion, and telling those two apart is what the hand-added
columns are for.

**This script owns those columns and nothing else.** Anything typed to
the right of them is read back and written out again untouched, in the
same order, so a mission named by hand survives the next run. It
refuses to write at all if the header has moved under it, because every
hand-typed cell would shift by the difference.

**Two sources, and the newest snapshot is usually not one of them.**
`mission_entities` reaches the wire only on a claim, and the addon's
cache is per-session -- so a session where nothing was claimed writes
no missions at all, and the dump has to reach further back than the
last capture. It takes the newest SNAPSHOT that carries them, and
failing that the newest WebSocket debug log, which holds the frames
whether or not the addon of the day knew to keep them. Finding neither
it leaves the file alone rather than blanking it.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "Vribbels" / "snapshots"
OUT = Path(__file__).resolve().parent

# The key both sources carry them under, and the columns this script
# owns.
FIELD = "mission_entities"
OWNED = ("res_id", "family", "score", "complete_time", "issued_time",
         "week_id", "pass_id")

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


def _row_values(row):
    """One mission's owned cells, in `OWNED` order after the id."""
    return (
        family_of(str(row.get("res_id", ""))),
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
        for key, value in payload.items():
            if key == FIELD:
                rows = value.values() if isinstance(value, dict) else value
                for row in rows or ():
                    if isinstance(row, dict) and row.get("res_id"):
                        into[str(row["res_id"])] = _row_values(row)
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
    """
    for path in sorted(SNAPSHOTS.glob("websocket_debug_*.jsonl"),
                       reverse=True):
        rows = {}
        with path.open(encoding="utf-8") as handle:
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
    """(user column names, {res_id: their values}) from a file on disk."""
    if not path.exists():
        return [], {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [], {}
    header = lines[0].split("\t")
    if header[:len(OWNED)] != list(OWNED):
        raise SystemExit(
            f"{path.name} starts with columns {header[:len(OWNED)]}, not "
            f"{list(OWNED)}. Rewriting it would move every hand-typed cell "
            f"into a neighbouring column. Reconcile the header first."
        )
    extra = header[len(OWNED):]
    kept = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        if not cells[0].strip():
            continue
        tail = cells[len(OWNED):]
        kept[cells[0]] = tail + [""] * (len(extra) - len(tail))
    return extra, kept


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
    extra, kept = read_existing(path)
    if not path.exists():
        extra = list(SEED)
    # By set, then by id inside it, so a set reads as a block rather
    # than being scattered by one alphabetical order over everything.
    order = sorted(set(rows) | set(kept),
                   key=lambda res_id: (rows.get(res_id, (family_of(res_id),))[0],
                                       res_id))
    # A mission this capture did not carry keeps its row and its
    # hand-typed cells; the columns this script owns go blank for it,
    # because a stale `complete_time` reads exactly like a current one.
    blank = [""] * (len(OWNED) - 1)
    gone = []
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join(list(OWNED) + extra) + "\n")
        for res_id in order:
            values = rows.get(res_id)
            if values is None:
                values = blank
                gone.append(res_id)
            tail = kept.get(res_id, [""] * len(extra))
            handle.write("\t".join(str(cell) for cell in
                                   [res_id, *values, *tail]) + "\n")

    families = sorted({rows[res_id][0] for res_id in rows})
    print(f"from {source}")
    print(f"{path.name}: {len(order)} rows, {len(extra)} hand-added columns"
          + (f", {len(gone)} not in this capture" if gone else ""))
    print("  sets: " + ", ".join(
        f"{family} x{sum(1 for r in rows.values() if r[0] == family)}"
        for family in families))


if __name__ == "__main__":
    main()
