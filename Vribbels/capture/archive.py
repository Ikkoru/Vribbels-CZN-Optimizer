"""Fold superseded captures into one solid archive.

`snapshots/` only grows: nothing in `capture/` deletes anything, so a
long-running install accumulates a `memory_fragments_*.json` per game
relaunch and a `websocket_debug_*.jsonl.gz` per session. This moves the
old ones into `archived_captures.tar.xz` beside them, and deletes a
loose file only after the archived copy has been read back and its
SHA-256 matched against the file about to go.

**One archive, rebuilt, never appended to.** Consecutive snapshots are
nearly identical and that only pays inside ONE compression stream:
measured over 114 real captures, a solid rebuild came to 242 KB where
compressing each file on its own came to 7.0 MB. Rebuild cost is
proportional to the whole archive rather than to what is being added,
which is what the high-water mark is for -- three rebuilds to add nine
files cost three times one rebuild to add nine.

**Positional, not temporal.** "Old" means the Nth file back from the
newest of its own kind, so the files the program reads are never
candidates however long ago they were written.

**Logs go in decompressed.** xz cannot shrink a `.gz`, and ungzipping
on the way in recovers about 85% of a log's archived size. The member
keeps the `.jsonl` name; `gzip.open` streams straight into the tar, so
no temporary file is involved.

**So a log loose in both forms is ONE capture**, `X.jsonl` beside the
`X.jsonl.gz` it was decompressed from. Tar does not refuse a second
member of a name, so the two are grouped by member name and go in once
-- and only where their contents agree; twins that differ are both left
loose for a human. Deleting is per FILE: a loose file goes only when its
own content matched the member this pass, which is what keeps a twin
from being deleted on the strength of the other one's check. A rebuild
carries the archive's own members across one per name and content, so
an identical repeat already inside is shed by the next compaction.
"""

import gzip
import hashlib
import io
import lzma
import os
import tarfile
import threading
import time
from pathlib import Path

ARCHIVE_NAME = "archived_captures.tar.xz"
TMP_NAME = ARCHIVE_NAME + ".tmp"

# The two kinds of capture, their globs, and their water marks: compact
# when this many are loose, leaving this many behind.
SNAPSHOTS = "snapshots"
LOGS = "logs"
KINDS = {
    SNAPSHOTS: (("memory_fragments_*.json",), 16, 3),
    LOGS: (("websocket_debug_*.jsonl", "websocket_debug_*.jsonl.gz"), 13, 3),
}

# What the Compression setting means. Presets 0, 6 and 9 are dominated:
# 0 is bigger AND slower than 3 (its dictionary is too small to reach
# across files), and 6 and 9 cost fourteen times the time of 3 for 5%.
PRESETS = {
    "balanced": 3,
    "strongest": 9 | lzma.PRESET_EXTREME,
}
DEFAULT_PRESET = "balanced"

# A held destination raises `PermissionError` on Windows -- the app
# reading the file, an indexer, an antivirus scanning what was just
# written. Transient, so it is retried rather than reported.
TRIES = 3
BACKOFF = 0.4

CHUNK = 1 << 20


class Refused(Exception):
    """A delete that the whitelist would not allow. Never expected."""


def _ordered(folder: Path, globs) -> list:
    """Every file of one kind, oldest first.

    By NAME, not mtime: the timestamp is in the stem, and an archive
    restored or copied about carries whatever mtime the copy gave it.
    """
    found = []
    for pattern in globs:
        found.extend(folder.glob(pattern))
    return sorted(found, key=lambda path: path.name)


def member_name(path) -> str:
    """What a loose file is called inside the archive.

    A `.gz` log is stored decompressed, so it loses that suffix; the
    name is all that says so, and nothing downstream needs more.
    """
    name = Path(path).name
    return name[:-3] if name.endswith(".gz") else name


def _source(path: Path):
    """The bytes to archive for one loose file, as a stream."""
    return gzip.open(path, "rb") if path.suffix == ".gz" else open(path, "rb")


def _digest(stream) -> tuple:
    """(size, sha256) over a stream, without holding it in memory."""
    size = 0
    sha = hashlib.sha256()
    while True:
        block = stream.read(CHUNK)
        if not block:
            return size, sha.hexdigest()
        size += len(block)
        sha.update(block)


