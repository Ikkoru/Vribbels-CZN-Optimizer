"""Executable checks for the invariants this project cannot afford to
break silently.

Not a test suite and not a framework: each module here is a plain
function that returns a list of failure strings, and `run_all.py` prints
them. Nothing to install, nothing to configure.

They exist because the invariants they cover are the ones that fail
QUIETLY, or LATE -- a parallel run that disagrees with the sequential
one, a syntax error inside a string literal that `compileall` cannot
see, a game-data table that still parses but no longer means what it
says, a name deleted from under a `setup_ui` that only raises when the
window is next opened. None of those announce themselves at edit time.

Run them from the repo root:

    python checks/run_all.py

Checks that need the maintainer's captured data skip themselves, with a
reason, when `Vribbels/snapshots/` is empty -- so this stays runnable on
a fresh clone.
"""
