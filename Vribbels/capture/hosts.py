"""The capture's redirect in the Windows hosts file: added without
rewriting the file, taken out touching as little as it can.

The file belongs to the system and carries other people's entries, so
nothing here rewrites what the program did not write unless it has to,
and never so that a crash could leave the file half-written without the
next launch saying so:

* **Adding appends.** The block goes on the end of the file; nothing
  before it is written. A crash mid-append leaves at worst part of the
  block, which removal takes out like the rest.
* **Removing cuts the file short** where the block is still its last
  lines, which is the usual case: the bytes before it are not written.
* **Where something follows the block**, or its markers were edited, the
  file is rewritten without the program's lines -- through
  `ReplaceFileW`, which swaps a complete new file in for the old in one
  step and keeps the old one's permissions and attributes. At every
  moment the file is either the old or the new.
* **Where Windows refuses the swap** (some antivirus guards the hosts
  file), it is rewritten in place. That is the one path a crash could
  corrupt, so it copies the file first and leaves a marker until the
  write is done; `interrupted` finds the marker at the next launch, and
  the main window asks before it opens.

Which lines are the program's is known exactly: the two markers and
`127.0.0.1 <host>` for each game host. A line that differs at all is not
the program's and is left alone.

Read and written as UTF-8 with surrogateescape, which round-trips any
byte, and with no newline translation, so the file's own line endings
stay as they are.
"""

import os
import re
import shutil
import sys
from pathlib import Path

# The markers around the block this program appends. Everything between
# them is the program's; nothing outside them is, but its own exact
# lines (see `removal`).
BLOCK_START = "# CZN-CAPTURE-START"
BLOCK_END = "# CZN-CAPTURE-END"
REDIRECT = "127.0.0.1 %s"

_BLOCK_RE = re.compile(
    re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"(?:\r?\n)?",
    re.DOTALL)
_LINE_RE = re.compile(r"[^\n]*(?:\n|$)")

# The marker a rewrite in place leaves while it runs, beside its copy.
PENDING_NAME = "hosts_rewrite_pending"
BACKUP_NAME = "hosts_before_rewrite"


class HostsError(Exception):
    """The redirect could not be added or taken out; the message says
    what to do."""


def read(path) -> str:
    with open(path, encoding="utf-8", errors="surrogateescape",
              newline="") as f:
        return f.read()


def _bytes(text) -> bytes:
    return text.encode("utf-8", errors="surrogateescape")


def line_ending(content: str) -> str:
    """The line ending the file's last line uses; CRLF, Windows' own,
    for a file with none."""
    found = re.search(r"\r?\n(?!.*\n)", content, re.DOTALL)
    return found.group(0) if found else "\r\n"


def addition(content: str, hosts) -> str:
    """What `add` appends to `content`: a line ending first where its
    last line has none, so the block starts on a line of its own, then
    the block, in the file's own line ending."""
    eol = line_ending(content)
    lead = eol if content and not content.endswith("\n") else ""
    lines = [BLOCK_START] + [REDIRECT % h for h in hosts] + [BLOCK_END]
    return lead + eol.join(lines) + eol


