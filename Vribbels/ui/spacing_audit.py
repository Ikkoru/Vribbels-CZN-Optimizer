"""Spacing audit: measure the gaps the UI spacing rules talk about.

Why this exists
---------------
A rendered gap is `ancestor padding + pack/grid pad + the child's own
internal inset + the font's line box`. Only the first two are visible in
the source, so the source cannot be read to find out what is on screen.
Until this module, the only way to check a gap was to launch the app,
screenshot it and count pixels by hand -- one gap per round trip.

How it measures
---------------
The same way the maintainer does. `docs/ui_spacing.md` "The rules"
defines a gap as the count of BACKGROUND-coloured pixels between two
painted edges, both end pixels included, with no hover effect showing.
So the audit screenshots the window and counts background pixels. That
is glyph-accurate for free: a title ending in "g" and one ending in "s"
produce different counts because their descenders differ, exactly as
they do on screen.

Nothing here runs in a normal launch -- see `run_audit`'s caller.

Preconditions (enforced, not assumed)
-------------------------------------
  * the window is mapped, unobscured and frontmost
  * the pointer is away from the widgets under test (hover changes
    painted pixels)
  * a snapshot is loaded, so data-driven panels exist to measure

Windows only: `ImageGrab.grab` reads the screen there. This is a Windows
application, so that is not a limitation in practice.
"""

import json
import os
import tkinter as tk
import time
from dataclasses import dataclass, field
from typing import Optional

from PIL import ImageGrab


# ------------------------------------------------------------------ geometry

@dataclass
class Box:
    """A widget's allocated box in ROOT (screen) coordinates.

    Root coordinates rather than parent-relative: gaps are routinely
    measured between widgets in different parents (a frame's edge and a
    label three levels down), and only a common origin makes those
    comparable. `right` and `bottom` are INCLUSIVE -- the last column
    and row the widget owns.
    """
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


def box_of(widget) -> Box:
    """The widget's allocated box. Raises tk.TclError if unmapped.

    This is the box Tk gave the widget, NOT what it painted inside it --
    a Label's box is mostly background. The pixel scan below is what
    finds the painted edges.
    """
    x = widget.winfo_rootx()
    y = widget.winfo_rooty()
    return Box(x, y, x + widget.winfo_width() - 1,
               y + widget.winfo_height() - 1)


# ------------------------------------------------------------------- capture

class Capture:
    """One screenshot of the window plus the palette to classify it.

    `background` is the window background and the notebook strip behind
    the tabs, and nothing else. It is tempting to also treat `bg_light`
    / `bg_lighter` as empty space -- they are backgrounds in the design
    sense -- but they are the FILL of buttons, spinboxes, comboboxes and
    Treeviews. Counting them as background makes the scan look straight
    through a control and measure to its text instead of its edge,
    inflating every gap whose first element is a control.

    Where a gap really is inside a lighter region (text inside a Text
    widget, which fills its panel with `bg_light`), the caller passes
    that colour explicitly via the `bg` argument.
    """

    SETTLE_MS = 250

    def __init__(self, image, origin, background, palette):
        self.image = image
        self.origin = origin              # (x, y) of the image's top-left
        self.background = set(background)
        self.palette = palette
        self._px = image.load()

    @classmethod
    def of_window(cls, root, colors):
        # update() drains Tk's paint queue, but ImageGrab reads the
        # COMPOSITED desktop, which lags it. Without the pause the grab
        # can catch the previous tab's pixels while using the new tab's
        # widget coordinates -- which reads as plausible-looking numbers
        # rather than as an error, so it is worth over-waiting.
        root.update()
        time.sleep(cls.SETTLE_MS / 1000)
        root.update()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        bbox = (x, y, x + root.winfo_width(), y + root.winfo_height())
        image = ImageGrab.grab(bbox).convert("RGB")
        palette = {k: _hex_to_rgb(v) for k, v in colors.items()
                   if isinstance(v, str) and v.startswith("#")}
        # `bg_strip` counts as empty space, unlike every other shade in
        # the palette. It is the notebook's own background, and it shows
        # in the top row or two of a tab's box where the client element
        # does not reach -- so treating it as ink made every tab's first
        # element measure 0 from the tab list.
        empty = [palette["bg"], palette["bg_strip"]]
        return cls(image, (x, y), empty, palette)

    # How far a pixel may sit from a background colour and still count
    # as empty, per channel.
    #
    # **Not slack for a close-enough match.** It is for ANTIALIASING:
    # where two background shades meet, the seam is blended, and the
    # blend belongs to neither. Darkening the notebook strip put such a
    # seam at the right-hand end of the tab row -- one pixel column of
    # (30, 30, 45) against a background of (30, 30, 46) -- and because a
    # row counts as painted if ANY column in it is, that single column
    # made every tab's first element measure 0 from the tab list.
    #
    # Safe at 1 because the palette's shades are a dozen apart at their
    # closest. Widening it would start swallowing real ink.
    NEAR = 1

    def is_background(self, x: int, y: int, bg=None) -> bool:
        ox, oy = self.origin
        colours = self.background if bg is None else bg
        pixel = self._px[x - ox, y - oy]
        if pixel in colours:
            return True
        return any(
            all(abs(p - c) <= self.NEAR for p, c in zip(pixel, colour))
            for colour in colours
        )

    def contains(self, x: int, y: int) -> bool:
        ox, oy = self.origin
        w, h = self.image.size
        return 0 <= x - ox < w and 0 <= y - oy < h


