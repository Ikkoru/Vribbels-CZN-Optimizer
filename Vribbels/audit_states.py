"""Every rendered run -- the spacing audit, the font gauge, the scale
survey -- in a scratch copy of the user data, so the live folders are
never read for anything but the copy and never written at all.

    python czn_optimizer_gui.py --spacing-audit --audit-state=empty

`--audit-scale=200%` runs any of them at a UI scale the settings do not
hold, and writes nothing about it (`requested_scale`).

Three copies, one per state:

  own     the maintainer's settings and snapshots, copied. What a
          rendered run with no `--audit-state` works in.
  empty   the maintainer's settings, copied, and an empty snapshots
          folder. What the panels do with no data to size to.
  fresh   no settings at all, so the startup sync installs the shipped
          defaults, and an empty snapshots folder. A new user's first
          launch.

Each is rebuilt from nothing on every launch that asks for it, under
`_tmp/audit_states/<state>/`, so a run never sees what the last one
left. That folder holds only these, and carries a CACHEDIR.TAG.

**A run in a copy takes no single-instance lock** (`czn_optimizer_gui.
main`): the lock keeps two copies of the program off one data folder,
and a rendered run has a folder of its own and never captures. So the
program can stay open while one runs, and can be opened during one.

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

import os
import shutil
import sys
from pathlib import Path

FLAG = "--audit-state"
EMPTY, FRESH = "empty", "fresh"
STATES = (EMPTY, FRESH)
# The maintainer's own data, copied. Not a state `--audit-state` names:
# it is where a rendered run with none works, and its baseline is the
# unsuffixed one.
OWN = "own"

# What makes a launch a rendered run, on the command line or in the
# environment. `czn_optimizer_gui.OptimizerGUI._spacing_audit_wanted`
# reads this one list.
RENDERED_FLAGS = ("--spacing-audit", "--spacing-audit-verbose",
                  "--spacing-audit-freeze", "--scale-survey", "--font-gauge")
RENDERED_ENV = "CZN_SPACING_AUDIT"
SCALE_FLAG = "--audit-scale"
SCALES = ("100%", "125%", "150%", "175%", "200%")

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


def requested_scale(argv=None):
    """The UI scale `argv` asks an audit run for (`--audit-scale=200%`),
    or None to keep the one saved in settings.

    The run uses it and nothing writes it, so an audit at 200% leaves
    the maintainer's own setting as it was. Spelled as the Settings
    dropdown spells it, `ui.scaling.SCALE_CHOICES`, which
    `check_audit_states` holds `SCALES` to; an unknown one stops the
    app, as an unknown state does. Ignored by a frozen build.
    """
    if getattr(sys, "frozen", False):
        return None
    argv = sys.argv if argv is None else argv
    for arg in argv:
        if arg.startswith(SCALE_FLAG + "="):
            scale = arg.partition("=")[2]
            if scale not in SCALES:
                raise SystemExit(f"{SCALE_FLAG}={scale}: no such scale. "
                                 f"One of: {', '.join(SCALES)}.")
            return scale
    return None


def rendered(argv=None):
    """Whether this launch is a rendered run: rendered, never shown,
    and exiting once it has reported."""
    argv = sys.argv if argv is None else argv
    return (any(flag in argv for flag in RENDERED_FLAGS)
            or os.environ.get(RENDERED_ENV) in ("1", "verbose"))


def copy_for(argv=None):
    """The copy this launch works in, or None for the live folders: the
    state asked for, else `OWN` for a rendered run. None in a frozen
    build, which works where its user's data is, whatever it is asked.
    """
    if getattr(sys, "frozen", False):
        return None
    return requested(argv) or (OWN if rendered(argv) else None)


def root_for(state):
    """The scratch folder `state` runs in."""
    return STATES_DIR / state


def data_root(default, argv=None):
    """The folder user data lives in: the copy this launch works in, or
    `default` when it works in none."""
    copy = copy_for(argv)
    return root_for(copy) if copy else default


def prepare(state, live_root):
    """Rebuild `state`'s folder from nothing.

    `live_root` is the folder the maintainer's own `settings/` is in. It
    is only ever READ: `empty` copies its settings, `own` its settings
    and snapshots, and nothing else of it is touched.

    Returns the state's root.
    """
    if state not in STATES + (OWN,):
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
    if state == OWN and (live_root / "snapshots").is_dir():
        shutil.copytree(live_root / "snapshots", root / "snapshots")
    else:
        (root / "snapshots").mkdir(parents=True)
    if state in (EMPTY, OWN) and (live_root / "settings").is_dir():
        shutil.copytree(live_root / "settings", root / "settings")
    return root