def due(folder: Path) -> dict:
    """{kind: [paths to archive]}, empty where a kind is under HIGH."""
    out = {}
    for kind, (globs, high, low) in KINDS.items():
        loose = _ordered(folder, globs)
        if len(loose) >= high:
            out[kind] = loose[:len(loose) - low]
    return out


def contents(folder: Path) -> list:
    """[(member name, uncompressed size)] without reading any payload."""
    book = folder / ARCHIVE_NAME
    if not book.exists():
        return []
    with tarfile.open(book, "r:xz") as tf:
        return [(m.name, m.size) for m in tf.getmembers() if m.isfile()]


def read_member(folder: Path, name: str) -> bytes:
    """One archived file's bytes, without unpacking anything."""
    with tarfile.open(folder / ARCHIVE_NAME, "r:xz") as tf:
        handle = tf.extractfile(name)
        if handle is None:
            raise KeyError(name)
        return handle.read()


def sweep(folder: Path) -> bool:
    """Drop a `.tmp` an interrupted run left behind. True if there was one."""
    tmp = folder / TMP_NAME
    if not tmp.exists():
        return False
    try:
        tmp.unlink()
        return True
    except OSError:
        return False


def _add(tf: tarfile.TarFile, name: str, stream, size: int):
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = int(time.time())
    tf.addfile(info, stream)


def _retried(work, path, say):
    """`work()`, retried on the `OSError` a held file raises. None once
    `TRIES` attempts have failed, with the file named."""
    for attempt in range(TRIES):
        try:
            return work()
        except OSError as exc:
            if attempt + 1 == TRIES:
                say("[!] %s could not be read (%s); left in place, the "
                    "next compaction will take it."
                    % (path.name, type(exc).__name__))
                return None
            time.sleep(BACKOFF)


def _plan(adding: list, say) -> list:
    """[(member name, the file to add, its fingerprint, every file it
    stands for)], one per member name.

    **One capture can be loose twice**: a log as `X.jsonl` beside the
    `X.jsonl.gz` it was decompressed from, both of which `member_name`
    calls `X.jsonl`. Added as they come, the tar holds two members of
    one name and everything that walks it counts that capture twice.
    So the files are grouped by member name first, and a group goes in
    ONCE, as its first file, standing for every file in it whose own
    content matched.

    A group is all or nothing. Twins whose contents differ, or one that
    will not read, leave the whole group loose: archiving one of them
    and deleting it, the next pass would take the other under the same
    name and replace the first -- whose content would then be nowhere.
    """
    groups = {}
    for path in adding:
        groups.setdefault(member_name(path), []).append(path)
    plan = []
    for name, paths in groups.items():
        prints = {}
        for path in paths:
            def fingerprint(path=path):
                with _source(path) as stream:
                    return _digest(stream)
            got = _retried(fingerprint, path, say)
            if got is None:
                break
            prints[path] = got
        if len(prints) < len(paths):
            continue
        if len(set(prints.values())) > 1:
            say("[!] %s are one capture with different contents; all "
                "left in place." % " and ".join(p.name for p in paths))
            continue
        plan.append((name, paths[0], prints[paths[0]], paths))
    return plan


def _copy_old(old: tarfile.TarFile, out: tarfile.TarFile, fresh: set, say):
    """Carry the archive's members into the rebuild, one per capture.

    A name added this pass is skipped: the fresh copy replaces it. A
    name held more than once keeps one copy per distinct CONTENT, so a
    repeat identical to one already carried is dropped and a repeat
    that differs is kept beside it -- two members of one name are an
    anomaly, but dropping either would lose what only it holds.

    Only a repeated name is read into memory to be fingerprinted; every
    other member streams straight across.
    """
    members = [info for info in old.getmembers()
               if info.isfile() and info.name not in fresh]
    counts = {}
    for info in members:
        counts[info.name] = counts.get(info.name, 0) + 1
    carried = {}
    for info in members:
        handle = old.extractfile(info)
        if handle is None:
            continue
        if counts[info.name] == 1:
            out.addfile(info, handle)
            continue
        body = handle.read()
        sha = hashlib.sha256(body).hexdigest()
        if sha in carried.setdefault(info.name, set()):
            continue
        carried[info.name].add(sha)
        out.addfile(info, io.BytesIO(body))
    for name, prints in carried.items():
        if len(prints) > 1:
            say("[!] %s is archived %d times with different contents; "
                "all kept." % (name, len(prints)))


