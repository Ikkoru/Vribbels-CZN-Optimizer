"""Run one build step, and show its warnings dark yellow, its errors red.

    python build_tools/colour_output.py COMMAND [ARG ...]

What `zCreate exe.bat` runs every step through. The exit code is the
command's own, so a failed step still stops the build.

A line is judged by what it says, first match winning: `RULES` below.
PyInstaller logs everything to stderr, INFO included, so the stream a
line came on says nothing and both are read as one.

Colours are ANSI sequences, which the Windows console draws only once
asked to. Where it will not be asked -- output sent to a file, an old
console -- the lines go out plain.
"""

import os
import re
import subprocess
import sys

WARNING = "\x1b[33m"            # dark yellow
ERROR = "\x1b[91m"              # red
RESET = "\x1b[0m"

# (what a line says, its colour). First match wins, so errors lead.
RULES = (
    # PyInstaller's own levels, Python's tracebacks, and the build
    # scripts' `FAILED:` lines.
    (re.compile(r"\b(ERROR|CRITICAL)\b|\berror:|^Traceback |FAILED"),
     ERROR),
    # PyInstaller's warnings, and `fold_shared_facts.py`'s refused (`!`)
    # and went-down (`?`) lines with its count of the latter.
    (re.compile(r"\bWARNING\b|^\s*[!?] |went DOWN"), WARNING),
)


def colour_of(line):
    for pattern, colour in RULES:
        if pattern.search(line):
            return colour
    return None


def _ask_for_colour():
    """Switch the console to drawing ANSI sequences. False where it
    will not: output that is not a console, or a console too old."""
    if not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)             # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    coloured = _ask_for_colour()
    # A Python child writes UTF-8 and at once rather than in blocks,
    # so a long step shows its progress as it makes it.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        child = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env)
    except OSError as exc:
        line = "cannot run %s: %s" % (argv[0], exc)
        print(ERROR + line + RESET if coloured else line, flush=True)
        return 1
    encoding = sys.stdout.encoding or "utf-8"
    for raw in child.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        colour = colour_of(line) if coloured else None
        text = colour + line + RESET if colour else line
        sys.stdout.buffer.write(
            (text + "\n").encode(encoding, "replace"))
        sys.stdout.buffer.flush()
    return child.wait()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
