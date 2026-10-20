"""A check leaves no Tk timer pending, and the runner fails one that
does.

A built tab arms `after()` chains -- the Optimizer's `check_queue`
re-arms itself every 100ms -- and `root.destroy()` deletes their
commands but not their timers, which belong to the thread. The next
check that runs Tk's event loop fires each into nothing, and stderr
gets `invalid command name "2823162179456check_queue"` under a check
that passes and had nothing to do with it, often dozens of checks
after the one that left it.

Two halves. `_harness.destroy_root` cancels what a root still holds, and
`run_all._run` records every root a check makes, cancels what is left
on them when it ends and fails that check by name. This drives the
runner with a three-check suite -- one destroying its root plainly, one
through `destroy_root`, one destroying its root as a `<Destroy>`
handler arms a timer -- and reads what it says and what is still
pending afterwards.
"""

import io
from contextlib import redirect_stdout
from types import SimpleNamespace

from ._harness import Skip, destroy_root, pending_timers

NAME = "a check leaves no Tk timer pending"

LEAKS = "leaves a timer on its destroyed root"
TIDY = "destroys its root with destroy_root"
LATE = "a <Destroy> handler arms a timer"


def _never():
    pass


def run():
    try:
        import tkinter as tk
        tk.Tk().destroy()
    except Exception as exc:                # noqa: BLE001
        raise Skip(f"Tk will not start here ({type(exc).__name__})")

    from checks import run_all

    roots = {}

    def leaks():
        root = roots[LEAKS] = tk.Tk()
        root.after(60_000, _never)
        root.destroy()
        return []

    def tidy():
        root = roots[TIDY] = tk.Tk()
        root.after(60_000, _never)
        destroy_root(root)
        return []

    def late():
        root = roots[LATE] = tk.Tk()
        root.bind("<Destroy>", lambda _e: root.after(60_000, _never))
        destroy_root(root)
        return []

    suite = [SimpleNamespace(NAME=LEAKS, run=leaks),
             SimpleNamespace(NAME=TIDY, run=tidy),
             SimpleNamespace(NAME=LATE, run=late)]
    saved = run_all.CHECKS
    run_all.CHECKS = suite
    said = io.StringIO()
    try:
        with redirect_stdout(said):
            run_all.main([])
    finally:
        run_all.CHECKS = saved
    said = said.getvalue()

    failures = []
    if f"FAIL\033[0m {LEAKS}" not in said or "_never" not in said:
        failures.append(
            "run_all did not fail a check that destroyed its root with a "
            "timer still pending, or did not name the timer's callback. "
            "Such a timer fires during the next check that runs Tk's "
            "event loop and prints 'invalid command name' there, so the "
            "leak is reported against the wrong check or not at all. "
            "See _record_tk_roots and _leftover_timers in run_all.py. "
            f"It printed:\n{said}")
    for name in (TIDY, LATE):
        if f"ok\033[0m   {name}" not in said:
            failures.append(
                f"the check that {name} did not pass: destroy_root left a "
                f"timer pending, so every check using it still leaks one "
                f"into the next check's event loop. See "
                f"checks/_harness.py. It printed:\n{said}")
    for name, root in roots.items():
        try:
            left = pending_timers(root)
        except Exception:                   # noqa: BLE001
            continue
        if left:
            failures.append(
                f"after the run, the root of the check that {name} still "
                f"holds {len(left)} timer(s). run_all must cancel what a "
                f"check leaves, or the next check's event loop fires it "
                f"anyway, failure reported or not.")
    return failures


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("the runner records no roots", "checks.run_all:_record_tk_roots",
     "        made.append(self)\n", "        pass\n",
     "run_all did not fail a check"),
    ("the runner reports but does not cancel",
     "checks.run_all:_leftover_timers",
     '            root.tk.call("after", "cancel", aid)\n', "",
     "still holds"),
    ("destroy_root does not cancel", "checks._harness:destroy_root",
     '            root.tk.call("after", "cancel", aid)\n',
     "            pass\n",
     "destroy_root left a timer pending"),
    ("destroy_root cancels before destroying",
     "checks._harness:destroy_root",
     ["    try:\n        root.destroy()\n    except Exception:\n"
      "        pass\n",
      "    except Exception:           # the interpreter itself is gone\n"
      "        pass\n"],
     ["",
      "    except Exception:           # the interpreter itself is gone\n"
      "        pass\n    root.destroy()\n"],
     "a <Destroy> handler arms a timer did not pass"),
]
