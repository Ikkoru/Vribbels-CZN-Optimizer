"""The capture archiver moves files without ever losing one.

`capture/archive.py` deletes the maintainer's captured history, which
is the only copy there is. Everything here guards that one sentence:

* a file goes in and comes back byte for byte, a `.gz` log included
  (it is stored decompressed, so what must match is its CONTENT);
* the water marks leave the newest LOW loose and take the rest, and do
  nothing at all below HIGH;
* **a failed verification deletes NOTHING** and leaves the previous
  archive untouched;
* the deleter refuses a path it did not verify in this pass, a path
  that is not a capture, and a path outside the folder -- which is
  where `_capture_addon.py` and `__pycache__/` live;
* an interrupted build leaves no `.tmp` behind once a run has swept.

Run against temp directories only. Nothing here reads or writes the
real `Vribbels/snapshots/`.
"""

import gzip
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, Skip

NAME = "capture archiver loses nothing"

add_source_to_path()

from capture import archive                                   # noqa: E402


def _snapshot(folder, stamp, filler=1):
    path = folder / ("memory_fragments_%s.json" % stamp)
    path.write_text(json.dumps({"capture_time": stamp,
                                "inventory": {"items": ["x"] * filler}}),
                    encoding="utf-8")
    return path


def _log(folder, stamp, lines=3):
    path = folder / ("websocket_debug_%s.jsonl.gz" % stamp)
    with open(path, "wb") as handle:
        for n in range(lines):
            handle.write(gzip.compress(
                (json.dumps({"ts": stamp, "n": n}) + "\n").encode("utf-8")))
    return path


