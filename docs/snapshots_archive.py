"""Fold superseded captures into `archived_captures.tar.xz`, by hand.

The program does this by itself at launch. This is the same code with
a report attached, for a run the maintainer chooses the moment of.

    python docs/snapshots_archive.py              # what it WOULD do
    python docs/snapshots_archive.py --write      # do it
    python docs/snapshots_archive.py --write --strongest
    python docs/snapshots_archive.py --list       # what is in there

**It reports by default and deletes only when told to.** `--write`
without `--dry-run` is what removes the loose copies, and only after
each one's archived member has been read back and its SHA-256 matched.

`--folder` points it somewhere other than `Vribbels/snapshots/`, which
is the only way to try it against a copy rather than the real captures.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Vribbels"
sys.path.insert(0, str(SOURCE))

from capture import archive                                    # noqa: E402

DEFAULT_FOLDER = SOURCE / "snapshots"

# How many members to print in full before falling back to a count.
SHOW = 40


def megabytes(count: int) -> str:
    return "%.1f MB" % (count / 1e6)


def show_contents(folder: Path) -> int:
    held = archive.contents(folder)
    book = folder / archive.ARCHIVE_NAME
    if not held:
        print("No %s in %s." % (archive.ARCHIVE_NAME, folder))
        return 0
    inside = sum(size for _name, size in held)
    print("%s: %d file(s), %s of captures in %s on disk"
          % (archive.ARCHIVE_NAME, len(held), megabytes(inside),
             megabytes(book.stat().st_size)))
    for name, size in held[:SHOW]:
        print("   %-46s %10d" % (name[:46], size))
    if len(held) > SHOW:
        print("   ... and %d more" % (len(held) - SHOW))
    return 0


def main(argv):
    argv = list(argv[1:])
    write = "--write" in argv
    preset = "strongest" if "--strongest" in argv else archive.DEFAULT_PRESET
    folder = DEFAULT_FOLDER
    if "--folder" in argv:
        at = argv.index("--folder")
        folder = Path(argv[at + 1]).resolve()
    if not folder.is_dir():
        print("No such folder: %s" % folder)
        return 1
    if "--list" in argv:
        return show_contents(folder)

    pending = archive.due(folder)
    if not pending:
        for kind, (globs, high, low) in archive.KINDS.items():
            loose = archive._ordered(folder, globs)
            print("%-10s %2d loose, compacts at %d, keeps %d"
                  % (kind, len(loose), high, low))
        print("\nNothing due.")
        return 0

    for kind, paths in pending.items():
        print("%s: %d file(s) to archive, %s"
              % (kind, len(paths),
                 megabytes(sum(p.stat().st_size for p in paths))))
    print()

    result = archive.compact(folder, preset=preset, delete=write)
    if result["failed"]:
        print("\nFAILED: %s" % result["failed"])
        print("Nothing was deleted and the previous archive is untouched.")
        return 1
    if not write:
        print("\n`--write` archives these and deletes the loose copies.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