def _hex_to_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------- painted-edge finding

def last_painted_row(cap: Capture, box: Box, x: int) -> Optional[int]:
    """Bottom-most painted row of `box` along column `x`.

    Scanning a single column is deliberate. The reference point for a
    gap below text is the bottom of the DESCENDERS, so the column has to
    be one that a descender actually occupies -- see `text_scan_column`.
    """
    for y in range(box.bottom, box.top - 1, -1):
        if cap.contains(x, y) and not cap.is_background(x, y):
            return y
    return None


def first_painted_row(cap: Capture, box: Box, x: int) -> Optional[int]:
    for y in range(box.top, box.bottom + 1):
        if cap.contains(x, y) and not cap.is_background(x, y):
            return y
    return None


def last_painted_col(cap: Capture, box: Box, y: int) -> Optional[int]:
    for x in range(box.right, box.left - 1, -1):
        if cap.contains(x, y) and not cap.is_background(x, y):
            return x
    return None


def first_painted_col(cap: Capture, box: Box, y: int) -> Optional[int]:
    for x in range(box.left, box.right + 1):
        if cap.contains(x, y) and not cap.is_background(x, y):
            return x
    return None


def painted_extent_v(cap: Capture, box: Box, bg=None) -> Optional[tuple]:
    """(topmost, bottom-most) painted row anywhere in `box`.

    Used where the reference is the whole element rather than one
    column: the deepest painted row ANYWHERE on a line of text, and the
    topmost. Those are the rules' two reference points -- the bottom of
    the descenders for a gap below, and the top of the capitals for a
    gap above.

    The upper one is approximated by the topmost painted pixel, which is
    an ascender where the string has one taller than its caps. The rule
    says to ignore ascenders and judge by capitals; at Segoe UI 9 and 11
    the two top out level, so the approximation costs nothing there. It
    is the 14 bold headings where they differ, and those are measured
    against targets read off the screen rather than derived.

    A line with no descender therefore reports a higher bottom edge, and
    the gap below it measures larger -- correctly, and with no need to
    inspect the string.
    """
    top = bottom = None
    for y in range(box.top, box.bottom + 1):
        row_painted = any(
            cap.contains(x, y) and not cap.is_background(x, y, bg)
            for x in range(box.left, box.right + 1)
        )
        if row_painted:
            if top is None:
                top = y
            bottom = y
    if top is None:
        return None
    return top, bottom


def painted_extent_h(cap: Capture, box: Box, bg=None) -> Optional[tuple]:
    left = right = None
    for x in range(box.left, box.right + 1):
        col_painted = any(
            cap.contains(x, y) and not cap.is_background(x, y, bg)
            for y in range(box.top, box.bottom + 1)
        )
        if col_painted:
            if left is None:
                left = x
            right = x
    if left is None:
        return None
    return left, right


# ---------------------------------------------------------------------- gaps

def gap_between(a: int, b: int) -> int:
    """Background pixels between two painted edges, both ends counted."""
    return b - a - 1


def vertical_gap(cap: Capture, upper, lower) -> tuple:
    """Background rows between the painted bottom of `upper` and the
    painted top of `lower`. Returns (value, note).
    """
    ub = painted_extent_v(cap, box_of(upper))
    lb = painted_extent_v(cap, box_of(lower))
    if ub is None or lb is None:
        return None, "one element painted nothing (empty or hidden)"
    return gap_between(ub[1], lb[0]), ""


