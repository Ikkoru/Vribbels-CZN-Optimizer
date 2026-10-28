"""The main tabs' group bars are drawn, fast, and where they belong.

`ui/utils/tab_bars.py` draws each tab from an image element and puts a
bar of its group's colour across its top. Every way that goes wrong is
silent:

1. **A tab with no group carries no bar.** Renaming a tab, or adding
   one, without a line in `TAB_GROUPS` leaves it bare among the rest.
   Green and yellow read alike, so their groups are never neighbours.
2. **The tab image's middle is TILED.** An image smaller than a tab is
   copied once per tile, and with a 1px middle every tab switch takes
   half a second. It has to be larger than any tab at 200%.
3. **The element's own size is its minimum**, the image's unless
   `width` and `height` say otherwise: every tab as large as the image.
4. **The bar meets the tab's top and right edges, and stops 1px short
   of its left**, where the outline parts it from the next tab's; the
   selected tab, narrower, carries a narrower bar; every tab is the
   width clam's tab had.
5. **A tab built on first need keeps its placeholder's bar**
   (`lazy_tabs.TabSlot.build`); no tab change follows a build in idle
   time to draw it again.

1 and 2 read the tables and the source; 3-5 render a notebook at alpha
0, which is invisible, and read its pixels.
"""

import ast
import time
from types import SimpleNamespace

from ._harness import SOURCE_ROOT, Skip, add_source_to_path

NAME = "the tabs' group bars"

APP = SOURCE_ROOT / "czn_optimizer_gui.py"
# Palette keys whose colours read alike: never neighbouring groups.
ALIKE = {frozenset(("green", "yellow"))}


