"""The tabs settled after the reveal stay unseen, and nothing breaks.

`ui/utils/presettle.py` lays out every unopened tab behind the one on
screen, with painting on the notebook switched off. Four things in it
fail silently, and all of them only on a live window:

1. **Painting must come back on whatever happens.** A notebook left
   with `WM_SETREDRAW` off never repaints again -- the program goes on
   working behind a frozen picture. So the call that switches it back
   on has to sit in a `finally`.
2. **Timers must not run while it is off.** `update()` runs them, and
   the capture's poll can reload a snapshot and redraw the tab on
   screen; none of that redraw would ever reach it. So the drain is
   `dooneevent` over window and idle events, never `update()`.
3. **The way back is drained with painting off too.** Left to the
   ordinary loop, the notebook repaints the page area's background and
   the page's widgets never paint over it: the tab on screen goes blank
   in patches.
4. **The Capture tab is skipped.** Its switch handlers clear its
   failure mark and start and stop its log title's pulse, which a tab
   switched behind the user's back would do for nobody.

Headless, so this reads the source: what is checked is that the lines
which keep each rule are still there. The third was found on a live
window, photographed frame by frame while the tabs settled.
"""

import ast

from ._harness import SOURCE_ROOT

NAME = "tabs settle unseen after the reveal"

MODULE = SOURCE_ROOT / "ui" / "utils" / "presettle.py"
APP = SOURCE_ROOT / "czn_optimizer_gui.py"


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls(node, attr):
    """Every call in `node` whose callee ends in `.attr` or is `attr`."""
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else None)
            if name == attr:
                out.append(sub)
    return out


def _redraw_on(call):
    """Whether a SendMessageW call switches WM_SETREDRAW back ON."""
    args = call.args
    return (len(args) >= 3 and isinstance(args[1], ast.Name)
            and args[1].id == "WM_SETREDRAW"
            and isinstance(args[2], ast.Constant) and args[2].value == 1)


def run():
    problems = []
    try:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"ui/utils/presettle.py cannot be read: {exc}"]

    settle = _function(tree, "_settle")
    if settle is None:
        problems.append("presettle.py has no `_settle`, so nothing below "
                        "can be checked.")
    else:
        in_finally = [c for t in ast.walk(settle) if isinstance(t, ast.Try)
                      for stmt in t.finalbody
                      for c in _calls(stmt, "SendMessageW") if _redraw_on(c)]
        if not in_finally:
            problems.append(
                "`_settle` does not switch painting back on inside a "
                "`finally`. Anything raised while it is off leaves the "
                "notebook frozen on its last picture for the rest of the "
                "session.")
        guarded = [n for t in ast.walk(settle) if isinstance(t, ast.Try)
                   for n in t.body]
        drains = sum(len(_calls(n, "_drain")) for n in guarded)
        if drains < 2:
            problems.append(
                f"`_settle` drains {drains} time(s) with painting off, not "
                f"twice. The way back has to be drained before painting "
                f"comes on, or the tab on screen goes blank in patches.")
        if _calls(settle, "update"):
            problems.append(
                "`_settle` calls `update()`, which runs timers with "
                "painting off -- a capture reload in there redraws the "
                "tab for nobody. Drain through `_drain`.")

    drain = _function(tree, "_drain")
    if drain is None:
        problems.append("presettle.py has no `_drain`.")
    else:
        names = {n.id for n in ast.walk(drain) if isinstance(n, ast.Name)}
        if {"TIMER_EVENTS", "ALL_EVENTS"} & names or _calls(drain, "update"):
            problems.append(
                "`_drain` lets timers run. With painting off, a timer's "
                "redraw never reaches the screen; window and idle events "
                "are all a layout needs.")
        if not _calls(drain, "dooneevent"):
            problems.append("`_drain` no longer drains through "
                            "`dooneevent`, so its flags say nothing.")

    try:
        app = APP.read_text(encoding="utf-8")
    except OSError as exc:
        return problems + [f"czn_optimizer_gui.py cannot be read: {exc}"]
    call = next((c for c in _calls(ast.parse(app), "settle_hidden_tabs")),
                None)
    if call is None:
        problems.append(
            "czn_optimizer_gui.py never calls `settle_hidden_tabs`, so "
            "every tab but the first assembles in view the first time it "
            "is opened.")
    else:
        skip = next((k.value for k in call.keywords if k.arg == "skip"),
                    None)
        text = ast.unparse(skip) if skip is not None else ""
        if "capture_tab" not in text:
            problems.append(
                "`settle_hidden_tabs` is not told to skip the Capture tab. "
                "Selecting it clears its failure mark and starts its "
                "title's pulse; a settle would do both behind the user's "
                "back.")
    return problems