def _stamps(count, start=1):
    return ["202601%02d_0000%02d" % (1 + (n // 60), n % 60)
            for n in range(start, start + count)]


def _folder(snapshots=0, logs=0):
    work = Path(tempfile.mkdtemp(prefix="czn_archive_"))
    for stamp in _stamps(snapshots):
        _snapshot(work, stamp)
    for stamp in _stamps(logs):
        _log(work, stamp)
    return work


def _quiet(*_a, **_k):
    pass


def _round_trip():
    """Everything archived comes back, and a log comes back decompressed."""
    out = []
    high, low = archive.KINDS[archive.SNAPSHOTS][1:]
    work = _folder(snapshots=high, logs=archive.KINDS[archive.LOGS][1])
    try:
        before = {p.name: p.read_bytes() for p in work.glob("memory_*.json")}
        logs = {}
        for path in work.glob("websocket_debug_*.gz"):
            with gzip.open(path, "rb") as fh:
                logs[archive.member_name(path)] = fh.read()

        result = archive.compact(work, say=_quiet)
        if result["failed"]:
            return ["a clean run reported %r" % result["failed"]]

        loose = sorted(p.name for p in work.glob("memory_fragments_*.json"))
        if len(loose) != low:
            out.append(
                f"{len(loose)} snapshot(s) left loose, not {low}. The newest "
                f"LOW have to stay: the app loads the newest and the dump "
                f"scripts walk back through the ones behind it.")
        if loose != sorted(before)[-low:]:
            out.append(
                f"the wrong snapshots were kept: {loose!r}. 'Old' is "
                f"positional -- the Nth file back from the newest.")

        for name in result["archived"]:
            got = archive.read_member(work, name)
            want = before.get(name) or logs.get(name)
            if want is None:
                out.append(f"{name!r} was archived but was never written.")
            elif got != want:
                out.append(
                    f"{name!r} came back {len(got)} bytes against "
                    f"{len(want)} written. A member that does not match is "
                    f"a capture lost, since the loose file is deleted.")
        if not any(n.endswith(".jsonl") for n in result["archived"]):
            out.append(
                "no log was stored under a `.jsonl` name. They go in "
                "decompressed -- xz cannot shrink a `.gz`, and ungzipping "
                "recovers about 85% of the archived size.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _below_high_does_nothing():
    high = archive.KINDS[archive.SNAPSHOTS][1]
    work = _folder(snapshots=high - 1)
    try:
        result = archive.compact(work, say=_quiet)
        if result["archived"] or result["deleted"]:
            return [
                f"a folder holding {high - 1} snapshots compacted anyway "
                f"({result['archived']!r}). Below HIGH nothing is due: the "
                f"mark is what keeps a rebuild from running per file."]
        if (work / archive.ARCHIVE_NAME).exists():
            return ["an archive was written with nothing due."]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return []


def _failed_verify_keeps_everything():
    """The one that matters: a mismatch must cost nothing."""
    out = []
    high = archive.KINDS[archive.SNAPSHOTS][1]
    work = _folder(snapshots=high)
    was = archive._verify
    try:
        archive._verify = lambda book, wanted: ["injected mismatch"]
        loose_before = sorted(p.name for p in work.iterdir())
        result = archive.compact(work, say=_quiet)
        if not result["failed"]:
            out.append("a failed verification reported success.")
        if result["deleted"]:
            out.append(
                f"a failed verification still deleted {result['deleted']!r}. "
                f"Nothing may be removed until its archived copy has been "
                f"read back and matched.")
        loose_after = sorted(p.name for p in work.iterdir())
        if loose_after != loose_before:
            out.append(
                f"the folder changed under a failed run: {loose_before!r} -> "
                f"{loose_after!r}.")
        if (work / archive.TMP_NAME).exists():
            out.append("a failed run left its `.tmp` behind.")
    finally:
        archive._verify = was
        shutil.rmtree(work, ignore_errors=True)
    return out


def _deleter_refuses_what_it_should():
    out = []
    work = _folder(snapshots=2)
    try:
        (work / "_capture_addon.py").write_text("x", encoding="utf-8")
        outside = Path(tempfile.mkdtemp(prefix="czn_outside_"))
        stray = _snapshot(outside, "20260101_000099")
        verified = {archive.member_name(p): (1, "x")
                    for p in work.glob("memory_fragments_*.json")}
        cases = [
            ("a file that sits in another directory", stray),
            ("a file that is not a capture", work / "_capture_addon.py"),
            ("a capture nothing verified this pass",
             work / "memory_fragments_20260101_000099.json"),
        ]
        for label, path in cases:
            try:
                archive._delete(work, path, verified, _quiet)
            except archive.Refused:
                continue
            out.append(
                f"the deleter accepted {label} ({path.name}). It takes a "
                f"whitelist, not a path: in the folder, named like a "
                f"capture, and verified in this same pass.")
        shutil.rmtree(outside, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _sweep_clears_an_interrupted_build():
    work = _folder(snapshots=1)
    try:
        (work / archive.TMP_NAME).write_bytes(b"half a tar")
        if not archive.sweep(work):
            return ["sweep did not report the `.tmp` it found."]
        if (work / archive.TMP_NAME).exists():
            return [
                "sweep left the `.tmp` in place. An interrupted build has to "
                "leave either the old archive or the new one, never a "
                "half-written file that the next run reads."]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return []


def _twice_leaves_one_member_each():
    """A second pass over files still loose must not double them up.

    A dry run, an interrupted delete or a file that would not unlink
    all leave a loose copy of something already archived. Tar does not
    reject a second member of the same name, so without a guard the
    archive gains a copy of everything on every pass.
    """
    out = []
    high = archive.KINDS[archive.SNAPSHOTS][1]
    work = _folder(snapshots=high)
    try:
        first = archive.compact(work, say=_quiet, delete=False)
        second = archive.compact(work, say=_quiet, delete=False)
        if second["failed"]:
            return ["a second pass reported %r" % second["failed"]]
        names = [name for name, _size in archive.contents(work)]
        if len(names) != len(set(names)):
            doubled = sorted({n for n in names if names.count(n) > 1})
            out.append(
                f"{len(doubled)} member(s) appear twice after two passes "
                f"({doubled[:3]!r}). A file still loose is re-added on the "
                f"next pass, so the archive grows by a copy every time and "
                f"`extractfile` answers with whichever it reaches last.")
        if sorted(first["archived"]) != sorted(second["archived"]):
            out.append("the two passes archived different sets.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _dry_run_deletes_nothing():
    high = archive.KINDS[archive.SNAPSHOTS][1]
    work = _folder(snapshots=high)
    try:
        before = sorted(p.name for p in work.glob("memory_fragments_*.json"))
        result = archive.compact(work, say=_quiet, delete=False)
        after = sorted(p.name for p in work.glob("memory_fragments_*.json"))
        if not result["archived"]:
            return ["a dry run archived nothing."]
        if after != before:
            return [f"a dry run removed {sorted(set(before) - set(after))!r}."]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return []


def _background_run_reports_instead_of_dying():
    """A thread that raises dies silently, taking the report with it.

    The launch path hands the archiver to a daemon thread, so an
    unexpected exception inside it reaches nobody: the UI carries on,
    the folder is never tidied, and no line says why. Everything the
    thread does is wrapped for that, and a failure arrives through the
    same callback the Capture Log listens on.
    """
    out = []
    high = archive.KINDS[archive.SNAPSHOTS][1]
    work = _folder(snapshots=high)
    said = []
    was = archive.compact
    try:
        thread = archive.compact_in_background(work, say=said.append)
        thread.join(60)
        if thread.is_alive():
            out.append("the background compaction did not finish.")
        if not thread.daemon:
            out.append(
                "the archiving thread is not a daemon, so a close while it "
                "runs waits for a rebuild instead of exiting.")
        if len(list(work.glob("memory_fragments_*.json"))) != \
                archive.KINDS[archive.SNAPSHOTS][2]:
            out.append("the background run did not compact the folder.")

        said.clear()

        def _boom(*_a, **_k):
            raise RuntimeError("injected")

        archive.compact = _boom
        thread = archive.compact_in_background(work, say=said.append)
        thread.join(60)
        if not any("RuntimeError" in line for line in said):
            out.append(
                f"an exception inside the archiving thread was not "
                f"reported ({said!r}). A thread that dies of one dies "
                f"silently, so nothing else would ever say so.")
    finally:
        archive.compact = was
        shutil.rmtree(work, ignore_errors=True)
    return out


def _the_setting_reaches_the_launch_path():
    """`Off` stops it, a typo does not, and the hook is still called.

    The launch path reads the setting rather than letting the archiver
    read it, so that `Off` starts no thread at all. Both halves fail
    quietly: a setting nothing reads leaves the folder growing, and a
    hook deleted from `__init__` raises nothing until a user notices
    their snapshots folder never shrinks.
    """
    import inspect
    import tempfile as tf

    out = []
    from config import AppConfig
    from settings_manager import SettingsManager
    import czn_optimizer_gui as gui

    work = Path(tf.mkdtemp(prefix="czn_archive_cfg_"))
    try:
        manager = SettingsManager(work)
        manager.load()
        config = AppConfig(manager)
        for value, want in (("off", "off"),
                            ("strongest", "strongest"),
                            ("balanced", "balanced"),
                            ("wharrgarbl", archive.DEFAULT_PRESET)):
            config.capture_archive = value
            got = config.capture_archive
            if got != want:
                out.append(
                    f"`capture_archive` set to {value!r} read back as "
                    f"{got!r}, not {want!r}. An unrecognised value reads as "
                    f"the default: a typo should not quietly stop the "
                    f"folder from being tidied.")
        if "capture_archive" not in dict(SettingsManager.LAYOUT):
            out.append(
                "`capture_archive` is not in SettingsManager.LAYOUT, so "
                "settings.json will not carry it for a user to find.")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not hasattr(gui.OptimizerGUI, "_start_capture_archiver"):
        out.append("OptimizerGUI lost `_start_capture_archiver`.")
    else:
        body = inspect.getsource(gui.OptimizerGUI.__init__)
        if "_start_capture_archiver" not in body:
            out.append(
                "`_start_capture_archiver` is never called from "
                "`OptimizerGUI.__init__`, so nothing archives at launch "
                "and the folder grows without bound. It belongs after the "
                "reveal, with the window already up.")
    return out


def run():
    try:
        tarfile.open  # noqa: B018 -- lzma may be missing from a build
        import lzma   # noqa: F401
    except Exception as e:                                    # noqa: BLE001
        raise Skip(f"no lzma here ({type(e).__name__})")
    problems = []
    for probe in (_round_trip, _below_high_does_nothing,
                  _failed_verify_keeps_everything,
                  _deleter_refuses_what_it_should,
                  _sweep_clears_an_interrupted_build,
                  _twice_leaves_one_member_each,
                  _dry_run_deletes_nothing,
                  _background_run_reports_instead_of_dying,
                  _the_setting_reaches_the_launch_path):
        problems.extend(probe())
    return problems