def horizontal_gap(cap: Capture, left, right) -> tuple:
    lb = painted_extent_h(cap, box_of(left))
    rb = painted_extent_h(cap, box_of(right))
    if lb is None or rb is None:
        return None, "one element painted nothing (empty or hidden)"
    return gap_between(lb[1], rb[0]), ""


MAX_BORDER = 4


def _painted_run_end(cap: Capture, start: int, limit: int, probe, step: int):
    """End of the painted run beginning at `start`, or None if `start`
    is not painted. `probe(i)` reports whether index i is painted.

    Capped at MAX_BORDER. Without the cap, a panel whose interior is
    FILLED (a Text widget's `bg_light` reaching the border) has no
    background pixel to stop at, and the run walks the full width of the
    widget -- which shows up as a gap of several hundred pixels rather
    than as an error. The cap turns that into a bounded wrong answer,
    and `frame_border_edges` reports that it was hit.
    """
    if not probe(start):
        return None, False
    i = start
    for _ in range(MAX_BORDER):
        if i == limit or not probe(i + step):
            return i, False
        i += step
    return i, True


def frame_border_edges(cap: Capture, frame) -> tuple:
    """The INNER edge of each of a frame's painted borders, and whether
    any scan hit the cap.

    The rules measure from the border, meaning the first background
    pixel after it -- not from the widget's box, which is where the
    border starts. clam paints a 2px LabelFrame border, so measuring
    from the box adds one pixel to every inset. Found by scanning rather
    than assuming a width, so a restyled or borderless frame still
    reports correctly.
    """
    fb = box_of(frame)
    mid_y = (fb.top + fb.bottom) // 2
    mid_x = (fb.left + fb.right) // 2

    def h(x):
        return cap.contains(x, mid_y) and not cap.is_background(x, mid_y)

    def v(y):
        return cap.contains(mid_x, y) and not cap.is_background(mid_x, y)

    left, l_sat = _painted_run_end(cap, fb.left, fb.right, h, 1)
    right, r_sat = _painted_run_end(cap, fb.right, fb.left, h, -1)
    top, t_sat = _painted_run_end(cap, fb.top, fb.bottom, v, 1)
    bottom, b_sat = _painted_run_end(cap, fb.bottom, fb.top, v, -1)
    edges = {
        "left": fb.left - 1 if left is None else left,
        "right": fb.right + 1 if right is None else right,
        "top": fb.top - 1 if top is None else top,
        "bottom": fb.bottom + 1 if bottom is None else bottom,
    }
    return edges, any((l_sat, r_sat, t_sat, b_sat))


def inset_from_frame_edge(cap: Capture, frame, child, side: str,
                          bg=None) -> tuple:
    """Background pixels between a frame's painted border and a child's
    painted content, for the "border edge -> ..." rules.

    Both ends are painted edges: the inner edge of the frame's border,
    and the child's painted extent (not its box, so a Label's empty
    margin does not count as part of the gap).
    """
    edges, saturated = frame_border_edges(cap, frame)
    note = "border scan hit its cap; interior may be filled" if saturated \
        else ""
    if side in ("top", "bottom"):
        extent = painted_extent_v(cap, box_of(child), bg)
    else:
        extent = painted_extent_h(cap, box_of(child), bg)
    if extent is None:
        return None, "child painted nothing"
    if side == "left":
        return gap_between(edges["left"], extent[0]), note
    if side == "right":
        return gap_between(extent[1], edges["right"]), note
    if side == "top":
        return gap_between(edges["top"], extent[0]), note
    return gap_between(extent[1], edges["bottom"]), note


# -------------------------------------------------------------- the registry