def _build(folder: Path, adding: list, preset: int, say):
    """Write the `.tmp` holding the old members plus `adding`.

    Returns (wanted, covered): {member name: (size, sha256)} for the
    members just added -- the fingerprints the verify step demands
    before anything is deleted -- and the loose files whose OWN content
    each matched the member added for it. A file that will not open
    after `TRIES` attempts is left out and stays loose; the archive is
    correct without it and the next compaction takes it.
    """
    book = folder / ARCHIVE_NAME
    tmp = folder / TMP_NAME
    wanted, covered = {}, set()
    plan = _plan(adding, say)
    # **A name added this pass wins over the copy already inside.** A
    # loose file can legitimately still be there after an interrupted
    # or dry run, and tar does not reject a second member of the same
    # name -- it stores both, so the archive grows by a copy every
    # pass and `extractfile` answers with whichever it reaches last.
    fresh = {name for name, _path, _print, _paths in plan}
    with tarfile.open(tmp, "w:xz", preset=preset) as out:
        if book.exists():
            with tarfile.open(book, "r:xz") as old:
                _copy_old(old, out, fresh, say)
        for name, path, (size, sha), paths in plan:
            def add(path=path, name=name, size=size):
                with _source(path) as stream:
                    _add(out, name, stream, size)
                return True
            if _retried(add, path, say):
                wanted[name] = (size, sha)
                covered.update(paths)
    return wanted, covered


def _verify(book: Path, wanted: dict) -> list:
    """Complaints about members that do not match what was put in."""
    problems = []
    with tarfile.open(book, "r:xz") as tf:
        held = {m.name for m in tf.getmembers() if m.isfile()}
        for name, (size, sha) in wanted.items():
            if name not in held:
                problems.append("%s is missing from the archive" % name)
                continue
            got_size, got_sha = _digest(tf.extractfile(name))
            if (got_size, got_sha) != (size, sha):
                problems.append(
                    "%s does not match what was written (%d bytes / %s "
                    "against %d / %s)"
                    % (name, got_size, got_sha[:12], size, sha[:12]))
    return problems


def _replace(tmp: Path, book: Path):
    """Put the new archive in place, retrying a held destination."""
    for attempt in range(TRIES):
        try:
            os.replace(tmp, book)
            return
        except PermissionError:
            if attempt + 1 == TRIES:
                raise
            time.sleep(BACKOFF)


def _delete(folder: Path, path: Path, verified: set, say) -> bool:
    """Remove one loose file, refusing anything not proven archived.

    THREE conditions, and all of them are the point: the file sits
    directly in the snapshots folder, its name matches a capture's, and
    its content was matched against the archive in this same pass.
    `_capture_addon.py` and `__pycache__/` live in this directory, and
    nothing here may ever reach them.

    **`verified` holds FILES, not member names.** Two loose files can
    share one member name -- see `_plan` -- and a name in the book says
    only that one of them matched.
    """
    if path.parent.resolve() != folder.resolve():
        raise Refused("%s is not directly in %s" % (path, folder))
    patterns = [p for globs, _h, _l in KINDS.values() for p in globs]
    if not any(path.match(pattern) for pattern in patterns):
        raise Refused("%s is not a capture file" % path.name)
    if path not in verified:
        raise Refused("%s was not verified in this pass" % path.name)
    for attempt in range(TRIES):
        try:
            path.unlink()
            return True
        except OSError as exc:
            if attempt + 1 == TRIES:
                # The archive is already good, so this is not a reason
                # to abandon anything: the next compaction finds the
                # file already inside and deletes it then.
                say("[!] %s is archived but could not be deleted (%s)."
                    % (path.name, type(exc).__name__))
                return False
            time.sleep(BACKOFF)


