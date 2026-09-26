"""No text the program draws holds a character past U+FFFF.

**The first time Tk draws such a character, it loads the character
ranges of every font installed on the machine** looking for one that
claims it -- and none does, since those ranges stop at U+FFFF. The
pause grows with the number of fonts installed and lands on the UI
thread, inside whatever showed the character first: typically a tab's
first open, where it can be most of the open.

Nothing reports it. An emoji draws correctly, the tab works, and the
only symptom is a first open that takes longer than the next.

Every string literal under `Vribbels/` is read, docstrings aside.
Captured game data is not: the game's own names are what they are.
"""

import ast

from ._harness import SOURCE_ROOT

NAME = "drawn text stays under U+FFFF"

# Folders under `Vribbels/` that hold no program text.
SKIPPED = {"__pycache__", "build", "dist", "snapshots", "settings"}


def _docstrings(tree):
    """The string nodes that are docstrings, which nothing draws."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant) and isinstance(
                    body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def run():
    problems = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if SKIPPED & set(path.relative_to(SOURCE_ROOT).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8",
                                            errors="replace"))
        except SyntaxError as exc:
            problems.append(f"{path.name} will not parse: {exc}")
            continue
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)) or id(node) in skip:
                continue
            wide = sorted({ch for ch in node.value if ord(ch) > 0xFFFF})
            if wide:
                where = path.relative_to(SOURCE_ROOT).as_posix()
                codes = ", ".join("U+%04X" % ord(ch) for ch in wide)
                problems.append(
                    f"{where}:{node.lineno} holds {codes}. Tk's first draw "
                    f"of a character past U+FFFF loads every installed "
                    f"font's character ranges looking for it, on the UI "
                    f"thread, which is a visible pause wherever it first "
                    f"appears. Use a character under U+FFFF.")
    return problems
