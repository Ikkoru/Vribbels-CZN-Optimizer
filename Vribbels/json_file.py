"""Saving a JSON file so that a crash never leaves half of one, and
setting aside one that would not read.

The settings files, the shared facts and the stats history all save
through `write_json`: the text goes to a `.tmp` beside the file, is
forced to disk, and only then takes the file's place. A crash or a
power cut at any point leaves either the old file or the new one, never
one cut short -- the state the corrupted-file recovery exists for.

**Forcing the copy to disk is the half that is easy to drop.** Without
it the rename can reach the disk before the data does, and a power cut
between the two leaves a file of the right name with nothing in it.

Not for the capture addon, which runs inside mitmproxy from a script
generated with everything it needs written into it, nor for the Gacha
History store, which reads its copy back before keeping it
(`gacha_history.write_verified`).
"""

import json
import os
from pathlib import Path


def write_json(path, data, *, indent=2, ensure_ascii=True, sort_keys=False,
               end=""):
    """Write `data` over `path` as JSON, by way of a copy on disk.

    The keyword arguments are `json.dumps`'s, and `end` is appended to
    the text. Text mode, as `Path.write_text` writes, so a file saved
    here is the same bytes it was before. The folder must exist.
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii,
                      sort_keys=sort_keys) + end
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def set_aside(path):
    """Rename a file that would not read to the first free
    `<stem>_corrupted<suffix>`, then `_corrupted2`, `_corrupted3`, ...
    beside it, so a fresh one can be saved in its place and the old one
    is still there to recover from. Returns where it went, or None where
    there was no file."""
    path = Path(path)
    if not path.exists():
        return None
    n = 1
    while True:
        tag = "_corrupted" if n == 1 else f"_corrupted{n}"
        target = path.with_name(f"{path.stem}{tag}{path.suffix}")
        if not target.exists():
            break
        n += 1
    os.rename(path, target)
    return target