def add(path, hosts) -> None:
    """Append the redirect to the file at `path`."""
    text = addition(read(path), hosts)
    with open(path, "a", encoding="utf-8", errors="surrogateescape",
              newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def _ours(hosts):
    return {REDIRECT % h for h in hosts} | {BLOCK_START, BLOCK_END}


def removal(content: str, hosts):
    """(how, what remains) for taking the redirect out of `content`.

    `how` is "clean" (nothing of the program's there), "tail" (one block,
    the file's last lines: cut the file short), "rewrite" (anything
    else: a block with something after it, more than one, or markers
    edited so only the program's exact lines are left to find).
    """
    found = list(_BLOCK_RE.finditer(content))
    rest = _BLOCK_RE.sub("", content)
    ours = _ours(hosts)
    kept = [line for line in _LINE_RE.findall(rest)
            if line and line.rstrip("\r\n") not in ours]
    remains = "".join(kept)
    if not found and remains == content:
        return "clean", content
    if (len(found) == 1 and found[0].end() == len(content)
            and remains == rest):
        return "tail", rest
    return "rewrite", remains


def leftovers(content: str, hosts) -> list:
    """The program's own lines still in `content`."""
    ours = _ours(hosts)
    return [line.rstrip("\r\n") for line in _LINE_RE.findall(content)
            if line.rstrip("\r\n") in ours]


def remove(path, hosts, backups, say) -> bool:
    """Take the redirect out of the file at `path`. False where there
    was none. `backups` is the folder an in-place rewrite copies the
    file to first; `say(line)` reports. Raises HostsError where any of
    the program's lines remain after."""
    path = Path(path)
    content = read(path)
    how, remains = removal(content, hosts)
    if how == "clean":
        return False
    if how == "tail":
        with open(path, "r+b") as f:
            f.truncate(len(_bytes(remains)))
            f.flush()
            os.fsync(f.fileno())
    else:
        replace(path, remains, backups, say)
    left = leftovers(read(path), hosts)
    if left:
        raise HostsError(
            f"The capture's lines are still in {path} after removing "
            f"them: {left}. Delete those lines by hand (as "
            f"Administrator); until then the game cannot connect.")
    return True


def _swap(path: Path, replacement: Path) -> bool:
    """Put `replacement` in place of `path` in one step, keeping `path`'s
    permissions and attributes. False where Windows refuses."""
    if sys.platform != "win32":
        os.replace(replacement, path)
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ReplaceFileW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
    return bool(kernel32.ReplaceFileW(str(path), str(replacement), None,
                                      0, None, None))


def _in_place(path: Path, data: bytes) -> None:
    with open(path, "r+b") as f:
        f.truncate(0)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def replace(path, text: str, backups, say) -> None:
    """Make the file at `path` read `text`: swapped in whole where
    Windows allows, else rewritten in place with a copy and a marker
    kept around the write (see `interrupted`)."""
    path = Path(path)
    data = _bytes(text)
    new = path.with_name(path.name + ".czn-new")
    try:
        with open(new, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if _swap(path, new):
            return
    except OSError:
        pass
    try:
        new.unlink()
    except OSError:
        pass
    backups = Path(backups)
    backups.mkdir(parents=True, exist_ok=True)
    backup, pending = backups / BACKUP_NAME, backups / PENDING_NAME
    # **An outstanding marker keeps its copy.** It belongs to a rewrite
    # that never finished, which `settle` may be restoring right now:
    # copying over it would put the damaged file where the good one was.
    ours = not pending.exists()
    if ours:
        shutil.copyfile(path, backup)
        pending.write_text(str(path), encoding="utf-8")
    _in_place(path, data)
    if ours:
        pending.unlink()
    say(f"[!] Windows refused to swap the hosts file in one step, so it "
        f"was rewritten in place. It is complete; the copy from just "
        f"before is {backup}.")


def interrupted(backups):
    """(hosts path, copy) where a rewrite in place did not finish -- the
    program stopped between the marker and its removal -- else None."""
    pending = Path(backups) / PENDING_NAME
    if not pending.exists():
        return None
    try:
        hosts = Path(pending.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return hosts, Path(backups) / BACKUP_NAME


def settle(backups, restore: bool, say=lambda line: None) -> None:
    """Close an interrupted rewrite: put the copy back over the hosts
    file where `restore`, then drop the marker either way. Raises
    OSError where the copy cannot be put back (no Administrator rights);
    the marker then stays, so the next launch asks again."""
    found = interrupted(backups)
    if found is None:
        return
    hosts, backup = found
    if restore:
        replace(hosts, read(backup), backups, say)
    (Path(backups) / PENDING_NAME).unlink()