@dataclass
class TrackedGap:
    """One row of the spacing ledger, in executable form.

    `tab` names the notebook tab that must be selected for the widgets
    to exist and be mapped. `scenario` names the app state the gap is
    measured in -- see SCENARIOS. `resolve(cap, app)` returns
    (value, note).

    `target` lives on the entry rather than being looked up from the
    rule, because two panels obeying the SAME rule can legitimately
    differ: the reference point is the painted glyph, so a title with a
    descender ("Upgrade Log Settings") sits lower than one without
    ("Slots") and its gap below measures smaller.

    `axis` is the direction the gap runs in, printed so a table of
    forty rows can be read for one direction at a time. It matches the
    orientation the spacing markers carry in their suffixes.

    `provisional` marks an entry that has been registered but not yet
    confirmed against a hand reading. Those rows print in yellow, and
    the flag comes off once the reading agrees -- so a batch being
    calibrated is visible at a glance among rows that already were.

    `target_source` records HOW that number was arrived at:

      "rule"     derived from the rule and the string -- a gap below
                 text, where the character set determines whether a
                 descender is present
      "exception" the site deliberately misses the rule, and its call
                  site carries an `exception` marker saying so. The
                  number is a reading of what it is meant to be
      "inferred"  the rule applies and is followed, but its number
                  cannot be COMPUTED for this case, so it was carried
                  across from a different panel or an earlier build.
                  Weaker than a reading and deliberately distinguished
                  from one. No entry needs this today

    The distinction is printed, so an exception's 7 is not later
    "corrected" to 5 by someone applying the rule from memory.
    """
    name: str
    tab: str
    rule: str
    target: int
    resolve: object
    axis: str = "h"                  # "h" or "v"
    scenario: str = "default"
    target_source: str = "rule"
    provisional: bool = False
    couples_with: tuple = field(default_factory=tuple)


REGISTRY: list[TrackedGap] = []


def track(name, tab, rule, target, resolve, axis, scenario="default",
          target_source="rule", provisional=False, couples_with=()):
    """Register one gap. `axis` is required: a row whose direction is
    not stated cannot be read out of a table of forty."""
    if axis not in ("h", "v"):
        raise ValueError(f"{name}: axis must be 'h' or 'v', got {axis!r}")
    REGISTRY.append(
        TrackedGap(name, tab, rule, target, resolve, axis, scenario,
                   target_source, provisional, tuple(couples_with)))


# ----------------------------------------------------------------- scenarios

# Some panels only exist in a particular app state, and their presence
# moves everything below them -- so the gaps under them have to be
# measured in BOTH states, not just the common one. A scenario is a
# (setup, teardown) pair run around a group of gaps; `default` is the
# app as it launches.
#
# element_override: the Optimizer tab's "Element override" frame is only
# packed for characters whose attribute is Unknown
# (_update_element_override_visibility). Forcing it visible is the only
# way to audit it, and it also shifts Important Settings / Have at Least
# / Set Configuration down, so those gaps are worth re-measuring with it
# shown.
SCENARIOS: dict = {
    "default": (lambda app: None, lambda app: None),
}


def register_scenario(name, setup, teardown):
    SCENARIOS[name] = (setup, teardown)


# ------------------------------------------------------------------- locating

def current_tab_widget(app):
    """The frame of the currently-selected notebook tab.

    Searching from here rather than from the root matters: widgets on
    UNSELECTED tabs still exist, so a root-wide search can return a
    same-named panel from a tab that is not on screen, and every pixel
    read from it would be garbage.
    """
    nb = app.notebook
    return nb.nametowidget(nb.select())


def find_labelframe(root, title: str):
    """The ttk.LabelFrame whose title is `title`, searched depth-first.

    Locating panels by their visible title rather than by attribute
    keeps the audit out of the tab files: most of these frames are
    locals (`slot_frame`, `req_frame`), and storing every one on `self`
    purely to measure it would be a large, spacing-irrelevant diff
    across six files.
    """
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            if w.winfo_class() == "TLabelframe" and w.cget("text") == title:
                return w
        except tk.TclError:
            pass
        stack.extend(w.winfo_children())
    return None


def first_child(widget):
    kids = widget.winfo_children()
    return kids[0] if kids else None


def find_descendant_class(root, cls: str):
    """First descendant whose Tk class is `cls`, breadth-first.

    Needed for the text-backed panels. Where one carries a scrollbar,
    its first child is a wrapper frame holding the text widget AND that
    scrollbar, and the scrollbar spans the full height -- so measuring
    the wrapper reports the scrollbar's top rather than the first line
    of prose. Reaching for the Text widget by class works whether or not
    a given panel has the wrapper: `Character` has neither, and packs
    its text widget straight into the LabelFrame.
    """
    queue = [root]
    while queue:
        w = queue.pop(0)
        try:
            if w.winfo_class() == cls:
                return w
        except tk.TclError:
            pass
        queue.extend(w.winfo_children())
    return None


def find_descendants_class(root, *classes) -> list:
    """Every descendant whose Tk class is one of `classes`."""
    found = []
    queue = [root]
    while queue:
        w = queue.pop(0)
        try:
            if w.winfo_class() in classes:
                found.append(w)
        except tk.TclError:
            pass
        queue.extend(w.winfo_children())
    return found


