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

# Glyphs that reach ABOVE cap height at Segoe UI 14 bold, the tab
# headings' font. The rule measures a gap above text to the top of the
# CAPITALS, so a string holding one of these reads 1px tighter than the
# rule asks while sitting exactly where it should -- the same shape as a
# descender reading tighter below.
#
# `i` and `l` are measured. The rest are the same typographic class --
# ascenders and tittles -- and are assumed to behave alike; `t` is NOT
# one of them, which "Data Capture" reading dead on 6 confirms. At
# Segoe UI 9 and 11 the whole class tops out level with the capitals and
# none of this applies.
ASCENDERS_ABOVE_CAP = "bdfhijkl"

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
ASCENDER_RISE_14_BOLD = 1


def ink_below_baseline(text: str) -> int:
    """How far `text`'s ink reaches below the baseline.

    Checked deepest first: a string can hold both a descender and a
    parenthesis, and the deeper glyph is the one the ink stops at.
    """
    if any(c in text for c in DESCENDERS):
        return DESCENDER_DEPTH
    if any(c in text for c in PARENTHESES):
        return PARENTHESIS_DEPTH
    return 0


def ink_above_caps(text: str, bold14: bool = False) -> int:
    """How far `text`'s ink reaches above its capitals.

    Only at Segoe UI 14 bold. At 9 and 11 the ascenders top out level
    with the caps, so every gap above body text needs no correction.
    """
    if bold14 and any(c in text for c in ASCENDERS_ABOVE_CAP):
        return ASCENDER_RISE_14_BOLD
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
        edges, saturated = sa.frame_border_edges(cap, frame)
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
        return sa.gap_between(extent[1], edges["bottom"]), note
    return resolve


# The rule says "5px, all edges" and only the left edges were tracked.
# (tab, panel, side, what the maintainer read off the screen). The
# readings are calibration, not targets: a resolver that disagrees with
# one is measuring the wrong thing, and no pixel should move until they
# agree.
PANEL_EDGES = [
    ("Optimizer", "Important Settings", "top", 13),
    ("Optimizer", "Important Settings", "right", 6),
    ("Optimizer", "Important Settings", "bottom", 8),
    ("Optimizer", "Have at least this much of a stat", "top", 7),
    ("Optimizer", "Exclude Combatant's MFs", "top", 4),
    ("Optimizer", "Set Configuration", "top", 6),
    ("Optimizer", "Set Configuration", "bottom", 6),
    ("Capture", "Requirements", "top", 7),
    ("Capture", "Requirements", "bottom", 9),
    ("Capture", "Upgrade Log Settings", "top", 6),
    ("Capture", "Upgrade Log Settings", "bottom", 4),
    ("Capture", "Upgrade Log Settings", "right", 6),
]


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


# (tab, name, target, provisional, resolver) for a panel with text
# beneath it. Two stacked panels are one of these: what sits across the
# gap is the lower panel's TITLE, not its border, and the nearer element
# decides which rule applies.
#
# The rule's 10px has never been measured anywhere. The Memory Fragments
# row is the site it was written for, registered so the number has a
# second reading to answer to rather than resting on the Capture pair
# alone.
PANEL_OVER_TEXT_ENTRIES = [
    ("Capture", "Status -> Server Region title", 10, False,
     _panel_gap("Status", "Server Region", "v")),
    ("Memory Fragments", "Slots -> active preset label", 10, False,
     _panel_over_label("Slots", "Preset:")),
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


def _tab_list_to_first_element(text=None, bold14=False):
    """Resolver: the tab strip's bottom -> the first ink on the tab.

    The strip has no widget of its own, so the reference is the tab
    frame's box top, which abuts it: `Flush.TNotebook` removed clam's
    2px client inset, so there is nothing between the two. The other end
    is whatever paints first anywhere across the tab's width -- a
    heading's capitals, a panel's border, a list.
    """
    def resolve(cap, app):
        tab = sa.current_tab_widget(app)
        box = sa.box_of(tab)
        extent = sa.painted_extent_v(cap, box)
        if extent is None:
            return None, "nothing painted on this tab"
        # Restated from the CAPITALS. The scan finds the topmost ink,
        # which on a 14 bold heading is an ascender standing above the
        # caps -- so it has eaten into this gap and the rise is added
        # back, leaving the target the plain 6 for every tab.
        gap = (sa.gap_between(box.top - 1, extent[0])
               + ink_above_caps(text or "", bold14))
        if gap == 0:
            # `painted_extent_v` scans EVERY column of a row, so one
            # stray pixel anywhere across the window's width puts the
            # first painted row at the tab's own top. Sampling a single
            # column reported "bg, counted as empty" and explained
            # nothing; this finds where the ink actually is.
            return gap, f"row {box.top}: {sa._first_painted_x(cap, box, box.top)}"
        return gap, ""
    return resolve


# The rule has nine marker sites and had no entry, which is how Setup
# came to sit a pixel below the other two headers with nothing
# reporting it.
#
# (tab, the string the gap is measured to, is it 14 bold). The string is
# there for the ascender class above; None where the first thing painted
# on the tab is not text.
#
# COMBATANTS IS ABSENT ON PURPOSE. Its topmost element is the detail
# pane's heading, whose text is the selected character's name -- so
# whether the reading is 5 or 6 depends on which row is selected, and an
# entry whose target changes with the data cannot be tracked.
TAB_LIST_TARGET = 6
TAB_LIST_TABS = [
    ("Optimizer", None, False),
    ("Memory Fragments", None, False),
    ("Gear Score", "Gear Score Calculation", True),
    ("Capture", "Data Capture", True),
    ("Setup", "First-Time Setup", True),
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
        edges, saturated = sa.frame_border_edges(cap, frame)
        note = "border scan hit its cap" if saturated else ""
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
        edges, saturated = sa.frame_border_edges(cap, frame)
        note = "border scan hit its cap" if saturated else ""
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
CHECKBOX_CLASSES = ("Checkbutton", "TCheckbutton")

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
        )

    for tab, name, target, provisional, resolve in PANEL_OVER_TEXT_ENTRIES:
        sa.track(
            name=name,
            tab=tab,
            rule=RULE_PANEL_UNRELATED_LABEL,
            target=target,
            resolve=resolve,
            axis="v",
            provisional=provisional,
        )

    for tab, _text, _bold in TAB_LIST_TABS:
        sa.track(
            name=f"{tab}: tab list -> first element",
            tab=tab,
            rule=RULE_TAB_LIST,
            target=_tab_list_target(tab),
            resolve=_tab_list_to_first_element(_text, _bold),
            axis="v",
            provisional=False,
        )

    for tab, title, side, hand in PANEL_EDGES:
        sa.track(
            name=f"{title}: {side} edge -> content",
            tab=tab,
            rule=RULE_BORDER_EDGE_CONTENT,
            target=5,
            resolve=_panel_edge_inset(title, side),
            axis=("v" if side in ("top", "bottom") else "h"),
            provisional=True,
            hand=hand,
        )

    for tab, title, side in TEXT_PANEL_EDGES:
        sa.track(
            name=f"{title}: {side} edge -> text",
            tab=tab,
            rule=RULE_BORDER_EDGE_CONTENT,
            target=5,
            resolve=_text_panel_inset(title, side),
            axis=("v" if side in ("top", "bottom") else "h"),
            provisional=True,
        )

    sa.track(
        name="Assign preset caption -> dropdown",
        tab="Combatants",
        rule=RULE_TITLE_ELEMENT,
        target=_title_gap_target("Assign preset to"),
        resolve=_caption_to_field("Assign preset to"),
        axis="v",
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
