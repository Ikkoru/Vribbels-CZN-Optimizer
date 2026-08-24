"""The white-flash fix, and the two things that silently undo it.

Opening a tab for the first time used to show its classic Tk widgets as
blank near-white blocks for a frame -- checkbox grids, the Capture Log,
the About tab's link buttons. Tk creates a widget's window at first MAP
and erases it to the system default before painting, so the fix is to
create every window earlier, while the app is still invisible
(`ui/utils/realize.py`).

Nothing about losing that is visible from a headless run, and nothing
about it is visible in a screenshot taken a frame later either -- which
is why it was mis-diagnosed twice before a side-by-side repro found it.
So this guards the SOURCE.

Three failure modes, all of which leave a working, silent program:

1. `_reveal_window` stops walking the tree, so anything built during
   `setup_ui` flashes again.
2. `make_checkbox` stops realizing its own widget, so the three panels
   that rebuild checkboxes AFTER startup flash again.
3. A tab builds a `Checkbutton` or a `ScrolledText` by hand instead of
   through its helper. Both have already drifted once. Two checkbutton
   sites had picked up Tk's default focus ring and border, which is a
   spacing difference as well as a flash; and of three ScrolledTexts,
   two had the wrapper fix and one did not -- which is why the Capture
   Log went on flashing after the walk in (1) was already fixing
   everything else.

A ScrolledText has a SECOND fault that the walk cannot touch: it builds
its own `tk.Frame` and `tk.Scrollbar`, neither reachable through the
constructor, so the frame keeps Tk's near-white default and paints
before the Text covers it. Realizing a window early cannot fix a
background that is genuinely white. `ui/utils/scrolled_text.py` is where
both corrections live together.

Other classic widgets are built once inside `setup_ui` and are covered
by the walk in (1) wherever they sit, so there is nothing for a rule to
catch there.
"""

import ast
import io

from ._harness import SOURCE_ROOT

NAME = "no first-map flash"

# Widget class -> the module holding the one legitimate constructor for
# it. Every other file must go through that module's helper.
SOLE_CONSTRUCTORS = {
    "Checkbutton": "ui/utils/checkbox.py",
    "ScrolledText": "ui/utils/scrolled_text.py",
}
CHECKBOX_HELPER = SOLE_CONSTRUCTORS["Checkbutton"]

# The modules each widget may be constructed from, so `tk.Checkbutton`,
# `ttk.Checkbutton` and `scrolledtext.ScrolledText` are all caught.
WIDGET_MODULES = ("tk", "ttk", "scrolledtext", "tkinter")


def _calls_winfo_id(tree, func_name):
    """True if `func_name` in `tree` calls `.winfo_id()` for its side
    effect somewhere in its body."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func_name:
            continue
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "winfo_id"):
                return True
    return False


def _parse(relpath):
    path = SOURCE_ROOT / relpath
    return ast.parse(io.open(path, encoding="utf-8").read(), filename=str(path))


def run():
    failures = []

    # 1. The startup walk.
    gui = _parse("czn_optimizer_gui.py")
    walks = [
        n for n in ast.walk(gui)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "realize_windows"
    ]
    if not walks:
        failures.append(
            "czn_optimizer_gui.py no longer calls realize_windows(). That "
            "walk is what creates every widget's window while the app is "
            "still invisible; without it, the first time each tab is "
            "opened its classic Tk widgets flash near-white. See "
            "ui/utils/realize.py."
        )
    else:
        in_reveal = _calls_winfo_id(gui, "_reveal_window") or any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_reveal_window"
            and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == "realize_windows"
                    for c in ast.walk(n))
            for n in ast.walk(gui)
        )
        if not in_reveal:
            failures.append(
                "realize_windows() is called, but not from _reveal_window(). "
                "It has to run while the window is still hidden and after "
                "every tab is built, or the widgets it misses flash on "
                "first map."
            )

    # 2. The helper's own call, for widgets built after that walk.
    checkbox = _parse(CHECKBOX_HELPER)
    if not _calls_winfo_id(checkbox, "make_checkbox"):
        failures.append(
            "make_checkbox no longer calls winfo_id(). The startup walk "
            "cannot cover it: Capture's log presets and Memory Fragments' "
            "Sets and unknown main stats rebuild their checkboxes long "
            "after that walk has run."
        )

    # 3. No hand-rolled widgets outside the module that owns each.
    WHY = {
        "Checkbutton":
            "Every checkbox goes through ui/utils/checkbox.make_checkbox -- "
            "it carries the palette, takefocus=0, the zeroed border and "
            "focus ring (a spacing lever, not just a look), and the "
            "winfo_id() that stops the flash.",
        "ScrolledText":
            "Every scrolled text goes through "
            "ui/utils/scrolled_text.make_scrolled_text -- it darkens the "
            "wrapping frame and scrollbar the widget builds for itself, "
            "which no constructor keyword can reach and which paint "
            "near-white before the Text covers them.",
    }
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        rel = path.relative_to(SOURCE_ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read(),
                             filename=str(path))
        except SyntaxError:
            continue                      # compileall is what reports this
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in WIDGET_MODULES):
                continue
            widget = node.func.attr
            owner = SOLE_CONSTRUCTORS.get(widget)
            if owner is None or rel == owner:
                continue
            failures.append(
                f"{rel}:{node.lineno} builds a "
                f"{node.func.value.id}.{widget} directly. {WHY[widget]}"
            )

    return failures