def find_descendant_text(root, prefix: str):
    """First descendant whose `text` option starts with `prefix`.

    Locating an element by the words on it, the same way the panel
    itself is located by its title. Cheaper and less invasive than
    storing a reference on the tab just so the audit can reach it -- and
    it fails loudly (the element is not found) rather than silently
    measuring the wrong widget.
    """
    queue = [root]
    while queue:
        w = queue.pop(0)
        try:
            text = w.cget("text")
            if isinstance(text, str) and text.startswith(prefix):
                return w
        except tk.TclError:
            pass
        queue.extend(w.winfo_children())
    return None


def leftmost_painted(cap: Capture, widgets, bg=None) -> Optional[int]:
    """Smallest painted left edge across `widgets`.

    For a rule that talks about "the checkboxes" rather than one
    checkbox: they share a left edge, and taking the minimum is immune
    to which one the tree walk happens to reach first.
    """
    lefts = []
    for w in widgets:
        try:
            extent = painted_extent_h(cap, box_of(w), bg)
        except tk.TclError:
            continue
        if extent is not None:
            lefts.append(extent[0])
    return min(lefts) if lefts else None


def labelframe_title_bottom(cap: Capture, frame, limit_y: int,
                            probe_offset: int = 8, bg=None) -> Optional[int]:
    """Bottom-most painted row of a ttk.LabelFrame's TITLE.

    The title is drawn by the style, not by a child widget, so it has no
    box to measure. It is bounded instead: above by the frame's top,
    below by `limit_y` -- the top of the first child's painted content,
    which the caller has already found. Everything painted between the
    two, in a column strip inside the title text, is title.

    Bounding by the child rather than by a fixed depth matters both ways.
    A fixed depth reaches past the title into the first child on a panel
    with no top padding. Taking the first painted RUN instead stops on
    the frame's own top border, which is separated from the glyphs by a
    background row.

    `bg` matters on a panel whose interior is FILLED: the strip between
    the title and the child crosses that fill, and with the default
    background the fill reads as painted, so the "title bottom" found is
    the fill's top row rather than the title's glyphs -- a gap of 0.
    Such callers pass a background set including the fill colour.

    `probe_offset` puts the strip inside the title text and clear of the
    frame's left border; it spans several columns so a probe landing
    between two letters still finds glyphs.
    """
    fb = box_of(frame)
    strip = Box(fb.left + probe_offset, fb.top,
                min(fb.left + probe_offset + 12, fb.right),
                min(limit_y - 1, fb.bottom))
    if strip.bottom < strip.top:
        return None
    extent = painted_extent_v(cap, strip, bg)
    return None if extent is None else extent[1]


def colour_at(cap: Capture, x: int, y: int) -> str:
    """The pixel at (x, y), named if the palette knows it.

    For diagnosing a scan that found ink where the eye sees empty
    space: a named colour says which style painted it, and a bare RGB
    triple says the palette is not where it came from.
    """
    if not cap.contains(x, y):
        return "outside the capture"
    ox, oy = cap.origin
    rgb = cap._px[x - ox, y - oy]
    for name, value in cap.palette.items():
        if value == rgb:
            empty = " (counted as empty)" if rgb in cap.background else ""
            return f"{name} {rgb}{empty}"
    return f"unnamed {rgb}"


