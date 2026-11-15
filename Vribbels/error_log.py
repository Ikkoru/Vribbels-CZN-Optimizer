"""error_log - what went wrong, kept for a bug report.

The released build is windowed: it has no console, so an exception in a
Tk callback or a thread goes to a stderr nobody sees, and a handler that
catches and carries on leaves no trace at all. This module is where
those go instead: `settings/error_log.txt`, beside the program, one
entry per error with its time, where it happened and its traceback.

Always on, unlike `perf_log`: an error is rare, and the one a player
hits is the one nobody else can reproduce.

`note()` never raises. A log that cannot be written is dropped quietly,
since the error it would have recorded is already being handled by
whoever called. The file is held under `MAX_BYTES` by dropping its older
half whenever a write would pass it.
"""

import threading
import traceback
from datetime import datetime
from pathlib import Path

# The most the file may hold. Past this, the older half goes.
MAX_BYTES = 512 * 1024

FILE_NAME = "error_log.txt"

_lock = threading.Lock()
_path = None
# What the last `note` recorded, for a caller that wants to say so.
last_message = None
# Called once, the first time a session writes the file, with its path:
# the window tells the player where it is.
first_write_callback = None
_written = False


def configure(base_dir) -> None:
    """Point the log at `<base_dir>/settings/error_log.txt`."""
    global _path
    try:
        _path = Path(base_dir) / "settings" / FILE_NAME
    except Exception:
        _path = None


def path():
    """Where the log is written, or None before `configure`."""
    return _path


def note(where: str, exc: BaseException | None = None) -> None:
    """Record an error: `where` it happened and, with `exc`, its
    traceback; without one, the traceback being handled, if any. Never
    raises."""
    global last_message, _written
    try:
        if exc is not None:
            text = "".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__))
        else:
            text = traceback.format_exc()
            if text.startswith("NoneType: None"):
                text = ""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = "%s | %s\n%s\n" % (stamp, where, text.rstrip())
        last_message = "%s: %s" % (
            where, (text.strip().splitlines() or [""])[-1])
        if _path is None:
            return
        with _lock:
            _path.parent.mkdir(parents=True, exist_ok=True)
            _hold_under_cap(len(entry.encode("utf-8")))
            with _path.open("a", encoding="utf-8", newline="") as fh:
                fh.write(entry)
            first = not _written
            _written = True
        if first and first_write_callback is not None:
            first_write_callback(_path)
    except Exception:
        pass


def _hold_under_cap(adding: int) -> None:
    """Drop the file's older half, at an entry's start, when `adding`
    bytes would take it past `MAX_BYTES`."""
    try:
        size = _path.stat().st_size
    except OSError:
        return
    if size + adding <= MAX_BYTES:
        return
    data = _path.read_bytes()
    keep = data[len(data) // 2:]
    # From the next entry's first line, so no entry is cut in two.
    cut = keep.find(b"\n20")
    keep = keep[cut + 1:] if cut >= 0 else b""
    _path.write_bytes(keep)


def install_hooks(root=None) -> None:
    """Record every uncaught exception: the Tk root's callbacks (when
    `root` is given), the main thread's and every other thread's. Each
    hook records, then does what the default would have done."""
    import sys

    def on_main(kind, value, tb):
        note("uncaught exception", value)
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = on_main

    previous = threading.excepthook

    def on_thread(args):
        name = getattr(args.thread, "name", "?")
        note("thread %s" % name, args.exc_value)
        previous(args)

    threading.excepthook = on_thread

    if root is not None:
        default = root.report_callback_exception

        def on_callback(kind, value, tb):
            note("Tk callback", value)
            default(kind, value, tb)

        root.report_callback_exception = on_callback
