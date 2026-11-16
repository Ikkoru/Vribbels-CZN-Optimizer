"""The capture's hosts-file redirect goes in and comes out touching only
its own lines, and a rewrite that never finished is said out loud.

The hosts file is the system's, and the program runs as Administrator.
Every way this goes wrong is silent until the game cannot connect, or a
player's own entries are gone without their knowing:

1. **Adding appends.** Nothing before the block is written, so its bytes
   come out the same; the block takes the file's own line ending.
2. **Removing a block that is the file's tail cuts the file short**,
   leaving the rest byte for byte, and no copy or marker is made.
3. **A line added after the block survives its removal**; the rewrite
   that takes for it goes through the one-step swap.
4. **Markers edited by hand**: the program's exact lines still come out,
   and removal does not claim success while any of them remain. A line
   that differs at all (another address, other spacing) is the
   player's and stays.
5. **Where Windows refuses the swap**, the file is rewritten in place:
   right, with a copy taken first, a marker that is gone once the write
   is done, and the Capture Log told.
6. **A rewrite in place that never finished** leaves its marker; the
   next launch's dialog names both files and, on Yes, puts the copy
   back and takes the redirect out; on No keeps the file and stops
   asking; without Administrator rights says how and asks again later.
"""

import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "the hosts-file redirect touches only its own lines"

MINE = b"# a hosts file\r\n127.0.0.1 localhost\n10.0.0.1 caf\xe9.lan\r\n"
GAME = ("one.game.example", "two.game.example")


def _scratch(content=MINE):
    root = Path(tempfile.mkdtemp(prefix="hosts_"))
    path = root / "hosts"
    path.write_bytes(content)
    return root, path


def _appends_and_cuts(hf):
    out = []
    root, path = _scratch()
    hf.add(path, GAME)
    added = path.read_bytes()
    if not added.startswith(MINE):
        out.append("adding the redirect changed the lines before it; it has "
                   "to be appended, never written over the file.")
    block = added[len(MINE):]
    if block.count(b"\r\n") != block.count(b"\n"):
        out.append("the block's lines do not end the way the file's last "
                   "line does (CRLF).")
    how, _rest = hf.removal(hf.read(path), GAME)
    if how != "tail":
        out.append(f"a block that is the file's last lines was to be taken "
                   f"out by {how!r}, not by cutting the file short; a "
                   f"rewrite writes every line the player owns.")
    said = []
    hf.remove(path, GAME, root / "backups", said.append)
    if path.read_bytes() != MINE:
        out.append(f"adding and removing the redirect did not give the file "
                   f"back byte for byte: {path.read_bytes()!r}.")
    if (root / "backups").exists() or said:
        out.append("cutting the block off the file's end copied the file or "
                   "spoke; only a rewrite in place needs either.")
    return out


def _a_line_after_the_block(hf):
    root, path = _scratch()
    hf.add(path, GAME)
    path.write_bytes(path.read_bytes() + b"10.9.9.9 added.later\r\n")
    hf.remove(path, GAME, root / "backups", lambda line: None)
    if path.read_bytes() != MINE + b"10.9.9.9 added.later\r\n":
        return [f"a line added after the block did not survive the block's "
                f"removal, or the block stayed: {path.read_bytes()!r}."]
    return []


def _markers_edited(hf):
    out = []
    root, path = _scratch()
    hf.add(path, GAME)
    edited = path.read_bytes().replace(hf.BLOCK_END.encode() + b"\r\n", b"")
    # The player's own lines that look like the program's and are not.
    edited += b"127.0.0.1  one.game.example\r\n0.0.0.0 two.game.example\r\n"
    path.write_bytes(edited)
    try:
        removed = hf.remove(path, GAME, root / "backups", lambda line: None)
    except hf.HostsError as e:
        return [f"removal gave up on a block with its end marker deleted "
                f"({e}), where the program's exact lines can still be "
                f"found and taken out."]
    left = hf.leftovers(hf.read(path), GAME)
    if not removed or left:
        out.append(
            f"with the end marker deleted by hand, the program's lines were "
            f"not all taken out ({left}). The game cannot connect while "
            f"they stand, and nothing would say why.")
    if not path.read_bytes().startswith(MINE) or \
            b"127.0.0.1  one.game.example" not in path.read_bytes() or \
            b"0.0.0.0 two.game.example" not in path.read_bytes():
        out.append("removing the program's lines took a line of the "
                   "player's: only the exact lines the program writes are "
                   "its own.")
    return out


def _claims_no_success(hf):
    """A redirect line that will not come out is reported, not passed."""
    root, path = _scratch()
    hf.add(path, GAME)
    real_replace = hf.replace
    hf.replace = lambda *a, **k: None          # a rewrite that changes nothing
    try:
        path.write_bytes(path.read_bytes() + b"# after\r\n")
        hf.remove(path, GAME, root / "backups", lambda line: None)
    except hf.HostsError:
        return []
    finally:
        hf.replace = real_replace
    return ["removal returned while the program's lines were still in the "
            "file. The game cannot connect, and the program says it is "
            "fine."]


