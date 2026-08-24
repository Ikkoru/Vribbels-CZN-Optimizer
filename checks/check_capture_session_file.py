"""A capture that recorded nothing must not report an older snapshot.

`get_latest_capture()` answers "what is the newest snapshot on disk",
from any session. `stop_capture` used it to decide what THIS run
produced, so a capture that saw no traffic announced the previous run's
file with a success line -- no error, no warning, and a Server Region
set to the wrong server looked exactly like a working capture.

The failure is invisible from the code and expensive to reproduce by
hand (it needs the proxy, the game and a deliberately wrong region), so
the watermark is checked directly here instead.
"""

import tempfile
import time
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture reports only its own snapshot"


def _touch(folder, name, mtime):
    p = Path(folder) / name
    p.write_text("{}", encoding="utf-8")
    import os
    os.utime(p, (mtime, mtime))
    return p


def run():
    add_source_to_path()
    from capture.manager import CaptureManager

    failures = []
    work = Path(tempfile.mkdtemp())
    mgr = CaptureManager(work, log_callback=lambda *a, **k: None)

    now = time.time()
    old = _touch(work, "memory_fragments_20260101_000000.json", now - 3600)

    # 1. Not capturing: no session, so no session file.
    if mgr.get_session_capture() is not None:
        failures.append(
            "get_session_capture() returned a file before any capture "
            "started. Only a snapshot written during a session counts."
        )

    # 2. A session that writes nothing must not adopt the older file.
    mgr._session_started_at = now
    got = mgr.get_session_capture()
    if got is not None:
        failures.append(
            f"a capture that wrote nothing reported {got.name!r}, which "
            f"predates it by an hour. That is how a wrong Server Region "
            f"looked like a successful capture."
        )

    # 3. A session that DOES write must find its own file.
    fresh = _touch(work, "memory_fragments_20260102_000000.json", now + 5)
    got = mgr.get_session_capture()
    if got is None or got.name != fresh.name:
        failures.append(
            f"a capture that wrote {fresh.name!r} reported {got!r} instead. "
            f"The watermark must admit files written after the proxy "
            f"started."
        )

    # 4. Same-second writes survive the filesystem's mtime resolution.
    mgr._session_started_at = now
    _touch(work, "memory_fragments_20260103_000000.json", now - 0.5)
    if mgr.get_session_capture() is None:
        failures.append(
            "a snapshot written in the same second the proxy started was "
            "rejected. Some filesystems keep mtime only to the second, so "
            "the comparison needs a second of slack."
        )

    # get_latest_capture keeps its own, different meaning.
    if mgr.get_latest_capture() is None:
        failures.append(
            "get_latest_capture() stopped seeing files. It answers "
            "'newest on disk, any session' and other callers rely on that."
        )
    _ = old
    return failures
