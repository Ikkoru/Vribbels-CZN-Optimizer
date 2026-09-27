"""The tabs settled after the reveal stay unseen, and nothing breaks.

`ui/utils/presettle.py` lays out every unopened tab behind the one on
screen, with painting on the notebook switched off. Everything in it
fails silently, and most of it only on a live window:

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
5. **A step counts its own tab as laid out, and `LazyTabs` keeps out
   of it.** The settler's tab-changed handler ignores a step's own
   selections, so a tab the step does not count is settled again and
   again. And `LazyTabs` holds no switch while painting is off: held,
   its release would switch painting back on mid-step, the tab being
   settled on screen.
6. **What is pending runs before a step, painting on.** A paint still
   owed to the tab on screen, spent with painting off, leaves it
   showing old pixels.
7. **When a step may start**: input on this window holds it back, the
   pointer moving does not inside the two windows, a click closes them.
8. **A click that landed behind the notebook during a step** is given
   back when it was on a tab, and only then.
9. **The input times are read as text.** One not noted yet is Tcl's
   shared literal 0, which any list read elsewhere turns into a list;
   read as an object it arrives a tuple, and the settler raising on it
   stops for the session.

Most of 1-6 reads the source; the rest runs the settler's own decisions
on a notebook at alpha 0, which is invisible. The third shows only on a
live window, frame by frame as the tabs settle.
"""

import ast
import sys

from ._harness import SOURCE_ROOT, add_source_to_path, note

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


def _first_line(calls):
    return min((c.lineno for c in calls), default=None)


def _source_rules(tree):
    problems = []
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
        marked = _first_line(c for c in _calls(settle, "add")
                             if "_settled" in ast.unparse(c.func))
        if marked is None:
            problems.append(
                "`_settle` does not count its tab as laid out. The tab-"
                "changed handler ignores a step's own selections, so the "
                "same tab is settled again at every idle moment for the "
                "rest of the session.")

    step = _function(tree, "_next")
    drained = _first_line(_calls(step, "_drain")) if step else None
    stepped = _first_line(_calls(step, "_settle")) if step else None
    if drained is None or stepped is None or drained > stepped:
        problems.append(
            "`_next` does not drain what is pending before a step. A paint "
            "still owed to the tab on screen is then spent with painting "
            "off, and that tab keeps its old pixels.")

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
    return problems


def _app_rules():
    try:
        app = APP.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"czn_optimizer_gui.py cannot be read: {exc}"]
    tree = ast.parse(app)
    problems = []
    call = next((c for c in _calls(tree, "settle_hidden_tabs")), None)
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
    reveal = _function(tree, "_reveal_window")
    if reveal is None or not _calls(reveal, "track_input"):
        problems.append(
            "`_reveal_window` does not start `track_input`. The settler "
            "then sees no input at all and steps under the user's hand, "
            "and its launch window opens whenever it happens to start.")
    return problems


