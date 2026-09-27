"""The Chaos runs the capture records, in a file of their own:
`snapshots/chaos_runs/runs.json.gz`.

**Every run ever recorded, and each once.** A snapshot carried the runs
before this file did, so every snapshot repeated all of them and a cap
had to bound the repeat. Here a run is added when it clears and never
changed after, so the file grows by one run's record at a time, with no
cap. gzip, whose decoding costs next to nothing beside the disk read.

Kept apart the way the Gacha History is (`docs/gacha_history.md`, *The
files*): a subfolder, because the snapshots folder is the one users
empty and `capture/archive.py` sweeps only its top level; ONE writer,
the capture addon; and every write goes through a checked copy that
keeps the file it replaces as `<name>.bak` -- `Addon._write_chaos_store`.
A reader here falls back to that backup as the addon does: a write
renames the file to it before the new copy lands, so a capture killed
between the two leaves only the backup.

No Tk: the Checklist and `docs/chaos_runs.py` both read through this.
"""

import gzip
import json
from pathlib import Path

FOLDER = "chaos_runs"
FILE = "runs.json.gz"
KIND = "vribbels chaos runs"
BACKUP = ".bak"

# (path, size, modified) -> runs, so a tab redrawing reads the file
# once per change rather than once per redraw.
_CACHE = {}


def path_in(snapshots):
    """Where the runs' file sits under a snapshots folder."""
    return Path(snapshots) / FOLDER / FILE


def read(snapshots):
    """(runs, note): the recorded runs, oldest first, and a note where
    the file had to be read from its backup or could not be read at
    all; [] and None where there is no file yet."""
    path = path_in(snapshots)
    tried = []
    for candidate in (path, path.with_name(path.name + BACKUP)):
        if not candidate.exists():
            continue
        try:
            with gzip.open(candidate, "rt", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, EOFError) as e:
            tried.append("%s: %s" % (candidate.name, e))
            continue
        runs = data.get("runs") if isinstance(data, dict) else None
        if not isinstance(runs, list):
            tried.append("%s: not a Chaos runs file" % candidate.name)
            continue
        note = None
        if candidate != path:
            note = "%s is missing or unreadable; read its backup" % path.name
        return [run for run in runs if isinstance(run, dict)], note
    return [], ("; ".join(tried) if tried else None)


def runs(snapshots):
    """The recorded runs, read once per change to the file."""
    path = path_in(snapshots)
    try:
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
    except OSError:
        key = (str(path), None, None)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = read(snapshots)[0]
    return list(_CACHE[key])


def merged(*sources):
    """Runs from several sources as one list, oldest first: a run is
    one run however many hold it, by the second it cleared."""
    by_closed = {}
    for source in sources:
        for run in source or ():
            if isinstance(run, dict) and run.get("closed") is not None:
                by_closed.setdefault(run["closed"], run)
    return [by_closed[closed] for closed in sorted(by_closed)]
