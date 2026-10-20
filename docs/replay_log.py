"""Replay debug captures through the real capture addon, into a scratch
folder: what the program would have logged and saved from them.

    python docs/replay_log.py [log ...] [--until WHEN] [--seed] [--quick] [--keep]

A `log` is a debug capture's name or the start of its stamp
(`20261020`, `20261020_0133`): every capture it matches, loose in
`Vribbels/snapshots/` or in their archive. With none named, the newest
loose one. Several replay in order into one folder, each through a fresh
addon, as a restart does, so each seeds from what the one before saved.

- `--until` stops at a moment of the last log: `HH:MM:SS` on the day it
  began (or the day after, for a time before its start), or a whole
  `YYYY-MM-DDTHH:MM:SS`.
- `--seed` starts from the snapshot the program held when the first log
  began. Without it the folder starts empty, as a first capture does;
  the Gacha, Chaos and base-stat stores start empty either way.
- `--region global|asia` is the server the capture talked to, which the
  proxy's routing tells a capture and no log records; with `--seed`, the
  seeding snapshot's, unless given. Without either, the replay's
  rankings and snapshots carry none.
- `--quick` saves nothing, for when only the Capture Log is wanted: a
  long log saves a snapshot after every frame that moves anything.
- `--keep` leaves the folder, and says where it is.

Prints the Capture Log's lines and what the last snapshot saved holds.
The addon is the one a capture generates
(`CaptureManager._generate_addon_script`), running on the log's clock:
what it dates or names, it dates and names as the capture would have.
Everything it writes lands in the scratch folder; the snapshots folder
is only read.

A question of its own is a probe importing this:

    sys.path.insert(0, "docs")
    import replay_log
    with replay_log.replay(["20261020"], until="01:40:00") as run:
        run.addon        # the addon, as the last frame left it
        run.lines        # [(when, Capture Log line)], when in epoch seconds
        run.snapshot()   # the newest snapshot it saved, or None
        run.folder       # the addon's output folder
"""

import argparse
import contextlib
import gzip
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import time
import types
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
SNAPSHOTS = SOURCE / "snapshots"
sys.path.insert(0, str(SOURCE))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

STAMP = re.compile(r"websocket_debug_(\d{8}_\d{6})")
SNAPSHOT = re.compile(r"memory_fragments_(\d{8}_\d{6})\.json$")


def stamp(name):
    """A capture's `YYYYMMDD_HHMMSS`, which sorts as its start does."""
    found = STAMP.search(str(name))
    return found.group(1) if found else ""


def _matches(name, wanted):
    key = stamp(wanted) or wanted
    return bool(stamp(name)) and stamp(name).startswith(key)


def find_logs(wanted=()):
    """[(name, lines)] for the debug captures `wanted` names, oldest
    first; the newest loose one where it names none.

    The archive holds only captures older than every loose one -- a
    compaction archives the oldest -- so it is opened only for a name
    that could reach back past the oldest loose capture. It is one
    solid stream, read end to end."""
    loose = sorted(SNAPSHOTS.glob("websocket_debug_*.jsonl.gz"),
                   key=lambda p: stamp(p.name))
    if not wanted:
        if not loose:
            raise LookupError("no debug capture in Vribbels/snapshots/")
        wanted = [loose[-1].name]
    found = {}
    for path in loose:
        if any(_matches(path.name, w) for w in wanted):
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                found[path.name] = fh.read().splitlines()
    oldest = stamp(loose[0].name) if loose else None
    older = [w for w in wanted if oldest is None
             or (stamp(w) or w) <= oldest[:len(stamp(w) or w)]]
    if older:
        from capture import archive
        for name, handle in archive.stream_members(SNAPSHOTS,
                                                   "websocket_debug_"):
            base = Path(name).name
            if any(_matches(base, w) for w in older):
                raw = handle.read()
                if base.endswith(".gz"):
                    raw = gzip.decompress(raw)
                found[base] = raw.decode("utf-8", "replace").splitlines()
    missing = [w for w in wanted
               if not any(_matches(name, w) for name in found)]
    if missing:
        raise LookupError(f"no debug capture matches {', '.join(missing)}")
    return sorted(found.items(), key=lambda item: stamp(item[0]))


class _Clock:
    """The time of the frame being replayed, which the addon reads as
    now. None between logs, where it reads the real time."""
    epoch = None


def _on_clock(module, clock):
    """Make the generated module's `datetime.now()` and `time.time()`
    read `clock`."""
    real = module.datetime

    class LogTime(real):
        @classmethod
        def now(cls, tz=None):
            if clock.epoch is None:
                return real.now(tz)
            return real.fromtimestamp(clock.epoch, tz)

    module.datetime = LogTime
    shim = types.ModuleType("time")
    shim.__dict__.update(vars(time))
    shim.time = lambda: time.time() if clock.epoch is None else clock.epoch
    module.time = shim


def _addon(folder, clock, lines, save):
    """The addon a capture generates, on an output folder of `folder`."""
    from capture.manager import CaptureManager
    manager = CaptureManager(folder, log_callback=lambda *a, **k: None)
    script = manager._generate_addon_script(debug_mode=False)
    spec = importlib.util.spec_from_file_location("_replayed_addon", script)
    module = importlib.util.module_from_spec(spec)
    # The script builds an addon of its own at import, printing as it
    # goes; it is never used.
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    _on_clock(module, clock)

    def log(message, *_args, **_kwargs):
        lines.append((clock.epoch, str(message)))

    addon = type(module.addons[0])(folder, dict_path=module.DICT_PATH,
                                   log_callback=log, debug_mode=False,
                                   catalogue_path=None)
    if not save:
        addon._save_data = lambda *a, **k: None
    return addon


