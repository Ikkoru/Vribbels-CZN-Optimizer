"""Every ttk style a tab defines is defined once, before layout.

Configuring, laying out or mapping any `ttk.Style` re-measures every
themed widget in the program. At startup that is free: nothing has
been laid out yet. After it, a tab already laid out lays out again,
and a Treeview whose stretching column has filled its space asks for
that space as its own: a style defined by a tab built after the
reveal takes 6px from the Combatants detail pane, for the rest of the
session.

So every style change under `Vribbels/ui/` sits in a function that
asks `style_once.first_time` first, and the app defines each at
startup (`OptimizerGUI.configure_styles`), so that a tab built later
finds it defined. The app's own `configure_styles` is where startup
styling lives and is not read here.

Headless, so this reads the source. A style is recognised by its
receiver: anything spelled `style`, or `Style()`.
"""

import ast

from ._harness import SOURCE_ROOT

NAME = "ttk styles are defined once"

MUTATORS = {"configure", "layout", "map", "element_create",
            "theme_settings"}
# Modules that run only on the maintainer's machine, with the window
# already up and every tab measured by them.
EXEMPT = {"ui/spacing_audit.py", "ui/spacing_registry.py"}


def _is_style(node):
    text = ast.unparse(node)
    return (text.split(".")[-1].lower() == "style"
            or text.endswith("Style()"))


def run():
    problems = []
    for path in sorted((SOURCE_ROOT / "ui").rglob("*.py")):
        rel = path.relative_to(SOURCE_ROOT).as_posix()
        if "__pycache__" in rel or rel in EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            guarded = any(
                isinstance(c, ast.Call) and ast.unparse(c.func).endswith(
                    "first_time") for c in ast.walk(func))
            for call in ast.walk(func):
                if not (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr in MUTATORS
                        and _is_style(call.func.value)):
                    continue
                # A query -- `style.configure(name, "option")` -- reads.
                if call.func.attr in ("configure", "map") \
                        and not call.keywords:
                    continue
                if call.func.attr == "layout" and len(call.args) < 2:
                    continue
                if not guarded:
                    problems.append(
                        f"{rel}:{call.lineno} changes a ttk style in "
                        f"`{func.name}` without `style_once.first_time`. "
                        f"Every style change re-measures every themed "
                        f"widget, and after the reveal that moves tabs "
                        f"already laid out. Guard it, and define it at "
                        f"startup from `configure_styles`.")
    return problems
