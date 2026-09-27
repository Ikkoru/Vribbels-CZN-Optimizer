"""A check's Tk garbage is collected on the main thread, before the next
check runs.

A built tab is a reference cycle -- a child names its master, the
master lists its children, a bound method holds its tab -- so every Tk
Variable a check's tabs hold outlives the check as garbage for the
cyclic collector. That collector runs on whichever thread next
allocates enough. When that is a worker thread of a LATER check, each
Variable.__del__ calls Tcl off the thread that made it and prints
"Exception ignored ... main thread is not in main loop", one traceback
per Variable, under a check that passes and had nothing to do with it.

`run_all.main` collects after every check, on the main thread. This
drives it with a two-check suite -- one that leaves a Variable in a
cycle, one that collects on a worker thread -- and listens on
`sys.unraisablehook` for what the worker's collection says.
"""

import gc
import io
import sys
import threading
from contextlib import redirect_stdout
from types import SimpleNamespace

from ._harness import Skip

NAME = "a check's Tk garbage is collected on the main thread"


def _leaves_a_variable_in_a_cycle():
    import tkinter as tk
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    held = SimpleNamespace(var=tk.StringVar(root, value="x"))
    held.itself = held
    root.destroy()
    return []


def _collects_on_a_worker():
    worker = threading.Thread(target=gc.collect)
    worker.start()
    worker.join()
    return []


def run():
    try:
        import tkinter as tk
        tk.Tk().destroy()
    except Exception as exc:                # noqa: BLE001
        raise Skip(f"Tk will not start here ({type(exc).__name__})")

    from checks import run_all

    heard = []
    suite = [
        SimpleNamespace(NAME="leaves a Variable in a cycle",
                        run=_leaves_a_variable_in_a_cycle),
        SimpleNamespace(NAME="collects on a worker thread",
                        run=_collects_on_a_worker),
    ]
    saved_suite, saved_hook = run_all.CHECKS, sys.unraisablehook
    was_enabled = gc.isenabled()
    # Off, so that between the two only the runner's own collection can
    # free the cycle. An automatic pass landing there would pass this
    # whether the runner collects or not.
    gc.disable()
    run_all.CHECKS = suite
    sys.unraisablehook = heard.append
    try:
        with redirect_stdout(io.StringIO()):
            run_all.main([])
    finally:
        run_all.CHECKS = saved_suite
        sys.unraisablehook = saved_hook
        if was_enabled:
            gc.enable()

    if not heard:
        return []
    first = heard[0]
    return [
        f"{len(heard)} exception(s) reached sys.unraisablehook when a "
        f"check's Tk Variable was collected on a later check's worker "
        f"thread; the first: {type(first.exc_value).__name__}: "
        f"{first.exc_value}. run_all.main must "
        f"gc.collect() after every check, on the main thread -- without "
        f"it, run_all prints a traceback per Variable under whichever "
        f"check runs threads next."
    ]
