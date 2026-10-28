"""A bar of colour across the top of each main tab, saying its group.

The tabs fall into groups -- the gear tabs, the progress tabs, the
program's own, and the account's records (Stats & Gacha History,
Epione) -- and a group's colour along the top of its tabs finds a tab
faster than reading their titles does.

**ttk has no per-tab colour.** `TNotebook.Tab` styles every tab of a
notebook at once, and a tab's state is only `normal` / `disabled` /
`hidden`. What IS per tab is `image` and `compound`, so the bar is an
image above the title (`compound="top"`), drawn here rather than
loaded.

**The tab is drawn by `bar.Notebook.tab`, an image element, not by
clam's.** Clam's tab element insets what it holds by its 2px border,
and its focus ring by 1px more, and neither can be set: a bar inside
them stops 3px short of every edge. The image element paints a tab the
way clam does -- an outline along the top and left, its corner cut,
and the light line inside it -- and insets nothing, so the bar meets
the tab's top and right edges and stops 1px short of the left, where
the outline shows and parts one tab's bar from the next. The tab's
padding takes over clam's inset (`CLAM_EDGE`), so the title sits
where it did. What goes with clam's element: the focus ring, and two
short outline lines clam draws 1px outside a tab, which an image
element cannot -- the last tab's right edge, and beside the selected
tab where that one sits lower.

**The selected tab is narrower than the rest** (the theme's selected
padding, `TAB_PAD_SELECTED`), and an image is one width whatever the
tab's state, so the selected tab carries a narrower bar, swapped in on
every tab change.

`ui/utils/alert.py` marks a tab by blinking its bar in the alert
colour (`TabBars.mark`). The two bars are the same width, so the strip
never moves.
"""

import tkinter as tk
from tkinter import font as tkfont

from ..scaling import px
from .style_once import first_time

# Each tab's group, by its title, and each group's colour, a key of the
# palette (`COLORS`). A tab not listed carries no bar. Green and yellow
# read alike, so they are never neighbours; red is the alert's.
TAB_GROUPS = {
    "Optimizer": "gear",
    "Memory Fragments": "gear",
    "Gear Score": "gear",
    "Combatants": "gear",
    "Materials": "progress",
    "Checklist": "progress",
    "Galactic Disaster": "progress",
    "Capture": "app",
    "Setup & Settings": "app",
    "Stats & Gacha History": "stats",
    "Epione": "stats",
}
GROUP_COLOURS = {
    "gear": "accent",
    "progress": "green",
    "app": "purple",
    "stats": "yellow",
}

# The tab's padding at 100%, and the selected tab's: the theme maps
# `selected` to its own, which wins over the app's (`scale_theme`
# restates it as these).
TAB_PAD = (10, 5, 10, 5)
TAB_PAD_SELECTED = (6, 4, 6, 2)
# What clam's tab element and focus ring put round the padding, in
# device pixels at every scale: the element's 2px border on top and
# both sides, none below, and the ring's 1px all round.
CLAM_EDGE = (3, 3, 3, 1)
# The bar's distance from the tab's left edge: the outline, 1px at
# every scale.
BAR_LEFT = 1
# The parts of the tab's padding, in both states, that are device
# pixels at every scale. `checks/check_theme_scaling.py` holds every
# other part to twice its 100% size at 200%.
FIXED_PADDING = (BAR_LEFT, 0, 0, CLAM_EDGE[3])
BAR_PX = 4
# Bar to title. The selected tab's, as its top padding, is 1px less.
SPACE_PX = 4

# The tab images' size. **NOT a detail**: an image element fills its
# area by TILING the image's middle, one copy per tile, so with a 1px
# middle a tab is a copy per pixel and every tab switch takes half a
# second. Larger than any tab at any scale, the middle is one tile.
# The element's `width` and `height` are its minimum size, which would
# otherwise be this.
TAB_IMAGE = (600, 120)

TAB_STYLE = "Flush.TNotebook.Tab"


def _tab_image(master, outline, light, fill):
    width, height = TAB_IMAGE
    image = tk.PhotoImage(master=master, width=width, height=height)
    # Pixel (0, 0) is left unset, transparent: the corner clam cuts.
    image.put(outline, to=(1, 0, width, 1))
    image.put(outline, to=(0, 1, 1, height))
    image.put(light, to=(1, 1, width, 2))
    image.put(light, to=(1, 2, 2, height))
    image.put(fill, to=(2, 2, width, height))
    return image


