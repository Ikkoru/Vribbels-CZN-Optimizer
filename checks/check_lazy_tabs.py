"""Tabs built on first need are whole when they arrive, and miss nothing.

Most tabs are built after the window appears (`ui/utils/lazy_tabs.py`),
and every tab switch is held until the tab is whole. Seven things about
that fail without a sound:

1. **A call made through a tab not built yet.** `load_data` and the
   live reload reach every tab; one that assumes the tab exists raises,
   and the live reload swallows what it raises -- the capture then
   stops updating anything, silently.
2. **The Checklist records from every snapshot**, and a tab not built
   yet reads nothing. So both load paths build it before they replace
   the snapshot it has not read.
3. **A switch holds painting off until the tab is whole** -- a
   placeholder built on the click, a tab built earlier and never laid
   out, or one shown before, whose widgets a hidden page unmapped. The
   hold ends in a queued event, so every tab-changed handler runs
   inside it, and painting has to come back on whatever happens -- or
   the notebook freezes on its last picture -- and then paint the new
   tab, none of which has been drawn.
4. **Gear Score's rescore reaches Memory Fragments and Combatants**
   through the context, where either is None until built.
5. **`LazyTabs` is created before any tab**, so its tab-changed handler
   is the first bound. A tab's own handler bound ahead of it draws
   before painting goes off -- in view, the thing the hold is for.
6. **What a switch does, run**: on a notebook at alpha 0, a tab's own
   handler must run once, with painting off, and painting come back.
7. **The still over a repainting tab comes off, and comes on in time**
   (`ui/utils/still.py`). Its window is destroyed in a `finally`, or
   the old tab stays on screen over the new one for good; it waits for
   the compositor to show it before the repaint starts, and has no fade,
   or the first widgets drawn flash through it; and it copies nothing
   from a window at alpha 0, whose copy would be of whatever lies
   behind it.

The first five and most of the seventh read the source; the sixth and
the last of the seventh map a window at alpha 0, which is invisible,
the way `check_tabs_build` measures the Checklist.
"""

import ast
import re
import sys

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "tabs built on first need"

APP = SOURCE_ROOT / "czn_optimizer_gui.py"
LAZY = SOURCE_ROOT / "ui" / "utils" / "lazy_tabs.py"
STILL = SOURCE_ROOT / "ui" / "utils" / "still.py"
SCORING = SOURCE_ROOT / "ui" / "tabs" / "scoring_tab.py"

# The app's handles on tabs that may not be built yet.
LAZY_HANDLES = ("inventory", "heroes", "materials", "checklist", "setup",
                "gacha")
UNGUARDED = re.compile(r"\b(?:%s)_tab_instance\." % "|".join(LAZY_HANDLES))
# The tabs the app builds at startup, each binding a tab-changed handler
# as it is built.
EAGER = ("OptimizerTab", "ScoringTab", "CaptureTab")


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


def _in_finally(func, name):
    """Whether `func` calls `name` inside a `finally`."""
    return bool(func) and any(
        _call_lines(stmt, name) for t in ast.walk(func)
        if isinstance(t, ast.Try) for stmt in t.finalbody)


def _painting_comes_back(lazy):
    """Complaints about the hold's way out, read off the source."""
    problems = []
    changed = _function(lazy, "_on_tab_changed")
    if not _in_finally(changed, "event_generate"):
        problems.append(
            "LazyTabs._on_tab_changed does not queue the end of a first "
            "show inside a `finally`. A build that raises then leaves "
            "painting off for good: the notebook freezes on its last "
            "picture.")
    if not _in_finally(_function(lazy, "_finish_show"), "_release_painting"):
        problems.append(
            "LazyTabs._finish_show does not release painting inside a "
            "`finally`. A layout that raises then leaves the notebook "
            "frozen on its last picture.")
    release = _function(lazy, "_release_painting")
    on = release is not None and any(
        isinstance(a, ast.Constant) and a.value == 1
        for c in ast.walk(release) if isinstance(c, ast.Call)
        and getattr(c.func, "attr", "") == "SendMessageW"
        for a in c.args[2:3])
    if not (on and release is not None
            and _call_lines(release, "RedrawWindow")):
        problems.append(
            "LazyTabs._release_painting does not switch painting back on "
            "AND repaint. Without the first, the notebook freezes on its "
            "last picture; without the second, the tab the user clicked "
            "was never drawn.")
    return problems