def debug_dump(cap: Capture, frame, child, out=print, bg=None):
    """Print the raw coordinates behind a title gap.

    For when a measurement disagrees with the eye: it shows WHICH end is
    wrong, which guessing from the resulting number cannot.

    Coordinates are screen coordinates, as everything here is; the
    window-relative column is printed alongside because that is what a
    screenshot of the client area shows.

    The run list is the useful part when a panel has something painted
    BETWEEN the title and the first child -- a frame border, a
    separator. Each run is (first_row, last_row); a title gap that looks
    too large usually has an extra run in it.
    """
    root_y = frame.winfo_toplevel().winfo_rooty()
    fb = box_of(frame)
    cb = box_of(child)
    extent = painted_extent_v(cap, cb, bg)
    out(f"    frame box   top={fb.top} ({fb.top - root_y} in window) "
        f"left={fb.left} right={fb.right} bottom={fb.bottom}")
    out(f"    child box   top={cb.top} ({cb.top - root_y} in window) "
        f"left={cb.left} ({child.winfo_class()})")
    out(f"    child paint {extent}")
    if extent is None:
        return
    # The strip `title_gap` actually uses -- FULL width, offset only
    # enough to clear the frame's own border. A narrow probe over the
    # title's own columns is a different measurement and reports
    # different runs, which is worse than no diagnostic: it agrees with
    # the eye while the code disagrees with both.
    wide = Box(fb.left + 2, fb.top, fb.right - 2,
               min(extent[0] - 1, fb.bottom))
    out(f"    title strip rows {wide.top}..{wide.bottom} "
        f"cols {wide.left}..{wide.right} (what title_gap scans)")
    runs = painted_runs_v(cap, wide, bg)
    out(f"    painted runs: {runs}")
    out(f"    merged:       {merge_runs(runs)}")
    for first, last in runs[:6]:
        out(f"      row {first}: first paint at "
            f"{_first_painted_x(cap, wide, first, bg)}")
    narrow = Box(fb.left + 8, fb.top, min(fb.left + 20, fb.right),
                 min(extent[0] - 1, fb.bottom))
    out(f"    over the title's own columns {narrow.left}..{narrow.right}: "
        f"{painted_runs_v(cap, narrow, bg)}")
    out(f"    title bottom {labelframe_title_bottom(cap, frame, extent[0], bg=bg)}")


def _first_painted_x(cap: Capture, box: Box, y: int, bg=None):
    """(x, offset from the box's left, colour) of the first paint on a
    row -- which is the whole question when a full-width scan finds ink
    that a narrow one does not."""
    for x in range(box.left, box.right + 1):
        if cap.contains(x, y) and not cap.is_background(x, y, bg):
            return f"x={x} (+{x - box.left}) {colour_at(cap, x, y)}"
    return "nothing painted on this row"


def merge_runs(runs, max_gap: int = 1) -> list:
    """Join runs separated by `max_gap` background rows or fewer.

    Anti-aliasing can leave a one-row hole across a narrow probe strip,
    which would otherwise split a single line of text into two runs and
    make the first one end early.
    """
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] - 1 <= max_gap:
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(run)
    return merged


def title_gap(cap: Capture, frame, limit_y: int, probe_offset: int = 2,
              bg=None) -> tuple:
    """Gap below a LabelFrame's title, by the rule as stated:

        from the bottom of the title text to the first non-background
        pixel below it, INCLUDING a border.

    That last clause is the whole point. A border is a painted element
    like any other, and the rule stops at the first painted thing below
    the title -- which, a LabelFrame's title being drawn above its own
    top border, is usually that border rather than any content.
    Measuring through it to the first child instead sums two
    independent gaps and reports a multiple of the target.

    Which of the two it hits is not special-cased: whatever paints first
    below the title is the answer. `limit_y` (the first child's painted
    top) is the backstop for a panel with no border between the two.

    The strip spans the frame's FULL width. A narrow probe samples only
    the first two or three characters, so it misses any descender
    sitting later in the string -- it finds the "q" near the start of
    "Requirements" but not the "g" at the end of "Set Configuration",
    and silently reports the no-descender value for the second. Full
    width is safe because
    the title sits ABOVE the border rectangle, so the rows it occupies
    contain no border columns; `probe_offset` trims only enough to clear
    the frame's own edge.
    """
    fb = box_of(frame)
    strip = Box(fb.left + probe_offset, fb.top,
                max(fb.right - probe_offset, fb.left + probe_offset),
                min(limit_y - 1, fb.bottom))
    if strip.bottom < strip.top:
        return None, "no room between frame top and first child"
    runs = merge_runs(painted_runs_v(cap, strip, bg))
    if not runs:
        return None, "title probe found no glyphs"
    title_end = runs[0][1]
    if len(runs) > 1:
        return gap_between(title_end, runs[1][0]), ""
    return gap_between(title_end, limit_y), ""


def painted_runs_v(cap: Capture, box: Box, bg=None) -> list:
    """Every painted band in `box`, as (first_row, last_row) pairs."""
    runs = []
    start = None
    for y in range(box.top, box.bottom + 1):
        painted = any(
            cap.contains(x, y) and not cap.is_background(x, y, bg)
            for x in range(box.left, box.right + 1)
        )
        if painted and start is None:
            start = y
        elif not painted and start is not None:
            runs.append((start, y - 1))
            start = None
    if start is not None:
        runs.append((start, box.bottom))
    return runs


