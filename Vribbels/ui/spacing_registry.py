"""The spacing ledger, in executable form.

Each entry here is one row of the rules table in
`docs/ui_spacing.md`, bound to the panel it applies to. Importing
this module registers them; `spacing_audit.run_audit` measures them.

Two conventions worth knowing before adding entries:

* **Panels are named by their visible title**, not by attribute. See
  `docs/ui_spacing.md` "Checking spacing" for why, and for what
  breaks if a title is renamed.
* **The READING is corrected, not the target.** The rules measure to a
  baseline and a cap; the screen shows ink, which overshoots both
  wherever the string has a descender or a tall ascender. The
  correction is applied where the gap is measured, so a title holding a
  `g` and one holding none answer to the same number -- which is what
  makes a target a plain number rather than one per glyph class.
"""

import re
import tkinter as tk
from tkinter import font as tkfont

from . import spacing_audit as sa


# Rule names. Canonical text lives in the Marker column of the rules
# table in `docs/ui_spacing.md`; these constants copy it, and the
# widget code that sets a lever for a rule carries the same string in a
# `# spacing: <rule>` comment. That comment cannot import from here, so
# the table is what both sides copy from -- and a string that drifts on
# either side does not fail, it just splits the grep into two partial
# answers. Every rule has a constant, including the ones nothing
# measures yet, so registering one later cannot invent a second
# spelling for it.
RULE_CONTENT_FRAME = "content frame -> content frame"
RULE_TAB_LIST = "tab list -> first element"
RULE_HEADER_SUBTEXT = "header subtext"
RULE_BORDER_EDGE_CONTENT = "border edge -> first non-button element"
RULE_BUTTON_GAP = "button -> button"
RULE_BORDER_EDGE_BUTTON = "border edge -> button"
RULE_ALL_NONE_ROW = "checkbox block -> All/None row"
RULE_SPINBOX_PITCH = "spinbox row -> spinbox row"
RULE_CHECKBOX_PITCH = "checkbox/slider ↕ checkbox/slider rows"
RULE_LABEL_ROW_PITCH = "label row -> label row"
RULE_CHECKBOX_DIVISION = "checkbox row -> checkbox row (small division)"
RULE_TITLE_ELEMENT = "title above, element below"
RULE_LABEL_ELEMENT = "label ↔ its element"
RULE_HEADING_ELEMENT = "heading ↔ element"
RULE_PAIR_GAP = "element and its label ↔ element and its label"
RULE_EXPLANATION = "explanation text -> the controls it explains"
RULE_UNRELATED_CHECKBOXES = "checkboxes -> unrelated checkboxes"
RULE_PANEL_UNRELATED_LABEL = "panel ↕ unrelated label"
RULE_CONFIG_PANEL_ROW = "config panel row ↕ row"
RULE_CONTROL_GROUP = "control group ↔ control group"


DESCENDERS = "gjpqy"

# One pixel above a descender at Segoe UI 9, measured. Between the two
# derived classes, which is why titles holding one used to need a hand
# target.
PARENTHESES = "()"

# Characters that never reach above the x-height, plus the punctuation
# that sits on or below the baseline. A string built only from these has
# NO cap and NO ascender, so its topmost painted pixel is the x-height
# top -- 2-3px lower than a string that has one, at the same padding.
#
# Deliberately conservative: anything not listed (capitals, digits,
# b d f h k l t, brackets, quotes, and every other tall mark) is assumed
# to reach cap height. Being wrong in that direction costs an entry an
# explicit target it did not strictly need; being wrong the other way
# silently mis-targets it.
X_HEIGHT_ONLY = set("acemnorsuvwxz " + ".,;:_-")


def reaches_cap_height(text: str) -> bool:
    """False when the string is entirely x-height, so its top reference
    sits lower than a normal line's."""
    return any(c not in X_HEIGHT_ONLY for c in text)


# How far below the BASELINE a string's ink reaches, and how far above
# its CAPITALS. The rules measure to the baseline and the cap; the
# screen shows ink; these are the difference.
#
# They were targets once -- a title with a descender was given 2 where
# one without was given 5, and a 14 bold heading with an ascender lost a
# pixel. Four glyph classes spread across two tables, all of them saying
# the same thing twice: that the tool reads a different reference point
# than the rules name. Correcting the READING says it once, and every
# target below is a plain number again.
DESCENDER_DEPTH = 3
PARENTHESIS_DEPTH = 2

# A descender at Segoe UI 14 bold, the tab headings' font, reaches a
# pixel deeper than one at 9. Measured from the three tab headings read
# against each other: "Data Capture" and "First-Time Setup" each carry a
# `p` and each read 1px tighter than the eye, where "Gear Score
# Calculation" has no descender and read dead on. Two sites saying the
# same thing with a control beside them.
DESCENDER_DEPTH_14_BOLD = 4

# Segoe UI 11 -- the Capture tab's status line and the Setup Status
# panel -- reaches NO deeper than 9 does. Measured off the Capture
# status pair with the two lines confirmed seated on one line: their ink
# stopped on the same row, and equal ink over equal baselines is equal
# depth. So the extra pixel at 14 bold is the WEIGHT and the size
# together, not size alone, and there is no ramp to interpolate along.
DESCENDER_DEPTH_11 = DESCENDER_DEPTH


def ink_below_baseline(text: str, bold14: bool = False) -> int:
    """How far `text`'s ink reaches below the baseline.

    Checked deepest first: a string can hold both a descender and a
    parenthesis, and the deeper glyph is the one the ink stops at.

    `bold14` for the tab headings, whose descenders reach a pixel
    further than body text's. A parenthesis has never been measured at
    that size and no heading holds one, so it keeps the 9pt depth.
    """
    if any(c in text for c in DESCENDERS):
        return DESCENDER_DEPTH_14_BOLD if bold14 else DESCENDER_DEPTH
    if any(c in text for c in PARENTHESES):
        return PARENTHESIS_DEPTH
    return 0


def _title_gap_target(title: str) -> int:
    """One number for every title now: the reading is corrected to the
    baseline before it gets here, so the glyphs in the string no longer
    change what the gap should be.

    Kept as a function rather than folded into its callers because it is
    what `checks/check_spacing_registry.py` compares against, and a
    rule whose target stops being uniform would go back through here.
    """
    return 5


def track_text_top_gap(name, tab, rule, resolve, text, target=None,
                       scenario="default"):
    """Register a gap measured TO the top of a line of text.

    Refuses to guess. The topmost painted pixel of a line is a cap, an
    ascender or -- when the string has neither -- the x-height, and the
    first two differ from each other by a per-font pixel that cannot be
    derived (see docs/ui_spacing.md). So `target` must be supplied,
    measured once and agreed, and it is recorded as an exception rather
    than rule-derived.

    The x-height-only case is the one worth catching early, because it
    looks like an ordinary gap that is 2-3px too wide: the error message
    names it rather than leaving the reader to spot it in the table.
    """
    if target is None:
        why = ("text has no capital or ascender, so its top sits at the "
               "x-height" if not reaches_cap_height(text)
               else "cap and ascender heights differ per font")
        raise ValueError(
            f"{name}: a target must be measured and passed for this gap -- "
            f"{why}"
        )
    sa.track(name=name, tab=tab, rule=rule, target=target, resolve=resolve,
             axis="v", scenario=scenario, target_source="exception")


# The panels whose only content is a text widget filling the frame
# with `bg_light`. Their gaps are measured INSIDE that fill: the panel's
# background reaching the border is intended (0 is correct there), and
# the frame-edge rule applies to the prose within it.
#
# "Character" joined them when it collapsed from stacked labels to a
# single Text widget. Measuring it the old way reports a NEGATIVE inset
# and a saturated border scan, because the scan looks for a background
# pixel between border and content and the fill leaves none.
TEXT_PANELS = {"Character", "Partner", "How Gear Score Works",
               "Capture Log", "Setup Instructions"}


def _text_of(app, title):
    frame = _panel(app, title)
    text = sa.find_descendant_class(frame, "Text")
    if text is None:
        raise LookupError(f"{title!r} has no Text widget")
    return frame, text


def restate_from_reference(measured, note, overshoot):
    """A gap read from a string's INK, restated from its reference edge.

    **The correction always ADDS, whichever end of the gap the text is
    on.** Ink overshoots INTO the gap in both directions: a descender
    hangs down into a gap below the text, and a tall ascender rises up
    into a gap above it. Either way the raw reading is short by however
    far the glyphs reach, and either way that is what gets added back.

    The two looked like opposites and one of them was written with the
    sign flipped, which put both 14 bold tab headings 2px out -- one for
    the correction going the wrong way and one for the target having
    moved to meet it.
    """
    if measured is None:
        return None, note
    return measured + overshoot, note


def _text_panel_title_gap(title):
    def resolve(cap, app):
        frame, text = _text_of(app, title)
        # The fill counts as background at BOTH ends here: for finding
        # the prose inside the text widget, and for the title strip,
        # which crosses the fill on its way down to the first line.
        fill = {cap.palette["bg_light"]}
        strip_bg = fill | cap.background
        extent = sa.painted_extent_v(cap, sa.box_of(text), fill)
        if extent is None:
            return None, "text widget is empty"
        return restate_from_reference(
            *sa.title_gap(cap, frame, extent[0], bg=strip_bg),
            ink_below_baseline(title))
    return resolve


def _text_panel_inset(title, side="left"):
    """Resolver: frame border -> the prose inside the text widget.

    The border is NOT found by scanning here. These panels are built so
    the fill reaches the border -- that is the point of them -- so there
    is no background pixel between the two for a scan to stop at. But
    the same fact gives the answer directly: the text widget abuts the
    border, so the border's inner edge is the widget's own box edge.
    """
    def resolve(cap, app):
        frame, text = _text_of(app, title)
        fill = {cap.palette["bg_light"]}
        box = sa.box_of(text)
        measure = (sa.painted_extent_v if side in ("top", "bottom")
                   else sa.painted_extent_h)
        extent = measure(cap, box, fill)
        if extent is None:
            return None, "text widget is empty"
        if side == "left":
            return sa.gap_between(box.left - 1, extent[0]), ""
        if side == "top":
            return sa.gap_between(box.top - 1, extent[0]), ""
        # The far edges take the text widget's box as the border's inner
        # edge, the way the near ones do. Confirmed by reading the raw
        # coordinates once: the frame sits exactly 2px outside the text
        # box, which is its own border, so the widget is flush and the
        # reading is the inset alone.
        if side == "right":
            return sa.gap_between(extent[1], box.right + 1), ""
        return sa.gap_between(extent[1], box.bottom + 1), ""
    return resolve


