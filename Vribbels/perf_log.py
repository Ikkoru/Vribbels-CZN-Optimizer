"""
perf_log - append-only diagnostics log for performance measurements.

Writes one line per measured event to `settings/perf_log.txt`, so timings
can be collected across several real runs and read back afterwards instead
of being watched live in a console.

Format is one line per event, pipe-separated:

    2026-07-27 14:03:11 | optimize | char=Fei | fragments=642 | ...

Deliberately dependency-free and failure-proof: every call is wrapped so a
logging problem can never interfere with the thing being measured. The file
is plain text, append-only and tiny (a line per run); it can be deleted at
any time and will be recreated.

`configure()` must be called once at startup with the same base directory
the settings managers use, so frozen builds write next to the executable
rather than into the read-only _MEIPASS tree.

Logging is OFF unless `configure(..., enabled=True)`. Disabled, nothing is
written and `perf_log.txt` is never created; `timed()` hands back the
original function so wrapped calls carry no overhead at all. The flag comes
from the `debug_perf_log` key in settings.json.
"""

import time
from datetime import datetime
from pathlib import Path
from threading import Lock


_lock = Lock()
_path: Path | None = None
_enabled = False


def configure(base_dir, enabled: bool = False) -> None:
    """Enable or disable logging, and point it at
    `<base_dir>/settings/perf_log.txt`.

    Disabled is the default and the normal state: no file is created and
    every entry point below short-circuits.
    """
    global _path, _enabled
    _enabled = bool(enabled)
    if not _enabled:
        _path = None
        return
    try:
        _path = Path(base_dir) / "settings" / "perf_log.txt"
    except Exception:
        _path = None


def is_enabled() -> bool:
    """True when timings are being recorded. Callers doing non-trivial work
    purely to produce a log line should check this first."""
    return _enabled and _path is not None


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{v}" for k, v in sorted(value.items())) + "}"
    return str(value)


def log(event: str, **fields) -> None:
    """Append one event line. No-op when disabled. Never raises."""
    if not _enabled or _path is None:
        return
    try:
        parts = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), event]
        parts += [f"{k}={_fmt(v)}" for k, v in fields.items()]
        with _lock:
            _path.parent.mkdir(parents=True, exist_ok=True)
            with _path.open("a", encoding="utf-8") as fh:
                fh.write(" | ".join(parts) + "\n")
    except Exception:
        pass


def _caller() -> str:
    """"file.py:lineno" of whatever called the wrapped function.

    Turns a timing line into an attribution line: not just how long
    something took, but what asked for it. Cheap enough for events that
    fire a few times a session; don't use it in a hot loop.
    """
    try:
        import traceback
        # Innermost frames are (-1) this function, (-2) the wrapper,
        # (-3) the actual caller.
        frame = traceback.extract_stack(limit=4)[-3]
        return f"{Path(frame.filename).name}:{frame.lineno}"
    except Exception:
        return "?"


def timed(event: str, func):
    """Wrap `func` so every call logs its wall-clock duration and caller.

    Used to measure a method without editing its body -- bind the wrapper
    over the instance attribute and every caller is covered at once.

    When logging is disabled this returns `func` unchanged, so a wrapped
    method costs exactly nothing in normal use.
    """
    if not _enabled:
        return func

    def _wrapped(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            log(event, secs=time.perf_counter() - start, caller=_caller())
    return _wrapped