def _app_titles():
    """The main notebook's tab titles, in order, from `setup_ui`."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    setup = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "setup_ui")
    titles = []
    for call in ast.walk(setup):
        if not isinstance(call, ast.Call):
            continue
        name = getattr(call.func, "attr", "")
        target = getattr(getattr(call.func, "value", None), "id", "") or \
            getattr(getattr(call.func, "value", None), "attr", "")
        if name == "add" and target == "lazy" and len(call.args) > 1:
            titles.append((call.lineno, call.args[1].value))
        elif name == "add" and target == "notebook":
            for kw in call.keywords:
                if kw.arg == "text":
                    titles.append((call.lineno, kw.value.value))
    return [title for _, title in sorted(titles)]


def _groups(tab_bars, colors):
    out = []
    titles = _app_titles()
    if not titles:
        return ["no tab titles found in `setup_ui`: this check reads them "
                "from its `notebook.add(..., text=...)` and `lazy.add` "
                "calls."]
    for title in titles:
        if title not in tab_bars.TAB_GROUPS:
            out.append(
                f"the {title!r} tab has no group in `tab_bars.TAB_GROUPS`, "
                f"so it carries no bar among tabs that all do.")
    for group, key in tab_bars.GROUP_COLOURS.items():
        if key not in colors:
            out.append(f"group {group!r} is coloured {key!r}, which is not "
                       f"a key of the palette.")
    keys = [tab_bars.GROUP_COLOURS.get(tab_bars.TAB_GROUPS.get(t))
            for t in titles]
    for left, right, a, b in zip(titles, titles[1:], keys, keys[1:]):
        if a != b and frozenset((a, b)) in ALIKE:
            out.append(
                f"{left!r} and {right!r} sit side by side in {a} and {b}, "
                f"which read alike: the boundary between their groups "
                f"does not show.")
    return out


def _image_size(tab_bars, titles):
    """Complaints unless the tab image outsizes every tab at 200%."""
    from tkinter import font as tkfont
    font = tkfont.nametofont("TkDefaultFont")
    # Text at 200% is under twice its 100% size (`scaling.TEXT_SCALING`);
    # every padding at most doubles.
    widest = max(2 * font.measure(t) for t in titles) + 2 * (
        2 * tab_bars.TAB_PAD[0] + tab_bars.CLAM_EDGE[0])
    tallest = 2 * (font.metrics("linespace") + tab_bars.BAR_PX
                   + tab_bars.SPACE_PX + tab_bars.TAB_PAD[3]) \
        + tab_bars.CLAM_EDGE[3]
    width, height = tab_bars.TAB_IMAGE
    if width < widest or height < tallest:
        return [f"`tab_bars.TAB_IMAGE` is {width}x{height}, and a tab at "
                f"200% can be {widest}x{tallest}: the element tiles the "
                f"image's middle to fill it, a copy per tile, and a small "
                f"middle makes every tab switch crawl."]
    return []


def _rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _rendered(tab_bars, titles, colors):
    """Complaints from a notebook of every tab, rendered at alpha 0."""
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk

    import czn_optimizer_gui as gui
    from ui.scaling import px
    from ui.utils.lazy_tabs import LazyTabs
    from ui.utils.presettle import _drain
    from ui.utils.window_render import render

    out = []
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-alpha", 0.0)
        style = ttk.Style(root)
        style.theme_use("clam")
        gui.OptimizerGUI.configure_styles(SimpleNamespace(
            style=style, colors=colors))
        notebook = ttk.Notebook(root, style="Flush.TNotebook")
        lazy = LazyTabs(root, notebook)
        bars = tab_bars.TabBars(notebook, colors)
        pages = []
        for n, title in enumerate(titles):
            if n == 1:
                # One built on first need, as most of the app's are.
                slot = lazy.add("slot", title, lambda: SimpleNamespace(
                    get_frame=lambda: built))
                built = ttk.Frame(notebook, height=40)
                pages.append(None)
                continue
            page = ttk.Frame(notebook, height=40)
            notebook.add(page, text=title)
            pages.append(page)
        bars.refresh()
        # Its own height, so the strip is the notebook less the page.
        notebook.pack(fill="x", anchor="n")
        root.geometry("1600x200")
        root.deiconify()

        def settle():
            root.update_idletasks()
            _drain(root, time.monotonic() + 0.5)

        settle()
        slot.build()
        pages[1] = built
        if not notebook.tab(built, "image"):
            out.append(
                "a tab built on first need lost its bar: "
                "`TabSlot.build` inserts the tab without its "
                "placeholder's image, and no tab change follows a build "
                "in idle time to draw it again.")
        strip = _rgb(colors["bg_strip"])
        font = tkfont.nametofont("TkDefaultFont")
        for chosen in (0, len(titles) - 1):
            notebook.select(pages[chosen])
            settle()
            image = render(root)
            x0 = notebook.winfo_rootx() - root.winfo_rootx()
            y0 = notebook.winfo_rooty() - root.winfo_rooty()
            bottom = notebook.winfo_height() - 40 - 1
            if bottom > 40:
                out.append(
                    f"the tab strip is {bottom + 1}px tall: the tab element "
                    f"takes its image's size as its minimum unless its "
                    f"`width` and `height` say otherwise.")
                break
            spans, cur, start = [], None, 0
            for x in range(notebook.winfo_width()):
                try:
                    index = notebook.index(f"@{x},{bottom}")
                except tk.TclError:
                    index = None
                if index != cur:
                    if cur is not None:
                        spans.append((cur, start, x - 1))
                    cur, start = index, x
            for index, left, right in spans:
                title = titles[index]
                state = "selected" if index == chosen else "normal"
                pad = (tab_bars.TAB_PAD_SELECTED if state == "selected"
                       else tab_bars.TAB_PAD)
                want = font.measure(title) + 2 * (px(pad[0])
                                                  + tab_bars.CLAM_EDGE[0])
                if right - left + 1 != want:
                    out.append(
                        f"the {state} {title!r} tab is {right - left + 1}px "
                        f"wide where clam's tab was {want}px.")
                    continue
                colour = _rgb(bars.bar_colour(pages[index]))
                mid = (left + right) // 2
                top = next((y for y in range(bottom)
                            if image.getpixel((x0 + mid, y0 + y)) != strip),
                           None)

                def at(x, y):
                    return image.getpixel((x0 + x, y0 + y)) == colour

                thick = px(tab_bars.BAR_PX)
                if top is None or not at(mid, top):
                    out.append(f"the {state} {title!r} tab has no bar of "
                               f"its group's colour along its top edge.")
                    continue
                if at(left, top) or not at(left + tab_bars.BAR_LEFT, top):
                    out.append(
                        f"the {state} {title!r} tab's bar does not start "
                        f"{tab_bars.BAR_LEFT}px in from its left edge, so "
                        f"it runs into its neighbour's or leaves a gap.")
                if not at(right, top):
                    out.append(f"the {state} {title!r} tab's bar stops "
                               f"short of its right edge.")
                if not at(mid, top + thick - 1) or at(mid, top + thick):
                    out.append(f"the {state} {title!r} tab's bar is not "
                               f"{thick}px thick.")
    finally:
        root.destroy()
    return out


def run():
    add_source_to_path()
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception as e:                    # no display
        raise Skip(f"Tk will not start here ({type(e).__name__})")
    import czn_optimizer_gui as gui
    from ui.utils import tab_bars
    colors = dict(gui.COLORS)
    out = _groups(tab_bars, colors)
    titles = _app_titles()
    import tkinter as tk
    root = tk.Tk()
    try:
        root.withdraw()
        out += _image_size(tab_bars, titles)
    finally:
        root.destroy()
    return out + _rendered(tab_bars, titles, colors)


FAULTS = [
    ("a tab without a group", "ui.utils.tab_bars:TAB_GROUPS",
     '    "Checklist": "progress",\n', "", "no group"),
    ("green beside yellow", "ui.utils.tab_bars:GROUP_COLOURS",
     '"app": "purple",', '"app": "yellow",', "read alike"),
    ("a tiny tab image", "ui.utils.tab_bars:TAB_IMAGE",
     "(600, 120)", "(3, 3)", "a copy per tile"),
    ("the element at the image's size", "ui.utils.tab_bars:configure",
     'sticky="nswe", width=3, height=3)', 'sticky="nswe")',
     "minimum"),
    ("the bar from the very left", "ui.utils.tab_bars:configure",
     "padding=(BAR_LEFT, 0, 0, normal[3])",
     "padding=(0, 0, BAR_LEFT, normal[3])", "in from its left edge"),
    ("the bar a pixel too wide", "ui.utils.tab_bars:TabBars._bar",
     "- BAR_LEFT)", ")", "where clam's tab was"),
    ("the selected tab's bar too wide", "ui.utils.tab_bars:TabBars.refresh",
     'state = "selected" if page == chosen else "normal"',
     'state = "normal"', "selected"),
    ("a built tab loses its bar", "ui.utils.lazy_tabs:TabSlot.build",
     ['image=notebook.tab(placeholder, "image"),\n',
      'compound=notebook.tab(placeholder, "compound"))'],
     ["", ")"], "lost its bar"),
]
