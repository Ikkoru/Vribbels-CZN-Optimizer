"""Tabs built on first need are whole when they arrive, and miss nothing.

Most tabs are built after the window appears (`ui/utils/lazy_tabs.py`).
Until one is, the app's handle on it is None, and four things about
that fail without a sound:

1. **A call made through a tab not built yet.** `load_data` and the
   live reload reach every tab; one that assumes the tab exists raises,
   and the live reload swallows what it raises -- the capture then
   stops updating anything, silently.
2. **The Checklist records from every snapshot**, and a tab not built
   yet reads nothing. So both load paths build it before they replace
   the snapshot it has not read.
3. **A tab the user opens before it is built is built with painting
   off**, and painting has to come back on whatever happens -- or the
   notebook freezes on its last picture -- and then paint the new tab,
   none of which has been drawn.
4. **Gear Score's rescore reaches Memory Fragments and Combatants**
   through the context, where either is None until built.

Headless, so this reads the source.
"""

import ast
import re

from ._harness import SOURCE_ROOT

NAME = "tabs built on first need"

APP = SOURCE_ROOT / "czn_optimizer_gui.py"
LAZY = SOURCE_ROOT / "ui" / "utils" / "lazy_tabs.py"
SCORING = SOURCE_ROOT / "ui" / "tabs" / "scoring_tab.py"

# The app's handles on tabs that may not be built yet.
LAZY_HANDLES = ("inventory", "heroes", "materials", "checklist", "setup",
                "gacha")
UNGUARDED = re.compile(r"\b(?:%s)_tab_instance\." % "|".join(LAZY_HANDLES))


def _function(tree, name):
    return next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == name), None)


def _call_lines(node, name):
    """Lines of the calls in `node` to `name` or `<anything>.name`."""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            got = (func.attr if isinstance(func, ast.Attribute)
                   else func.id if isinstance(func, ast.Name) else None)
            if got == name:
                out.append(sub.lineno)
    return out


def run():
    problems = []
    app_text = APP.read_text(encoding="utf-8")
    app = ast.parse(app_text)

    # 1. No attribute taken straight off a handle that may be None.
    for number, line in enumerate(app_text.splitlines(), 1):
        if UNGUARDED.search(line):
            problems.append(
                f"czn_optimizer_gui.py:{number} calls through a tab that "
                f"may not be built yet: {line.strip()!r}. Take the handle "
                f"into a name and test it for None first; building the "
                f"tab later reads whatever loaded before it.")

    # 2. The Checklist reads the old snapshot before either load path
    # replaces it.
    for name in ("load_data", "_handle_live_update"):
        func = _function(app, name)
        if func is None:
            problems.append(f"czn_optimizer_gui.py has no `{name}`.")
            continue
        record = _call_lines(func, "_let_the_checklist_record")
        loads = [n for n in _call_lines(func, "load_data")]
        if not record or not loads or min(record) > min(loads):
            problems.append(
                f"`{name}` does not build the Checklist before it loads a "
                f"snapshot over the one it has not read. The Checklist "
                f"records event totals, finals and the floor clock from "
                f"every snapshot, and the game purges what they come "
                f"from.")

    # 3. The build a click asks for ends with painting on, and painted.
    lazy = ast.parse(LAZY.read_text(encoding="utf-8"))
    view = _function(lazy, "_build_in_view")
    finals = [stmt for t in ast.walk(view) if isinstance(t, ast.Try)
              for stmt in t.finalbody] if view else []
    on = any(isinstance(a, ast.Constant) and a.value == 1
             for stmt in finals for c in ast.walk(stmt)
             if isinstance(c, ast.Call) and getattr(c.func, "attr", "")
             == "SendMessageW" for a in c.args[2:3])
    repaint = any(_call_lines(stmt, "RedrawWindow") for stmt in finals)
    if not (on and repaint):
        problems.append(
            "LazyTabs._build_in_view does not switch painting back on AND "
            "repaint inside a `finally`. Without the first, the notebook "
            "freezes on its last picture; without the second, the tab the "
            "user clicked was never drawn.")

    # 4. Gear Score's rescore tests both tabs before reaching them.
    scoring = ast.parse(SCORING.read_text(encoding="utf-8"))
    parents = {}
    for node in ast.walk(scoring):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(scoring):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr in ("inventory_tab",
                                             "heroes_tab")):
            continue
        handle = node.func.value.attr
        up, guarded = parents.get(node), False
        while up is not None and not guarded:
            if isinstance(up, ast.If) and handle in ast.unparse(up.test):
                guarded = True
            up = parents.get(up)
        if not guarded:
            problems.append(
                f"scoring_tab.py:{node.lineno} reaches `context.{handle}` "
                f"without testing it for None. That tab may not be built "
                f"yet when Gear Score rescores.")
    return problems
