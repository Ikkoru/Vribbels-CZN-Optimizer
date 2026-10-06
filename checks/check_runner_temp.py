"""A run's temporary folders are made in one folder of its own, and that
folder is gone when the run ends.

Most checks make their folders with `tempfile.mkdtemp` and never remove
them. Each full run left about fifty in %TEMP%, every run of every turn,
with nothing to show for it but a slower Explorer. `run_all.main` points
`tempfile` and the TEMP variables at a per-run folder and removes it
afterwards, the read-only files git writes included, and puts the
previous settings back.

This drives the runner with a one-check suite that makes a folder of
its own, the way the real checks do, holding a read-only file, and asks
where it landed and what was left.
"""

import io
import os
import stat
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

NAME = "a run's temporary folders go when it ends"


def run():
    from checks import run_all

    made = {}

    def makes_a_folder():
        folder = Path(tempfile.mkdtemp(prefix="leftover_"))
        locked = folder / "object"
        locked.write_text("x", encoding="utf-8")
        os.chmod(locked, stat.S_IREAD)
        made["folder"] = folder
        made["TEMP"] = os.environ.get("TEMP")
        return []

    saved_suite = run_all.CHECKS
    saved = (tempfile.tempdir, os.environ.get("TEMP"),
             os.environ.get(run_all.RUN_TEMP_ENV))
    # Under run_all this already runs inside a run, and a run inside a
    # run keeps the outer folder; cleared here, the inner run makes and
    # removes its own, which is the behaviour being checked.
    os.environ.pop(run_all.RUN_TEMP_ENV, None)
    run_all.CHECKS = [SimpleNamespace(NAME="makes a folder",
                                      run=makes_a_folder)]
    try:
        with redirect_stdout(io.StringIO()):
            run_all.main([])
    finally:
        run_all.CHECKS = saved_suite
        if saved[2] is not None:
            os.environ[run_all.RUN_TEMP_ENV] = saved[2]

    out = []
    folder = made.get("folder")
    parent = run_all.RUN_TEMP_PARENT.resolve()
    if folder is None:
        return ["the one-check suite never ran"]
    if parent not in folder.resolve().parents:
        out.append(
            f"a check's mkdtemp landed in {folder.parent}, outside "
            f"{parent}: run_all no longer points tempfile at a folder of "
            f"its own, and every run leaves its folders in %TEMP%.")
    if made.get("TEMP") is None or parent not in Path(
            made["TEMP"]).resolve().parents:
        out.append(
            f"TEMP during the run was {made.get('TEMP')!r}, outside "
            f"{parent}: the processes a check starts leave their folders "
            f"in %TEMP%.")
    if folder.exists():
        out.append(
            f"{folder} is still there after the run: run_all no longer "
            f"removes its run folder, or stops at a read-only file in it.")
    if (tempfile.tempdir, os.environ.get("TEMP")) != saved[:2]:
        out.append(
            f"after the run tempfile.tempdir is {tempfile.tempdir!r} and "
            f"TEMP {os.environ.get('TEMP')!r}, not what they were: "
            f"everything after the run makes its folders in a removed one.")
    return out
