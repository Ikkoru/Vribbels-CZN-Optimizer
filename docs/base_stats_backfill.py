"""Fold the battles in the debug logs into the base stat readings, and
report what they say about characters.py.

The capture files every battle's base stat readings as it runs
(`Addon._note_base_stats`, `Vribbels/base_stats_store.py`). The debug
logs taken before it did hold the same battles -- the loose ones and
those folded into `archived_captures.tar.xz` -- and this walks them all
through the real addon and files what they hold. Older logs are what
show a patch: a base stat that changed reads as two plain readings.

    python docs/base_stats_backfill.py            # report only
    python docs/base_stats_backfill.py --write    # file them, then report
    python docs/base_stats_backfill.py --battles  # and list every battle

**The real addon does the reading.** The addon is built from its
template exactly as a capture builds it, each client request goes
through `_note_command` so a reply is tied to what asked for it, and
each server reply through `_note_base_stats`. Nothing else in the addon
runs, so no snapshot is written. A battle already on file is recognised
and only its last sighting moves, so running it twice files nothing
twice.

**The report is `base_stats_store.audit`**: which combatants
characters.py has wrong or lacks, what a level-61 or 62 gain is where
the program does not know it, which base stats changed between plain
readings (a patch), and who has not yet appeared in a plain battle --
take those into any stage outside Chaos during a debug capture.
"""

import glob
import gzip
import io
import json
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
SNAPSHOTS = SOURCE / "snapshots"
sys.path.insert(0, str(SOURCE))


def _addon(folder):
    """The capture addon on `folder`, writing nothing until asked."""
    import base_stats_store
    import chaos_store
    from capture.manager import ADDON_TEMPLATE
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     ITEM_NAMES={}, KNOWN_UNIT_IDS=set(), REGION_ROUTES={},
                     CHAOS_FOLDER=chaos_store.FOLDER,
                     CHAOS_FILE=chaos_store.FILE, CHAOS_KIND=chaos_store.KIND,
                     BASE_FOLDER=base_stats_store.FOLDER,
                     BASE_FILE=base_stats_store.FILE,
                     BASE_KIND=base_stats_store.KIND)
    addon = namespace["Addon"](Path(folder), log_callback=print)
    real_write = addon._write_base_store
    # One write at the end, not one per battle.
    addon._write_base_store = lambda *a, **k: True
    return addon, real_write


def _logs():
    """(name, open it) for every debug log: the ones folded into the
    capture archive first, then the loose ones, each oldest first."""
    out = []
    archive = SNAPSHOTS / "archived_captures.tar.xz"
    if archive.exists():
        tar = tarfile.open(archive, "r:xz")
        members = sorted((m for m in tar.getmembers()
                          if Path(m.name).name.startswith("websocket_debug_")),
                         key=lambda m: Path(m.name).name)
        for m in members:
            out.append((Path(m.name).name, lambda m=m: io.TextIOWrapper(
                tar.extractfile(m), encoding="utf-8")))
    for name in sorted(glob.glob(str(SNAPSHOTS / "websocket_debug_*.jsonl*"))):
        opener = gzip.open if name.endswith(".gz") else open
        out.append((Path(name).name, lambda name=name, opener=opener:
                    opener(name, "rt", encoding="utf-8")))
    return out


def _replay(addon, open_log):
    """Feed one debug log's frames to the addon; how many battles it
    carried."""
    battles = 0
    with open_log() as fh:
        for line in fh:
            if '"qid"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            data = entry.get("data")
            if entry.get("direction") == "client_to_server":
                for command in data if isinstance(data, list) else ():
                    if isinstance(command, dict):
                        addon._note_command(command)
            elif isinstance(data, dict) and data.get("res") == "ok":
                if '"enter_chars"' in line:
                    battles += 1
                addon._note_base_stats(
                    addon.qid_commands.get(data.get("qid")), data)
    return battles


def _when(stamp):
    try:
        return datetime.fromtimestamp(float(stamp)).strftime(
            "%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(stamp)


def main(argv):
    import base_stats_store
    write = "--write" in argv
    folder = SNAPSHOTS if write else Path(tempfile.mkdtemp())
    if not write:
        # A report starts from what is on file, in a scratch copy.
        stored, _note = base_stats_store.read(SNAPSHOTS)
        target = base_stats_store.path_in(folder)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"kind": base_stats_store.KIND,
                                      "version": 1, "battles": stored}),
                          encoding="utf-8")
    addon, real_write = _addon(folder)
    for name, open_log in _logs():
        print("%-45s %4d battle entries" % (name, _replay(addon, open_log)))
    battles = addon.base_battles or []
    print("%d distinct battles on file%s" % (
        len(battles), "" if write else " (not written: --write files them)"))
    if write and addon.base_battles:
        real_write()

    found = base_stats_store.audit(battles)
    if "--battles" in argv:
        from game_data.characters import CHARACTERS
        plain = {id(b) for b in base_stats_store.plain_battles(battles)}
        print()
        print("BATTLES: last seen, mode, stage, Zero System, plain, who")
        for b in sorted(battles, key=lambda b: b.get("last") or 0):
            who = ", ".join(
                "%s %s" % ((CHARACTERS.get(r.get("res_id")) or {}).get(
                    "name", r.get("res_id")), r.get("level"))
                for r in b.get("chars") or [])
            print("  %s %-24s %-8s %-5s %-5s %s" % (
                _when(b.get("last")), b.get("content"), b.get("stage"),
                b.get("zero_system"), id(b) in plain, who))
    print()
    print("WRONG in characters.py (newest plain reading):")
    for name, level, wire, program, last in found["differs"]:
        print("  %-12s lvl %-3s server %-17s characters.py %-17s (%s)" % (
            name, level, wire, program, _when(last)))
    print("MISSING from characters.py:")
    for rid, level, wire, last in found["missing"]:
        print("  res_id %-8s lvl %-3s server %s (%s)" % (rid, level, wire,
                                                       _when(last)))
    print("LEVEL GAINS the program does not know (server minus level 60):")
    for name, cls, grade, level, gain in found["gains"]:
        print("  %-12s %s grade %s, level %s: %s" % (name, cls, grade, level,
                                                   gain))
    print("CHANGED between plain readings (a patch?):")
    for name, level, older, newer, old_last, new_first in found["changed"]:
        print("  %-12s lvl %-3s %s until %s, %s from %s" % (
            name, level, older, _when(old_last), newer, _when(new_first)))
    print("NOT YET IN A PLAIN BATTLE:")
    print("  " + (", ".join(found["unseen"]) or "-"))


if __name__ == "__main__":
    main(sys.argv[1:])
