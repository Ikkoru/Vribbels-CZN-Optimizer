"""The app in a state other than the maintainer's own, for the spacing
audit: a scratch copy of the user data, so the live folders are never
read for anything but the copy and never written at all.

    python czn_optimizer_gui.py --spacing-audit --audit-state=empty

Two states, both with nothing captured:

  empty   the maintainer's settings, copied, and an empty snapshots
          folder. What the panels do with no data to size to.
  fresh   no settings at all, so the startup sync installs the shipped
          defaults, and an empty snapshots folder. A new user's first
          launch.

Each is rebuilt from nothing on every launch that asks for it, under
`_tmp/audit_states/<state>/`, so a run never sees what the last one
left. That folder holds only these, and carries a CACHEDIR.TAG.

**Both data roots follow the state**: `capture.constants.BASE_DIR`, which
the snapshots folder hangs off, and the app's settings folder, which is
`czn_optimizer_gui._user_data_dir()` and returns the same root. A state
that moved one and not the other would read the copy's settings beside
the live captures, or the reverse, and look like a state it is not.

The shipped defaults are NOT data and do not move: `default_settings/`
is read from the source tree, which is what makes `fresh` install them.

Only from source. A frozen build ignores the flag, so a released exe
cannot be pointed away from the folder its user's data is in.
"""

import shutil
import sys
from pathlib import Path

FLAG = "--audit-state"
EMPTY, FRESH = "empty", "fresh"
STATES = (EMPTY, FRESH)

# The repository's scratch folder. Its subfolder for these is wholly
# disposable, so it carries the tag that keeps it out of backups.
STATES_DIR = Path(__file__).resolve().parent.parent / "_tmp" / "audit_states"
CACHEDIR_TAG = (b"Signature: 8a477f597d28d172789f06886806bc55\n"
                b"# The spacing audit's scratch states: rebuilt on every "
                b"launch that asks for one. See Vribbels/audit_states.py.\n")


def requested(argv=None):
    """The state `argv` asks for, or None.

    Raises SystemExit on a state that does not exist: carrying on would
    run against the LIVE folders, which is the one thing this module is
    for preventing.
    """
    if getattr(sys, "frozen", False):
        return None
    argv = sys.argv if argv is None else argv
    for arg in argv:
        if arg == FLAG or arg.startswith(FLAG + "="):
            state = arg.partition("=")[2]
            if state not in STATES:
                raise SystemExit(
                    f"{FLAG}={state}: no such state. One of: "
                    f"{', '.join(STATES)}.")
            return state
    return None


def root_for(state):
    """The scratch folder `state` runs in."""
    return STATES_DIR / state


def data_root(default, argv=None):
    """The folder user data lives in: the requested state's, or
    `default` when no state is asked for."""
    state = requested(argv)
    return root_for(state) if state else default


def prepare(state, live_root):
    """Rebuild `state`'s folder from nothing.

    `live_root` is the folder the maintainer's own `settings/` is in. It
    is only ever READ: `empty` copies its settings, and nothing else of
    it is touched.

    Returns the state's root.
    """
    if state not in STATES:
        raise ValueError(f"no audit state {state!r}")
    root = root_for(state)
    live_root = Path(live_root).resolve()
    # The guard on the one destructive line here: it deletes only a
    # folder that is a direct child of STATES_DIR, and never one that
    # holds the live data or sits above it.
    if (root.resolve().parent != STATES_DIR.resolve()
            or root.resolve() in (live_root, *live_root.parents)):
        raise ValueError(f"refusing to rebuild {root}")
    STATES_DIR.mkdir(parents=True, exist_ok=True)
    tag = STATES_DIR / "CACHEDIR.TAG"
    if not tag.exists():
        tag.write_bytes(CACHEDIR_TAG)
    if root.exists():
        shutil.rmtree(root)
    (root / "snapshots").mkdir(parents=True)
    if state == EMPTY and (live_root / "settings").is_dir():
        shutil.copytree(live_root / "settings", root / "settings")
    return root