def _caption_to_field(prefix):
    """Resolver: a caption's ink -> the field packed under it.

    The caption is found by the words on it and the field by class among
    its siblings, so neither has to be stored on the tab just to be
    measured.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        label = sa.find_descendant_text(tab, prefix)
        if label is None:
            return None, f"no caption starting {prefix!r}"
        field = sa.find_descendant_class(label.master, "TCombobox")
        if field is None:
            return None, "no dropdown under that caption"
        return restate_from_reference(
            *sa.vertical_gap(cap, label, field),
            ink_below_baseline(label.cget("text")))
    return resolve


# What phase 4 of plan.md asked for, as measurements rather than nudges.
# Its list was written before anything could measure, and two of the
# gaps it named have since been tracked and found ON target -- so the
# remaining question is only about the edges nothing watches.
#
# (tab, name, title, side). BOTTOM is absent everywhere: a text panel's
# prose stops where it stops, so the space under it is slack rather than
# an inset. RIGHT is Character only -- Partner puts a scrollbar between
# its text and the border, and the other three wrap, which makes their
# right edge the wrap point rather than a lever.
TEXT_PANEL_EDGES = [
    ("Combatants", "Character", "top"),
    ("Combatants", "Character", "right"),
    ("Combatants", "Partner", "top"),
    ("Capture", "Capture Log", "top"),
    ("Setup", "Setup Instructions", "top"),
    ("Gear Score", "How Gear Score Works", "top"),
]


def _panel(app, title):
    frame = sa.find_labelframe(sa.current_tab_widget(app), title)
    if frame is None:
        raise LookupError(f"no panel titled {title!r} on the selected tab")
    return frame


def _title_to_first_element(title):
    """Resolver: bottom of the panel's title -> the first thing painted
    below it, border included.

    The child is still located first, but only as a backstop: it bounds
    the search, and stands in as the endpoint on a panel with no border
    between title and content.
    """
    def resolve(cap, app):
        frame = _panel(app, title)
        child = sa.first_child(frame)
        if child is None:
            return None, "panel has no children"
        extent = sa.painted_extent_v(cap, sa.box_of(child))
        if extent is None:
            return None, "first child painted nothing"
        return restate_from_reference(*sa.title_gap(cap, frame, extent[0]),
                                      ink_below_baseline(title))
    return resolve


def _left_inset(title):
    """Resolver: panel's left border -> painted left edge of its first
    child."""
    def resolve(cap, app):
        frame = _panel(app, title)
        child = sa.first_child(frame)
        if child is None:
            return None, "panel has no children"
        return sa.inset_from_frame_edge(cap, frame, child, "left")
    return resolve


def _is(cap, x, y, colour):
    """Whether the pixel at (x, y) is exactly `colour`."""
    ox, oy = cap.origin
    return cap._px[x - ox, y - oy] == colour


def _border_inner_edges(cap, frame):
    """Each border's inner edge, found by scanning INWARD for the first
    paint rather than requiring paint at the frame's box edge.

    `sa.frame_border_edges` requires it, and a LabelFrame does not
    oblige: it reserves its title's height at the top, so the top border
    sits several rows inside the box and that scan finds nothing there.
    It then falls back to the box edge, which puts the interior ABOVE
    the border -- so the first thing found inside is the TITLE, and
    every panel reports its title's own offset instead of its content's.
    Six panels read a constant 3 that way, against hand readings from 4
    to 13.

    The same fallback on the right puts the interior over the border and
    finds the border itself, which reads 0.

    Kept here rather than fixed in `frame_border_edges`: twenty-seven
    frozen entries measure through that function on their LEFT edges,
    where the assumption happens to hold, and moving them all to prove a
    point is not worth a re-freeze.
    """
    fb = sa.box_of(frame)
    mid_y = (fb.top + fb.bottom) // 2
    mid_x = (fb.left + fb.right) // 2

    def run_end(start, limit, step, painted):
        """Skip inward to the first paint, then walk to that run's end."""
        i = start
        while i != limit and not painted(i):
            i += step
        if not painted(i):
            return start - step, False           # no border on this side
        crossed = 0
        while i != limit and painted(i + step):
            i += step
            crossed += 1
            if crossed >= sa.MAX_BORDER:
                return i, True
        return i, False

    # The border is drawn in `bordercolor`, which `configure_styles`
    # sets to `bg_lighter` -- a DIFFERENT shade from the `bg_light` that
    # fills spinboxes and Treeviews. Looking for that one colour finds
    # the border however much content abuts it, where "the first thing
    # that is not background" cannot: a panel whose spinboxes reach
    # every scan line has no background for such a run to stop at, and
    # the edge lands inside the fill.
    border = cap.palette.get("bg_lighter")

    def h_at(y):
        return lambda x: cap.contains(x, y) and _is(cap, x, y, border)

    def v_at(x):
        return lambda y: cap.contains(x, y) and _is(cap, x, y, border)

    def best(start, limit, step, probe_at, positions):
        """The first scan line that does NOT run into filled content.

        One line through the middle is not enough: a panel whose content
        reaches the centre -- a row of spinboxes, all `bg_light` -- has
        no background there for the border run to stop at, so the scan
        saturates and reports an edge inside the fill. Trying a few
        lines and taking one that terminates cleanly costs three scans
        and avoids a reading of 0.
        """
        first = None
        for at in positions:
            found, saturated = run_end(start, limit, step, probe_at(at))
            if first is None:
                first = (found, saturated)
            if not saturated:
                return found, False
        return first

    def spread(lo, hi):
        span = hi - lo
        return [lo + span // 2, lo + span // 4, lo + (span * 3) // 4]

    rows, cols = spread(fb.top, fb.bottom), spread(fb.left, fb.right)
    left, ls = best(fb.left, fb.right, 1, h_at, rows)
    right, rs = best(fb.right, fb.left, -1, h_at, rows)
    top, ts = best(fb.top, fb.bottom, 1, v_at, cols)
    bottom, bs = best(fb.bottom, fb.top, -1, v_at, cols)
    return ({"left": left, "right": right, "top": top, "bottom": bottom},
            any((ls, rs, ts, bs)))


# Widgets whose lowest ink is their TEXT. A Checkbutton's is its
# INDICATOR and a Button's is its border, so a descender in either one's
# label never reaches the bottom of the widget -- correcting by it would
# add three pixels that are not there. Three bottom insets moved that
# way before this was restricted.
TEXT_ONLY_CLASSES = ("TLabel", "Label")


def _lowest_text(cap, frame, floor):
    """The text of the label whose ink reaches `floor`, or "".

    Two guards, both learned the hard way. Only LABELS count, because
    only their lowest ink is a glyph. And the label has to be what the
    edge actually measures to -- `floor` is the lowest ink in the whole
    panel, and a label sitting above a spinbox is not what the reading
    stopped at, however low it is among labels.
    """
    stack = [frame]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        try:
            if widget.winfo_class() not in TEXT_ONLY_CLASSES:
                continue
            text = widget.cget("text")
            extent = sa.painted_extent_v(cap, sa.box_of(widget))
        except tk.TclError:
            continue
        if isinstance(text, str) and text and extent and extent[1] == floor:
            return text
    return ""


def _panel_edge_inset(title, side):
    """Resolver: one border of a panel -> the nearest ink inside it.

    Scans the whole INTERIOR rather than a nominated child, which is
    what makes it work on all four sides: the first child is the right
    reference for a top or left inset and the wrong one for a bottom or
    right, where what matters is whichever element reaches furthest.

    Deliberately NOT used for the left insets that were already
    registered. Those read against `first_child` and are frozen on
    target; swapping their resolver would move 20 rows to prove a point
    about tidiness.
    """
    def resolve(cap, app):
        frame = _panel(app, title)
        edges, saturated = _border_inner_edges(cap, frame)
        note = ("border scan hit its cap; interior may be filled"
                if saturated else "")
        interior = sa.Box(edges["left"] + 1, edges["top"] + 1,
                          edges["right"] - 1, edges["bottom"] - 1)
        measure = (sa.painted_extent_v if side in ("top", "bottom")
                   else sa.painted_extent_h)
        extent = measure(cap, interior)
        if extent is None:
            return None, "nothing painted inside the panel"
        if side == "left":
            return sa.gap_between(edges["left"], extent[0]), note
        if side == "top":
            return sa.gap_between(edges["top"], extent[0]), note
        if side == "right":
            return sa.gap_between(extent[1], edges["right"]), note
        # The BOTTOM edge measures up to text as often as not, and the
        # rules take the baseline -- so a panel whose last line has a
        # descender reads short by its depth, exactly as a title gap
        # does. Requirements ends on "...starting a new capture" and read
        # 6 against a hand reading of 9.
        return restate_from_reference(
            sa.gap_between(extent[1], edges["bottom"]), note,
            ink_below_baseline(_lowest_text(cap, frame, extent[1])))
    return resolve


# The rule says "5px, all edges" and only the left edges were tracked.
#
# These carried hand readings while their resolvers were being
# calibrated, and the readings earned it: they caught a scan that was
# measuring panel TITLES, another that stopped inside a spinbox's fill,
# and a baseline correction applied to checkboxes that have no baseline.
# All twelve agree with the eye now, so the readings are gone -- see
# `TrackedGap.hand` for why leaving them would have been worse than
# never adding them.
PANEL_EDGES = [
    ("Optimizer", "Important Settings", "top"),
    ("Optimizer", "Important Settings", "right"),
    ("Optimizer", "Important Settings", "bottom"),
    ("Optimizer", "Have at least this much of a stat", "top"),
    ("Optimizer", "Exclude Combatant's MFs", "top"),
    ("Optimizer", "Set Configuration", "top"),
    ("Optimizer", "Set Configuration", "bottom"),
    ("Capture", "Requirements", "top"),
    ("Capture", "Requirements", "bottom"),
    ("Capture", "Upgrade Log Settings", "top"),
    ("Capture", "Upgrade Log Settings", "bottom"),
    ("Capture", "Upgrade Log Settings", "right"),
    ("Gear Score", "Stat Weight Configuration", "top"),
]

# Hand readings for PANEL_EDGES rows that have not been nudged yet.
# Keyed by (panel, side) rather than carried in the table, because every
# other row in it has been on target for long enough to have none.
PANEL_EDGE_HANDS = {}


def _panel_gap(first, second, axis):
    """Resolver: the gap between two panels, painted edge to painted
    edge like every other rule.

    What each end IS differs by direction, and that is why the two
    directions answer to different rules. Side by side, both ends are
    borders. Stacked, the lower panel's topmost ink is its TITLE, drawn
    above its border -- so the nearest thing across the gap is text, and
    by proximity the text rule governs rather than the frame one.
    """
    def resolve(cap, app):
        a, b = _panel(app, first), _panel(app, second)
        return (sa.horizontal_gap(cap, a, b) if axis == "h"
                else sa.vertical_gap(cap, a, b))
    return resolve


def _list_to_panel_gap(panel):
    """Resolver: the character list's right edge -> a panel beside it.

    The list is a Treeview and a scrollbar sharing a frame, and the
    SCROLLBAR is the rightmost painted thing -- so the gap is measured
    from the frame that holds both, not from the tree. Located by class
    because there is exactly one Treeview on this tab.
    """
    def resolve(cap, app):
        tree = sa.find_descendant_class(sa.current_tab_widget(app), "Treeview")
        if tree is None:
            return None, "no Treeview on this tab"
        return sa.horizontal_gap(cap, tree.master, _panel(app, panel))
    return resolve


def _first_button_gap(title):
    """Resolver: the gap between a panel's first two buttons.

    The All/None rows are the only pairs of adjacent buttons inside a
    panel, so the first two found are them. A panel that grows a third
    button before these two would measure the wrong pair -- the entry is
    named for the row so that reads as wrong rather than as a number.
    """
    def resolve(cap, app):
        frame = _panel(app, title)
        buttons = sa.find_descendants_class(frame, "TButton", "Button")
        if len(buttons) < 2:
            return None, f"{len(buttons)} buttons in panel, need 2"
        return sa.horizontal_gap(cap, buttons[0], buttons[1])
    return resolve


# (tab, name, target, resolver) for the gaps between content frames.
# Not every instance -- the rule has 47 marker sites and most are pads
# on borderless containers with nothing painted to measure to. These
# are the ones where both ends draw an edge.
CONTENT_FRAME_ENTRIES = [
    ("Memory Fragments", "Slots -> Sets", 4, "h",
     _panel_gap("Slots", "Sets", "h")),
    ("Memory Fragments", "Sets -> Main Stats", 4, "h",
     _panel_gap("Sets", "Main Stats", "h")),
    # Nothing vertical belongs here. Stacked panels put the lower
    # one's TITLE across the gap, and the nearest element decides which
    # rule applies -- see PANEL_OVER_TEXT_ENTRIES.
    ("Setup", "Setup Status -> Restore Defaults", 4, "h",
     _panel_gap("Setup Status", "Restore Defaults", "h")),
    ("Combatants", "character list -> Equipped Memory Fragments", 4, "h",
     _list_to_panel_gap("Equipped Memory Fragments")),
    # Four more pairs of panels sitting side by side. The rule's other
    # thirty-odd marker sites are pads on borderless containers with
    # nothing painted at either end; these draw an edge each.
    ("Optimizer", "Important Settings -> Have at least", 4, "h",
     _panel_gap("Important Settings",
                "Have at least this much of a stat", "h")),
    ("Combatants", "Character -> Partner", 4, "h",
     _panel_gap("Character", "Partner", "h")),
    ("Gear Score", "How Gear Score Works -> Stat Weight Configuration", 4, "h",
     _panel_gap("How Gear Score Works", "Stat Weight Configuration", "h")),
    ("Capture", "Requirements -> Upgrade Log Settings", 4, "h",
     _panel_gap("Requirements", "Upgrade Log Settings", "h")),
]

def _panel_over_label(panel, prefix):
    """Resolver: a panel's painted bottom -> the ink of a label below it.

    The label is found by the words on it, like a panel by its title.
    `prefix` has to be the part that never changes -- this one's text is
    rewritten with the active preset's name.
    """
    def resolve(cap, app):
        label = sa.find_descendant_text(sa.current_tab_widget(app), prefix)
        if label is None:
            return None, f"no element whose text starts {prefix!r}"
        return sa.vertical_gap(cap, _panel(app, panel), label)
    return resolve


def _label_over_panel(prefix, panel, bold14=False):
    """Resolver: a label's ink -> the title of the panel below it.

    The mirror of `_panel_over_label`, and the rule reaches both ways: a
    tab heading standing over the first panel on its tab is the same
    kind of gap seen from the other side.

    `bold14` says the label is a 14pt heading, whose descenders reach
    deeper than body text's. Every site is one today; the argument is
    there rather than assumed because the resolver is named for labels
    in general.

    The string is read off the widget rather than passed in, because two
    of these are rewritten while the app runs.
    """
    def resolve(cap, app):
        label = sa.find_descendant_text(sa.current_tab_widget(app), prefix)
        if label is None:
            return None, f"no element whose text starts {prefix!r}"
        return restate_from_reference(
            *sa.vertical_gap(cap, label, _panel(app, panel)),
            ink_below_baseline(label.cget("text"), bold14))
    return resolve


def _button_over_panel(text, panel):
    """Resolver: a button's bottom -> the title of the panel below it.

    For the two tabs whose panels are not stacked directly: a row of
    buttons sits between them, so the nearest thing above the lower
    panel's title is a button border rather than another panel.

    The button is taken rather than the frame that holds it. Both rows
    carry something taller beside the buttons -- Capture's a wrapping
    checkbox label -- and the rule is read off the buttons.

    No correction: a button's bottom edge is a border, not a baseline.
    """
    def resolve(cap, app):
        button = sa.find_descendant_text(sa.current_tab_widget(app), text)
        if button is None:
            return None, f"no button reading {text!r}"
        return sa.vertical_gap(cap, button, _panel(app, panel))
    return resolve


def _user_info_to_list():
    """Resolver: the Combatants user line's ink -> the list beneath it.

    The list rather than a panel, because this column has none: the
    Treeview and its scrollbar sit straight in the column, and the
    scrollbar is what reaches furthest, so the frame holding both is the
    reference (as in `_list_to_panel_gap`).

    The label is taken off the tab instead of found by its words, the
    only entry that does. Its text is one of three strings depending on
    whether a snapshot is loaded and whether that snapshot has a
    nickname, so any prefix stable enough to find it is short enough to
    find something else -- and it is already stored on the tab, so
    reaching for it costs nothing the convention exists to avoid.
    """
    def resolve(cap, app):
        label = app.heroes_tab_instance.user_info_label
        tree = sa.find_descendant_class(sa.current_tab_widget(app), "Treeview")
        if tree is None:
            return None, "no Treeview on this tab"
        return restate_from_reference(
            *sa.vertical_gap(cap, label, tree.master),
            ink_below_baseline(label.cget("text")))
    return resolve


def _dropdown_over_panel(prefix, panel):
    """Resolver: the dropdown under a caption -> the panel below it.

    The caption is found by its words and the field by class among its
    siblings, the same pair `_caption_to_field` uses. No correction: a
    dropdown's bottom edge is its border, not a baseline.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        label = sa.find_descendant_text(tab, prefix)
        if label is None:
            return None, f"no caption starting {prefix!r}"
        field = sa.find_descendant_class(label.master, "TCombobox")
        if field is None:
            return None, "no dropdown under that caption"
        return sa.vertical_gap(cap, field, _panel(app, panel))
    return resolve


# (tab, name, target, hand reading, resolver) for a panel with text
# across the gap from it. Two stacked panels are one of these: what sits
# across the gap is the lower panel's TITLE, not its border, and the
# nearer element decides which rule applies.
#
# The rule runs BOTH ways and one number serves both: a panel over a
# title, and a heading or header control over a panel. The two shapes
# were built 7-9 and 11-14 respectively, which is why the ruling was
# worth taking before any of them moved.
#
# The hand column is empty because every reading it held has been
# nudged past; see `TrackedGap.hand` for why one does not outlive the
# build it was taken in.
PANEL_OVER_TEXT_ENTRIES = [
    ("Capture", "Status -> Server Region title", 10, None,
     _panel_gap("Status", "Server Region", "v")),
    ("Memory Fragments", "Slots -> active preset label", 10, None,
     _panel_over_label("Slots", "Preset:")),

    # A panel above, the next panel's title below.
    ("Optimizer", "Important Settings -> Set Configuration title", 10, None,
     _panel_gap("Important Settings", "Set Configuration", "v")),
    # Results' title is a labelwidget, so there is no LabelFrame text to
    # find it by -- the label itself is what the gap ends at.
    ("Optimizer", "Exclude Combatant's MFs -> Results title", 10, None,
     _panel_over_label("Exclude Combatant's MFs", "Results")),
    ("Combatants", "Character -> Equipped Memory Fragments title", 10, None,
     _panel_gap("Character", "Equipped Memory Fragments", "v")),

    # A button row, then a panel title. Neither of these two pairs is
    # stacked: Capture puts its capture buttons between Server Region
    # and Requirements, and Setup puts Check Status between the top row
    # and the instructions. Measuring panel to panel here skips the row
    # entirely and reports the whole distance across it.
    ("Capture", "capture buttons -> Requirements title", 10, None,
     _button_over_panel("Start Capture", "Requirements")),
    ("Setup", "Setup buttons -> Setup Instructions title", 10, None,
     _button_over_panel("Check Status", "Setup Instructions")),

    # BOTH columns of the Capture tab's top grid, against the same
    # title below them. Requirements is the one the rule is read off:
    # it ends the left column, which is where the eye measures. The
    # Upgrade Log Settings row is what catches the two columns falling
    # out of level -- its panel grows with the number of preset rows and
    # is meant to sit flush with Requirements' bottom until it has
    # enough of them to reach past it. Two entries at one target rather
    # than a rule about alignment: when both read the same number the
    # columns are level, and when they do not, the difference IS the
    # misalignment.
    ("Capture", "Requirements -> Capture Log title", 10, None,
     _panel_gap("Requirements", "Capture Log", "v")),
    ("Capture", "Upgrade Log Settings -> Capture Log title", 10, None,
     _panel_gap("Upgrade Log Settings", "Capture Log", "v")),

    # Text above, a panel below. The three tab headings differ only in
    # how much container padding stands under them -- Gear Score and
    # Capture spend 4px and read 12, Setup spends 6 and reads 14.
    #
    # These three are what measured `DESCENDER_DEPTH_14_BOLD`. Two of
    # them carry a `p` and the third carries no descender at all, so
    # reading all three against the eye isolates the depth from
    # everything else in the gap.
    ("Gear Score", "Gear Score Calculation -> How Gear Score Works title",
     10, None,
     _label_over_panel("Gear Score Calculation", "How Gear Score Works",
                       bold14=True)),
    ("Capture", "Data Capture -> Status title", 10, None,
     _label_over_panel("Data Capture", "Status", bold14=True)),
    ("Setup", "First-Time Setup -> Setup Status title", 10, None,
     _label_over_panel("First-Time Setup", "Setup Status", bold14=True)),

    # The Combatants header band, one entry per column. Both read 11,
    # from two unrelated constructions -- the left column's label is a
    # single line over a list, the right column's is the second row of a
    # control group over a panel.
    ("Combatants", "user info -> character list", 10, None,
     _user_info_to_list()),
    ("Combatants", "preset dropdown -> Character title", 10, None,
     _dropdown_over_panel("Assign preset to", "Character")),
]

def _heading_to_subtitle(heading, subtitle):
    """Resolver: a tab heading's ink -> the subtitle's ink beside it.

    Both by the words on them. The heading is 14pt and the subtitle 9pt,
    and they sit on one line bottom-aligned, so this measures the gap
    `make_tab_header` exists to keep identical across the three tabs
    that have one.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        a = sa.find_descendant_text(tab, heading)
        b = sa.find_descendant_text(tab, subtitle)
        if a is None:
            return None, f"no heading starting {heading!r}"
        if b is None:
            return None, f"no subtitle starting {subtitle!r}"
        return sa.horizontal_gap(cap, a, b)
    return resolve


def _status_subtext_baseline(status, subtext, status_drop):
    """Resolver: a Segoe UI 11 status line against the hint beside it.

    The same question as `_heading_subtitle_baseline` for a pair that is
    not a tab header: `header subtext` covers any subtext sharing a
    line with the text it belongs to, and the Capture tab's Status panel
    is the other kind.

    `status_drop` is passed in because the larger line is Segoe UI 11,
    which `ink_below_baseline` has no branch for -- it knows 9 and 14
    bold. The note keeps carrying the raw ink bottoms: they are what
    established the depth, and they are what would show it moving.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        a = sa.find_descendant_text(tab, status)
        b = sa.find_descendant_text(tab, subtext)
        if a is None:
            return None, f"no status line starting {status!r}"
        if b is None:
            return None, f"no subtext starting {subtext!r}"
        top = sa.painted_extent_v(cap, sa.box_of(a), cap.background)
        bottom = sa.painted_extent_v(cap, sa.box_of(b), cap.background)
        if top is None or bottom is None:
            return None, "status or subtext painted nothing"
        sub_drop = ink_below_baseline(b.cget("text"))
        note = (f"ink {top[1]}/{bottom[1]}, drop {status_drop}/{sub_drop} "
                f"(the first is STATED, not measured)")
        return ((bottom[1] - sub_drop) - (top[1] - status_drop)), note
    return resolve


def _heading_subtitle_baseline(heading, subtitle):
    """Resolver: how far the subtitle's baseline sits off the heading's.

    `header subtext` is the one rule that is not a distance. It says the
    subtitle sits ON the heading's line, so what it asks for is 0 and
    what has to be measured is an OFFSET rather than a gap.

    Baselines, not ink bottoms. The two strings are different sizes and
    hold different glyphs, so their ink stops at different depths even
    when they sit on the same line -- the heading here has no descender
    and every subtitle does. Each ink bottom is lifted by its own string's
    descender depth to recover the baseline, the same correction
    `restate_from_reference` makes horizontally.

    NEGATIVE means the subtitle rides above the heading's line.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        a = sa.find_descendant_text(tab, heading)
        b = sa.find_descendant_text(tab, subtitle)
        if a is None:
            return None, f"no heading starting {heading!r}"
        if b is None:
            return None, f"no subtitle starting {subtitle!r}"
        top = sa.painted_extent_v(cap, sa.box_of(a), cap.background)
        bottom = sa.painted_extent_v(cap, sa.box_of(b), cap.background)
        if top is None or bottom is None:
            return None, "heading or subtitle painted nothing"
        head_drop = ink_below_baseline(a.cget("text"), bold14=True)
        sub_drop = ink_below_baseline(b.cget("text"))
        head_base = top[1] - head_drop
        sub_base = bottom[1] - sub_drop
        # The descender depths are the only MODELLED numbers here; the
        # ink bottoms are measured. So when this row disagrees with the
        # eye, the disagreement is in one of the two drops, and the note
        # is what says which.
        note = (f"ink {top[1]}/{bottom[1]}, drop {head_drop}/{sub_drop}, "
                f"baseline {head_base}/{sub_base}")
        return sub_base - head_base, note
    return resolve


def _tab_list_to_first_element(heading=None):
    """Resolver: the tab strip's bottom -> the first ink on the tab.

    The strip has no widget of its own, so the reference is the tab
    frame's box top, which abuts it: `Flush.TNotebook` removed clam's
    2px client inset, so there is nothing between the two.

    `heading` names the label the gap ends at, either as a string to
    find by or as a callable given the app. Where it is None the tab's
    first element is not text -- a panel's border, a list -- and the
    scan takes whatever paints first across the whole width.

    **Where it IS text, the scan is narrowed to that label's FIRST
    GLYPH.** The rule measures to the capitals, and a heading's first
    character is always one; anything later in the string may be an
    ascender standing above them, which a full-width scan would find
    instead. Measuring the first glyph puts the reading on the cap
    height directly, so no correction is modelled and no table of
    ascender classes has to stay right. It also frees the reading from
    the string: the Combatants heading carries whichever combatant is
    selected, and every one of those starts on a capital too.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        box = sa.box_of(tab)
        if heading is None:
            extent = sa.painted_extent_v(cap, box)
            if extent is None:
                return None, "nothing painted on this tab"
            gap = sa.gap_between(box.top - 1, extent[0])
            if gap == 0:
                # `painted_extent_v` scans EVERY column of a row, so one
                # stray pixel anywhere across the window's width puts the
                # first painted row at the tab's own top. Sampling a
                # single column reported "bg, counted as empty" and
                # explained nothing; this finds where the ink actually is.
                return gap, (f"row {box.top}: "
                             f"{sa._first_painted_x(cap, box, box.top)}")
            return gap, ""

        label = (heading(app) if callable(heading)
                 else sa.find_descendant_text(tab, heading))
        if label is None:
            return None, f"no heading starting {heading!r}"
        lbox = sa.box_of(label)
        ink = sa.painted_extent_h(cap, lbox, cap.background)
        if ink is None:
            return None, "the heading painted nothing"
        text = label.cget("text")
        if not text:
            return None, "the heading has no text"
        advance = tkfont.Font(font=label.cget("font")).measure(text[0])
        first = sa.Box(left=ink[0], top=lbox.top,
                       right=min(ink[0] + advance - 1, lbox.right),
                       bottom=lbox.bottom)
        extent = sa.painted_extent_v(cap, first, cap.background)
        if extent is None:
            return None, f"the first glyph of {text!r} painted nothing"
        return sa.gap_between(box.top - 1, extent[0]), ""
    return resolve


# The rule has nine marker sites and had no entry, which is how Setup
# came to sit a pixel below the other two headers with nothing
# reporting it.
#
# (tab, the string the gap is measured to, is it 14 bold). The string is
# there for the ascender class above; None where the first thing painted
# on the tab is not text.
#
# (tab, the heading the gap ends at). A string is found by its words; a
# callable is handed the app. None where the tab's first element is not
# text at all, and the scan takes the whole width.
#
# COMBATANTS is found by ATTRIBUTE rather than by words, because its
# heading carries whichever combatant is selected. The reading does not
# depend on which -- it is taken from the first glyph, and every name
# starts on a capital -- but LOCATING the label by a string it only
# holds while nothing is selected would.
TAB_LIST_TARGET = 6
TAB_LIST_TABS = [
    ("Optimizer", None),
    ("Memory Fragments", None),
    ("Combatants", lambda app: app.heroes_tab_instance.hero_detail_name),
    ("Gear Score", "Gear Score Calculation"),
    ("Capture", "Data Capture"),
    ("Setup", "First-Time Setup"),
]


def _tab_list_target(tab: str) -> int:
    """One number for every tab now: the reading is dropped to the
    capitals before it gets here, so an ascender in the heading no
    longer changes what the gap should be.

    Still a function because `checks/check_spacing_registry.py` compares
    against it, and a rule whose target stops being uniform would come
    back through here.
    """
    return TAB_LIST_TARGET

# (tab, heading, subtitle) for every tab whose header `make_tab_header`
# builds. Registered so the helper's one set of numbers is measured
# rather than trusted -- three call sites had drifted apart before it,
# and nothing would have reported that.
TAB_HEADERS = [
    ("Capture", "Data Capture", "Capture game data"),
    ("Gear Score", "Gear Score Calculation", "Configure how gear scores"),
    ("Setup", "First-Time Setup", "Complete these steps"),
]

def _panel_buttons(app, title):
    frame = _panel(app, title)
    return frame, sa.find_descendants_class(frame, "TButton", "Button")


# The widget classes the row rules count. Checkbuttons are matched by
# both spellings because a panel that has not been through
# `make_checkbox` yet would still register as the ttk one -- a check
# enforces the helper, and this outlives it being briefly wrong.
CHECKBOX_CLASSES = ("Checkbutton", "TCheckbutton")
SPINBOX_CLASSES = ("Spinbox", "TSpinbox")
ENTRY_CLASSES = ("Entry", "TEntry")
TREE_CLASSES = ("Treeview",)

# Prefixes that locate a widget with no other handle on it. Kept here
# rather than inline because each is a fragment of a sentence the tab
# owns: if one is reworded the entry stops finding its widget, and the
# audit reports that as an error rather than as a distance.
OPTIMIZER_HELP_PREFIX = "The Optimizer finds the six"
DEF_CAPTION = "What percent of damage scales off DEF?"
SHIELD_CAPTION = "How much value should be given"
FORCE_CAPTION = "Force HP/Ego on a Slot:"


def _controls_beyond(cap, frame, classes, edge, side):
    """The nearest painted edge of `classes` on one side of `edge`.

    `side` is "below" or "above". Controls on the WRONG side are
    dropped rather than min'd over, which is what lets one explanation
    label be measured against the spinboxes above it and the list below
    it without either resolver naming a widget.
    """
    found = []
    for w in sa.find_descendants_class(frame, *classes):
        extent = sa.painted_extent_v(cap, sa.box_of(w))
        if extent is None:
            continue
        if side == "below" and extent[0] > edge:
            found.append(extent[0])
        elif side == "above" and extent[1] < edge:
            found.append(extent[1])
    if not found:
        return None
    return min(found) if side == "below" else max(found)


def _label_over_controls(panel, prefix, *classes):
    """Resolver: an explanation label's ink -> the controls beneath it.

    The label is found by its words and the controls by class, taking
    the topmost that starts below the label -- so a panel with controls
    on both sides of its explanation measures the right ones.
    """
    def resolve(cap, app):
        frame = _panel(app, panel)
        label = sa.find_descendant_text(frame, prefix)
        if label is None:
            return None, f"no label starting {prefix!r} in {panel!r}"
        ink = sa.painted_extent_v(cap, sa.box_of(label))
        if ink is None:
            return None, "label painted nothing"
        top = _controls_beyond(cap, frame, classes, ink[1], "below")
        if top is None:
            return None, f"no {'/'.join(classes)} below that label"
        return restate_from_reference(
            sa.gap_between(ink[1], top), "",
            ink_below_baseline(label.cget("text")))
    return resolve


def _controls_over_label(panel, prefix, *classes):
    """Resolver: the controls above an explanation label -> its ink.

    The mirror of `_label_over_controls`. No correction: the gap ends at
    the TOP of the text, which at Segoe UI 9 is the cap height the rule
    names.
    """
    def resolve(cap, app):
        frame = _panel(app, panel)
        label = sa.find_descendant_text(frame, prefix)
        if label is None:
            return None, f"no label starting {prefix!r} in {panel!r}"
        ink = sa.painted_extent_v(cap, sa.box_of(label))
        if ink is None:
            return None, "label painted nothing"
        bottom = _controls_beyond(cap, frame, classes, ink[0], "above")
        if bottom is None:
            return None, f"no {'/'.join(classes)} above that label"
        return sa.gap_between(bottom, ink[0]), ""
    return resolve


def _neighbour_gaps(cap, frame, classes):
    """The horizontal gap at each neighbour position, taken as the
    SMALLEST any row shows there.

    Controls are grouped into rows by their painted top, and each row is
    read left to right, so a reflowed block and a grid are handled the
    same way -- neither is asked for a column number it may not have.

    The smallest is the one the rule means. A column sizes to its widest
    member, so every other row in it shows a gap padded out by however
    much shorter its own label is; the widest member is the only one
    whose gap is the distance that was set.
    """
    found = []
    # DIRECT children only. Searching the subtree finds the frames a cell
    # is built out of as well as the cells themselves, and one stray
    # packed widget among them is enough to make a gridded block look
    # ungridded and send it down the wrong branch below.
    for w in [c for c in sa.find_descendants_class(frame, *classes)
              if c.master is frame]:
        box = sa.box_of(w)
        top = sa.painted_extent_v(cap, box)
        span = sa.painted_extent_h(cap, box)
        if top is None or span is None:
            continue
        info = w.grid_info()
        found.append((w, top[0], top[1], span,
                      info.get("column") if info else None))
    if not found:
        return []

    if all(col is not None for _w, _t, _b, _s, col in found):
        # Gridded: a COLUMN is the unit, and its span is its widest
        # member's. Reading row by row instead would miss the widest
        # member of a column whose own row is short -- Main Stats has
        # four columns in its first row and two in its second, so the
        # widest thing in column 2 has nothing to its right on its own
        # line and never gets measured.
        cols = {}
        for _w, _top, _bottom, span, col in found:
            edge = cols.setdefault(col, [span[0], span[1]])
            edge[0] = min(edge[0], span[0])
            edge[1] = max(edge[1], span[1])
        ordered = [cols[c] for c in sorted(cols)]
        return [sa.gap_between(a[1], b[0])
                for a, b in zip(ordered, ordered[1:])]

    # Packed or placed: there are no columns to group by, so each row is
    # read left to right and the smallest gap at each position wins.
    #
    # A row is a set of controls whose painted heights OVERLAP, not a set
    # sharing a top edge. Different controls start their ink at different
    # heights -- a label at its cap, a spinbox at its border -- so keying
    # on the top edge splits one visual line of alternating labels and
    # spinboxes into two rows, and then measures label to label straight
    # across the spinbox between them.
    rows = []
    for _w, top, bottom, span, _col in sorted(found, key=lambda f: f[1]):
        for row in rows:
            if top <= row[1] and bottom >= row[0]:
                row[0] = min(row[0], top)
                row[1] = max(row[1], bottom)
                row[2].append(span)
                break
        else:
            rows.append([top, bottom, [span]])
    at = {}
    for _top, _bottom, spans in rows:
        spans.sort()
        for i, (a, b) in enumerate(zip(spans, spans[1:])):
            gap = sa.gap_between(a[1], b[0])
            at[i] = gap if i not in at else min(at[i], gap)
    return [at[i] for i in sorted(at)]


def _pair_gap(container, classes, index=None):
    """Resolver: the gap between two controls sitting side by side.

    `container` is a LOCATOR, not a panel title, because a panel can
    hold more than one block of the same control: Upgrade Log Settings
    has its four mismatch filters and forty preset checkboxes, and a
    panel-wide reading would report whichever block is tighter.

    `index` picks a neighbour position, counting from the left, for a
    grid whose columns are set apart by different distances. Without one
    the smallest gap in the container is reported, which is what a row
    of equally-spaced controls has exactly one of, and what a reflowing
    block promises as its minimum.
    """
    def resolve(cap, app):
        gaps = _neighbour_gaps(cap, container(app), classes)
        if not gaps:
            return None, f"no two {'/'.join(classes)} share a row"
        if index is None:
            return min(gaps), ""
        if index >= len(gaps):
            return None, f"only {len(gaps)} neighbour gaps, wanted #{index}"
        return gaps[index], ""
    return resolve


def _panel_at(title):
    """Locator: a panel by its visible title, for the resolvers that
    take a container rather than a title."""
    def find(app):
        return _panel(app, title)
    return find


def _block_in(panel, classes):
    """Locator: the frame a panel's block of controls actually sits in.

    Some panels hold their block directly and some put it in an inner
    frame; taking the first control's parent finds it either way,
    without the entry having to know which. A panel with two blocks
    would give the first, so it is only for panels with one.
    """
    def find(app):
        frame = _panel(app, panel)
        found = sa.find_descendants_class(frame, *classes)
        if not found:
            raise LookupError(f"no {'/'.join(classes)} in {panel!r}")
        return found[0].master
    return find


def _tab_attr(instance, attr):
    """Locator: a frame the tab already stores on itself.

    The convention is to find things by their words, and these two
    cannot be: the Sets grid is labelled with set names and the Set
    Configuration grid with them too, both of which come from the data.
    Neither frame is being stored FOR the audit -- the tabs rebuild
    their contents and kept the handle already.
    """
    def find(app):
        return getattr(getattr(app, instance), attr)
    return find


LABEL_CLASSES = ("TLabel", "Label")
SCALE_CLASSES = ("TScale",)

# Cells of a grid, for the two panels that wrap each label-and-control
# pair in a frame of its own. A frame paints nothing itself, so its
# painted extent is its children's -- which is exactly the pair's.
CELL_CLASSES = ("TFrame",)


FILTER_CHECKBOX = "Don't show presets on ATK/DEF"

# (tab, name, target, hand reading, container locator, classes, index)
# for two label-and-control pairs side by side.
PAIR_GAP_ENTRIES = [
    ("Optimizer", "Force HP/Ego checkboxes", 8, None,
     lambda app: _group_of(FORCE_CAPTION)(app), CHECKBOX_CLASSES, None),
    # Variable by construction: the row reflows to the panel's width, so
    # every gap but the smallest is slack. The smallest is the one the
    # reflow is told to keep, and the only one worth a target.
    ("Optimizer", "Exclude checkboxes", 8, None,
     _block_in("Exclude Combatant's MFs", CHECKBOX_CLASSES),
     CHECKBOX_CLASSES, None),
    # The grid frame, not the panel: the panel also holds the row of
    # unknown main stats, which is gridded from column 0 of its own
    # frame and would merge into these columns.
    ("Memory Fragments", "Main Stats columns 1-2", 8, None,
     lambda app: _group_of("ATK%")(app), CHECKBOX_CLASSES, 0),
    ("Memory Fragments", "Main Stats columns 2-3", 8, None,
     lambda app: _group_of("ATK%")(app), CHECKBOX_CLASSES, 1),
    ("Memory Fragments", "Main Stats columns 3-4", 8, None,
     lambda app: _group_of("ATK%")(app), CHECKBOX_CLASSES, 2),
    # The mismatch filters only, NOT the preset checklist above them --
    # that is the other block of checkboxes in this panel and it sits
    # tighter, so a panel-wide reading would report it instead.
    ("Capture", "log filter checkboxes", 8, None,
     lambda app: _group_of(FILTER_CHECKBOX)(app), CHECKBOX_CLASSES, None),
    # Slots had no column entry where Main Stats beside it had three.
    ("Memory Fragments", "Slots checkboxes", 8, None,
     _block_in("Slots", CHECKBOX_CLASSES), CHECKBOX_CLASSES, None),

    # The rule's other half: pairs of UNLIKE controls, where one class
    # list cannot describe both ends.
    #
    # Two of them wrap each pair in a frame, so the cells are the units
    # and the gap between grid columns is the gap between pairs.
    ("Optimizer", "Set Configuration cells", 8, None,
     _tab_attr("optimizer_tab_instance", "set_grid_frame"),
     CELL_CLASSES, 0),
    ("Gear Score", "weight columns", 8, None,
     lambda app: _group_of("ATK Flat")(app).master, CELL_CLASSES, 0),

    # The other two pack or grid their labels and controls side by side
    # with nothing wrapping a pair, so the gaps alternate: label to its
    # own control, then control to the NEXT label. The odd positions are
    # this rule's; the even ones belong to `label ↔ its element`.
    ("Optimizer", "Set Config averages", 8, None,
     lambda app: _by_text("Avg Card DMG%")(app).master,
     LABEL_CLASSES + SPINBOX_CLASSES, 1),
    ("Memory Fragments", "Sets count -> next set", 8, None,
     _tab_attr("inventory_tab_instance", "inv_set_frame_inner"),
     CHECKBOX_CLASSES + LABEL_CLASSES, 1),
]


# (tab, name, target, hand reading, container locator, classes, index)
# for a label beside the element it names. Same resolver as the pair
# gaps -- a row read left to right -- with a different position picked
# out of it: the even ones here, the odd ones there.
#
# Every entry is the LONGEST label in its group. A row of labels shares
# one width, sized to the longest, so every shorter label simply has
# more room before its element and only the longest one's gap is the
# distance that was set.
LABEL_ELEMENT_ENTRIES = [
    # [Fracture] [====slider====] [nn%] -- the widest of the three damage
    # rows, and the one the shared label width is sized to.
    ("Optimizer", "Fracture -> its slider", 4, None,
     lambda app: _group_of("Fracture")(app),
     LABEL_CLASSES + SCALE_CLASSES, 0),
    # A slider's PERCENT READOUT is deliberately absent, on all four
    # rows. The readout is a fixed-width label with `anchor=tk.E`, so a
    # short value leaves its slack on the LEFT -- which is the side the
    # rule measures. `0%` is 16px of ink and `100%` is 28, and the gap
    # moves by exactly that 12 as the slider travels. There is no
    # distance there to have a target for; the space is slack, the way
    # the Requirements panel's right edge is.
    #
    # [ATK] [====slider====] [DEF] [nn%] -- four elements, so DEF is the
    # SECOND gap, not the third. The third is a readout.
    ("Optimizer", "ATK -> its slider", 4, None,
     lambda app: _sibling_before(_by_text(SHIELD_CAPTION))(app),
     LABEL_CLASSES + SCALE_CLASSES, 0),
    ("Optimizer", "slider -> DEF", 4, None,
     lambda app: _sibling_before(_by_text(SHIELD_CAPTION))(app),
     LABEL_CLASSES + SCALE_CLASSES, 1),
    ("Optimizer", "Max Flex Slots -> its spinbox", 4, None,
     lambda app: _by_text("Max Flex Slots")(app).master,
     LABEL_CLASSES + SPINBOX_CLASSES, 0),
    ("Optimizer", "Force HP/Ego -> its checkboxes", 4, None,
     lambda app: _group_of(FORCE_CAPTION)(app),
     LABEL_CLASSES + CHECKBOX_CLASSES, 0),
    # The Optimizer toolbar's status cluster: two rows, each a caption
    # beside the control it names.
    ("Optimizer", "Ignore MFs below level -> its spinbox", 4, None,
     lambda app: _by_text("Ignore MFs below level:")(app).master,
     LABEL_CLASSES + SPINBOX_CLASSES, 0),
    ("Optimizer", "Ignore off-Element MFs -> its checkbox", 4, None,
     lambda app: _by_text("Ignore off-Element MFs")(app).master,
     LABEL_CLASSES + CHECKBOX_CLASSES, 0),

    ("Memory Fragments", "Sets set -> its count", 4, None,
     _tab_attr("inventory_tab_instance", "inv_set_frame_inner"),
     CHECKBOX_CLASSES + LABEL_CLASSES, 0),
    # The first of the three Restore Defaults rows. One is enough: the
    # three are built from one loop with one pad, so a second entry would
    # report the same lever twice.
    ("Setup", "Restore Defaults button -> its explanation", 4, None,
     lambda app: _by_text("Presets")(app).master,
     ("TButton", "Button") + LABEL_CLASSES, 0),
    # The first of the three averages. Its pad is shared by all three,
    # so one entry reports the lever; the gap BETWEEN the pairs is
    # `Set Config averages` under the other rule.
    ("Optimizer", "Avg Card DMG% -> its spinbox", 4, None,
     lambda app: _by_text("Avg Card DMG%")(app).master,
     LABEL_CLASSES + SPINBOX_CLASSES, 0),
]

# The same rule, measured with every percent slider at 100 so the
# readouts are as wide as they get. See `_max_readouts` for why the gap
# is not a distance at any other value.
#
# (tab, name, target, hand reading, container locator, classes, index)
READOUT_ENTRIES = [
    ("Optimizer", "damage slider -> its readout", 4, None,
     lambda app: _group_of("Fracture")(app),
     LABEL_CLASSES + SCALE_CLASSES, 1),
    # [ATK] [====slider====] [DEF] [nn%] -- the readout is the third gap
    # on this row, where the other two have it second.
    ("Optimizer", "DEF -> its readout", 4, None,
     lambda app: _sibling_before(_by_text(SHIELD_CAPTION))(app),
     LABEL_CLASSES + SCALE_CLASSES, 2),
    ("Optimizer", "Shielding slider -> its readout", 4, None,
     lambda app: _sibling_before(_group_of(FORCE_CAPTION))(app),
     LABEL_CLASSES + SCALE_CLASSES, 0),
]


def _debug_neighbours(container, classes, index, limit=4):
    """Measures as usual and dumps the raw edges with it.

    A gap is a number; this says which SIDE of it the pixels are on. For
    each of the leftmost few controls it prints the widget's box and the
    ink inside it, so a distance that no padding reaches can be read as
    either "the left widget's ink stops short of its box" or "the right
    one's starts late" rather than inferred from the total.

    Wired onto one entry at a time through DEBUG_PAIR_GAPS, and taken
    off once it has answered. It closed the Sets count, whose seven
    pixels turned out to be six of label lead and one of checkbox.
    """
    inner = _pair_gap(container, classes, index)

    def describe(cap, w, note):
        box = sa.box_of(w)
        ink = sa.painted_extent_h(cap, box)
        try:
            text = str(w.cget("text"))[:20]
        except tk.TclError:
            text = ""
        if ink is None:
            print(f"    {note:<6} {w.winfo_class():12} {text:<20} painted nothing")
            return
        print(f"    {note:<6} {w.winfo_class():12} {text:<20} "
              f"box {box.left}..{box.right}  ink {ink[0]}..{ink[1]}  "
              f"lead {ink[0] - box.left}  trail {box.right - ink[1]}")

    def resolve(cap, app):
        frame = container(app)
        kids = [c for c in sa.find_descendants_class(frame, *classes)
                if c.master is frame]
        # The two widgets the reported gap actually runs between: the one
        # reaching furthest RIGHT in its column, and the one starting
        # furthest LEFT in the next. Printing the leftmost few instead
        # just lists one column's rows, which is what they share.
        cols = {}
        for w in kids:
            info = w.grid_info()
            if not info:
                continue
            ink = sa.painted_extent_h(cap, sa.box_of(w))
            if ink:
                cols.setdefault(info["column"], []).append((ink, w))
        order = sorted(cols)
        print(f"  [debug] {len(kids)} controls in {len(order)} columns")
        if index is not None and index + 1 < len(order):
            left = max(cols[order[index]], key=lambda p: p[0][1])[1]
            right = min(cols[order[index + 1]], key=lambda p: p[0][0])[1]
            describe(cap, left, "left")
            describe(cap, right, "right")
        return inner(cap, app)
    return resolve


def _indicator_gap(container, classes, debug=False):
    """Resolver: a checkbox's indicator -> its own label.

    Both live inside ONE widget, so there is no second widget to measure
    between and no pack or grid pad anywhere near them. What separates
    them is a stretch of background inside the box, and the painted runs
    across it are the only way to see it: the first run is the
    indicator, the second is the label's first glyph.

    Reported from the checkbox whose gap is SMALLEST, on the usual
    grounds -- every one of these is built by `make_checkbox`, so they
    should agree, and a spread would itself be the finding.

    `debug` prints the runs for the first few, which is what says
    whether the distance is Tk's own or something a padding reaches.
    """
    def resolve(cap, app):
        frame = container(app)
        boxes = sa.find_descendants_class(frame, *classes)
        if not boxes:
            return None, f"no {'/'.join(classes)} in that container"
        best = None
        shown = 0
        for w in boxes:
            runs = sa.painted_runs_h(cap, sa.box_of(w))
            if len(runs) < 2:
                continue
            gap = sa.gap_between(runs[0][1], runs[1][0])
            if debug and shown < 3:
                shown += 1
                try:
                    text = str(w.cget("text"))[:18]
                except tk.TclError:
                    text = ""
                box = sa.box_of(w)
                print(f"    {text:<18} box {box.left}..{box.right}  "
                      f"indicator {runs[0][0]}..{runs[0][1]}  "
                      f"then {runs[1][0]}..{runs[1][1]}  gap {gap}  "
                      f"({len(runs)} runs)")
            best = gap if best is None else min(best, gap)
        if best is None:
            return None, "no checkbox showed an indicator and a glyph"
        return best, ""
    return resolve


def _gap_within_cells(container, classes, index=0, column=None):
    """Resolver: the gap INSIDE a grid's cells, smallest across them.

    Where a panel wraps each label-and-control pair in a frame, the gap
    the rule names lives inside those frames and there is nothing at the
    grid level to measure. This reads each cell in turn and reports the
    tightest, which is the one whose label is longest -- the reference
    the rule names, the same as for a column.

    `column` narrows it to one grid column, for a panel whose columns
    are set apart by different distances and answer separately.
    """
    def resolve(cap, app):
        frame = container(app)
        gaps = []
        for cell in frame.winfo_children():
            info = cell.grid_info()
            if column is not None and (not info or info["column"] != column):
                continue
            found = _neighbour_gaps(cap, cell, classes)
            if len(found) > index:
                gaps.append(found[index])
        if not gaps:
            where = "" if column is None else f" in column {column}"
            return None, f"no cell{where} showed that pair"
        return min(gaps), ""
    return resolve


def _to_window_edge(locator):
    """Resolver: a widget's painted right edge -> the window's.

    The capture is the CLIENT area -- `winfo_rootx` plus `winfo_width`,
    with no title bar, border or shadow in it -- so the window edge is
    the first column past the image, and the gap is the background
    between the ink and that. Counted the same way as every other rule:
    the pixels BETWEEN the two, neither end included.

    Right edge only. Nothing in the app ends at the bottom of the
    window; the panel that looks like it does has another beneath it.
    """
    def resolve(cap, app):
        span = sa.painted_extent_h(cap, sa.box_of(locator(app)))
        if span is None:
            return None, "painted nothing"
        return sa.gap_between(span[1], cap.origin[0] + cap.image.size[0]), ""
    return resolve


def _by_text(prefix):
    """Locator: the widget whose words start with `prefix`."""
    def find(app):
        w = sa.find_descendant_text(sa.current_tab_widget(app), prefix)
        if w is None:
            raise LookupError(f"no element whose text starts {prefix!r}")
        return w
    return find


def _group_of(prefix):
    """Locator: the frame a caption is stacked inside.

    The toolbar's control groups are `Frame(caption over control)` and
    the Important Settings rows are `Frame(label, slider, readout)`;
    either way the frame is what the gap runs to, and the caption is the
    only part of it with words to find it by.
    """
    def find(app):
        return _by_text(prefix)(app).master
    return find


def _sibling_before(locator):
    """Locator: the widget packed immediately above the one `locator`
    finds.

    For the row above a caption, which has nothing on it to search for
    -- a slider row's words are its stat name, and those repeat
    elsewhere on the tab.

    Takes a locator rather than a prefix because the widget whose
    neighbour is wanted is not always the one with the words on it: a
    caption stacked in the panel is its own sibling, but a caption
    sharing a row with checkboxes is the FIRST child of that row, and it
    is the row that has a sibling above.
    """
    def find(app):
        w = locator(app)
        kids = w.master.winfo_children()
        i = kids.index(w)
        if i == 0:
            raise LookupError(f"{w} is first in its frame")
        return kids[i - 1]
    return find


def _of_class(locator, *classes):
    """Locator: the first widget of `classes` inside what `locator`
    finds.

    A config row's painted extent is not necessarily the element the
    rule names. The Important Settings rows put a name label and a
    percent readout either side of their slider, and the markers at
    those sites name the SLIDER as the pair's upper element -- so that
    is what the entry reaches for.

    Both read the same today: the slider is the lowest thing in each of
    those rows, measured. Naming it anyway is what stops the entry
    quietly changing meaning if a taller widget ever joins the row.
    """
    def find(app):
        w = locator(app)
        for cls in classes:
            found = sa.find_descendant_class(w, cls)
            if found is not None:
                return found
        raise LookupError(f"no {'/'.join(classes)} inside {w}")
    return find


def _gap(first, second, axis):
    """Resolver: the painted gap between two located widgets."""
    def resolve(cap, app):
        a, b = first(app), second(app)
        return (sa.horizontal_gap(cap, a, b) if axis == "h"
                else sa.vertical_gap(cap, a, b))
    return resolve


def _class_block_gap(panel, left_classes, right_classes):
    """Resolver: the rightmost of one class of control -> the leftmost
    of another, inside one panel.

    For a column of controls beside a column of buttons, where neither
    side is one widget and neither frame has any words on it.
    """
    def resolve(cap, app):
        frame = _panel(app, panel)
        edges = []
        for classes, pick in ((left_classes, max), (right_classes, min)):
            spans = [sa.painted_extent_h(cap, sa.box_of(w))
                     for w in sa.find_descendants_class(frame, *classes)]
            spans = [s for s in spans if s]
            if not spans:
                return None, f"nothing painted for {'/'.join(classes)}"
            edges.append(pick(s[1] if pick is max else s[0] for s in spans))
        return sa.gap_between(edges[0], edges[1]), ""
    return resolve


# (tab, name, target, hand reading, resolver) for the gaps between
# groups of tab-wide controls, and between the rows of a config panel.
#
# The two Important Settings captions read 3px wider than the checkbox
# row for the same padding, because what sits across the gap is text in
# one case and a checkbox indicator in the other, and an indicator
# paints nearer the top of its box than a capital does. So the same 12px
# target costs 4px of padding above a caption and 7px above the checkbox
# row -- a difference that looks like a mistake and is not.
CONTROL_GROUP_ENTRIES = [
    ("Optimizer", "Combatant group -> LVL group", 16, None,
     _gap(_group_of("Combatant:"), _group_of("Optimize for LVL:"), "h")),
    ("Optimizer", "LVL group -> Start", 16, None,
     _gap(_group_of("Optimize for LVL:"), _by_text("Start"), "h")),
    ("Optimizer", "Stop -> help text", 16, None,
     _gap(_by_text("Stop"), _by_text(OPTIMIZER_HELP_PREFIX), "h")),
    ("Gear Score", "stat grid -> button column", 16, None,
     _class_block_gap("Stat Weight Configuration",
                      SPINBOX_CLASSES, ("TButton", "Button"))),
]

# (tab, name, target, hand reading, resolver) for a button row against
# the panel edge above it. Both are `content frame -> content frame`:
# what sits across the gap is a border on one side and a button's own
# border on the other, with no text at either end.
BUTTON_ROW_ABOVE_ENTRIES = [
    ("Capture", "Server Region -> capture buttons", 4, None,
     _gap(_panel_at("Server Region"), _by_text("Start Capture"), "v")),
    ("Setup", "Setup Status -> Check Status row", 4, None,
     _gap(_panel_at("Setup Status"), _by_text("Check Status"), "v")),
]

# A checkbox's indicator against its own label. One entry, not one per
# panel: every checkbox in the app comes from `make_checkbox`, so they
# should all report the same distance, and a spread between panels would
# be the finding rather than a set of separate nudges. Dumping its runs
# while it answers whether the distance is Tk's own.
INDICATOR_ENTRIES = [
    ("Memory Fragments", "checkbox indicator -> its label", 5, None,
     _indicator_gap(_block_in("Slots", CHECKBOX_CLASSES),
                    CHECKBOX_CLASSES)),
]

# (tab, name, target, hand reading, resolver) for a label beside its
# control where the pair is wrapped in a cell of its own, so the gap is
# inside the cell and nothing at the grid level can see it.
CELL_LABEL_ENTRIES = [
    # The piece count is inside the checkbox now, so this measures the
    # checkbox's text to the set NAME beside it -- an ordinary gap with
    # an ordinary pad, where it used to be the indicator against a label
    # across 7px of reserved space nothing could reach.
    ("Optimizer", "Set Config checkbox -> its label", 4, None,
     _gap_within_cells(_tab_attr("optimizer_tab_instance", "set_grid_frame"),
                       CHECKBOX_CLASSES + LABEL_CLASSES)),
    # Two weight columns, each with its own distance, so each is read
    # alone rather than as the smallest of the two.
    #
    # Column 1 sits a pixel wide and is PARKED there, not fudged: both
    # columns take the same extra on top of their own longest label, so
    # the pixel is the difference between what `font.measure` reports for
    # "ATK Flat" and what it renders as. Closing it with a per-column
    # constant would tie a number to today's stat names, and the
    # antialiasing question may delete it -- see docs/ui_spacing.md.
    ("Gear Score", "weight column 1 label -> its spinbox", 4, None,
     _gap_within_cells(lambda app: _group_of("ATK Flat")(app).master,
                       LABEL_CLASSES + SPINBOX_CLASSES, column=0)),
    ("Gear Score", "weight column 2 label -> its spinbox", 4, None,
     _gap_within_cells(lambda app: _group_of("ATK Flat")(app).master,
                       LABEL_CLASSES + SPINBOX_CLASSES, column=1)),
]

# (tab, name, target, hand reading, resolver) for content that ends at
# the window's right edge.
WINDOW_EDGE_ENTRIES = [
    ("Optimizer", "status cluster -> window edge", 4, None,
     _to_window_edge(
         lambda app: app.optimizer_tab_instance.status_label.master)),
    ("Combatants", "Partner -> window edge", 4, None,
     _to_window_edge(_panel_at("Partner"))),
]

def _results_title_to_tree():
    """Resolver: the Results title's ink -> the results tree below it.

    This panel's title is a labelwidget rather than a `text=`, so there
    is no LabelFrame title to find it by and the label itself is the top
    of the gap. Going up two levels from the label reaches the panel,
    which is how the right tree is found without naming one of the three
    on this tab.
    """
    def resolve(cap, app):
        label = _by_text("Results")(app)
        tree = sa.find_descendant_class(label.master.master, "Treeview")
        if tree is None:
            return None, "no Treeview under the Results header"
        return restate_from_reference(
            *sa.vertical_gap(cap, label, tree),
            ink_below_baseline(label.cget("text")))
    return resolve


def _list_inset(panel, side):
    """Resolver: a panel's border -> the preset list inside it.

    The list is located by its Treeview's parent, which is the frame
    that holds the tree and its scrollbar -- the scrollbar is the
    rightmost painted thing, so measuring the tree alone would miss the
    right edge by its width.
    """
    def resolve(cap, app):
        frame = _panel(app, panel)
        tree = sa.find_descendant_class(frame, "Treeview")
        if tree is None:
            return None, f"no Treeview in {panel!r}"
        return sa.inset_from_frame_edge(cap, frame, tree.master, side)
    return resolve


# The preset list runs to its panel's edges. A zero nothing watches is
# exactly the kind that quietly regains a padding, so all three sides
# are tracked -- and the panel's own inset lives on its other children's
# padx, which the entries above measure in their own right.
PRESET_LIST_ENTRIES = [
    ("Gear Score", "preset list: left edge -> list", 0, None,
     _list_inset("Stat Weight Configuration", "left")),
    ("Gear Score", "preset list: right edge -> list", 0, None,
     _list_inset("Stat Weight Configuration", "right")),
]

# The same three sides, split because a table carries one axis.
PRESET_LIST_BOTTOM_ENTRIES = [
    ("Gear Score", "preset list: bottom edge -> list", 0, None,
     _list_inset("Stat Weight Configuration", "bottom")),
]


# The last two readings, one apiece for their rules.
RESULTS_TITLE_ENTRIES = [
    ("Optimizer", "Results title -> its tree", 5, None,
     _results_title_to_tree()),
]

# The three options checkboxes that sit OUTSIDE any panel, at the right
# of the Memory Fragments filter row. The last of them wraps onto a
# second line, so its box is taller than the other two -- the pitch is
# still read between painted rows, which is what the rule names.
OPTIONS_TRIO_ENTRIES = [
    ("Memory Fragments", "options trio: row pitch", 7, None,
     lambda cap, app: _row_pitch_in(
         lambda a: _group_of("Unequipped Only")(a),
         CHECKBOX_CLASSES)(cap, app)),
]

CONFIG_ROW_ENTRIES = [
    ("Optimizer", "Fracture row -> DEF caption", 12, None,
     _gap(_of_class(_sibling_before(_by_text(DEF_CAPTION)), "TScale"),
          _by_text(DEF_CAPTION), "v")),
    ("Optimizer", "ATK row -> Shielding caption", 12, None,
     _gap(_of_class(_sibling_before(_by_text(SHIELD_CAPTION)), "TScale"),
          _by_text(SHIELD_CAPTION), "v")),
    # The Force HP/Ego caption shares a row with its checkboxes, so the
    # ROW is what has a sibling above it and the row is also the lower
    # end: the gap runs to the checkbox indicators, which paint higher
    # than the caption's capitals.
    ("Optimizer", "Shielding row -> Force HP/Ego row", 12, None,
     _gap(_of_class(_sibling_before(_group_of(FORCE_CAPTION)), "TScale"),
          _group_of(FORCE_CAPTION), "v")),
]


# (tab, name, target, hand reading, source, resolver) for the prose that
# introduces a group of controls. The rule runs both ways -- the label
# sits above its controls everywhere except HAL and the Gear Score
# status line, which sit below theirs.
EXPLANATION_ENTRIES = [
    ("Optimizer", "HAL note -> the spinboxes above it", 8, None, "rule",
     _controls_over_label("Have at least this much of a stat",
                          "Input stats as you expect", *SPINBOX_CLASSES)),
    ("Optimizer", "set explanation -> the set rows", 8, None, "rule",
     _label_over_controls("Set Configuration",
                          "All selected Set and Flex", *CHECKBOX_CLASSES)),
    # Important Settings' three blocks, each a caption over the sliders
    # it explains. All three carried the marker and none was measured.
    ("Optimizer", "damage caption -> its sliders", 8, None, "rule",
     _label_over_controls("Important Settings",
                          "What percent of damage is Extra", *SCALE_CLASSES)),
    ("Optimizer", "DEF caption -> its slider", 8, None, "rule",
     _label_over_controls("Important Settings",
                          "What percent of damage scales off DEF",
                          *SCALE_CLASSES)),
    ("Optimizer", "Shielding caption -> its slider", 8, None, "rule",
     _label_over_controls("Important Settings", SHIELD_CAPTION,
                          *SCALE_CLASSES)),
    ("Gear Score", "weights caption -> the stat grid", 8, None, "rule",
     _label_over_controls("Stat Weight Configuration",
                          "Adjust weights for custom", *SPINBOX_CLASSES)),
    ("Gear Score", "Preset Name: -> its entry", 8, None, "rule",
     _label_over_controls("Stat Weight Configuration",
                          "Preset Name:", *ENTRY_CLASSES)),
    # One label, two gaps: the status line sits between the stat grid
    # and the preset list, so moving it trades one against the other.
    ("Gear Score", "stat grid -> Applied status", 8, None, "rule",
     _controls_over_label("Stat Weight Configuration",
                          "Applied ", *SPINBOX_CLASSES)),
    ("Gear Score", "Applied status -> preset list", 8, None, "rule",
     _label_over_controls("Stat Weight Configuration",
                          "Applied ", *TREE_CLASSES)),
    ("Capture", "presets caption -> the checklist", 8, None, "rule",
     _label_over_controls("Upgrade Log Settings",
                          "Assigned presets compared", *CHECKBOX_CLASSES)),
]


def _painted_rows(cap, frame, classes):
    """The painted (top, bottom) of each ROW of `classes` in a panel.

    Widgets are grouped by whether they overlap vertically, not by grid
    row: a row's members are laid out by several different calls in
    these panels, and a grid can leave its last row part-empty, so the
    pixels are the only thing that says which widgets sit level.
    """
    spans = []
    for widget in sa.find_descendants_class(frame, *classes):
        try:
            extent = sa.painted_extent_v(cap, sa.box_of(widget))
        except tk.TclError:
            continue
        if extent:
            spans.append(list(extent))
    spans.sort()
    rows = []
    for top, bottom in spans:
        if rows and top <= rows[-1][1]:
            rows[-1][1] = max(rows[-1][1], bottom)
        else:
            rows.append([top, bottom])
    return rows


def _row_gaps(cap, frame, classes):
    rows = _painted_rows(cap, frame, classes)
    return [sa.gap_between(rows[i][1], rows[i + 1][0])
            for i in range(len(rows) - 1)]


def _tally(gaps):
    """`0 x4, 1 x2` -- every distinct gap and how many pairs sit at it."""
    return ", ".join(f"{g} x{gaps.count(g)}"
                     for g in sorted(set(gaps)))


# Painted bands this close together on one line are the same word: a
# letter-space at these sizes is a pixel or two of background, where the
# narrowest gap any rule puts BETWEEN columns is four. Merging at this
# distance is what lets a column be indexed -- without it `10.0%` is
# three bands and `ATK` is one, and no fixed position means the same
# thing on two lines.
TEXT_COLUMN_MERGE = 2


def _inside_border(widget):
    """A Text's box, minus whatever it paints around its own content.

    An Equipped MF cell draws a RIDGE relief, so every row of its box
    holds painted pixels at the left and right borders -- a run scan
    over the whole box finds ONE run covering the cell and never sees
    the lines inside it. The insets are read off the widget rather than
    stated, so a cell that changes its border does not quietly take a
    resolver with it.
    """
    box = sa.box_of(widget)
    def opt(name):
        try:
            return int(widget.cget(name))
        except (tk.TclError, ValueError):
            return 0
    edge = opt("bd") + opt("highlightthickness")
    return sa.Box(left=box.left + edge + opt("padx"),
                  top=box.top + edge,
                  right=box.right - edge - opt("padx"),
                  bottom=box.bottom - edge)


def _text_columns(cap, box, fill):
    """The painted COLUMNS across one line, letters merged into words."""
    runs = sa.painted_runs_h(cap, box, fill)
    if not runs:
        return []
    columns = [list(runs[0])]
    for first, last in runs[1:]:
        if sa.gap_between(columns[-1][1], first) <= TEXT_COLUMN_MERGE:
            columns[-1][1] = last
        else:
            columns.append([first, last])
    return columns


def _text_column_gap(locator, needles, index=0, from_end=False,
                     fill="bg_light"):
    """Resolver: the SMALLEST gap at one column boundary of a Text.

    A Text's columns are TAB STOPS, so there is no widget on either side
    of the gap -- and its lines are not widgets either, so each line has
    to be found before its columns can be. `dlineinfo` turns a line into
    the band of rows it occupies, and the columns are read across that
    band.

    **Smallest across the lines, not one line's.** These value stops are
    RIGHT-aligned, so a short value starts further right and leaves a
    wider gap after the label -- the distance is only the one that was
    set on the row whose value is widest. Reading a single row reports
    whatever the selected combatant happens to have: a three-digit ATK
    read 10 where the rule asks 4, and a four-digit one would have read
    4. Same reasoning as `_neighbour_gaps` taking the smallest gap a
    column shows.

    `needles` find the lines by their words rather than by number, so a
    line inserted above them moves the reading instead of silently
    changing which row is read. **Include the TAB** where the words
    could occur in prose too: `ATK` alone first matches the
    `Bonus: ATK+39` line, whose painted bands are the words of a
    sentence and not columns at all.

    `from_end` counts the boundary from the RIGHT. A row with no left
    column -- the Element row emits both of the left pair's tabs and
    nothing between them -- has two bands where the others have four, so
    its right-hand pair is at a different index and only the same one
    counting backwards.
    """
    def resolve(cap, app):
        widget = locator(app)
        if widget is None:
            return None, "no text widget there"
        origin = sa.box_of(widget).top
        box = _inside_border(widget)
        readings = []
        for needle in needles:
            where = widget.search(needle, "1.0", tk.END)
            if not where:
                continue
            info = widget.dlineinfo(where)
            if info is None:
                continue
            top = origin + info[1]
            band = sa.Box(left=box.left, top=top,
                          right=box.right, bottom=top + info[3] - 1)
            columns = _text_columns(cap, band, {cap.palette[fill]})
            first = len(columns) - 2 - index if from_end else index
            if first < 0 or first + 1 >= len(columns):
                continue
            gap = sa.gap_between(columns[first][1], columns[first + 1][0])
            line = widget.get(f"{where} linestart", f"{where} lineend")
            readings.append((gap, line.strip(), len(columns)))
        if not readings:
            return None, f"no line with that column, of {list(needles)}"
        readings.sort()
        # Every row is reported, because which one is tightest is the
        # whole question: the rule's distance lives on the row with the
        # widest value, and the rest are that plus their own slack.
        #
        # The COLUMN COUNT goes with each, because the merge is a
        # judgement and a row that came out with more columns than its
        # neighbours has had one of its values split -- a decimal point
        # opening a wider gap than TEXT_COLUMN_MERGE allows for would do
        # it, and then the boundary counted from the end is inside the
        # value rather than before it.
        note = " | ".join(f"{g}[{n}c]: {line[:30]}" for g, line, n in readings)
        return readings[0][0], note
    return resolve


def _first_filled_text(title):
    """Locator: the first Text in a panel that HAS lines in it.

    The Equipped MF grid is six cells, and an unequipped slot renders
    the single word `Empty` -- content, but with no second row to
    measure to. So "has text in it" is not the test; "has two lines" is.
    Walking past those is also what makes the entry read the same
    whichever slots the selected combatant has filled.
    """
    def find(app):
        frame = _panel(app, title)
        for widget in sa.find_descendants_class(frame, "Text"):
            lines = [l for l in widget.get("1.0", "end-1c").splitlines()
                     if l.strip()]
            if len(lines) >= 2:
                return widget
        return None
    return find


def _text_line_pitch(locator, fill="bg_light"):
    """Resolver: the SMALLEST gap between painted LINES inside a Text.

    A Text's rows are not widgets, so `_row_pitch_in` cannot see them:
    there is nothing to group and nothing to take a box from. What
    separates one line from the next is the font's own leading plus
    whatever `spacing3` adds, and only the pixels say what the two come
    to together -- the lever is the added part alone.

    **Line by line, not one scan down the widget.** A run scan over the
    whole box finds ONE run wherever a line WRAPS: `spacing3` is the
    space after a logical line, and Tk puts none between the display
    lines a wrapped one occupies, so their ink touches row to row. An
    Equipped MF cell ends in a wrapped set description, which merged the
    whole cell into a single run -- six logical lines over a hundred and
    fifty rows, and no gap anywhere in them. `dlineinfo` gives each
    logical line its own band, and the gaps BETWEEN those bands are the
    pitch the rule means.

    Smallest for the same reason the widget version takes it: a division
    between blocks is always the widest gap, so it can never be mistaken
    for the pitch, while a group of rows sitting tighter than the rest
    is exactly what this has to report.
    """
    def resolve(cap, app):
        widget = locator(app)
        if widget is None:
            return None, "no text widget there"
        box = _inside_border(widget)
        origin = sa.box_of(widget).top
        colours = {cap.palette[fill]}
        edges = []
        count = int(widget.index("end-1c").split(".")[0])
        for n in range(1, count + 1):
            if not widget.get(f"{n}.0", f"{n}.end").strip():
                continue
            info = widget.dlineinfo(f"{n}.0")
            if info is None:
                continue
            top = origin + info[1]
            band = sa.Box(left=box.left, top=top,
                          right=box.right, bottom=top + info[3] - 1)
            extent = sa.painted_extent_v(cap, band, colours)
            if extent:
                edges.append(extent)
        if len(edges) < 2:
            return None, (f"{len(edges)} of {count} lines painted anything "
                          f"inside rows {box.top}-{box.bottom}")
        gaps = [sa.gap_between(a[1], b[0]) for a, b in zip(edges, edges[1:])]
        note = "" if len(set(gaps)) == 1 else f"gaps {_tally(gaps)}"
        return min(gaps), note
    return resolve


def _row_pitch(title, classes):
    """The pitch of a panel's rows, by the panel's visible title."""
    return _row_pitch_in(_panel_at(title), classes)


def _row_pitch_in(container, classes):
    """Resolver: the SMALLEST gap between a container's rows of `classes`.

    The smallest, not the most common. The pitch rule says every row
    sits at one distance, so the reading that matters is the one
    furthest from it -- and a division is always the widest gap, so it
    can never be mistaken for the pitch.

    It was the most common once. Three panels kept a whole group of rows
    4px tighter than the rest and passed anyway, the wrong rows being
    out-voted by the right ones.

    No glyph correction: a checkbox row's painted bottom is its
    INDICATOR and a spinbox row's is its border, so no descender in any
    label reaches either edge of these gaps.
    """
    def resolve(cap, app):
        gaps = _row_gaps(cap, container(app), classes)
        if not gaps:
            return None, "fewer than two rows of that kind there"
        common = min(gaps)
        # A panel whose rows do not all sit at one pitch is worth
        # saying so about. The value already reports the worst of them,
        # so the tally is what says how many rows are wrong rather than
        # just that one is -- `7 x6, 3 x2` is two stragglers, `3 x8` is
        # a panel nobody has touched.
        note = "" if len(set(gaps)) == 1 else f"gaps {_tally(gaps)}"
        return common, note
    return resolve


def _row_division(title, classes):
    """Resolver: the LARGEST gap between a panel's rows of `classes`.

    Which pair carries the division is data-driven -- the Sets grid
    divides where the four-piece sets end, and how many of those exist
    depends on the game -- so it is found by being the widest rather
    than by an index that would go stale.
    """
    def resolve(cap, app):
        gaps = _row_gaps(cap, _panel(app, title), classes)
        if len(gaps) < 2:
            return None, "no division: fewer than three rows"
        return max(gaps), ""
    return resolve


# (tab, panel, rule, classes, target).
ROW_PITCH_ENTRIES = [
    ("Memory Fragments", "Slots", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
    ("Memory Fragments", "Sets", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
    ("Capture", "Upgrade Log Settings", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
    # CHECKBOXES here, not the spinboxes beside them, per the standing
    # exception in docs/ui_spacing.md: only conditional sets carry a
    # spinbox, so consecutive ones can be rows apart and the column has
    # no pitch to measure. Read as spinboxes it came out `0 x5, 9 x1,
    # 42 x1` -- a vote, not a distance.
    ("Optimizer", "Set Configuration", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
    ("Gear Score", "Stat Weight Configuration", RULE_SPINBOX_PITCH,
     SPINBOX_CLASSES, 2),
    # The other spinbox grid. Its rows are packed where Gear Score's are
    # gridded, which is the reason to read both rather than assume one
    # stands for the other.
    ("Optimizer", "Have at least this much of a stat", RULE_SPINBOX_PITCH,
     SPINBOX_CLASSES, 2),
    # Important Settings' slider rows sit at 7, not the 12 their markers
    # claimed: adjacent slider rows are `checkbox/slider ↕ rows` like any
    # other non-tall pair, and the 12 belongs to the gaps that cross a
    # CAPTION, which are tracked separately as row-to-caption. The min is
    # the pitch and the tally shows those crossings as the divisions
    # they are.
    ("Optimizer", "Important Settings", RULE_CHECKBOX_PITCH,
     SCALE_CLASSES, 7),
    # Restore Defaults stacks three buttons, so its pitch is a
    # button-to-button gap read vertically.
    ("Setup", "Restore Defaults", RULE_BUTTON_GAP,
     ("TButton", "Button"), 4),
    # Main Stats had a row DIVISION entry and no row pitch, so the gap
    # between its ordinary rows went unread while the wide one between
    # its blocks was watched.
    ("Memory Fragments", "Main Stats", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
    # The exclude list places its rows itself, at `row * row_h`, rather
    # than letting a geometry manager space them -- so its pitch is the
    # one in this table that no padding value backs.
    ("Optimizer", "Exclude Combatant's MFs", RULE_CHECKBOX_PITCH,
     CHECKBOX_CLASSES, 7),
]

# The same rows, measured for their widest gap instead of their usual
# one. Separate because a panel can have both.
ROW_DIVISION_ENTRIES = [
    ("Optimizer", "Set Configuration", CHECKBOX_CLASSES),
    ("Memory Fragments", "Sets", CHECKBOX_CLASSES),
    ("Memory Fragments", "Main Stats", CHECKBOX_CLASSES),
]


def _checkbox_block_to_buttons(title):
    """Resolver: the lowest checkbox in a panel -> its All/None row.

    The block's bottom is the LOWEST painted checkbox, not the last one
    registered: these grids fill row by row, so the final column of the
    last row can be empty and the widget order says nothing about which
    sits deepest.
    """
    def resolve(cap, app):
        frame, buttons = _panel_buttons(app, title)
        boxes = sa.find_descendants_class(frame, *CHECKBOX_CLASSES)
        if not boxes or not buttons:
            return None, f"{len(boxes)} checkboxes and {len(buttons)} buttons"
        bottoms = [e[1] for e in
                   (sa.painted_extent_v(cap, sa.box_of(w)) for w in boxes)
                   if e]
        top = sa.painted_extent_v(cap, sa.box_of(buttons[0]))
        if not bottoms or top is None:
            return None, "checkbox block or button painted nothing"
        return sa.gap_between(max(bottoms), top[0]), ""
    return resolve


def _first_button_left_inset(title):
    """Resolver: a panel's left border -> its All button."""
    def resolve(cap, app):
        frame, buttons = _panel_buttons(app, title)
        if not buttons:
            return None, "no buttons in panel"
        return sa.inset_from_frame_edge(cap, frame, buttons[0], "left")
    return resolve


# Every panel `make_all_none_row` builds a row for. Both of the row's
# gaps are tracked: the helper holds one set of levers, but each panel's
# own padding differs, so the same lever renders a different inset in
# each and only measuring says which.
ALL_NONE_PANELS = [
    ("Memory Fragments", "Slots"),
    ("Memory Fragments", "Sets"),
    ("Memory Fragments", "Main Stats"),
    ("Optimizer", "Exclude Combatant's MFs"),
]

# The All/None rows, the only adjacent button pairs inside a panel.
BUTTON_ROW_PANELS = [
    ("Memory Fragments", "Slots"),
    ("Memory Fragments", "Sets"),
    ("Memory Fragments", "Main Stats"),
    ("Optimizer", "Exclude Combatant's MFs"),
]


# Tab label -> the panels on it that follow the standard two rules.
# Tab labels must match the notebook's tab text exactly; a mismatch is
# reported as "no tab" on the first run rather than failing silently.
PANELS = {
    "Memory Fragments": ["Slots", "Sets", "Main Stats"],
    "Combatants": ["Character", "Partner", "Equipped Memory Fragments"],
    "Optimizer": [
        "Important Settings",
        "Have at least this much of a stat",
        "Set Configuration",
        "Exclude Combatant's MFs",
        "Stats Comparison",
        "Selected Build",
    ],
    "Gear Score": ["How Gear Score Works", "Stat Weight Configuration"],
    "Capture": [
        "Status",
        "Server Region",
        "Requirements",
        "Capture Log",
        "Upgrade Log Settings",
    ],
    "Setup": ["Setup Status", "Restore Defaults", "Setup Instructions"],
}

# Panels whose left inset is NOT the border-edge rule.
LEFT_INSET_EXCEPTIONS = {
    # Confirmed by measurement as deliberate; the border-edge rule does
    # not apply to this panel's left edge at all, so registering it
    # would show a permanent red row and train the reader to ignore
    # them.
    "Status",
    # The three `Borderless` panels. Two reasons, both disqualifying.
    # There is no border, so the rule has no edge to measure from --
    # and a border scan does not merely fail here, it walks into the
    # content's own fill and saturates. And what fills them draws its
    # own inset by rules of its own: a Treeview's internals are style
    # options (see docs/ui_spacing.md), and a gear cell carries its
    # padding on the Text inside it, marked there. Their TITLE gaps are
    # tracked -- that is what these three were added for.
    "Stats Comparison",
    "Selected Build",
    "Equipped Memory Fragments",
}

# Panels whose left inset is not the border-edge rule at its 5px. The
# RULE is stated per entry rather than inferred from membership,
# because the two entries here are here for opposite reasons and one
# flag cannot carry both.
# `target_source` is stated per entry rather than inferred from
# membership. The two are here for opposite reasons and only one of them
# has a target the rules table cannot supply -- deriving the flag from
# the dict labelled Restore Defaults' perfectly ordinary 3 as a reading.
LEFT_INSET_OVERRIDES = {
    # A different rule, at that rule's own number: the first element is
    # a button, so the button rule applies rather than the one for text.
    "Restore Defaults": (RULE_BORDER_EDGE_BUTTON, 3, "rule"),
    # THIS rule, deliberately missed. The panel is built to be legible
    # before anything else on the tab, in Segoe UI 11 rather than 9, and
    # 7 is where its left edge is meant to sit. Tracked at what it is so
    # a drift still shows, rather than left out and unwatched.
    "Setup Status": (RULE_BORDER_EDGE_CONTENT, 7, "exception"),
}


# Panels that only exist in a non-default app state, and the panels
# beneath them whose position that state changes. Both are measured in
# the scenario as well as (where they exist) in the default one.
ELEMENT_OVERRIDE_TITLE = "Element override (Unknown character)"
ELEMENT_OVERRIDE_PANELS = [
    ELEMENT_OVERRIDE_TITLE,
    # These sit below it in the middle column, so packing the override
    # frame pushes them down. Their own title gaps should be unchanged;
    # measuring them here is what proves it.
    "Important Settings",
    "Have at least this much of a stat",
    "Set Configuration",
]


# The Optimizer's percent sliders, whose readouts the max_readouts
# scenario fills out.
READOUT_VARS = ("extra_pct_var", "dot_pct_var", "fracture_pct_var",
                "atk_def_split_var", "shielding_healing_weight_var")


def _max_readouts(app):
    """Drive every percent slider to 100.

    A readout is a fixed-width label with `anchor=tk.E`, so a short value
    leaves its slack on the LEFT -- the side the gap to the slider is
    measured on. At 0% that gap is 12px wider than at 100%, purely
    because "0%" is 12px narrower than "100%". Filling the readouts is
    what makes the distance a distance, and it is the same convention as
    measuring a column from its LONGEST label.

    Two things stop this writing to the maintainer's settings. The saves
    no-op while no character is selected, which is the state the app
    starts in -- `checks/check_optimizer_starts_unselected.py` keeps it
    that way. And `_loading_settings` is raised here as well, which is
    the app's own guard for programmatic var writes.
    """
    tab = app.optimizer_tab_instance
    app._spacing_readouts = {n: getattr(tab, n).get() for n in READOUT_VARS}
    app._spacing_was_loading = tab._loading_settings
    tab._loading_settings = True
    for name in READOUT_VARS:
        getattr(tab, name).set(100)


def _restore_readouts(app):
    tab = app.optimizer_tab_instance
    for name, value in getattr(app, "_spacing_readouts", {}).items():
        getattr(tab, name).set(value)
    tab._loading_settings = getattr(app, "_spacing_was_loading", False)


def _widest_stats(app):
    """Select the combatant whose stat block holds the widest values.

    The Character panel's value stops are RIGHT-aligned, so a short
    value starts further right and leaves a wider gap after its label --
    the distance that was SET only shows where the widest value is on
    screen. Which combatant that is depends on the snapshot, so it is
    found rather than named: the tab's own formatter builds each one's
    text without displaying it, and the longest number in it decides.

    Same convention as `_max_readouts` filling the sliders, and as
    measuring a column from its longest label.

    **Selecting is safe to automate here.** `_on_tree_select` leads to
    `select_hero_row` and `show_hero_details`, and neither writes: the
    Combatants list repaints a detail pane where the Optimizer's
    combatant box saves per-combatant settings.
    """
    tab = getattr(app, "heroes_tab_instance", None)
    rows = getattr(tab, "hero_data_list", None) if tab else None
    if not rows:
        return
    app._spacing_hero_index = tab.selected_hero_index
    best, widest = None, -1
    for index, row in enumerate(rows):
        try:
            text = tab._format_char_text(row["name"])
        except Exception:
            continue
        longest = max((len(tok) for tok in re.findall(r"[\d.]+", text)),
                      default=0)
        if longest > widest:
            best, widest = index, longest
    if best is not None:
        tab.select_hero_row(best)


def _restore_selection(app):
    tab = getattr(app, "heroes_tab_instance", None)
    was = getattr(app, "_spacing_hero_index", None)
    if tab is not None and was is not None and was >= 0:
        tab.select_hero_row(was)


def _force_element_override(app):
    """Show the Optimizer's Element override frame.

    Goes through the tab's OWN visibility method rather than packing the
    frame here: it positions itself with `before=` relative to whatever
    is first in the middle column, and a hand-rolled pack in the audit
    would measure a layout the app never produces. An empty character
    name resolves to the Unknown attribute, which is the condition the
    method shows the frame for.
    """
    tab = app.optimizer_tab_instance
    app._spacing_override_was_mapped = \
        tab.element_override_frame.winfo_ismapped()
    tab._update_element_override_visibility("")


def _restore_element_override(app):
    tab = app.optimizer_tab_instance
    if getattr(app, "_spacing_override_was_mapped", False):
        tab._update_element_override_visibility(
            tab.selected_character.get())
    else:
        # selected_character can be empty before a snapshot loads, and
        # an empty name is exactly what forced the frame open, so asking
        # the tab to restore would leave it open. Close it directly.
        tab.element_override_frame.pack_forget()


sa.register_scenario("element_override",
                     _force_element_override,
                     _restore_element_override)
sa.register_scenario("max_readouts", _max_readouts, _restore_readouts)
sa.register_scenario("widest_stats", _widest_stats, _restore_selection)


def _title_target_and_source(title):
    """Every title gap derives now. Kept as a pair because a title whose
    lowest glyph is not in one of the three classes would have to be
    measured, and the caller has to be able to say so."""
    return _title_gap_target(title), "rule"


# Empty now that the tool reproduces every hand measurement. Add a
# panel here to have its raw coordinates dumped when a reading is
# disputed again. It found the last one: a single antialiased column
# where the darkened tab strip met the window background, one unit off
# `bg` and therefore counted as ink -- which a scan that reports a row
# as painted if ANY column in it is turns into a gap of 0.
DEBUG_PANELS = ()

# Pair-gap entries to dump raw edges for on the next run.
DEBUG_PAIR_GAPS = ()

# Entries whose target deliberately misses their rule, where the
# table they live in is otherwise rule-derived. Each one has an
# `exception` marker at its site saying what stops it.
# Nothing needs this today; the Set Config checkbox left it when its
# piece count moved inside the widget.
EXCEPTION_ENTRIES = {}


def _debug_panel(title):
    """Resolver that measures as usual AND dumps its raw coordinates.

    Registered for the panels where the tool and the maintainer's eye
    disagree, so the next run says WHICH end is wrong instead of leaving
    it to be inferred from the total.
    """
    inner = _title_to_first_element(title)

    def resolve(cap, app):
        frame = _panel(app, title)
        child = sa.first_child(frame)
        print(f"  [debug] {title}")
        if child is not None:
            sa.debug_dump(cap, frame, child)
        return inner(cap, app)
    return resolve


def _class_left_inset(title, *classes):
    """Resolver: frame border -> the leftmost of a class of elements.

    "The checkboxes are at 8" is a statement about a group, not about
    one widget, so the group's shared left edge is what gets measured.
    """
    def resolve(cap, app):
        frame = _panel(app, title)
        widgets = sa.find_descendants_class(frame, *classes)
        if not widgets:
            return None, f"no {'/'.join(classes)} in panel"
        left = sa.leftmost_painted(cap, widgets)
        if left is None:
            return None, "elements painted nothing"
        edges, note = sa.frame_border_edges(cap, frame)
        return sa.gap_between(edges["left"], left), note
    return resolve


def _text_left_inset(title, prefix):
    """Resolver: frame border -> an element identified by its words."""
    def resolve(cap, app):
        frame = _panel(app, title)
        widget = sa.find_descendant_text(frame, prefix)
        if widget is None:
            return None, f"no element starting {prefix!r}"
        extent = sa.painted_extent_h(cap, sa.box_of(widget))
        if extent is None:
            return None, "element painted nothing"
        edges, note = sa.frame_border_edges(cap, frame)
        return sa.gap_between(edges["left"], extent[0]), note
    return resolve


# Elements measured in their own right, because a panel's left inset is
# not one number. Each of these disagrees with its panel's FIRST element,
# so a frame-level padding change would fix one and break the other --
# which is the whole reason they are tracked separately.
#
# The class names are Tk's, not the widget module's: a `ttk.Checkbutton`
# reports "TCheckbutton" and a `tk.Checkbutton` reports "Checkbutton".
# Every checkbox in this app is the latter, and will stay that way (see
# `ui/utils/checkbox.py`) -- naming only the ttk spelling here matched
# nothing and reported "no ... in panel", which the audit prints as a
# skipped row rather than a failure. Both spellings are listed anyway, so
# the entry survives a widget swap either way.
#
# (tab, panel, label, target, resolver)

ELEMENT_ENTRIES = [
    ("Optimizer", "Important Settings", "slider", 5,
     _class_left_inset("Important Settings", "TScale", "Scale")),
    ("Optimizer", "Set Configuration", "checkboxes", 5,
     _class_left_inset("Set Configuration", *CHECKBOX_CLASSES)),
    ("Capture", "Upgrade Log Settings", "checkboxes", 5,
     _class_left_inset("Upgrade Log Settings", *CHECKBOX_CLASSES)),
    ("Gear Score", "Stat Weight Configuration", "applied preset label", 5,
     _text_left_inset("Stat Weight Configuration", "Applied")),
]


# Entries registered but never yet read off a screen. They print yellow,
# and a name comes out of this set once a run has confirmed it -- so a
# batch being calibrated is visible at a glance among rows that already
# were. Their TARGETS come from the rules table, which is a claim about
# what the gap should be and says nothing about what it is.
#
# The entries built by `sa.track` further down state the flag directly;
# this set is for the ones the tables above generate, whose tuples have
# no room for it.
AWAITING_FIRST_READING = {
    "Have at least this much of a stat: row pitch",
    "Important Settings: row pitch",
    "Restore Defaults: row pitch",
    "Main Stats: row pitch",
    "Exclude Combatant's MFs: row pitch",
    "Important Settings -> Have at least",
    "Character -> Partner",
    "How Gear Score Works -> Stat Weight Configuration",
    "Requirements -> Upgrade Log Settings",
    "damage caption -> its sliders",
    "DEF caption -> its slider",
    "Shielding caption -> its slider",
    "Slots checkboxes",
    "Avg Card DMG% -> its spinbox",
}


def register_all():
    for tab, titles in PANELS.items():
        for title in titles:
            is_text = title in TEXT_PANELS
            if title in DEBUG_PANELS:
                title_resolve = _debug_panel(title)
            elif is_text:
                title_resolve = _text_panel_title_gap(title)
            else:
                title_resolve = _title_to_first_element(title)
            target, source = _title_target_and_source(title)
            sa.track(
                name=f"{title}: title -> first element",
                tab=tab,
                rule=RULE_TITLE_ELEMENT,
                target=target,
                target_source=source,
                resolve=title_resolve,
                axis="v",
            )
            if title in LEFT_INSET_EXCEPTIONS:
                continue
            left_rule, left_target, left_source = LEFT_INSET_OVERRIDES.get(
                title, (RULE_BORDER_EDGE_CONTENT, 5, "rule"))
            sa.track(
                name=f"{title}: left edge -> content",
                tab=tab,
                rule=left_rule,
                target=left_target,
                axis="h",
                target_source=left_source,
                resolve=(_text_panel_inset(title) if is_text
                         else _left_inset(title)),
            )

    for tab, panel, label, target, resolve in ELEMENT_ENTRIES:
        sa.track(
            name=f"{panel}: left edge -> {label}",
            tab=tab,
            rule=RULE_BORDER_EDGE_CONTENT,
            target=target,
            resolve=resolve,
            axis="h",
        )

    for tab, name, target, axis, resolve in CONTENT_FRAME_ENTRIES:
        sa.track(
            name=name,
            tab=tab,
            rule=RULE_CONTENT_FRAME,
            target=target,
            resolve=resolve,
            axis=axis,
            provisional=name in AWAITING_FIRST_READING,
        )

    for tab, name, target, hand, resolve in PANEL_OVER_TEXT_ENTRIES:
        sa.track(
            name=name,
            tab=tab,
            rule=RULE_PANEL_UNRELATED_LABEL,
            target=target,
            resolve=resolve,
            axis="v",
            hand=hand,
        )

    for tab, _heading in TAB_LIST_TABS:
        sa.track(
            name=f"{tab}: tab list -> first element",
            tab=tab,
            rule=RULE_TAB_LIST,
            target=_tab_list_target(tab),
            resolve=_tab_list_to_first_element(_heading),
            axis="v",
            provisional=False,
        )

    for tab, title, rule, classes, target in ROW_PITCH_ENTRIES:
        sa.track(
            name=f"{title}: row pitch",
            tab=tab,
            rule=rule,
            target=target,
            resolve=_row_pitch(title, classes),
            axis="v",
            provisional=f"{title}: row pitch" in AWAITING_FIRST_READING,
        )

    for tab, title, classes in ROW_DIVISION_ENTRIES:
        sa.track(
            name=f"{title}: row division",
            tab=tab,
            rule=RULE_CHECKBOX_DIVISION,
            target=12,
            resolve=_row_division(title, classes),
            axis="v",
        )

    for tab, title, side in PANEL_EDGES:
        sa.track(
            name=f"{title}: {side} edge -> content",
            tab=tab,
            rule=RULE_BORDER_EDGE_CONTENT,
            target=5,
            resolve=_panel_edge_inset(title, side),
            axis=("v" if side in ("top", "bottom") else "h"),
            hand=PANEL_EDGE_HANDS.get((title, side)),
        )

    for rule, table, scenario in (
            (RULE_PAIR_GAP, PAIR_GAP_ENTRIES, "default"),
            (RULE_LABEL_ELEMENT, LABEL_ELEMENT_ENTRIES, "default"),
            (RULE_LABEL_ELEMENT, READOUT_ENTRIES, "max_readouts")):
        for tab, name, target, hand, container, classes, index in table:
            # One entry at a time, while a distance no padding reaches is
            # being chased. Empty the set once it has answered.
            build = (_debug_neighbours if name in DEBUG_PAIR_GAPS
                     else _pair_gap)
            sa.track(
                name=name,
                tab=tab,
                rule=rule,
                target=target,
                resolve=build(container, classes, index),
                axis="h",
                hand=hand,
                scenario=scenario,
                provisional=name in AWAITING_FIRST_READING,
            )

    for rule, table, axis, source in (
            (RULE_CONTROL_GROUP, CONTROL_GROUP_ENTRIES, "h", "rule"),
            (RULE_CONFIG_PANEL_ROW, CONFIG_ROW_ENTRIES, "v", "rule"),
            (RULE_CONTENT_FRAME, BUTTON_ROW_ABOVE_ENTRIES, "v", "rule"),
            (RULE_LABEL_ELEMENT, INDICATOR_ENTRIES, "h", "exception"),
            (RULE_CONTENT_FRAME, WINDOW_EDGE_ENTRIES, "h", "rule"),
            (RULE_LABEL_ELEMENT, CELL_LABEL_ENTRIES, "h", None),
            (RULE_TITLE_ELEMENT, RESULTS_TITLE_ENTRIES, "v", "rule"),
            (RULE_CHECKBOX_PITCH, OPTIONS_TRIO_ENTRIES, "v", "rule"),
            (RULE_BORDER_EDGE_CONTENT, PRESET_LIST_ENTRIES, "h",
             "exception"),
            (RULE_BORDER_EDGE_CONTENT, PRESET_LIST_BOTTOM_ENTRIES, "v",
             "exception")):
        for tab, name, target, hand, resolve in table:
            sa.track(
                name=name,
                tab=tab,
                rule=rule,
                target=target,
                resolve=resolve,
                axis=axis,
                hand=hand,
                # None means per-entry: a table can hold one row that
                # misses its rule beside rows that meet it.
                target_source=(source if source is not None
                               else EXCEPTION_ENTRIES.get(name, "rule")),
            )

    for tab, name, target, hand, source, resolve in EXPLANATION_ENTRIES:
        sa.track(
            name=name,
            tab=tab,
            rule=RULE_EXPLANATION,
            target=target,
            resolve=resolve,
            axis="v",
            target_source=source,
            hand=hand,
            provisional=name in AWAITING_FIRST_READING,
        )

    for tab, title, side in TEXT_PANEL_EDGES:
        sa.track(
            name=f"{title}: {side} edge -> text",
            tab=tab,
            rule=RULE_BORDER_EDGE_CONTENT,
            target=5,
            resolve=_text_panel_inset(title, side),
            axis=("v" if side in ("top", "bottom") else "h"),
            provisional=False,
        )

    sa.track(
        name="Assign preset caption -> dropdown",
        tab="Combatants",
        rule=RULE_TITLE_ELEMENT,
        target=_title_gap_target("Assign preset to"),
        resolve=_caption_to_field("Assign preset to"),
        axis="v",
        provisional=False,
    )

    # `Region:` names a READOUT rather than a control, and at the
    # distance it sits it reads as a heading with its value beside it
    # rather than a label against its element.
    sa.track(
        name="Region: -> its readout",
        tab="Capture",
        rule=RULE_HEADING_ELEMENT,
        target=14,
        resolve=_pair_gap(lambda app: _by_text("Region:")(app).master,
                          LABEL_CLASSES, 0),
        axis="h",
        provisional=True,
    )

    for tab, heading, subtitle in TAB_HEADERS:
        sa.track(
            name=f"{heading} -> its subtitle",
            tab=tab,
            rule=RULE_HEADING_ELEMENT,
            target=14,
            resolve=_heading_to_subtitle(heading, subtitle),
            axis="h",
            provisional=False,
        )
        # The vertical half of the same pair, and a different rule: the
        # one above is the gap ALONG the header line, this is whether the
        # subtitle sits on that line at all. Nothing watched it, and the
        # subtitle rides a pixel high on every tab that has one.
        sa.track(
            name=f"{heading} subtitle: off the heading's line",
            tab=tab,
            rule=RULE_HEADER_SUBTEXT,
            target=0,
            resolve=_heading_subtitle_baseline(heading, subtitle),
            axis="v",
            provisional=False,
        )

    # The rule's other shape: a status line with its hint beside it,
    # rather than a tab heading with its subtitle. Same question, and the
    # site the maintainer's eye found -- the hint rode a pixel high.
    sa.track(
        name="Status hint: off the status line",
        tab="Capture",
        rule=RULE_HEADER_SUBTEXT,
        target=0,
        resolve=_status_subtext_baseline("Ready", "Click 'Start Capture'",
                                         DESCENDER_DEPTH_11),
        axis="v",
        provisional=False,
    )

    # The toolbar's two buttons. They sit in a plain frame rather than a
    # panel, so `_first_button_gap` -- which searches a panel -- has
    # nothing to search.
    sa.track(
        name="Start -> Stop",
        tab="Optimizer",
        rule=RULE_BUTTON_GAP,
        target=4,
        resolve=_gap(_by_text("Start"), _by_text("Stop"), "h"),
        axis="h",
        provisional=True,
    )

    # Capture's four action buttons, likewise in a plain frame.
    sa.track(
        name="capture buttons: button -> button",
        tab="Capture",
        rule=RULE_BUTTON_GAP,
        target=4,
        resolve=_pair_gap(lambda app: _by_text("Open Snapshots")(app).master,
                          ("TButton", "Button"), 0),
        axis="h",
        provisional=True,
    )

    # And the other two plain-frame button rows.
    sa.track(
        name="Gear Score buttons: button -> button",
        tab="Gear Score",
        rule=RULE_BUTTON_GAP,
        target=4,
        resolve=_pair_gap(
            lambda app: _by_text("Apply Current Weights")(app).master,
            ("TButton", "Button"), 0),
        axis="h",
        provisional=True,
    )
    sa.track(
        name="Setup buttons: button -> button",
        tab="Setup",
        rule=RULE_BUTTON_GAP,
        target=4,
        resolve=_pair_gap(lambda app: _by_text("Check Status")(app).master,
                          ("TButton", "Button"), 0),
        axis="h",
        provisional=True,
    )

    # The Character panel's stat block, whose columns are tab stops. Its
    # `label ↔ its element` and `element and its label ↔ ...` markers
    # sit on CHAR_TAB_*, and nothing could read them: the audit measures
    # widgets, and a tab stop has none on either side.
    #
    # A stat row holds four columns: a stat, its value, the second
    # column's stat, and ITS value -- so the three gaps across it are
    # the two rules alternating.
    #
    # Every row is read and the tightest reported, because the value
    # stops are RIGHT-aligned: a short value starts further right and
    # leaves a wider gap after its label, so the distance that was SET
    # is the one on the row whose value is widest. Which row that is
    # depends on the selected combatant, which is why no single row can
    # be named.
    #
    # **THE READING IS ONLY BINDING WHERE THE WIDEST VALUE IS PRESENT**,
    # and no combatant carries every column's widest. The left pair
    # needs a FOUR-DIGIT stat: a combatant whose largest is 591 reads 10
    # against the rule's 4, and the six pixels are the digit that is not
    # there rather than a gap to nudge. Select one with a stat in the
    # thousands before reading these rows, and treat a reading taken
    # without one as a lower bound on the slack, not a distance.
    #
    # A scenario could pick that combatant the way `max_readouts` fills
    # the sliders. It is not written: unlike a slider variable, the
    # selection drives a repaint of the whole detail pane, and whether
    # that path is free of writes has not been established.
    #
    # The LEFT pair is read on the four rows that have one. The Element
    # row emits both of the left pair's tabs with nothing between them,
    # so it has two bands where the others have four -- its right-hand
    # pair is at the same boundary only when counted from the END, which
    # is what `from_end` is for and why the right pair reads all five.
    CHAR_LEFT_ROWS = ("ATK	", "DEF	", "HP	", "Ego	")
    CHAR_ALL_ROWS = CHAR_LEFT_ROWS + ("Element	",)
    for _name, _index, _end, _rows, _rule, _target in (
            ("stat -> its value", 0, False, CHAR_LEFT_ROWS,
             RULE_LABEL_ELEMENT, 4),
            ("value -> the next stat", 1, False, CHAR_LEFT_ROWS,
             RULE_PAIR_GAP, 8),
            ("second stat -> its value", 0, True, CHAR_ALL_ROWS,
             RULE_LABEL_ELEMENT, 4)):
        sa.track(
            name=f"Character: {_name}",
            tab="Combatants",
            rule=_rule,
            target=_target,
            resolve=_text_column_gap(
                lambda app: sa.find_descendant_class(
                    _panel(app, "Character"), "Text"),
                _rows, _index, _end),
            axis="h",
            scenario="widest_stats",
            provisional=True,
        )

    # The one site of `label row -> label row`: the lines inside an
    # Equipped MF gear cell. Its rows are text, not widgets, so the
    # pitch has to be read off the painted lines.
    sa.track(
        name="Equipped MF cell: line pitch",
        tab="Combatants",
        rule=RULE_LABEL_ROW_PITCH,
        target=10,
        resolve=_text_line_pitch(_first_filled_text(
            "Equipped Memory Fragments")),
        axis="v",
        provisional=True,
    )

    for tab, title in ALL_NONE_PANELS:
        sa.track(
            name=f"{title}: checkbox block -> All/None",
            tab=tab,
            rule=RULE_ALL_NONE_ROW,
            target=5,
            resolve=_checkbox_block_to_buttons(title),
            axis="v",
            provisional=False,
        )
        sa.track(
            name=f"{title}: left edge -> All",
            tab=tab,
            rule=RULE_BORDER_EDGE_BUTTON,
            target=3,
            resolve=_first_button_left_inset(title),
            axis="h",
            provisional=False,
        )

    for tab, title in BUTTON_ROW_PANELS:
        sa.track(
            name=f"{title}: All -> None",
            tab=tab,
            rule=RULE_BUTTON_GAP,
            target=4,
            resolve=_first_button_gap(title),
            axis="h",
        )

    for title in ELEMENT_OVERRIDE_PANELS:
        target, source = _title_target_and_source(title)
        sa.track(
            name=f"{title}: title -> first element",
            tab="Optimizer",
            rule=RULE_TITLE_ELEMENT,
            target=target,
            target_source=source,
            resolve=_title_to_first_element(title),
            axis="v",
            scenario="element_override",
        )


# Runs at IMPORT, so importing this module is what fills
# spacing_audit.REGISTRY -- importing spacing_audit alone leaves it
# empty. Not idempotent: calling it again after the import appends a
# second copy of every entry.
register_all()