# ------------------------------------------------------------------ reporting

# ASCII, not the arrows the markers use: this prints to a cp932 console,
# where a non-ASCII character raises UnicodeEncodeError before the table
# reaches the screen.
AXIS_MARK = {"h": "<>", "v": "^v"}

# Dark yellow for a row nobody has confirmed against a hand reading yet,
# red for one that misses its target. `checks/run_all.py` colours its
# results the same way.
PROVISIONAL = "\033[33m"
OFF_TARGET = "\033[31m"
RESET = "\033[0m"


def _colour(line, flag, provisional):
    """Paint one row: yellow for unconfirmed, red for off target.

    A row can be both. It stays yellow and only the `<-` turns red, so
    "nobody has checked this" and "this is wrong" remain two facts
    rather than one colour cancelling the other.
    """
    if provisional and flag:
        marked = line.replace(flag, f"{OFF_TARGET}{flag}{PROVISIONAL}")
        return f"{PROVISIONAL}{marked}{RESET}"
    if provisional:
        return f"{PROVISIONAL}{line}{RESET}"
    if flag:
        return f"{OFF_TARGET}{line}{RESET}"
    return line

BASELINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs", "spacing_baseline.json")


def save_baseline(rows, path=BASELINE_PATH, out=print):
    data = {name: value for name, _t, value, *_ in rows if value is not None}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    out(f"baseline written: {len(data)} gaps -> {path}")


def compare_baseline(rows, path=BASELINE_PATH, out=print):
    """Report what has CHANGED since the baseline was frozen.

    Distinct from the target check, and it catches a different class of
    problem. A gap can sit on its target in both runs and still have
    been re-plumbed underneath; more importantly, an entry that stops
    being measured -- a panel renamed, so the title lookup no longer
    finds it -- silently vanishes from the table rather than failing.
    Against the baseline that shows up as MISSING.
    """
    if not os.path.exists(path):
        out("no baseline to compare against")
        return
    with open(path, encoding="utf-8") as fh:
        base = json.load(fh)
    now = {name: value for name, _t, value, *_ in rows if value is not None}

    changed = [(n, base[n], now[n]) for n in base if n in now
               and base[n] != now[n]]
    missing = [n for n in base if n not in now]

    # Entries the baseline has never seen are NOT reported. An entry
    # that new is one nobody has confirmed, so it is flagged
    # `provisional` and its whole row prints yellow -- saying it twice
    # only lengthens the run.
    if not (changed or missing):
        out("baseline: no change")
        return
    for name, was, is_ in changed:
        out(f"baseline CHANGED  {name}: {was} -> {is_}")
    for name in missing:
        out(f"baseline MISSING  {name} (renamed panel, or no longer measured)")


def run_audit(app, out=print, verbose: bool = False, freeze: bool = False):
    """Measure every registered gap and print a table.

    By default only rows that MISS their target are printed: a clean
    run should be short, so that the rows needing attention are the
    ones on screen rather than four lines in forty. `verbose` prints
    every row, which is what you want when calibrating the tool itself
    rather than checking the UI.

    Walks each scenario in turn; within a scenario, selects each tab
    (the widgets on an unselected tab are not mapped and report
    nonsense), captures it, and measures every gap registered against
    it. The original tab selection and app state are restored at the
    end.

    Must run AFTER `_reveal_window`'s settle loop: before that, half the
    widgets are still at their requested rather than allocated size.
    """
    notebook = app.notebook
    original = notebook.select()
    rows = []

    by_scenario: dict = {}
    for g in REGISTRY:
        by_scenario.setdefault(g.scenario, []).append(g)

    for scenario, gaps in by_scenario.items():
        setup, teardown = SCENARIOS.get(scenario, (None, None))
        if setup is None:
            rows.extend((g.name, g.target, None, f"no scenario {scenario!r}",
                         g.tab, g.axis, g.provisional) for g in gaps)
            continue
        setup(app)
        app.root.update()
        try:
            rows.extend(_measure_tabs(app, notebook, gaps, scenario))
        finally:
            teardown(app)
            app.root.update()

    notebook.select(original)
    app.root.update()

    _print_table(rows, out, verbose)
    if freeze:
        save_baseline(rows, out=out)
    else:
        compare_baseline(rows, out=out)
    return rows