def compact(folder, preset=DEFAULT_PRESET, say=print, delete=True) -> dict:
    """Archive what is due, then delete what verified. The whole run.

    Returns {"archived": [names], "deleted": [names], "failed": str|None}.
    `delete=False` is the dry run: everything is written and verified
    and nothing is removed.
    """
    folder = Path(folder)
    result = {"archived": [], "deleted": [], "failed": None}
    sweep(folder)
    adding = [path for paths in due(folder).values() for path in paths]
    if not adding:
        return result

    book = folder / ARCHIVE_NAME
    tmp = folder / TMP_NAME
    try:
        wanted, covered = _build(folder, adding, PRESETS[preset], say)
        problems = _verify(tmp, wanted)
        if problems:
            # A mismatch is not something a retry can fix: either the
            # archive is wrong or the file changed underneath, and both
            # want a human. Nothing is deleted and the old archive is
            # left exactly as it was.
            result["failed"] = problems[0]
            return result
        _replace(tmp, book)
        problems = _verify(book, wanted)
        if problems:
            result["failed"] = problems[0]
            return result
    except OSError as exc:
        result["failed"] = "%s: %s" % (type(exc).__name__, exc)
        return result
    finally:
        if tmp.exists():
            sweep(folder)

    result["archived"] = sorted(wanted)
    if not delete:
        say("[OK] %d capture(s) archived and verified; nothing deleted."
            % len(wanted))
        return result
    for path in adding:
        if path in covered and _delete(folder, path, covered, say):
            result["deleted"].append(path.name)
    # Three counts that usually say one thing. They diverge only when
    # a file would not delete, or when the archive already held members
    # from an earlier pass -- and those are the cases worth spelling
    # out, so the short form is the one that says nothing is amiss.
    added, gone, held = (len(result["archived"]), len(result["deleted"]),
                         len(contents(folder)))
    if added == gone == held:
        say("[OK] %d capture(s) archived to %s." % (added, ARCHIVE_NAME))
    else:
        say("[OK] %d capture(s) archived, %d deleted; %s holds %d file(s)."
            % (added, gone, ARCHIVE_NAME, held))
    return result


def compact_in_background(folder, preset=DEFAULT_PRESET, say=print):
    """Start a compaction off the calling thread, and return the thread.

    The pass rebuilds the whole archive -- about a second at Balanced
    over a hundred captures, half a minute at Strongest -- and there is
    nothing for the UI to wait on, so it runs beside it. A capture
    writing at the same time is not a hazard: a capture only ever
    writes NEW files, and nothing older than the newest few is a
    candidate.

    **Nothing here may raise into the caller.** A thread that dies of
    an unexpected exception dies silently, taking the report with it,
    so the whole run is wrapped and anything unforeseen is reported
    through `say` like the failures the run knows about.
    """
    def work():
        try:
            result = compact(folder, preset=preset, say=say)
        except Exception as exc:                              # noqa: BLE001
            say("[X] Archiving old captures stopped on an unexpected "
                "%s: %s. Nothing was deleted." % (type(exc).__name__, exc))
            return
        if result["failed"]:
            say("[X] Archiving old captures failed: %s. Nothing was "
                "deleted and the previous archive is untouched."
                % result["failed"])

    thread = threading.Thread(target=work, name="capture-archive",
                              daemon=True)
    thread.start()
    return thread


def stream_members(folder, prefix=""):
    """(name, binary stream) for archived captures, in stored order.

    ONE pass over the archive. A `.tar.xz` is a solid stream, so
    reaching a member means decompressing everything ahead of it --
    opening the file once per member turns a walk into a quadratic one.
    The generator hands out each member as it reaches it and closes the
    archive when the caller stops.

    Stored order is OLDEST first, since that is the order `_ordered`
    adds them in. A caller looking for the newest capture that carries
    something keeps the last match rather than breaking on the first.
    """
    book = Path(folder) / ARCHIVE_NAME
    if not book.exists():
        return
    with tarfile.open(book, "r:xz") as tf:
        for info in tf:
            if not info.isfile() or not info.name.startswith(prefix):
                continue
            handle = tf.extractfile(info)
            if handle is not None:
                yield info.name, handle
