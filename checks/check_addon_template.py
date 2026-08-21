"""The capture addon is a Python program inside a string literal.

`ADDON_TEMPLATE` in `capture/manager.py` is written out to disk and then
executed by mitmdump. It is roughly half of that file, and because it is
a string, `python -m compileall` cannot see it: a syntax error there
surfaces only when a capture starts, which is the worst possible moment
to find one.

It also has a strict ASCII requirement. The generated script is written
from a Windows process whose locale may be cp932 / cp949 / cp1252, and a
smart quote or em dash in the template would fail to encode.
"""

import ast

from ._harness import add_source_to_path

NAME = "capture addon template"


def run():
    failures = []
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    try:
        ast.parse(ADDON_TEMPLATE)
    except SyntaxError as e:
        failures.append(
            f"ADDON_TEMPLATE does not parse: line {e.lineno}: {e.msg}. "
            "A capture would fail the moment it starts."
        )

    bad = [(i + 1, line) for i, line in enumerate(ADDON_TEMPLATE.splitlines())
           if any(ord(c) > 127 for c in line)]
    for lineno, line in bad[:5]:
        failures.append(
            f"ADDON_TEMPLATE line {lineno} is not ASCII: {line.strip()[:60]!r}. "
            "The generated addon cannot be written on a cp932/cp949 locale."
        )

    for lineno in _unencoded_text_opens(ADDON_TEMPLATE):
        failures.append(
            f"ADDON_TEMPLATE line {lineno}: open() in text mode with no "
            f"encoding=. The snapshot would be written in whatever the "
            f"locale happens to be and read back as something else."
        )
    return failures


def _unencoded_text_opens(source):
    """Line numbers of text-mode open() calls with no explicit encoding.

    Parsed rather than grepped: the template is a string literal, so a
    substring probe lands on whichever occurrence comes first and says
    nothing about the call that matters.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []                      # already reported above
    bad = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        mode = "r"
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        if "b" in mode:
            continue
        bad.append(node.lineno)
    return bad