def _run_decisions():
    """The settler's choices, run on a notebook at alpha 0."""
    import tkinter as tk
    from tkinter import ttk
    from ui.utils import presettle
    from ui.utils.lazy_tabs import LazyTabs

    out = []
    root = tk.Tk()
    held = presettle._held_in_front
    try:
        root.withdraw()
        root.attributes("-alpha", 0.0)
        root.geometry("400x200")
        nb = ttk.Notebook(root)
        lazy = LazyTabs(root, nb)
        nb.pack(fill=tk.BOTH, expand=True)
        pages = []
        for text in ("One", "Two", "Three"):
            page = ttk.Frame(nb)
            ttk.Label(page, text=text).pack()
            nb.add(page, text=text)
            pages.append(page)
        root.deiconify()
        root.update_idletasks()
        presettle._drain(root, 10 ** 12)
        presettle.track_input(root)
        lazy.watch()
        settler = presettle.HiddenTabSettler(root, nb, lazy=lazy)
        tcl = root.tk

        # A time not noted yet is the literal 0, one object Tcl shares
        # with every script holding a 0, and any of them reading it as a
        # list makes it one -- ttk's `-padding 0` does. So read one after
        # a list read of 0 elsewhere.
        tcl.eval("proc ::vribbels_shimmer {} {lindex 0 0}; "
                 "::vribbels_shimmer")
        try:
            never = presettle._input(root, "act")
        except TypeError as exc:
            never = exc
        if never != 0:
            out.append(f"a time not noted yet reads back as {never!r} once "
                       f"some script has read a 0 as a list. The settler "
                       f"raises on exactly that and stops for the "
                       f"session; `_noted` reads the times as text.")

        # `LazyTabs` holds nothing inside a step.
        holds = []
        hold = lazy._hold_painting
        lazy._hold_painting = lambda: (holds.append(1), hold())
        try:
            settler._settle(str(pages[1]), nb.select())
        finally:
            lazy._hold_painting = hold
        if holds:
            out.append("`LazyTabs` held a settle step's own selection. Its "
                       "release switches painting back on mid-step and "
                       "puts the tab being settled on screen; with painting "
                       "off already, it must hold nothing.")
        if nb.select() != str(pages[0]):
            out.append("a settle step left another tab selected than the "
                       "one it found.")

        # Input reaching the window is noted.
        pages[0].event_generate("<Motion>", x=3, y=3, when="now")
        pages[0].event_generate("<ButtonPress-1>", x=3, y=3, when="now")
        pages[0].event_generate("<ButtonRelease-1>", x=3, y=3, when="now")
        if not (presettle._input(root, "move")
                and presettle._input(root, "act")):
            out.append("`track_input` did not note a motion and a click on "
                       "the window. The settler would step under the "
                       "user's hand.")

        # When a step may start.
        presettle._held_in_front = lambda: False
        now = presettle._clock_ms(root)

        def wait(since, act, move, switched=None, settle=False):
            tcl.call("set", "::vribbels_input::act", act)
            tcl.call("set", "::vribbels_input::move", move)
            settler._revealed_at, settler._switched_at = since, switched
            return settler._wait(settle)

        cases = (
            ("the pointer moving just after the reveal",
             wait(now - 100, 0, now - 5), lambda w: w == (0, "launch")),
            ("a settle step just after the reveal",
             wait(now - 100, 0, now - 5, settle=True),
             lambda w: w == (0, "launch")),
            ("a settle step inside a switch window, which holds painting "
             "while the next click is likely on the tab's contents",
             wait(now - 5000, now - 151, now - 2, switched=now - 150,
                  settle=True),
             lambda w: w[1] == "idle" and w[0] > 0),
            ("a click just after the reveal",
             wait(now - 100, now - 50, now - 5),
             lambda w: w[1] == "idle" and w[0] > 0),
            ("the pointer moving once the launch window is over",
             wait(now - 5000, 0, now - 5),
             lambda w: w[1] == "idle" and w[0] > 0),
            ("a switch whose tab has not painted yet",
             wait(now - 5000, now - 31, now - 2, switched=now - 30),
             lambda w: w[1] == "switch" and w[0] > 0),
            ("the pointer moving inside a switch window",
             wait(now - 5000, now - 151, now - 2, switched=now - 150),
             lambda w: w == (0, "switch")),
            ("a click after a switch",
             wait(now - 5000, now - 20, now - 2, switched=now - 150),
             lambda w: w[1] == "idle" and w[0] > 0),
            ("nothing on the window for long",
             wait(now - 5000, now - 4000, now - 3000),
             lambda w: w == (0, "idle")),
        )
        for what, got, good in cases:
            if not good(got):
                out.append(f"{what}: the settler would wait {got[0]} ms "
                           f"for a {got[1]!r} step, which is wrong. See "
                           f"`HiddenTabSettler._wait`.")
        presettle._held_in_front = lambda: True
        if settler._wait(False)[0] <= 0:
            out.append("a held mouse button in front let a step start: a "
                       "drag of the window would stutter under it.")
        presettle._held_in_front = held

        # A click lost behind the notebook, given back on a tab only.
        root.update_idletasks()
        spot = next((x for x in range(2, nb.winfo_width(), 2)
                     if str(tcl.call(str(nb), "identify", "tab", x, 6))
                     == "2"), None)
        if spot is None:
            out.append("no tab found on the tab row to click, so the "
                       "replay of a lost click went unchecked.")
        else:
            x, y = nb.winfo_rootx() + spot, nb.winfo_rooty() + 6
            stamp = presettle._clock_ms(root)
            replays = (
                ("a click behind the notebook, on a tab", ".", stamp, 2),
                ("a click the notebook got itself", str(nb), stamp, 0),
                ("a click before the step", ".", stamp - 100, 0),
                # A path, not a window: a Toplevel would map, visibly.
                ("a click on another window", ".!toplevel", stamp, 0))
            for what, widget, when, want in replays:
                nb.select(pages[0])
                tcl.call("set", "::vribbels_input::press",
                         (when, widget, x, y))
                presettle.replay_lost_tab_click(root, nb, stamp - 5)
                if nb.index("current") != want:
                    out.append(f"{what}: the notebook shows tab "
                               f"{nb.index('current')}, not {want}. Only a "
                               f"click that landed behind the notebook, on "
                               f"a tab, during the step is given back.")
    finally:
        presettle._held_in_front = held
        root.destroy()
    return out


def run():
    try:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"ui/utils/presettle.py cannot be read: {exc}"]
    problems = _source_rules(tree) + _app_rules()
    if sys.platform != "win32":
        note("not Windows: the settler's decisions were not run.")
    else:
        add_source_to_path()
        problems += _run_decisions()
    return problems
