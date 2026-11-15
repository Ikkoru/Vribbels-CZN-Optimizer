"""An error the player never sees is still kept.

The released build is windowed, so it has no stderr: an exception in a
Tk callback or a thread vanishes, and a bug report can only say that
something did not happen. `error_log.py` keeps them in
`settings/error_log.txt`, through hooks the main window installs before
it builds a tab. Every part of that fails quietly:

1. a hook not installed records nothing, and nothing says so;
2. a log that raises when its folder cannot be written turns a handled
   error into a crash in the handler;
3. a log without a cap grows for as long as an error repeats.

Held on a scratch folder; the live `settings/` is never written.
"""

import contextlib
import inspect
import io
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "errors are kept in error_log.txt"


def _a_callback_error_lands(error_log):
    import tkinter as tk
    out = []
    folder = Path(tempfile.mkdtemp(prefix="errlog_"))
    error_log.configure(folder)
    root = tk.Tk()
    try:
        root.withdraw()
        error_log.install_hooks(root)

        def a_callback_that_raises():
            raise ValueError("the check's own error")

        # Through Tk, as a button's command runs: tkinter catches the
        # exception and hands it to `report_callback_exception`.
        with contextlib.redirect_stderr(io.StringIO()):
            root.tk.call(root.register(a_callback_that_raises))
    finally:
        root.destroy()
    log = folder / "settings" / "error_log.txt"
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    if "a_callback_that_raises" not in text \
            or "the check's own error" not in text:
        out.append(
            "an exception raised in a Tk callback did not reach "
            "error_log.txt with its traceback. The build has no console, "
            "so that error is lost and a bug report can say nothing about "
            "it.")
    return out


def _the_cap_holds(error_log):
    out = []
    folder = Path(tempfile.mkdtemp(prefix="errlog_cap_"))
    error_log.configure(folder)
    held = error_log.MAX_BYTES
    error_log.MAX_BYTES = 4000
    try:
        for n in range(200):
            try:
                raise RuntimeError("entry %d" % n)
            except RuntimeError as e:
                error_log.note("the cap's test", e)
    finally:
        error_log.MAX_BYTES = held
    log = folder / "settings" / "error_log.txt"
    size = log.stat().st_size if log.exists() else 0
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    if size > 4000:
        out.append(
            f"error_log.txt reached {size} bytes against a cap of 4000. An "
            f"error that repeats on every save would fill the disk.")
    if "entry 199" not in text:
        out.append("the cap dropped the newest entry rather than the "
                   "oldest.")
    if text and not text.startswith("20"):
        out.append("the cap cut an entry in two: the file no longer starts "
                   "at an entry's time.")
    return out


def _an_unwritable_folder_is_survived(error_log):
    out = []
    folder = Path(tempfile.mkdtemp(prefix="errlog_ro_"))
    # `settings` is a FILE here, so nothing can be made inside it.
    (folder / "settings").write_text("not a folder", encoding="utf-8")
    error_log.configure(folder)
    try:
        error_log.note("an unwritable folder", ValueError("x"))
    except Exception as e:
        out.append(
            f"error_log.note raised {type(e).__name__} where its folder "
            f"could not be written. It is called from error handlers; one "
            f"that raises turns a handled error into a crash.")
    return out


def _the_window_installs_them_first():
    import czn_optimizer_gui as gui
    source = inspect.getsource(gui.OptimizerGUI.__init__)
    hook = source.find("error_log.install_hooks(self.root)")
    tabs = source.find("self.setup_ui()")
    if hook < 0:
        return ["OptimizerGUI.__init__ no longer installs the error hooks."]
    if 0 <= tabs < hook:
        return ["OptimizerGUI.__init__ installs the error hooks after the "
                "tabs are built, so an error in building one is lost."]
    return []


def run():
    add_source_to_path()
    import sys
    import threading
    import error_log
    held = (error_log._path, sys.excepthook, threading.excepthook)
    try:
        failures = _a_callback_error_lands(error_log)
        failures.extend(_the_cap_holds(error_log))
        failures.extend(_an_unwritable_folder_is_survived(error_log))
    finally:
        error_log._path, sys.excepthook, threading.excepthook = held
    failures.extend(_the_window_installs_them_first())
    return failures


FAULTS = [
    ("the Tk hook not installed", "error_log:install_hooks",
     "    if root is not None:\n", "    if False:\n",
     "Tk callback did not reach"),
    ("note raising on an unwritable folder", "error_log:note",
     "    except Exception:\n        pass\n",
     "    except Exception:\n        raise\n",
     "error_log.note raised"),
    ("no cap", "error_log:_hold_under_cap",
     "    if size + adding <= MAX_BYTES:\n",
     "    if True:\n",
     "against a cap of 4000"),
]