class _Message:
    """What `Addon.websocket_message` reads off a mitmproxy message."""

    def __init__(self, payload, from_client, at):
        self.text = json.dumps(payload)
        self.content = self.text.encode("utf-8")
        self.is_text = True
        self.from_client = from_client
        self.timestamp = at


class _Flow:
    def __init__(self, message):
        self.websocket = types.SimpleNamespace(messages=[message])


def _frames(lines):
    """(epoch seconds, frame) for each frame of a log, in order."""
    for line in lines:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
            at = datetime.fromisoformat(frame["ts"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        yield at, frame


def _stop_at(until, lines):
    """`--until` as epoch seconds, a time of day read against the day
    the log began."""
    if until is None:
        return None
    if "T" in until or "-" in until:
        return datetime.fromisoformat(until).timestamp()
    first = next(_frames(lines), None)
    if first is None:
        return None
    start = datetime.fromtimestamp(first[0])
    day = start.date().isoformat()
    stop = datetime.fromisoformat(f"{day}T{until}").timestamp()
    # A time before the log began is the next morning's.
    return stop + 86400 if stop < first[0] else stop


def _seed(folder, before):
    """Copy the newest loose snapshot from before `before` (a stamp)
    into `folder`. Its name, or None where there is none."""
    held = sorted((SNAPSHOT.search(p.name).group(1), p)
                  for p in SNAPSHOTS.glob("memory_fragments_*.json")
                  if SNAPSHOT.search(p.name)
                  and SNAPSHOT.search(p.name).group(1) < before)
    if not held:
        return None
    shutil.copy2(held[-1][1], folder / held[-1][1].name)
    return held[-1][1].name


class Replay:
    """One replay's addon, folder and Capture Log."""

    def __init__(self, root):
        self.root = Path(root)
        self.folder = self.root / "snapshots"
        self.lines = []
        self.logs = []
        self.addon = None
        self.frames = 0
        self.seeded = None
        self.errors = []

    def saved(self):
        """The snapshots the replay saved, oldest first."""
        return sorted(p for p in self.folder.glob("memory_fragments_*.json")
                      if p.name != self.seeded)

    def snapshot(self):
        """The newest snapshot the replay saved, read; None if none."""
        saved = self.saved()
        if not saved:
            return None
        return json.loads(saved[-1].read_text(encoding="utf-8"))


@contextlib.contextmanager
def replay(logs=(), until=None, seed=False, save=True, keep=False,
           region=None, prepare=None):
    """Replay `logs` (names or stamp starts, see `find_logs`) and yield
    the `Replay`. `prepare(folder)` runs before the first addon is made,
    for a probe that needs something in the folder first -- a copy of a
    store, say. The folder is removed afterwards unless `keep`."""
    root = Path(tempfile.mkdtemp(prefix="replay_"))
    run = Replay(root)
    run.folder.mkdir()
    try:
        found = find_logs(list(logs))
        run.logs = [name for name, _ in found]
        if seed:
            run.seeded = _seed(run.folder, stamp(found[0][0]))
            if run.seeded and region is None:
                held = json.loads((run.folder / run.seeded)
                                  .read_text(encoding="utf-8"))
                region = held.get("detected_region")
        if prepare is not None:
            prepare(run.folder)
        stop = _stop_at(until, found[-1][1])
        clock = _Clock()
        for index, (name, lines) in enumerate(found):
            clock.epoch = None
            run.addon = _addon(run.folder, clock, run.lines, save)
            if region:
                run.addon._note_region(region)
            last = index == len(found) - 1
            for at, frame in _frames(lines):
                if last and stop is not None and at > stop:
                    break
                clock.epoch = at
                message = _Message(frame.get("data"),
                                   frame.get("direction") ==
                                   "client_to_server", at)
                try:
                    run.addon.websocket_message(_Flow(message))
                except Exception as exc:                 # noqa: BLE001
                    run.errors.append((at, f"{type(exc).__name__}: {exc}"))
                run.frames += 1
            run.addon.done()
        yield run
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)


def _clock_text(epoch):
    return "--:--:--" if epoch is None else \
        datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


def _summary(value):
    if isinstance(value, dict):
        return f"{len(value)} keys"
    if isinstance(value, list):
        return f"{len(value)} items"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--until")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--region", choices=("global", "asia"))
    args = ap.parse_args(argv)
    try:
        with replay(args.logs, until=args.until, seed=args.seed,
                    save=not args.quick, keep=args.keep,
                    region=args.region) as run:
            print(f"replayed {', '.join(run.logs)}: {run.frames} frames"
                  + (f", until {args.until}" if args.until else ""))
            if args.seed:
                print(f"seeded from {run.seeded or 'nothing: no snapshot '}"
                      + ("" if run.seeded else "before the first log"))
            print("\n-- Capture Log --")
            for epoch, line in run.lines:
                print(f"{_clock_text(epoch)}  {line}")
            for epoch, error in run.errors:
                print(f"{_clock_text(epoch)}  ! the replay raised {error}")
            saved = run.saved()
            if saved:
                print(f"\n-- {len(saved)} snapshot(s) saved; the last, "
                      f"{saved[-1].name} --")
                for key, value in (run.snapshot() or {}).items():
                    print(f"  {key}: {_summary(value)}")
            elif not args.quick:
                print("\n-- no snapshot saved --")
            if args.keep:
                print(f"\nkept: {run.root}")
    except LookupError as exc:
        print(exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
