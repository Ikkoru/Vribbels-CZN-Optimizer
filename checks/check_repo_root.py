"""Nothing unexpected may be tracked at the repository root.

**A rule name typed unquoted into a shell command creates a file.**
`label row -> label row` and `checkboxes -> unrelated checkboxes` both
make the `>` a redirect and the next word a filename, so a grep for a
spacing rule leaves `label` or `unrelated` at the root -- sometimes
holding a stray error message. `git add -A` then commits it.

That is the shape this directory exists for: silent, and invisible in a
diff that is scrolled past. Nothing in the program breaks, so nothing
else would ever report it.

The root is a SMALL, SLOW-CHANGING list, which is what makes an
allowlist the right instrument here rather than a pattern. Adding a file
to the root is a deliberate act; adding one to this list alongside it is
one line, and the prompt to do so is the point.

Directories are not listed -- only files, and only tracked ones.
Anything ignored is between the maintainer and `.gitignore`.
"""

import subprocess

from ._harness import REPO_ROOT

NAME = "no junk at the repo root"

ALLOWED = {
    ".gitignore",
    "CHANGELOG.md",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "zCreate exe.bat",
    "zRUN Checks.bat",
    "zRUN Spacing Audit Freeze.bat",
    "zRUN Spacing Audit Verbose.bat",
    "zRUN Spacing Audit.bat",
    "zRUN.bat",
}


def run():
    try:
        listing = subprocess.run(
            ["git", "ls-files"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return [f"could not list tracked files ({type(e).__name__}: {e})"]
    if listing.returncode != 0:
        return []                      # not a git checkout; nothing to say

    root = {line for line in listing.stdout.splitlines()
            if line and "/" not in line}
    failures = []
    for name in sorted(root - ALLOWED):
        failures.append(
            f"{name!r} is tracked at the repository root and is not in this "
            f"check's list. If it belongs there, add it to ALLOWED. If it "
            f"does not, it is most likely a shell redirect that `git add -A` "
            f"swept up -- an unquoted `->` in a command makes the next word "
            f"a filename."
        )
    for name in sorted(ALLOWED - root):
        failures.append(
            f"{name!r} is on this check's list but is no longer tracked at "
            f"the root. Drop it from ALLOWED, so the list keeps saying what "
            f"is actually there."
        )
    return failures