def configure(style):
    """`bar.Notebook.tab`, and `Flush.TNotebook.Tab` drawn by it.

    At startup, before any notebook exists (`OptimizerGUI.
    configure_styles`): a style changed later re-measures every widget
    there is (`style_once.py`). The colours are the theme's own as the
    app has set them, read from the plain tab style.
    """
    if not first_time(style, "bar.Notebook.tab"):
        return
    master = style.master

    def look(option, state=()):
        return style.lookup("TNotebook.Tab", option, state)

    outline = look("bordercolor")
    images = [_tab_image(master, outline, look("lightcolor", state),
                         look("background", state))
              for state in ((), ("selected",))]
    # Held on the root: a PhotoImage with no Python reference is
    # collected, and every tab goes blank.
    master._tab_bar_images = images
    style.element_create("bar.Notebook.tab", "image", images[0],
                         ("selected", images[1]), border=(2, 2, 0, 0),
                         padding=0, sticky="nswe", width=3, height=3)
    style.layout(TAB_STYLE, [("bar.Notebook.tab", {
        "sticky": "nswe", "children": [("Notebook.padding", {
            "sticky": "nswe", "children": [
                ("Notebook.label", {"sticky": "nswe"})]})]})])
    normal, selected = (_inset(px(pad)) for pad in (TAB_PAD,
                                                    TAB_PAD_SELECTED))
    # spacing: unique -- a tab's own inset, its bar at the top edge -- tab, text ↔↕
    # No padding above the bar or right of it, 1px left of it; the
    # bar's width carries the sides (`TabBars._bar`).
    style.configure(TAB_STYLE, padding=(BAR_LEFT, 0, 0, normal[3]),
                    space=px(SPACE_PX))
    # The selected tab's lost top padding comes out of the space.
    style.map(TAB_STYLE, padding=[("selected",
                                   (BAR_LEFT, 0, 0, selected[3]))],
              space=[("selected",
                      px(SPACE_PX) - (normal[1] - selected[1]))])


def _inset(pad):
    """A title's distance from each edge of a clam tab padded `pad`."""
    return tuple(p + e for p, e in zip(pad, CLAM_EDGE))


class TabBars:
    """The bars on one notebook's tabs.

    Created before the tabs, so that the tab that marks itself finds
    it, and `refresh`ed once they are added. Finds every tab by its
    title whenever it redraws, so a tab built later (`lazy_tabs.py`) is
    found where its placeholder stood.
    """

    def __init__(self, notebook, colors):
        self.notebook = notebook
        self.colors = colors
        # (title, state, colour) -> the bar, held for the same reason
        # the tab images are.
        self._bars = {}
        self._marks = {}
        self._shown = {}
        style = notebook.cget("style") or "TNotebook"
        self._font = tkfont.Font(
            root=notebook,
            font=notebook.tk.call("ttk::style", "lookup", f"{style}.Tab",
                                  "-font") or "TkDefaultFont")
        notebook._tab_bars = self
        notebook.bind("<<NotebookTabChanged>>", self.refresh, add="+")
        self.refresh()

    @staticmethod
    def of(notebook):
        """The bars on `notebook`, or None where it has none."""
        return getattr(notebook, "_tab_bars", None)

    def mark(self, page, colour):
        """Draw `page`'s bar in `colour`, or its group's for None."""
        title = self.notebook.tab(page, "text")
        if colour is None:
            self._marks.pop(title, None)
        else:
            self._marks[title] = colour
        self.refresh()

    def bar_colour(self, page):
        """The colour `page`'s bar is drawn in now, or None."""
        title = self.notebook.tab(page, "text")
        group = TAB_GROUPS.get(title)
        if group is None:
            return None
        return self._marks.get(title) or self.colors[GROUP_COLOURS[group]]

    def refresh(self, _event=None):
        """Every tab's bar for its state and mark. Only what changed is
        set: a tab's options set again re-measure the strip."""
        try:
            chosen = self.notebook.select()
            pages = self.notebook.tabs()
        except tk.TclError:
            return
        for page in pages:
            colour = self.bar_colour(page)
            if colour is None:
                continue
            title = self.notebook.tab(page, "text")
            state = "selected" if page == chosen else "normal"
            bar = self._bar(title, state, colour)
            if self._shown.get(page) is not bar:
                self._shown[page] = bar
                self.notebook.tab(page, image=bar, compound=tk.TOP)

    def _bar(self, title, state, colour):
        """The bar for `title`'s tab: the title, and the title's inset
        either side but the bar's own 1px. Measured, so not through
        `px`; the paddings are."""
        key = (title, state, colour)
        if key not in self._bars:
            pad = TAB_PAD_SELECTED if state == "selected" else TAB_PAD
            inset = _inset(px(pad))
            width = (self._font.measure(title) + inset[0] + inset[2]
                     - BAR_LEFT)
            bar = tk.PhotoImage(master=self.notebook, width=width,
                                height=px(BAR_PX))
            bar.put(colour, to=(0, 0, width, px(BAR_PX)))
            self._bars[key] = bar
        return self._bars[key]
