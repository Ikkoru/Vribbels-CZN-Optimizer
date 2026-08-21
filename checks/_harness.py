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


def describe(path) -> str:
    return os.path.basename(str(path))
