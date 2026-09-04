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

## Adding one

A module here needs two names: `NAME`, the line `run_all.py` prints,
and `run()`, returning a list of complaint strings -- empty for a pass.
Call `add_source_to_path()` from `._harness` before importing anything
under `Vribbels/`, raise `Skip("reason")` where the check cannot run,
and add the module to `run_all.py` twice: once to the import block and
once to `CHECKS`, which is ordered cheapest first.

**A complaint says what broke, what it costs, and where to look.** The
reader is meeting the invariant for the first time, and a check that
only names a mismatch leaves them to rediscover why it matters.

**Prove a new check FAILS before trusting it.** Break the thing it
guards, watch it report, put it back. A check that has never failed is
an untested claim.
"""
