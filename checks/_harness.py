"""Shared plumbing: import path, snapshot discovery, result types."""

import glob
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT / "Vribbels"


def add_source_to_path() -> None:
    """Make `Vribbels/` importable, and make it the working directory.

    Both matter. The package uses plain top-level imports
    (`from game_data import ...`), and several managers resolve their
    files relative to the process's directory.
    """
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    os.chdir(SOURCE_ROOT)


def newest_snapshot():
    """Newest capture snapshot, or None when there are none.

    Snapshots are the maintainer's own captured game data and are
    gitignored, so every check that needs one must handle None by
    SKIPPING rather than failing -- otherwise a fresh clone reports
    breakage that isn't there.
    """
    snaps = glob.glob(str(SOURCE_ROOT / "snapshots" / "*.json"))
    return max(snaps, key=os.path.getmtime) if snaps else None


class Skip(Exception):
    """Raised by a check that cannot run here. Not a failure."""


# What the check about to finish could NOT cover. Drained by the runner
# after every check; see `note`.
NOTES = []


def note(text: str) -> None:
    """Say that part of this check's coverage was not exercised.

    A check that still passes with half its ground unchecked reports the
    same `ok` as one that checked everything, and the gap is invisible
    exactly when it matters -- a snapshot folder emptied for an unrelated
    reason leaves every row-level assertion running over zero rows. A
    note prints beside the result without failing a fresh clone, which
    legitimately has no captured data.

    For coverage lost, not for progress: a check with nothing to say
    says nothing.
    """
    NOTES.append(str(text))


def take_notes():
    """Everything noted since the last drain, emptying the list."""
    held = list(NOTES)
    NOTES.clear()
    return held


def describe(path) -> str:
    return os.path.basename(str(path))