def _swap_refused(hf):
    out = []
    root, path = _scratch()
    hf.add(path, GAME)
    path.write_bytes(path.read_bytes() + b"# after\r\n")
    real_swap = hf._swap
    hf._swap = lambda *a: False
    said = []
    try:
        hf.remove(path, GAME, root / "backups", said.append)
    finally:
        hf._swap = real_swap
    if path.read_bytes() != MINE + b"# after\r\n":
        out.append(f"with the one-step swap refused, the rewrite in place "
                   f"left {path.read_bytes()!r}.")
    backups = root / "backups"
    if not (backups / hf.BACKUP_NAME).exists():
        out.append("a rewrite in place kept no copy of the file first: a "
                   "crash in the middle of it would lose the player's lines "
                   "with nothing to put back.")
    if hf.interrupted(backups) is not None:
        out.append("a rewrite in place that finished left its marker; every "
                   "launch would then ask about a damage that never was.")
    if not said:
        out.append("a rewrite in place was not said in the Capture Log.")
    if list(path.parent.glob("*.czn-new")):
        out.append("the refused swap's new file was left beside the hosts "
                   "file.")
    return out


def _interrupted_and_asked(hf, gui):
    out = []
    root, path = _scratch()
    hf.add(path, GAME)
    path.write_bytes(path.read_bytes() + b"# after\r\n")
    before = path.read_bytes()
    backups = root / "backups"
    real_swap, real_in_place = hf._swap, hf._in_place

    def dies(where, data):
        where.write_bytes(data[:5])        # the crash: half a file
        raise KeyboardInterrupt
    hf._swap, hf._in_place = (lambda *a: False), dies
    try:
        hf.remove(path, GAME, backups, lambda line: None)
    except KeyboardInterrupt:
        pass
    finally:
        hf._swap, hf._in_place = real_swap, real_in_place
    if hf.interrupted(backups) is None:
        return ["a rewrite in place that was cut short left no marker, so "
                "the next launch cannot know the hosts file may have lost "
                "lines."]

    boxes = []

    def say(title, text, flags, answer=None):
        boxes.append((title, text))
        return answer
    # Not Administrator: told how, and asked again later.
    gui._offer_hosts_restore(lambda t, x, f: say(t, x, f), lambda: False,
                             backups)
    if not boxes or str(path) not in boxes[-1][1] or \
            str(backups / hf.BACKUP_NAME) not in boxes[-1][1]:
        out.append("an interrupted rewrite was not said at launch with the "
                   "hosts file's path and the copy's.")
    if hf.interrupted(backups) is None:
        out.append("without Administrator rights the marker was dropped, so "
                   "the elevated launch never asks.")
    # Administrator, Yes: the copy goes back, the redirect comes out.
    gui._offer_hosts_restore(
        lambda t, x, f: say(t, x, f, gui.IDYES), lambda: True, backups)
    if path.read_bytes() != MINE + b"# after\r\n":
        out.append(f"Yes did not put the copy back with the redirect taken "
                   f"out: {path.read_bytes()!r}, from {before!r}.")
    if hf.interrupted(backups) is not None:
        out.append("after restoring, the marker stayed: every launch asks "
                   "again.")
    return out


def _no_keeps_the_file(hf, gui):
    root, path = _scratch()
    backups = root / "backups"
    backups.mkdir()
    (backups / hf.BACKUP_NAME).write_bytes(b"# the copy\r\n")
    (backups / hf.PENDING_NAME).write_text(str(path), encoding="utf-8")
    gui._offer_hosts_restore(lambda t, x, f: 7, lambda: True, backups)  # IDNO
    out = []
    if path.read_bytes() != MINE:
        out.append("No still changed the hosts file.")
    if hf.interrupted(backups) is not None:
        out.append("after No, the marker stayed, so the question comes back "
                   "at every launch.")
    return out


def run():
    add_source_to_path()
    from capture import hosts as hf
    import czn_optimizer_gui as gui
    failures = _appends_and_cuts(hf)
    failures.extend(_a_line_after_the_block(hf))
    failures.extend(_markers_edited(hf))
    failures.extend(_claims_no_success(hf))
    failures.extend(_swap_refused(hf))
    failures.extend(_interrupted_and_asked(hf, gui))
    failures.extend(_no_keeps_the_file(hf, gui))
    return failures


FAULTS = [
    ("the block written over the file", "capture.hosts:add",
     'with open(path, "a",', 'with open(path, "w",',
     "changed the lines before it"),
    ("a tail block rewritten", "capture.hosts:removal",
     '        return "tail", rest\n', '        return "rewrite", rest\n',
     "not by cutting the file short"),
    ("only marked blocks removed", "capture.hosts:removal",
     "            if line and line.rstrip(\"\\r\\n\") not in ours]",
     "            if line]",
     "were not all taken out"),
    ("success claimed with lines left", "capture.hosts:remove",
     "    if left:\n", "    if False:\n",
     "still in the file"),
    ("no copy before a rewrite in place", "capture.hosts:replace",
     "        shutil.copyfile(path, backup)\n", "",
     "kept no copy"),
    ("no marker around a rewrite in place", "capture.hosts:replace",
     ['        pending.write_text(str(path), encoding="utf-8")\n',
      "        pending.unlink()\n"], ["", "        pass\n"],
     "left no marker"),
    ("the marker dropped without rights",
     "czn_optimizer_gui:_offer_hosts_restore",
     "            MB_OK | MB_ICONWARNING)\n        return\n",
     "            MB_OK | MB_ICONWARNING)\n"
     "        hosts_file.settle(backups, restore=False)\n        return\n",
     "the marker was dropped"),
]
