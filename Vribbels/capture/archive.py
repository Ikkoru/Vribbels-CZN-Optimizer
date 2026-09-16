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
"""

import gzip
import hashlib
import lzma
import os
import tarfile
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


def _build(folder: Path, adding: list, preset: int, say) -> dict:
    """Write the `.tmp` holding the old members plus `adding`.

    Returns {member name: (size, sha256)} for the files just added --
    the fingerprints the verify step demands before anything is
    deleted. A file that will not open after `TRIES` attempts is left
    out and stays loose; the archive is correct without it and the next
    compaction takes it.
    """
    book = folder / ARCHIVE_NAME
    tmp = folder / TMP_NAME
    wanted = {}
    # **A name being added now wins over the copy already inside.** A
    # loose file can legitimately still be there after an interrupted
    # or dry run, and tar does not reject a second member of the same
    # name -- it stores both, so the archive grows by a copy every
    # pass and `extractfile` answers with whichever it reaches last.
    fresh = {member_name(path) for path in adding}
    with tarfile.open(tmp, "w:xz", preset=preset) as out:
        if book.exists():
            with tarfile.open(book, "r:xz") as old:
                for info in old.getmembers():
                    if not info.isfile() or info.name in fresh:
                        continue
                    handle = old.extractfile(info)
                    if handle is not None:
                        out.addfile(info, handle)
        for path in adding:
            name = member_name(path)
            for attempt in range(TRIES):
                try:
                    with _source(path) as stream:
                        size, sha = _digest(stream)
                    with _source(path) as stream:
                        _add(out, name, stream, size)
                    wanted[name] = (size, sha)
                    break
                except OSError as exc:
                    if attempt + 1 == TRIES:
                        say("[!] %s could not be read (%s); left in place, "
                            "the next compaction will take it."
                            % (path.name, type(exc).__name__))
                    else:
                        time.sleep(BACKOFF)
    return wanted


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


def _delete(folder: Path, path: Path, verified: dict, say) -> bool:
    """Remove one loose file, refusing anything not proven archived.

    THREE conditions, and all of them are the point: the file sits
    directly in the snapshots folder, its name matches a capture's, and
    its content was matched against the archive in this same pass.
    `_capture_addon.py` and `__pycache__/` live in this directory, and
    nothing here may ever reach them.
    """
    if path.parent.resolve() != folder.resolve():
        raise Refused("%s is not directly in %s" % (path, folder))
    patterns = [p for globs, _h, _l in KINDS.values() for p in globs]
    if not any(path.match(pattern) for pattern in patterns):
        raise Refused("%s is not a capture file" % path.name)
    if member_name(path) not in verified:
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
        wanted = _build(folder, adding, PRESETS[preset], say)
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
        say("[i] %d capture(s) archived and verified; nothing deleted."
            % len(wanted))
        return result
    for path in adding:
        if member_name(path) in wanted and _delete(folder, path, wanted, say):
            result["deleted"].append(path.name)
    say("[i] %d capture(s) archived, %d deleted; %s holds %d file(s)."
        % (len(result["archived"]), len(result["deleted"]),
           ARCHIVE_NAME, len(contents(folder))))
    return result
