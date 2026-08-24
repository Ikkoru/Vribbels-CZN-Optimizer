"""The spacing ledger, in executable form.

Each entry here is one row of the rules table in
`docs/ui_spacing.md`, bound to the panel it applies to. Importing
this module registers them; `spacing_audit.run_audit` measures them.

Two conventions worth knowing before adding entries:

* **Panels are named by their visible title**, not by attribute. See
  `docs/ui_spacing.md` "Checking spacing" for why, and for what
  breaks if a title is renamed.
* **Targets are per-entry, not per-rule.** The reference point for a gap
  below text is the bottom of the DESCENDERS, so a title containing a
  `g` sits lower than one that does not and its gap below measures 3
  where the other measures 6 -- same rule, same panel spacing, two
  numbers. `_title_gap_target` derives which from the title itself
  rather than making each entry state it.
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
RULE_FRAME_EDGE_CONTENT = "frame edge -> first non-button element"
RULE_BUTTON_GAP = "button -> button"
RULE_FRAME_EDGE_BUTTON = "frame edge -> button"
RULE_ALL_NONE_ROW = "checkbox block -> All/None row"
RULE_SPINBOX_PITCH = "spinbox row -> spinbox row"
RULE_CHECKBOX_PITCH = "checkbox/slider ↕ checkbox/slider rows"
RULE_TEXT_LABEL_PITCH = "text label row -> text label row"
RULE_CHECKBOX_DIVISION = "checkbox row -> checkbox row (small division)"
RULE_TITLE_ELEMENT = "title above, element below"
RULE_LABEL_ELEMENT = "label ↔ its element"
RULE_HEADING_ELEMENT = "heading ↔ element"
RULE_PAIR_GAP = "element and its label ↔ element and its label"
RULE_EXPLANATION = "explanation text -> the controls it explains"
RULE_UNRELATED_CHECKBOXES = "checkboxes -> unrelated checkboxes"
RULE_PANEL_UNRELATED_LABEL = "panel ↕ unrelated label"
RULE_CONFIG_PANEL_ROW = "config panel row ↕ row"
RULE_OTC_GROUP = "overarching tab control element group ↔ OTC element group"


DESCENDERS = "gjpqy"

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


def _title_gap_target(title: str) -> int:
    """2 where the title has a descender, 5 where it does not.

    Same rendered spacing either way -- the glyphs just reach further
    down in one case. See `docs/ui_spacing.md`.
    """
    return 2 if any(c in title for c in DESCENDERS) else 5


def track_text_top_gap(name, tab, rule, resolve, text, target=None,
                       scenario="default"):
    """Register a gap measured TO the top of a line of text.

    Refuses to guess. The topmost painted pixel of a line is a cap, an
    ascender or -- when the string has neither -- the x-height, and the
    first two differ from each other by a per-font pixel that cannot be
    derived (see docs/ui_spacing.md). So `target` must be supplied,
    measured once and agreed, and it is recorded as observed rather than
    rule-derived.

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
             scenario=scenario, target_source="observed")


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
        return sa.title_gap(cap, frame, extent[0], bg=strip_bg)
    return resolve


def _text_panel_left_inset(title):
    """Resolver: frame border -> the prose inside the text widget.

    The border is NOT found by scanning here. These panels are built so
    the fill reaches the border -- that is the point of them -- so there
    is no background pixel between the two for a scan to stop at. But
    the same fact gives the answer directly: the text widget abuts the
    border, so the border's inner edge is the widget's own left edge.
    """
    def resolve(cap, app):
        _frame, text = _text_of(app, title)
        fill = {cap.palette["bg_light"]}
        box = sa.box_of(text)
        extent = sa.painted_extent_h(cap, box, fill)
        if extent is None:
            return None, "text widget is empty"
        return sa.gap_between(box.left - 1, extent[0]), ""
    return resolve


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
        return sa.title_gap(cap, frame, extent[0])
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


# Tab label -> the panels on it that follow the standard two rules.
# Tab labels must match the notebook's tab text exactly; a mismatch is
# reported as "no tab" on the first run rather than failing silently.
PANELS = {
    "Memory Fragments": ["Slots", "Sets", "Main Stats"],
    "Combatants": ["Character", "Partner"],
    "Optimizer": [
        "Important Settings",
        "Have at least this much of a stat",
        "Set Configuration",
        "Exclude Combatant's MFs",
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

# Panels whose left inset is NOT the frame-edge rule.
LEFT_INSET_EXCEPTIONS = {
    # Confirmed by measurement as deliberate; the frame-edge rule does
    # not apply to this panel's left edge at all, so registering it
    # would show a permanent red row and train the reader to ignore
    # them.
    "Status",
}

# Panels whose left inset follows a DIFFERENT rule, with the target.
LEFT_INSET_TARGETS = {
    # First element is a button, so the button rule applies rather than
    # the frame-edge text rule. Measured, and correct.
    "Restore Defaults": 3,
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


# Titles whose gap target cannot be derived from the character set.
# Parentheses drop below the baseline but not as far as a descender, so
# a title ending in one sits between the two derived values.
#
# NOT measured. The parenthesis class was read off an earlier build, and
# this target is that class carried across the app-wide `labelmargins`
# correction rather than a reading of its own -- which is why the entry
# reports `target inferred`. Measuring it needs an Unknown-attribute
# character on screen to make the panel appear, which is why the
# hand-measuring pass skipped it. See docs/ui_spacing.md "Three glyph
# classes below the baseline, not two".
TITLE_GAP_TARGETS = {
    "Element override (Unknown character)": 4,
}


def _title_target_and_source(title):
    if title in TITLE_GAP_TARGETS:
        return TITLE_GAP_TARGETS[title], "inferred"
    return _title_gap_target(title), "rule"


# Empty now that the tool reproduces every hand measurement. Add a
# panel here to have its raw coordinates dumped when a reading is
# disputed again.
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
    ("Optimizer", "Important Settings", "slider", 6,
     _class_left_inset("Important Settings", "TScale", "Scale")),
    ("Optimizer", "Set Configuration", "checkboxes", 6,
     _class_left_inset("Set Configuration", *CHECKBOX_CLASSES)),
    ("Capture", "Upgrade Log Settings", "checkboxes", 6,
     _class_left_inset("Upgrade Log Settings", *CHECKBOX_CLASSES)),
    ("Gear Score", "Stat Weight Configuration", "applied preset label", 6,
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
            )
            if title in LEFT_INSET_EXCEPTIONS:
                continue
            sa.track(
                name=f"{title}: left edge -> content",
                tab=tab,
                rule=(RULE_FRAME_EDGE_BUTTON if title in LEFT_INSET_TARGETS
                      else RULE_FRAME_EDGE_CONTENT),
                target=LEFT_INSET_TARGETS.get(title, 6),
                resolve=(_text_panel_left_inset(title) if is_text
                         else _left_inset(title)),
            )

    for tab, panel, label, target, resolve in ELEMENT_ENTRIES:
        sa.track(
            name=f"{panel}: left edge -> {label}",
            tab=tab,
            rule=RULE_FRAME_EDGE_CONTENT,
            target=target,
            resolve=resolve,
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
            scenario="element_override",
        )


# Runs at IMPORT, so importing this module is what fills
# spacing_audit.REGISTRY -- importing spacing_audit alone leaves it
# empty. Not idempotent: calling it again after the import appends a
# second copy of every entry.
register_all()