def _still_rules(still):
    """Complaints about the still's way on and off, read off the source."""
    problems = []
    held = _function(still, "held")
    if not _in_finally(held, "DestroyWindow"):
        problems.append(
            "Still.held does not destroy its window inside a `finally`. "
            "Anything raised while the tab repaints then leaves the old "
            "tab's copy on screen over the new one for good.")
    show = _function(still, "_show")
    shown = _call_lines(show, "ShowWindow") if show else []
    flushed = _call_lines(show, "DwmFlush") if show else []
    if not shown or not flushed or min(flushed) < min(shown):
        problems.append(
            "Still._show does not wait for the compositor after showing "
            "the copy. The repaint can then reach the screen a frame "
            "before the copy does, and the first widgets drawn flash "
            "over the old tab.")
    if not (show and _call_lines(show, "DwmSetWindowAttribute")):
        problems.append(
            "Still._show no longer switches the copy's transitions off. "
            "Faded in, it lets the repaint through as it arrives; faded "
            "out, it lingers over the finished tab.")
    return problems


def _first_bound(app):
    """Complaints unless `LazyTabs` is created before every eager tab."""
    made = _call_lines(app, "LazyTabs")
    eager = {name: _call_lines(app, name) for name in EAGER}
    if not made:
        return ["czn_optimizer_gui.py never creates `LazyTabs`."]
    late = [name for name, lines in eager.items()
            if lines and min(lines) < min(made)]
    if late:
        return [f"czn_optimizer_gui.py creates {', '.join(late)} before "
                f"`LazyTabs`, so their tab-changed handlers run first on a "
                f"first show -- and draw in view, before painting goes "
                f"off. Create `LazyTabs` before any tab."]
    return []


def _first_show_runs():
    """A first show, run on a notebook at alpha 0. Complaints."""
    import ctypes
    import tkinter as tk
    from tkinter import ttk
    from ui.utils.lazy_tabs import LazyTabs
    from ui.utils.presettle import _drain

    user32 = ctypes.windll.user32
    out = []
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-alpha", 0.0)
        root.geometry("400x200")
        nb = ttk.Notebook(root)
        lazy = LazyTabs(root, nb)
        nb.pack(fill=tk.BOTH, expand=True)

        def drain():
            _drain(root, 10 ** 12)

        def painting():
            return bool(user32.IsWindowVisible(int(nb.winfo_id())))

        class Tab:
            """Notes, each time it is shown, whether painting was on."""

            def __init__(self):
                self.frame = ttk.Frame(nb)
                ttk.Label(self.frame, text="-").pack()
                self.seen = []
                nb.bind("<<NotebookTabChanged>>", self._changed, add="+")

            def get_frame(self):
                return self.frame

            def _changed(self, _event=None):
                if nb.select() == str(self.frame):
                    self.seen.append(painting())

        first, built = Tab(), Tab()
        nb.add(first.frame, text="First")
        nb.add(built.frame, text="Built")
        slot = lazy.add("later", "Later", Tab)
        root.deiconify()
        root.update_idletasks()
        drain()
        lazy.watch()
        cases = []
        nb.select(built.frame)
        drain()
        # Copies: `built.seen` is cleared and used again below.
        cases.append(("a tab built but never shown", list(built.seen),
                      [False]))
        nb.select(slot.placeholder)
        drain()
        cases.append(("a placeholder, built on the click",
                      list(slot.instance.seen) if slot.instance else None,
                      [False]))
        if not painting():
            out.append("painting stayed off after a first show: the "
                       "notebook is frozen on its last picture.")
        nb.select(first.frame)
        drain()
        built.seen.clear()
        nb.select(built.frame)
        drain()
        cases.append(("a tab shown before", list(built.seen), [False]))
        for what, seen, want in cases:
            if seen != want:
                out.append(
                    f"{what}: its own tab-changed handler ran with painting "
                    f"{['off' if not on else 'on' for on in seen or []]}, "
                    f"not {['off' if not on else 'on' for on in want]}. "
                    f"Every switch runs it once, painting off, so what it "
                    f"draws appears with the rest of the tab.")
        if not painting():
            out.append("painting stayed off after a switch to a tab shown "
                       "before: the notebook is frozen on its last picture.")
        from ui.utils.still import Still
        copy = Still(nb)
        if copy._copy is not None:
            copy._free()
            out.append("a still was copied off a window at alpha 0. What "
                       "it copies is whatever lies behind the window, and "
                       "that is what it would hold over the tab.")
    finally:
        root.destroy()
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

    # 3. A first show ends with painting on, and painted.
    problems += _painting_comes_back(
        ast.parse(LAZY.read_text(encoding="utf-8")))

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

    # 5. LazyTabs' handler is the first bound.
    problems += _first_bound(app)

    # 7. The still over a repaint comes on in time and comes off.
    problems += _still_rules(ast.parse(STILL.read_text(encoding="utf-8")))

    # 6. And a first show, run.
    if sys.platform != "win32":
        note("not Windows: a first show's painting hold was not run.")
    else:
        add_source_to_path()
        problems += _first_show_runs()
    return problems