def _measure_tabs(app, notebook, gaps, scenario):
    by_tab: dict = {}
    for g in gaps:
        by_tab.setdefault(g.tab, []).append(g)

    # Walk the tabs in the order they appear in the notebook, not in
    # registration order, so the report reads the way the app does.
    ordered = [notebook.tab(t, "text") for t in notebook.tabs()]
    tab_names = [n for n in ordered if n in by_tab]
    tab_names += [n for n in by_tab if n not in ordered]

    prefix = "" if scenario == "default" else f"[{scenario}] "
    rows = []
    for tab_name in tab_names:
        # A panel's rows stay together. Entries tracking a second element
        # inside a panel are registered after every panel's title and
        # edge, so in registration order they land at the bottom of the
        # tab, away from the panel they belong to -- and a panel is read
        # as a unit.
        tab_gaps = _grouped_by_panel(by_tab[tab_name])
        tab_id = _tab_id(notebook, tab_name)
        if tab_id is None:
            rows.extend((prefix + g.name, g.target, None,
                         f"no tab {tab_name!r}", tab_name, g.axis,
                         g.provisional) for g in tab_gaps)
            continue
        notebook.select(tab_id)
        app.root.update()
        cap = Capture.of_window(app.root, app.colors)
        for g in tab_gaps:
            try:
                value, note = g.resolve(cap, app)
            except tk.TclError as exc:
                rows.append((prefix + g.name, g.target, None,
                             f"unmapped: {exc}", tab_name, g.axis,
                             g.provisional))
                continue
            except Exception as exc:                      # noqa: BLE001
                rows.append((prefix + g.name, g.target, None,
                             f"error: {exc}", tab_name, g.axis,
                             g.provisional))
                continue
            rows.append((prefix + g.name, g.target, value,
                         _with_source(note, g.target_source), tab_name,
                         g.axis, g.provisional))
    return rows


def _grouped_by_panel(gaps):
    """Gaps reordered so one panel's rows are adjacent, panels keeping
    the order they were first registered in.

    The tab-list gap leads, whatever order it was registered in: it is
    the distance to the topmost thing on the tab, so it reads first for
    the same reason the rest read left to right and top to bottom.
    """
    order, buckets = [], {}
    gaps = sorted(gaps, key=lambda g: g.rule != "tab list -> first element")
    for g in gaps:
        panel = g.name.split(":")[0]
        if panel not in buckets:
            order.append(panel)
            buckets[panel] = []
        buckets[panel].append(g)
    return [g for panel in order for g in buckets[panel]]


def _with_source(note, source):
    """The note column, with the target's provenance where it has one.

    Bare word, not "target exception": the column already reads as
    something about this row, and what a reader wants from it is what
    the row IS, not where its number came from.
    """
    if source == "rule":
        return note
    return f"{note}, {source}" if note else source


def _tab_id(notebook, tab_name):
    for tab_id in notebook.tabs():
        if notebook.tab(tab_id, "text") == tab_name:
            return tab_id
    return None


def _print_table(rows, out, verbose=False):
    """The measured rows, under a heading per tab.

    `manual note` is left empty on purpose. It is the column a hand
    reading goes in when the tool and the eye disagree, which is the
    only way to tell a wrong measurement from a wrong target -- see
    plan.md 3.0.
    """
    on_target = sum(1 for _n, t, v, *_ in rows
                    if v is not None and v == t)
    shown = rows if verbose else [r for r in rows
                                  if r[2] is None or r[2] != r[1]]
    if not shown:
        out(f"all {len(rows)} gaps on target")
        return

    body = []
    for name, target, value, note, tab, axis, provisional in shown:
        arrow = AXIS_MARK[axis]
        if value is None:
            body.append((tab, name, arrow, f"{target:>6}", f"{'--':>8}",
                         f"{'--':>5}", note, provisional, "  <-"))
            continue
        delta = value - target
        flag = "" if delta == 0 else "  <-"
        body.append((tab, name, arrow, f"{target:>6}", f"{value:>8}",
                     f"{delta:>+5}", f"{note}{flag}", provisional, flag))

    width = max(len(r[1]) for r in body)
    out(f"{'gap'.ljust(width)}  axis  target  measured  delta  note")
    current = None
    for tab, name, arrow, target, value, delta, note, prov, flag in body:
        if tab != current:
            out(f"  {tab}")
            current = tab
        line = (f"{name.ljust(width)}  {arrow:>4}  {target}  {value}  "
                f"{delta}  {note}".rstrip())
        out(_colour(line, flag, prov))
    out(f"\n{on_target}/{len(rows)} on target")
