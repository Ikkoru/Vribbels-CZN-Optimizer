"""Fold the captures taken before the catalogue into it.

`docs/wire_catalogue.py` reports what the wire has sent that nothing
reads, off a record the capture keeps as it runs. That record begins
the day the capture learned to keep one, and the debug logs already on
disk are older than it. This walks those and files what they hold under
the same `command|key` pairs, so the record reaches back to the first
capture ever taken.

    python docs/wire_catalogue_backfill.py            # what it WOULD add
    python docs/wire_catalogue_backfill.py --write    # add it
    python docs/wire_catalogue_backfill.py --file X --write   # elsewhere
    python docs/wire_catalogue_backfill.py --all      # compressed ones too
    python docs/wire_catalogue_backfill.py --again    # re-read mined files

**It reports by default and writes only when told to.** The catalogue
is a record built up over months and a merge ADDS counts, so a run
nobody asked for is not undoable by running it again.

**The uncompressed captures are the ones that predate the catalogue.**
Compression and the catalogue arrived in the same change, so a `.jsonl`
capture is from before there was a catalogue and a `.jsonl.gz` was
catalogued live as it was taken -- folding those in counts one sighting
twice. `--all` takes them anyway, for a catalogue that was moved or
lost.

Files already folded in are listed in `wire_catalogue_mined.json`
beside the catalogue and skipped on the next run; `--again` ignores
that list.

**The real addon does the reading.** This generates the capture addon
exactly as a capture does, imports it, and hands it the logged frames
in order -- so what is recorded is what the live capture would have
recorded, down to the `helo` that clears the qid table. Only the CLOCK
is replaced: a sighting is filed under the frame's own timestamp, and
reaching back is the whole point.
"""

import gzip
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "Vribbels"
SNAPSHOTS = SOURCE / "snapshots"
CATALOGUE = SOURCE / "settings" / "wire_catalogue.json"

# What has been folded in already, beside whichever catalogue is used.
MINED = "wire_catalogue_mined.json"

# How many new pairs to print in full before falling back to a count.
SHOW = 60


class _Clock(datetime):
    """`datetime` with `now()` answering for the frame being replayed.

    The addon stamps a sighting with the moment it saw it, which in a
    replay is today -- and a first-seen date of today is exactly the
    fact this run exists to correct. Subclassed rather than stubbed so
    every other classmethod the addon reaches for still works.
    """

    at = datetime.now()

    @classmethod
    def now(cls, tz=None):
        return cls.at


def load_addon(work):
    """The real capture addon, built and imported as a capture builds it.

    `work` takes the generated script and anything the addon decides to
    write, so nothing of this lands in the maintainer's snapshots.
    """
    sys.path.insert(0, str(SOURCE))
    from capture.manager import CaptureManager       # noqa: E402

    manager = CaptureManager(work, log_callback=lambda *a, **k: None)
    script = manager._generate_addon_script(debug_mode=False)
    spec = importlib.util.spec_from_file_location("_backfill_addon", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # **The one substitution.** `_note_keys` dates a sighting with
    # `datetime.now()`, and the module holds that name itself.
    module.datetime = _Clock
    return module


def frames(path):
    """Every logged frame of one capture, in the order it arrived."""
    opener = gzip.open if path.suffix == ".gz" else io.open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue                 # a half-written last line


def replay(addon, frame):
    """One logged frame through the addon's own catalogue readers.

    Returns 1 for a reply that was catalogued, 0 otherwise.
    """
    stamp = frame.get("ts")
    if stamp:
        try:
            _Clock.at = datetime.fromisoformat(str(stamp))
        except ValueError:
            pass                         # keep the last good stamp
    data = frame.get("data")
    if frame.get("direction") == "client_to_server":
        for entry in data if isinstance(data, list) else ():
            if not isinstance(entry, dict):
                continue
            # **A connection restarts its qids at 1.** The live addon
            # clears the table on `helo` for that reason, and a replay
            # that did not would file a reply's keys under whatever
            # asked the same number in the previous connection.
            if entry.get("cmd") == "helo":
                addon.qid_commands.clear()
            else:
                addon._note_command(entry)
        return 0
    if not isinstance(data, dict):
        return 0
    addon._note_keys(data)
    return 1


def captures(every):
    """The debug logs to read, oldest first."""
    found = list(SNAPSHOTS.glob("websocket_debug_*.jsonl"))
    if every:
        found += list(SNAPSHOTS.glob("websocket_debug_*.jsonl.gz"))
    return sorted(found, key=lambda path: path.name)


def already_mined(ledger):
    """The capture filenames a previous run folded in."""
    if not ledger.exists():
        return set()
    try:
        held = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    names = held.get("files") if isinstance(held, dict) else None
    return set(names) if isinstance(names, list) else set()


def main(argv):
    argv = list(argv[1:])
    write = "--write" in argv
    again = "--again" in argv
    every = "--all" in argv
    book = CATALOGUE
    if "--file" in argv:
        at = argv.index("--file")
        book = Path(argv[at + 1]).resolve()
        del argv[at:at + 2]

    found = captures(every)
    if not found:
        print("No debug captures in %s." % SNAPSHOTS)
        print("They are written when Debug WS is ticked on the Capture tab.")
        return 1
    ledger = book.parent / MINED
    done = set() if again else already_mined(ledger)
    todo = [path for path in found if path.name not in done]
    print("%d capture(s), %d already folded in, %d to read"
          % (len(found), len(found) - len(todo), len(todo)))
    if not todo:
        return 0

    work = Path(tempfile.mkdtemp(prefix="wire_backfill_"))
    try:
        module = load_addon(work)
        addon = type(module.addons[0])(
            work, dict_path=module.DICT_PATH,
            log_callback=lambda *a, **k: None,
            debug_mode=False, catalogue_path=book)

        replies = 0
        for path in todo:
            for frame in frames(path):
                replies += replay(addon, frame)

        held = addon._read_catalogue()
        seen = addon.catalogue
        fresh = sorted(name for name in seen if name not in held)
        earlier = sorted(
            (name for name, row in seen.items()
             if name in held
             and str(row["first"]) < str(held[name].get("first") or "")),
            key=lambda name: seen[name]["first"])

        print("%d replies read, %d command|key pair(s) seen, %d of them new"
              % (replies, len(seen), len(fresh)))
        if fresh:
            width = min(52, max(len(name) for name in fresh))
            print()
            print("%-*s  %6s  %-19s  %s"
                  % (width, "command|key", "seen", "first seen", "sample"))
            for name in fresh[:SHOW]:
                row = seen[name]
                print("%-*s  %6d  %-19s  %s"
                      % (width, name[:width], row["count"],
                         str(row["first"])[:19], str(row["sample"])[:58]))
            if len(fresh) > SHOW:
                print("... and %d more" % (len(fresh) - SHOW))
        if earlier:
            print()
            print("%d pair(s) would be dated earlier than the catalogue has "
                  "them:" % len(earlier))
            for name in earlier[:SHOW]:
                print("  %-52s %s -> %s"
                      % (name[:52], str(held[name].get("first"))[:19],
                         str(seen[name]["first"])[:19]))

        if not write:
            print()
            print("Nothing written. `--write` folds this into %s." % book)
            return 0

        addon._write_catalogue()
        ledger.write_text(
            json.dumps({"files": sorted(done | {p.name for p in todo})},
                       indent=1),
            encoding="utf-8")
        print()
        print("Folded into %s; %s lists what has been read."
              % (book, ledger.name))
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
