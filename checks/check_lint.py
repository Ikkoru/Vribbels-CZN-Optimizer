"""The code passes its lint: `ruff.toml`'s rules, over everything.

`compileall` sees syntax and nothing else, and the other checks see only
the paths they drive. A name used and never defined, a `raise` that
drops its cause, a `zip` that silently drops a tail, a bare `except`
that swallows Ctrl+C: each runs until the line is reached, often in a
branch no check takes. Ruff reads every line, in about a second.

Two runs:

1. `Vribbels/`, `checks/` and `docs/`, under the repo's `ruff.toml`;
2. the capture addon AS MITMDUMP RUNS IT: the script
   `_generate_addon_script` writes, constants appended. The template on
   its own reads two dozen undefined names that generation supplies, and
   `compileall` cannot see inside the string at all.

The ruff version is pinned, so a release that adds a rule to a family
`ruff.toml` selects cannot fail this overnight; moving the pin is an
edit, with its findings fixed in the same change. Ruff comes through
uv's `uvx`; where that is not installed, or ruff cannot be fetched, the
check skips and says why.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from ._harness import REPO_ROOT, Skip, add_source_to_path

NAME = "the code passes its lint (ruff)"

RUFF = "ruff@0.17.5"
PATHS = ("Vribbels", "checks", "docs")
# Shown in full up to this many; past it, the count and the first ones.
SHOWN = 25
TIMEOUT_S = 300

# More files to lint, for this check's own fault.
EXTRA_PATHS = []


def _uvx():
    found = shutil.which("uvx")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "uvx.exe"
    return str(local) if local.exists() else None


def _ruff(uvx, args):
    """(findings, None) or (None, why the run did not happen)."""
    try:
        run = subprocess.run(
            [uvx, RUFF, "check", "--output-format", "concise",
             "--no-cache", *args],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", stdin=subprocess.DEVNULL, timeout=TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"ruff did not run ({type(e).__name__}: {e})"
    if run.returncode not in (0, 1):
        tail = (run.stderr or run.stdout).strip().splitlines()[-3:]
        return None, "ruff could not run: " + " | ".join(tail)
    return [line for line in run.stdout.splitlines()
            if ": " in line and line[:1] not in ("", " ")
            and not line.startswith(("Found ", "All checks", "["))], None


def _generated_addon(folder):
    from capture.manager import CaptureManager
    return CaptureManager(folder, log_callback=lambda *a, **k: None) \
        ._generate_addon_script(debug_mode=False)


def _complain(where, findings):
    shown = "\n".join(f"  {line}" for line in findings[:SHOWN])
    more = (f"\n  ... and {len(findings) - SHOWN} more"
            if len(findings) > SHOWN else "")
    return (f"{where}: {len(findings)} lint finding(s) under ruff.toml:\n"
            f"{shown}{more}\nEach is a likely bug or a needless cost; "
            f"fix it, or where the rule's worry does not apply, put "
            f"`# noqa: <code> -- <why>` on the line. "
            f"`uvx {RUFF} check {' '.join(PATHS)}` shows them.")


def run():
    add_source_to_path()
    uvx = _uvx()
    if uvx is None:
        raise Skip("ruff runs through uv's `uvx`, which is not installed "
                   "(https://docs.astral.sh/uv/)")
    failures = []
    findings, why = _ruff(uvx, [*PATHS, *map(str, EXTRA_PATHS)])
    if findings is None:
        raise Skip(why)
    if findings:
        failures.append(_complain("the repository", findings))

    folder = Path(tempfile.mkdtemp(prefix="lint_addon_"))
    try:
        script = _generated_addon(folder)
        findings, why = _ruff(uvx, [str(script), "--config",
                                    str(REPO_ROOT / "ruff.toml")])
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if findings is None:
        failures.append(f"the generated capture addon could not be linted: "
                        f"{why}")
    elif findings:
        failures.append(_complain(
            "the generated capture addon (fix them in ADDON_TEMPLATE, "
            "capture/manager.py)", findings))
    return failures


def _a_name_never_defined():
    """A file in the run holding a name nothing defines."""
    path = Path(tempfile.mkdtemp(prefix="lint_fault_")) / "broken.py"
    path.write_text("print(never_defined)\n", encoding="utf-8")
    EXTRA_PATHS.append(path)


FAULTS = [
    ("a name never defined in the repository", _a_name_never_defined,
     None, None, "never_defined"),
    ("a name never defined in the addon", "capture.manager:ADDON_TEMPLATE",
     "SAVE_REPLACE_TRIES = 5\n", "SAVE_REPLACE_TRIES = FIVE\n",
     "generated capture addon"),
]
