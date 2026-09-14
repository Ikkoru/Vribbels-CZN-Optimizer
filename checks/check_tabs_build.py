"""Every tab must survive being built.

`compileall` proves a file parses. Importing it proves its module body
runs. NEITHER touches the inside of `setup_ui`, where the widgets are
actually made -- so a name that went missing there is invisible to both
and surfaces as a traceback on the next launch, with the window never
appearing.

This builds each tab against a withdrawn Tk root and a real AppContext.
It catches the whole class: undefined names, wrong widget options, a
constant deleted from under a caller.

Settings managers are pointed at a COPY of `Vribbels/settings/`. Building
a tab is not reliably read-only, and the maintainer's own state is not
something a check may write through.

Skips itself where Tk cannot open a display.

It also guards the `winfo_id()` call in `make_checkbox`, which reads as
dead code -- its return value is discarded -- and is the only thing
stopping a gridful of checkboxes flashing light grey the first time
their tab is shown. Nothing about losing it is visible from a headless
run, so the guard is on the source rather than on behaviour.

And it guards the other piece of `ui/utils/` that looks like reflection
waiting to be deleted: the loop copying a wrapper frame's geometry
methods onto the Text `make_scrolled_text` returns. Without it a
caller's `.pack()` packs the bare Text and the scrollbar is never
placed.
"""

import ast
import re
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip

NAME = "tabs build"

# About is static and out of the spacing work's scope, but it is cheap
# to build and a missing name would break the notebook the same way, so
# it is here too.
TAB_ATTRS = ("SetupTab", "CaptureTab", "InventoryTab", "OptimizerTab",
             "HeroesTab", "ScoringTab", "MaterialsTab",
             "ChecklistTab")


def _make_checkbox_forces_its_window():
    """True if make_checkbox still calls winfo_id() on the widget."""
    tree = ast.parse((SOURCE_ROOT / "ui" / "utils" / "checkbox.py")
                     .read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "make_checkbox":
            return any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "winfo_id"
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            )
    return False


def _scrolled_text_packs_the_pair(root, colors):
    """Why the caller's `.pack()` has to reach the wrapper, not the Text.

    `make_scrolled_text` hands back the Text, so `.pack()` on it would
    put the bare Text in the panel and leave the scrollbar unplaced --
    the wrapper never sized, nothing on screen. What prevents that is a
    loop copying the wrapper's geometry methods onto the Text, which
    reads like tidy-up-able reflection and is the whole mechanism.

    Returns a complaint, or None.
    """
    import tkinter as tk
    from tkinter import ttk
    from ui.utils.scrolled_text import make_scrolled_text

    parent = ttk.Frame(root)
    widget = make_scrolled_text(parent, colors, height=2)
    widget.pack(fill=tk.BOTH, expand=True)
    try:
        packed = parent.pack_slaves()
        if len(packed) != 1 or packed[0].winfo_class() != "TFrame":
            return (
                "make_scrolled_text's .pack() no longer packs the wrapper "
                "frame -- the scrollbar goes unplaced and the panel shows "
                "nothing. See the geometry-method copy in "
                "ui/utils/scrolled_text.py."
            )
        inside = sorted(w.winfo_class() for w in packed[0].winfo_children())
        if inside != ["TScrollbar", "Text"]:
            return (
                f"a scrolled text's wrapper holds {inside} rather than a "
                "Text and a TScrollbar. Every scrollbar in the app is a "
                "ttk one so the TScrollbar style paints them all; a tk "
                "Scrollbar ignores it and paints classic grey."
            )
    finally:
        parent.destroy()
    return None


def _percent_fields_are_clamped(tab):
    """The 0-100 fields must hold a TYPED value in range.

    A `tk.Spinbox`'s `from_`/`to` bound its buttons and its wheel, not
    its text: 500 and -7 both reach the variable through a `from_=0,
    to=100` spinbox. Nothing about that is visible until a bad number
    reaches the optimizer, so it is guarded here.

    The BINDING cannot be exercised -- Tk will not deliver a key event
    to an unmapped widget -- so this calls the handler the binding calls
    and checks the wiring separately.
    """
    import tkinter as tk
    failures = []

    def spin_for(var):
        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)
        name = str(var)
        for w in walk(tab.get_frame()):
            if (w.winfo_class() == "Spinbox"
                    and str(w.cget("textvariable")) == name):
                return w
        return None

    # One of each shape: a percent capped at 100, a percent that is not
    # (CDmg runs past it in game), an integer with a small range, and a
    # field that takes negatives.
    cases = [("CRate", tab.have_at_least_vars.get("CRate")),
             ("CDmg", tab.have_at_least_vars.get("CDmg")),
             ("Max Flex Slots", tab.max_flex_slots_var),
             ("Avg Card DMG%", tab.avg_card_dmg_pct_var)]
    shares = list(tab.set_effect_pct_vars.items())
    if shares:
        cases.append((f"set share {shares[0][0]}", shares[0][1]))

    for label, var in cases:
        if var is None:
            failures.append(f"no variable behind {label}; the clamp cannot "
                            f"be checked and may have gone with it")
            continue
        spin = spin_for(var)
        if spin is None:
            failures.append(f"no Spinbox bound to {label}'s variable")
            continue
        bound = spin.bind()
        for seq in ("<Key-Return>", "<FocusOut>"):
            if seq not in bound:
                failures.append(
                    f"{label}'s spinbox has no {seq} binding, so nothing "
                    f"clamps what is TYPED into it -- from_/to bound the "
                    f"buttons only. See _clamp_on_commit."
                )
        before = var.get()
        lo, hi = float(spin.cget("from")), float(spin.cget("to"))
        for typed in (500, -7):
            var.set(typed)
            tab._commit_clamp(spin, var)
            got = var.get()
            want = type(got)(min(max(typed, lo), hi))
            if got != want:
                failures.append(
                    f"{label} holds {got} after {typed} was entered, not "
                    f"{want} -- its own declared range is {lo} to {hi}. "
                    f"The clamp reads from_/to off the widget, so either "
                    f"it is not wired here or the range is not what the "
                    f"field means."
                )
        # Text that is not a number at all cannot be clamped toward a
        # bound, so it goes back to the last value the field held.
        state = {"good": before}
        spin.delete(0, tk.END)
        spin.insert(0, "abc")
        tab._commit_clamp(spin, var, state)
        try:
            got = var.get()
        except tk.TclError:
            got = "still not a number"
        if got != before:
            failures.append(
                f"{label} holds {got!r} after 'abc' was entered, not the "
                f"{before} it held before. Non-numeric text has no bound "
                f"to snap to, so the field has to go back to what it had."
            )
        var.set(before)
    return failures


def _log_preset_columns_leave_the_gap(tab):
    """The preset checklist packs as many columns as fit, and no more.

    The names in it are the USER's presets, so a stated column count is
    right for one person's presets and wrong for the next: too many and
    the last one clips against the panel edge, too few and a third of
    the panel is empty. `LOG_PRESET_COLUMN_GAP` is the floor the count
    is solved against.

    A column costs its OWN widest name, so a count that does not fit
    does not mean a larger one cannot -- which is why the ceiling here
    is "no larger count fits" rather than "the next one does not".
    Pricing every column at the longest name in the whole list is the
    mistake this guards: it refused six columns of names that fit in
    ninety per cent of the panel.

    Checked at several widths rather than the current one, because the
    panel takes whatever the left column does not and the maintainer's
    window is only one of those widths.

    Returns a list of complaints.
    """
    from ui.tabs.capture_tab import LOG_PRESET_COLUMN_GAP

    def need(widths, columns):
        """What those columns cost -- stated here, not imported.

        Importing the module's own pricing would make this check agree
        with the solver by construction: both would be wrong together
        and nothing would say so.
        """
        per = [max(widths[c::columns]) for c in range(columns)
               if widths[c::columns]]
        return sum(per) + max(0, len(per) - 1) * LOG_PRESET_COLUMN_GAP

    class _Width:
        """A frame of a stated width, for the solver alone."""

        def __init__(self, width):
            self.width = width

        def winfo_width(self):
            return self.width

        def update_idletasks(self):
            pass

    out = []
    gap = LOG_PRESET_COLUMN_GAP
    # A uniform list, a spread like a real roster's, and one name far
    # longer than the rest -- the case where per-column pricing and
    # widest-times-count differ most.
    lists = {
        "uniform": [120] * 12,
        "spread": [40, 189, 55, 136, 72, 173, 51, 149, 64, 176, 43, 157],
        "one long": [50] * 11 + [300],
    }
    for label, widths in lists.items():
        for width in (150, 320, 640, 1028, 1600):
            n = tab._log_preset_columns(_Width(width), widths)
            if n < 1 or n > len(widths):
                out.append(f"the solver asked for {n} columns of "
                           f"{label} names at width={width}")
                continue
            used = need(widths, n)
            if n > 1 and used > width:
                out.append(
                    f"{n} columns of {label} names need {used}px at a width "
                    f"of {width}px. The count has to leave {gap}px between "
                    f"columns, so the last column clips instead."
                )
            wider = [m for m in range(n + 1, len(widths) + 1)
                     if need(widths, m) <= width]
            if wider:
                out.append(
                    f"{n} columns of {label} names at a width of {width}px "
                    f"wastes the panel: {max(wider)} fit in "
                    f"{need(widths, max(wider))}px."
                )
    return out


def _weight_fields_are_clamped(tab):
    """A Gear Score weight must hold a TYPED value in range.

    Same exposure as the Optimizer's fields and a worse blast radius: a
    weight reaches every Gear Score in the app, so a typed 1e9 skews the
    Memory Fragments list, the Combatants totals and the Optimizer's
    candidate filter at once.

    The range is deliberately wide rather than 0-5, because a NEGATIVE
    weight marks a stat harmful and the panel's own text says so -- a
    clamp that undid those would be worse than none. What it exists for
    is the far ends and text that is not a number.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.utils.spinbox_clamp import commit_clamp

    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)

    out = []
    stat = next(iter(tab.stat_weight_vars), None)
    if stat is None:
        return ["ScoringTab has no stat weight variables at all"]
    var = tab.stat_weight_vars[stat]
    spin = next((w for w in walk(tab.get_frame())
                 if w.winfo_class() == "Spinbox"
                 and str(w.cget("textvariable")) == str(var)), None)
    if spin is None:
        return [f"no Spinbox bound to the {stat} weight"]

    bound = spin.bind()
    for seq in ("<Key-Return>", "<FocusOut>"):
        if seq not in bound:
            out.append(
                f"the {stat} weight has no {seq} binding, so nothing clamps "
                f"what is TYPED into it -- from_/to bound the buttons only."
            )
    lo, hi = float(spin.cget("from")), float(spin.cget("to"))
    if lo >= 0:
        out.append(
            f"the {stat} weight declares from_={lo}, so the clamp would "
            f"snap every NEGATIVE weight to it. Marking a stat harmful is "
            f"a documented feature of this panel."
        )
    for typed, want in ((-3.0, -3.0), (1e9, hi), (-1e9, lo)):
        var.set(typed)
        commit_clamp(spin, var, tab.colors, tab.root, {"good": 1.0})
        if var.get() != want:
            out.append(
                f"the {stat} weight holds {var.get()} after {typed} was "
                f"entered, not {want}, against its declared {lo}..{hi}"
            )
    state = {"good": 1.0}
    spin.delete(0, tk.END)
    spin.insert(0, "abc")
    commit_clamp(spin, var, tab.colors, tab.root, state)
    try:
        got = var.get()
    except tk.TclError:
        got = "still not a number"
    if got != 1.0:
        out.append(
            f"the {stat} weight holds {got!r} after 'abc' was entered. Text "
            f"that is not a number cannot be clamped toward a bound, so the "
            f"field goes back to what it last held."
        )
    var.set(1.0)
    return out


def _character_card_lines_fit():
    """The Character card is a FIXED width, and a long line clips.

    Its panel is sized to `CHAR_CONTENT_PX` and the Text inside carries
    `wrap=tk.NONE`, so a line that outgrows that width is cut off mid
    word with nothing reporting it -- no exception, no reflow, just a
    combatant whose potential node reads `Node 5: Lv3 (CDMG` and stops.

    The line most likely to do it is a potential node's, because its
    third column comes from the game data: a stat with a longer display
    name, a bonus reaching three digits, or a character whose node is
    worded differently lengthens it without anything in this file
    changing.

    **A node line is tab-stopped, so its width is its last STOP plus
    what follows, not the sum of its words.** Two things follow from
    that, and this checks both: the line has to fit the panel, and no
    column may reach past the next stop -- a column that does is not
    overlapped, it pushes the rest of the line right, and the block's
    alignment goes with it on that line alone.

    The level stop is a RIGHT one, so the pair that has to clear it is
    a REAL ROW's label and value together -- not the widest label and
    the widest value, which sit on different rows.

    Returns a list of complaints.
    """
    from tkinter import font as tkfont
    from game_data.characters import (
        CHARACTERS, POTENTIAL_NODES, get_potential_node_does,
        get_potential_stat, get_potential_stat_bonus)
    from game_data.constants import DISPLAY_NAMES
    from ui.tabs.heroes_tab import (
        CHAR_CONTENT_PX, CHAR_NODE_TAB_DESC, CHAR_NODE_TAB_LEVEL,
        CHAR_NODE_TAKEN, CHAR_NODE_UNTAKEN, CHAR_SUBLIST_INDENT)

    measure = tkfont.nametofont("TkDefaultFont").measure
    out = []
    widest = {"does": ("", 0)}
    pair = ("", 0)

    def consider(column, text):
        if text and measure(text) > widest[column][1]:
            widest[column] = (text, measure(text))

    for node in POTENTIAL_NODES:
        label = f"{CHAR_SUBLIST_INDENT}Node {node.shown}:"
        levels = ((CHAR_NODE_TAKEN, CHAR_NODE_UNTAKEN)
                  if node.max_level == 1
                  else tuple(str(v) for v in range(node.max_level + 1)))
        for level in levels:
            width = measure(label) + measure(level)
            if width > pair[1]:
                pair = (f"{label}{level}", width)

    for res_id, data in CHARACTERS.items():
        if not isinstance(data, dict):
            continue
        for node in POTENTIAL_NODES:
            if not node.stat:
                consider("does", get_potential_node_does(res_id, node))
                continue
            for level in range(0, node.max_level + 1):
                stat, bonus = get_potential_stat_bonus(
                    res_id, node.wire, level)
                if stat is None:
                    stat, bonus = get_potential_stat(res_id, node.wire), None
                if stat is None:
                    continue
                what = DISPLAY_NAMES.get(stat, stat)
                if bonus:
                    what = f"{what} +{bonus:g}%"
                consider("does", what)

    if pair[1] > CHAR_NODE_TAB_LEVEL:
        out.append(
            f"the node block's widest name-and-level row is {pair[1]}px "
            f"({pair[0]!r}) against the level column's right stop at "
            f"{CHAR_NODE_TAB_LEVEL}. A row that does not fit before its "
            f"stop pushes the rest of the line right instead of "
            f"overlapping, so that line alone comes out of the columns."
        )
    if CHAR_NODE_TAB_DESC <= CHAR_NODE_TAB_LEVEL:
        out.append(
            f"the description stop is at {CHAR_NODE_TAB_DESC}, not past "
            f"the level column's right stop at {CHAR_NODE_TAB_LEVEL}. "
            f"Every level ends on that stop, so a description starting at "
            f"or before it is pushed right on every line."
        )

    text, width = widest["does"]
    if CHAR_NODE_TAB_DESC + width > CHAR_CONTENT_PX:
        out.append(
            f"the Character card's widest node line is "
            f"{CHAR_NODE_TAB_DESC + width}px ({text!r} at the description "
            f"stop) against CHAR_CONTENT_PX = {CHAR_CONTENT_PX}. The panel "
            f"is a fixed width and the Text does not wrap, so this clips "
            f"silently. Raise CHAR_CONTENT_PX or shorten the wording."
        )

    # The DETAILS line takes the widest-line title back whenever no
    # node's wording runs longer, and it is built from a combatant's
    # element and class -- so a combination the tables carry but the
    # account does not own would clip on the day it is obtained, with
    # nothing before then to say so. Measured over every pair in
    # CHARACTERS, not over the roster.
    line, width = _widest_details_line(measure)
    if width > CHAR_CONTENT_PX:
        out.append(
            f"the Character card's widest details line is {width}px "
            f"({line!r}) against CHAR_CONTENT_PX = {CHAR_CONTENT_PX}. That "
            f"combatant's card clips as soon as one is obtained -- the "
            f"panel is a fixed width and the Text does not wrap."
        )
    return out


def _widest_details_line(measure):
    """(line, px) for the widest first line any combatant can render.

    Its shape is `<level>  |  <grade>*  |  <element>  |  <class>`, with
    the element alone where the two words match -- which is what an
    entry the tables do not place looks like, and is narrower.

    The level is `61/62`, the widest a two-part level can be at the
    promotion cap.
    """
    from game_data.characters import CHARACTERS

    best = ("", 0)
    for data in CHARACTERS.values():
        if not isinstance(data, dict):
            continue
        element, klass = data.get("attribute"), data.get("class")
        tail = element if klass == element else f"{element}  |  {klass}"
        line = f"61/62  |  {data.get('grade')}*  |  {tail}"
        if measure(line) > best[1]:
            best = (line, measure(line))
    return best


def _show_missing_adds_rather_than_replaces(tab):
    """`Show missing characters` ADDS to the roster, never swaps it.

    Three ways it goes wrong quietly:

    * building the roster from `CHARACTERS` alone instead of unioning
      with it drops any combatant the capture knows and this build does
      not -- a release without a table entry yet, which is exactly when
      the list matters most.
    * a missing row has no capture data, so every number on it is a
      placeholder. Showing a real-looking 0 for Level or Affinity reads
      as an owned combatant at rock bottom.
    * a new Element in `ATTRIBUTE_COLORS` with no dimmed variant leaves
      its missing rows on Tk's default foreground, which on this theme
      is near-invisible.

    Skips itself with no roster.

    Returns a list of complaints.
    """
    from game_data.characters import ATTRIBUTE_COLORS
    from ui.tabs.heroes_tab import HERO_TAG_MISSING, HERO_TAG_UNKNOWN

    out = []
    for element in list(ATTRIBUTE_COLORS) + [HERO_TAG_UNKNOWN]:
        if not tab.hero_tree.tag_configure(HERO_TAG_MISSING + element,
                                           "foreground"):
            out.append(
                f"no dimmed row colour for {element!r}. A missing row wears "
                f"one tag and one colour, so without it the row falls back "
                f"to the theme's default foreground."
            )

    if tab.show_missing_var is None:
        return out + ["HeroesTab has no `Show missing characters` variable"]

    from models.character_info import CharacterInfo

    # A combatant the CAPTURE knows and CHARACTERS does not -- a release
    # without a table entry yet. Planted rather than hoped for: in a
    # roster where every owned combatant happens to be in CHARACTERS,
    # replacing the set and unioning it give the same answer, and the
    # bug this is about would pass.
    # ASCII, because it reaches a failure message and those print to
    # a cp932 console.
    unknown = "<uncaptured probe>"
    was = tab.show_missing_var.get()
    tab.optimizer.character_info[unknown] = CharacterInfo(
        res_id=0, name=unknown)
    try:
        tab.show_missing_var.set(False)
        tab.refresh_heroes()
        owned = {h["name"] for h in tab.hero_data_list}
        if not owned:
            return out

        tab.show_missing_var.set(True)
        tab.refresh_heroes()
        shown = {h["name"] for h in tab.hero_data_list}
        if not owned <= shown:
            out.append(
                f"turning it on DROPPED {sorted(owned - shown)}. The roster "
                f"is the union of what the capture holds with CHARACTERS, "
                f"never CHARACTERS alone."
            )
        for row in tab.hero_data_list:
            if not row.get("missing"):
                continue
            index = tab.hero_data_list.index(row)
            values = tab.hero_tree.item(str(index), "values")
            wrong = [c for c in (4, 5, 6) if values[c] != "-"]
            if wrong:
                out.append(
                    f"{row['name']} is missing but reads "
                    f"{[values[c] for c in wrong]} for Level/Ego/Affinity. "
                    f"There is no capture data behind those, so a number "
                    f"there reads as an owned combatant at rock bottom."
                )
            break
    finally:
        tab.optimizer.character_info.pop(unknown, None)
        tab.show_missing_var.set(was)
        tab.refresh_heroes()
    return out


def _combatant_selection_survives_a_rebuild(tab):
    """A rebuilt list must come back to the same combatant.

    `refresh_heroes` clears the tree and rebuilds it, and it runs on
    every live update -- so upgrading one fragment in game would drop
    the selection to row 0 and swap the detail pane out from under the
    reader. It also runs on a re-sort, where landing on row 0 loses the
    combatant being looked at.

    The restore has to be by NAME. An index kept across the rebuild
    lands on whoever took that row, which looks like it worked in a
    roster sorted by name and fails the moment the sort changes.

    Skips itself with no roster: the check needs the maintainer's
    captured data to have two combatants to move between.

    Returns a list of complaints.
    """
    tab.refresh_heroes()
    names = [h["name"] for h in tab.hero_data_list]
    if len(names) < 2:
        return []

    out = []
    target = names[len(names) // 2]
    tab.select_hero_row(names.index(target))

    tab.refresh_heroes()
    got = tab.hero_data_list[tab.selected_hero_index]["name"]
    if got != target:
        out.append(
            f"a rebuild moved the selection from {target!r} to {got!r}. "
            f"`refresh_heroes` has to read the selected NAME before it "
            f"clears the list and find it again afterwards."
        )

    tab.sort_heroes("gs")
    got = tab.hero_data_list[tab.selected_hero_index]["name"]
    if got != target:
        out.append(
            f"re-sorting moved the selection from {target!r} to {got!r}. "
            f"Restoring by index rather than by name does exactly this."
        )
    return out


def _capture_log_colours_its_values(tab):
    """The Upgraded line's parts must each keep their own colour.

    Tk breaks a tie between two tags covering one range by the order
    they were CREATED, latest winning. The whole line already carries a
    tag when it is inserted, so a per-word tag created EARLIER is
    silently outranked -- the line goes one flat colour and nothing
    reports it. That is the failure this holds: the value tags are
    defined after the four line tags, and must stay there.

    It also pins the two shapes apart. A range's floor is dim and its
    ceiling is judged against `LOG_VALUE_POOR`; a fragment with no
    upgrades left prints ONE number, which is a ceiling and must not be
    read as a floor.

    And it pins the two item marks, which say opposite things and are
    easy to confuse: an id no table names is dim yellow, a NAME that
    may not stay its item's is red. The red one is the warning, because
    nothing else on the line says the name was a guess.

    Returns a list of complaints.
    """
    from game_data.constants import PROVISIONAL_NAMES, item_names

    log = tab.capture_log
    line = ("[LIVE] Upgraded Set Slot IV +3. "
            "Highest Potential: 21-80 Fast, 15-38 Bulk")
    single = "[LIVE] Upgraded Set Slot I +5. Highest GS: 82 Fast, 31 Bulk"
    deleted = "[LIVE] Deleted Set Slot VI +0"
    created = "[LIVE] Created Set Slot III +0"
    # An id nothing names, and a name that may not last, on one line.
    named = item_names()
    watched = sorted(name for name in
                     (named.get(rid) for rid in PROVISIONAL_NAMES) if name)
    received = "[LIVE] Received %s +16, 9999999 +1" % (
        watched[0] if watched else "Premium Battle Memory")
    for msg in (line, single, deleted, created, received):
        tab.capture_log_msg(msg, "info")

    out = []
    missing = sorted(rid for rid in PROVISIONAL_NAMES if not named.get(rid))
    if missing:
        out.append(
            f"{missing!r} is in PROVISIONAL_NAMES but no table names it, so "
            f"the Capture Log has no name to draw red and the warning is "
            f"silently absent. An id belongs in RECORDED_NAMES first.")

    def tag_over(row, needle, text):
        col = text.index(needle)
        names = log.tag_names(f"{row}.{col}")
        return names[-1] if names else None

    for row, text, wanted in (
        (1, line, {"Upgraded": "event_good", "21": "value_floor",
                   "80": "value_good", "38": "value_poor",
                   "Fast": "preset_name"}),
        (2, single, {"Upgraded": "event_good", "82": "value_good",
                     "31": "value_poor", "Bulk": "preset_name"}),
        (3, deleted, {"Deleted": "event_bad"}),
        (4, created, {"Created": "event_new"}),
        (5, received, ({watched[0]: "item_provisional",
                        "9999999": "item_unknown"} if watched
                       else {"9999999": "item_unknown"})),
    ):
        for needle, expected in wanted.items():
            got = tag_over(row, needle, text)
            if got != expected:
                out.append(
                    f"in {text!r}, {needle!r} is drawn by tag {got!r}, not "
                    f"{expected!r}. A value tag has to be created AFTER "
                    f"the line tags in `setup_ui`, or the line's own tag "
                    f"outranks it and the whole line goes one colour."
                )
    return out


def _all_none_panels_carry_no_left_padding(built):
    """Why the four All/None panels must keep 0 on their left.

    `border edge -> button` and `border edge -> first non-button
    element` are separate rules with different targets, and inside these
    four panels they answer to separate levers -- `EDGE_PAD` in
    `ui/utils/all_none_row.py` for the buttons, each block's own padx
    for the content. A LabelFrame's `padding` insets every child alike,
    so a non-zero LEFT component there rides both at once and the two
    rules cannot be set independently -- all four `All` buttons follow
    the content off target.

    Returns a list of complaints.
    """
    import tkinter as tk

    wanted = {
        "InventoryTab": ("Slots", "Sets", "Main Stats"),
        "OptimizerTab": ("Exclude Combatant's MFs",),
    }
    out = []
    for attr, titles in wanted.items():
        tab = built.get(attr)
        if tab is None:
            continue

        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)

        by_title = {}
        for w in walk(tab.get_frame()):
            if w.winfo_class() != "TLabelframe":
                continue
            try:
                by_title[str(w.cget("text"))] = w
            except tk.TclError:
                pass
        for title in titles:
            frame = by_title.get(title)
            if frame is None:
                out.append(
                    f"{attr}: no LabelFrame titled {title!r}. The All/None "
                    f"unlink check locates panels by their visible title."
                )
                continue
            padding = frame.cget("padding")
            parts = (padding if isinstance(padding, (tuple, list))
                     else str(padding).split())
            left = int(str(parts[0])) if parts else 0
            if left:
                out.append(
                    f"{title!r} carries a left padding of {left}. That "
                    f"insets its All/None buttons AND its content alike, "
                    f"so `border edge -> button` and `border edge -> "
                    f"first non-button element` stop being separately "
                    f"settable -- put the inset on the block's own padx "
                    f"and leave this at 0."
                )
    return out


def _every_popup_closes_on_escape():
    """Every window the app opens over the main one answers to Escape.

    A window with no Escape is only noticed by someone who presses it,
    and pressing it is the first thing anyone tries on a dialog. The
    `messagebox` ones get it from Windows; the three this app builds
    itself have to ask.

    Scoped to the CLASS or module holding the `Toplevel`, not to the
    function: the tooltip wires the key where the focus is rather than
    on the popup -- a window with `wm_overrideredirect` set never
    receives a keystroke -- so the call sits in a different method of
    the same class.

    Returns a list of complaints.
    """
    out = []
    for path in sorted((SOURCE_ROOT / "ui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Innermost class (else the module) for each node, so a
        # Toplevel can be checked against the scope that would hold the
        # binding.
        scope_of = {}
        for scope in [tree] + [n for n in ast.walk(tree)
                               if isinstance(n, ast.ClassDef)]:
            for node in ast.walk(scope):
                scope_of[node] = scope
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Toplevel"):
                continue
            scope = scope_of.get(node, tree)
            wired = any(
                (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                 and c.func.id == "close_on_escape")
                or (isinstance(c, ast.Constant) and c.value == "<Escape>")
                for c in ast.walk(scope))
            if not wired:
                out.append(
                    f"{path.name} line {node.lineno} opens a Toplevel that "
                    f"nothing closes on Escape. Call `close_on_escape` on "
                    f"it -- or, for a window that takes no keyboard focus, "
                    f"bind the key where the focus is."
                )
    return out


def _breakdown_text_stays_ascii():
    """The Stat Contributions block must hold no character Consolas lacks.

    The popup is set in Consolas and sized from it. A character that
    face has no glyph for is drawn from another at another width -- a
    check mark and a cross measured 13px against a 7px cell -- so the
    line is wider than the field reserved for it and is clipped, with
    nothing reporting it. The width is measured rather than counted for
    that reason, but the marks were also unreadable at that size, so
    the text is plain ASCII and this is what keeps it so.

    Reads the string CONSTANTS in `_format_breakdown_text`. The values
    interpolated into them are numbers and combatant names, which the
    game supplies.

    Returns a list of complaints.
    """
    tree = ast.parse((SOURCE_ROOT / "ui" / "tabs" / "optimizer_tab.py")
                     .read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "_format_breakdown_text"):
            continue
        for const in ast.walk(node):
            if (isinstance(const, ast.Constant)
                    and isinstance(const.value, str)
                    and not const.value.isascii()):
                stray = [c for c in const.value if not c.isascii()]
                out.append(
                    f"_format_breakdown_text line {const.lineno} holds "
                    f"{stray!r}, which Consolas may have no glyph for. The "
                    f"popup sizes itself from that face, so a character "
                    f"drawn from another one is a line wider than the field "
                    f"reserved for it."
                )
        return out
    return ["optimizer_tab.py has no _format_breakdown_text to check"]


def _hero_columns_line_up(tab):
    """The combatant list's three column tuples, and its sort map.

    `zip` pairs ids with titles and widths and STOPS at the shortest,
    so a column added to one tuple and not the others is dropped in
    silence -- the tree still builds, with one fewer column than it has
    values to put in.

    A sort key missing from the map is the same shape of failure: the
    lookup falls back to sorting by name, and a heading click then does
    nothing that looks like nothing.

    And every row's values have to be as long as the id tuple, or the
    cells shift left of the headings from the gap onward.

    Returns a list of complaints.
    """
    from ui.tabs.heroes_tab import (
        HERO_COL_IDS, HERO_COL_PX, HERO_COL_TITLES,
    )

    out = []
    lengths = {"ids": len(HERO_COL_IDS), "titles": len(HERO_COL_TITLES),
               "widths": len(HERO_COL_PX)}
    if len(set(lengths.values())) != 1:
        out.append(
            f"the combatant list's column tuples are {lengths}. They are "
            f"zipped together, so the extra entries are dropped without a "
            f"word."
        )

    tree = getattr(tab, "hero_tree", None)
    if tree is not None:
        if tuple(str(c) for c in tree["columns"]) != tuple(HERO_COL_IDS):
            out.append(
                f"the tree carries columns {tree['columns']}, not "
                f"{HERO_COL_IDS}"
            )
        rows = tree.get_children()
        if rows:
            values = tree.item(rows[0])["values"]
            if len(values) != len(HERO_COL_IDS):
                out.append(
                    f"a row carries {len(values)} values for "
                    f"{len(HERO_COL_IDS)} columns. Every cell after the "
                    f"missing one sits under the wrong heading."
                )

    # The sort map is built inside refresh_heroes, so it is read here
    # off the source rather than off an object.
    source = (SOURCE_ROOT / "ui" / "tabs" / "heroes_tab.py").read_text(
        encoding="utf-8")
    block = source.split("sort_key_map = {", 1)
    if len(block) == 2:
        mapped = set(re.findall(r'"([a-z_]+)":\s*lambda',
                                block[1].split("}", 1)[0]))
        for col in HERO_COL_IDS:
            if col not in mapped:
                out.append(
                    f"column {col!r} has no entry in sort_key_map, so "
                    f"clicking its heading sorts by name instead -- which "
                    f"looks like a heading that does not sort."
                )
    return out


def _level_stepper_offers_auto(tab):
    """AUTO must be reachable, storable, and safe from the level sync.

    `Auto` stores as None, which the optimizer already reads as "take
    the combatant's own level". Three things can quietly take it away
    and none of them raises:

    * a stepper built from `from_`/`to` again, which has no room for a
      word and so drops the stop entirely;
    * the generic clamp, which reads `from`/`to` off the widget -- both
      0 on a `values` spinbox -- and would snap every level to zero;
    * `_sync_optimize_level`, which writes the observed level into the
      entry. Running that over an Auto entry turns the default into a
      choice nobody made, on the first load, for every combatant.

    Returns a list of complaints.
    """
    from ui.tabs.optimizer_tab import LEVEL_AUTO, LEVEL_CHOICES
    from optimizer_settings_manager import _fresh_character_settings

    out = []

    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)

    name = str(tab.optimize_for_level_var)
    spin = next((w for w in walk(tab.get_frame())
                 if w.winfo_class() == "Spinbox"
                 and str(w.cget("textvariable")) == name), None)
    if spin is None:
        return ["no Spinbox bound to the Optimize for LVL variable"]

    values = tuple(str(v) for v in spin.cget("values"))
    if values != tuple(LEVEL_CHOICES):
        out.append(
            f"the level stepper offers {values}, not {tuple(LEVEL_CHOICES)}. "
            f"AUTO has to be one of its stops: it is not a number, so a "
            f"stepper bounded by from_/to cannot reach it at all.")
    elif str(spin.cget("wrap")) not in ("0", "false", "False"):
        out.append(
            "the level stepper wraps, so stepping below 60 comes back "
            "round at 62 instead of stopping on Auto.")
    else:
        tab.optimize_for_level_var.set(LEVEL_CHOICES[1])
        spin.invoke("buttondown")
        if tab.optimize_for_level_var.get() != LEVEL_AUTO:
            out.append(
                f"stepping one below {LEVEL_CHOICES[1]} reached "
                f"{tab.optimize_for_level_var.get()!r} rather than "
                f"{LEVEL_AUTO!r}, which is the only way into Auto from the "
                f"buttons -- there is no level under 60 to type.")

    # The clamp, called rather than typed: Tk delivers no key event to
    # an unmapped widget.
    for typed, want in (("55", LEVEL_AUTO), ("99", LEVEL_CHOICES[-1]),
                        ("nonsense", LEVEL_CHOICES[2])):
        tab.optimize_for_level_var.set(LEVEL_CHOICES[2])
        tab._commit_level_clamp()
        tab.optimize_for_level_var.set(typed)
        tab._commit_level_clamp()
        got = tab.optimize_for_level_var.get()
        if got != want:
            out.append(
                f"typing {typed!r} into the level stepper left {got!r}, "
                f"not {want!r}. `values` bounds the buttons and the wheel "
                f"only -- typed text reaches the variable unchecked, and "
                f"the optimizer then reads a level nobody offered.")

    if _fresh_character_settings("probe")["optimize_for_level"] is not None:
        out.append(
            "a fresh character entry carries a LEVEL rather than None, so "
            "Auto is not the default it is meant to be.")

    # The sync, over an entry on Auto.
    if tab.opt_settings is not None:
        probe_rid, probe_name = "999999", "_probe_combatant_"
        characters = tab.opt_settings.data.setdefault("characters", {})
        kept_entry = characters.get(probe_rid)
        kept_info = tab.optimizer.character_info.get(probe_name)
        seen = tab.opt_settings.data.setdefault("optimize_level_seen", {})
        kept_seen = seen.get(probe_rid)
        try:
            characters[probe_rid] = _fresh_character_settings(probe_name)
            tab.optimizer.character_info[probe_name] = type(
                "_Info", (), {"level": 62})()
            seen.pop(probe_rid, None)
            tab._sync_optimize_level(probe_rid, probe_name)
            after = characters[probe_rid]["optimize_for_level"]
            if after is not None:
                out.append(
                    f"the level sync wrote {after!r} over an entry on Auto. "
                    f"Following the combatant's level is what Auto already "
                    f"does, and the entry is the DEFAULT -- so this fires "
                    f"on the first load for every new combatant and no "
                    f"stepper ever reads Auto again.")
        finally:
            if kept_entry is None:
                characters.pop(probe_rid, None)
            else:
                characters[probe_rid] = kept_entry
            if kept_info is None:
                tab.optimizer.character_info.pop(probe_name, None)
            else:
                tab.optimizer.character_info[probe_name] = kept_info
            if kept_seen is None:
                seen.pop(probe_rid, None)
            else:
                seen[probe_rid] = kept_seen
    return out


def _checklist_redraw_replaces_nothing(tab):
    """A Checklist refresh that changes nothing must rebuild nothing.

    The tab redraws whenever a capture saves, which during a login
    burst is many times a minute, and whenever the tab is shown. If
    that rewrites the columns, every embedded checkbox is destroyed and
    recreated and the Text reflows -- the whole tab blinks, once per
    save, for no change at all.

    Widget IDENTITY is what says so: same data in, same widgets out.
    Comparing the drawn text would pass happily while every widget
    behind it was replaced.

    Returns a list of complaints.
    """
    def widgets(w, out):
        out.append(w)
        for child in w.winfo_children():
            widgets(child, out)
        return out

    frame = tab.get_frame()
    before = widgets(frame, [])
    boxes = sum(len(v) for v in tab._boxes.values())
    tab.refresh_checklist()
    after = widgets(frame, [])
    if len(before) != len(after) or any(a is not b for a, b in
                                        zip(before, after)):
        return [
            f"refreshing the Checklist with unchanged data replaced its "
            f"widgets ({len(before)} before, {len(after)} after, "
            f"{boxes} checkbox(es) in the columns). Every capture save "
            f"triggers this refresh, so the tab blinks each time."
        ]

    # And a changed READING must patch, not rebuild. A countdown moves
    # every time the tab is looked at, so this is the common case, not
    # the rare one.
    #
    # **The column has to be one holding checkboxes.** Only an embedded
    # window is destroyed by a rewrite, so a column of plain rows shows
    # the same widgets either way and would pass without testing
    # anything. With no captured snapshot there are no shop rows at
    # all, and there is nothing here to check.
    with_boxes = [t for t, boxes in tab._boxes.items() if boxes]
    if not with_boxes:
        return []
    title = with_boxes[0]
    text, rows = tab.column_texts[title]
    keyed = [key for key, _label, widest in rows if widest]
    if not keyed:
        return []
    import ui.tabs.checklist_tab as mod
    moved = mod._readings(getattr(tab.optimizer, "raw_data", None) or {})
    moved[keyed[0]] = [("999999", mod.TODO)]
    tab._fill(title, text, rows, moved)
    patched = widgets(frame, [])
    if len(after) != len(patched) or any(a is not b for a, b in
                                         zip(after, patched)):
        return [
            f"changing one reading in the {title} column replaced its "
            f"widgets ({len(after)} before, {len(patched)} after). A row's "
            f"value is its own stretch of the line and can be rewritten "
            f"on its own; rebuilding the block destroys every checkbox in "
            f"it and the reflow shows."
        ]
    if "999999" not in text.get("1.0", "end"):
        return [f"patching the {title} column's first reading did not put "
                f"the new value on screen."]

    # Ticking a box rebuilds ONE column. It has to rebuild that one --
    # an untracked product sinks within its shop, so the rows move --
    # but the other three hold nothing that changed.
    #
    # `_tracked` is swapped rather than the manager written to: the
    # manager saves to `settings/`, which is the maintainer's.
    others = {t: widgets(tab.column_texts[t][0], [])
              for t in tab.column_texts if t != title}
    # **The LAST product of a shop**, which is the case that once got
    # through: untracking it changes its colour and moves no row, so a
    # redraw decided on the row keys alone found them unchanged, left
    # the column standing, and rewrote the Text that was on screen.
    shop_keys = [key for key, _l, _w in rows if mod._is_shop(key)]
    product = mod._product_of(shop_keys[-1])
    original = tab._tracked
    tab._tracked = lambda p, _f=original, _p=product: (
        not _f(_p) if p == _p else _f(p))

    # A rebuilt column must be FILLED BEFORE IT IS SHOWN. Tk destroys
    # an embedded window with its text, so a rebuild always builds new
    # checkboxes, and one built inside a Text that is already on screen
    # appears at the Text's origin until `window_create` places it -- a
    # white dot at the top left of the column, once per box.
    #
    # `winfo_manager()` is what says so headlessly: empty means no
    # geometry manager has the widget, so neither it nor anything
    # inside it can be mapped. `winfo_ismapped` would read False for
    # every widget here, the test root never being shown.
    managers = []
    fill = tab._fill
    tab._fill = lambda t, txt, r, rd, _f=fill: (
        managers.append((t, txt.winfo_manager())), _f(t, txt, r, rd))[1]
    try:
        tab.refresh_checklist()
    finally:
        tab._tracked = original
        tab._fill = fill
    # The FIRST fill of that column is the one that populated it; the
    # refresh's own pass over every column comes after and finds
    # nothing to do, on a Text that is by then rightly packed.
    first = next((manager for t, manager in managers if t == title), None)
    if first:
        return [
            f"the {title} column was filled while its Text was already "
            f"managed by {first!r}. Build the replacement unmanaged, "
            f"fill it, drop the old one and only then pack it -- "
            f"otherwise every checkbox flashes at the column's origin "
            f"before it lands."
        ]
    for other, before_widgets in others.items():
        now = widgets(tab.column_texts[other][0], [])
        if len(before_widgets) != len(now) or any(
                a is not b for a, b in zip(before_widgets, now)):
            return [
                f"ticking a product in the {title} column rebuilt the "
                f"{other} column too. Every column redrawing for a change "
                f"in one is what makes the whole tab blink on a click."
            ]
    tab.refresh_checklist()
    return []


def _log_presets_redraw_replaces_nothing(tab):
    """A Log Presets refresh with unchanged assignments rebuilds nothing.

    It runs on every snapshot load, and a login burst saves several
    times in a few seconds -- so an unconditional rebuild destroys and
    recreates every checkbox two or three times while the user watches.
    That shows as a dot blinking in the corner of the first one.

    Widget IDENTITY is what says so: same assignments in, same widgets
    out. Comparing the labels would pass while every widget behind them
    was replaced.

    Returns a list of complaints.
    """
    def widgets(w, out):
        out.append(w)
        for child in w.winfo_children():
            widgets(child, out)
        return out

    frame = getattr(tab, "log_presets_list_frame", None)
    if frame is None:
        return []
    before = widgets(frame, [])
    tab.refresh_log_presets()
    after = widgets(frame, [])
    if len(before) != len(after) or any(a is not b for a, b in
                                        zip(before, after)):
        return [
            f"refreshing Log Presets with unchanged assignments replaced "
            f"its widgets ({len(before)} before, {len(after)} after). "
            f"Every capture save triggers this refresh, so the checklist "
            f"blinks each time."
        ]
    return []


def _checklist_block_is_tall_enough(tab):
    """A column's fixed height has to match the pitches it draws.

    The rows live in a Text inside a frame with `pack_propagate(False)`
    and a height in PIXELS, so nothing pushes back when the sum is
    wrong: Tk clips whatever does not fit off the bottom and the column
    simply ends a row early. Three different pitches feed it now -- an
    ordinary row, a block heading, a checkbox -- plus a pad under the
    last checkbox of a run, and `ROW_TAG_PITCH` is the one table both
    the tags and the height are built from.

    So this holds the two ends together: every tag the Text configures
    carries the `spacing1` the table says, and a column's computed
    height equals the pitches of the rows it actually contains.

    Returns a list of complaints.
    """
    import tkinter as tk
    import tkinter.font as tkfont
    from ui.scaling import px
    from ui.tabs import checklist_tab as mod
    out = []

    texts = [widget for frame in tab._column_frames
             for widget in _descendants(frame)
             if isinstance(widget, tk.Text)]
    if not texts:
        return ["the Checklist built no row blocks, so nothing about "
                "their height can be checked."]

    for tag, pitch in mod.ROW_TAG_PITCH.items():
        got = texts[0].tag_cget(tag, "spacing1")
        if int(got or 0) != px(pitch):
            out.append(
                f"the {tag!r} rows are drawn at spacing1 {got!r} where "
                f"ROW_TAG_PITCH says {px(pitch)}. That table is what "
                f"`_block_height` adds up, so the block is sized for rows "
                f"the Text does not draw and Tk clips the difference.")
    if int(texts[0].tag_cget("boxlast", "spacing3") or 0) != px(mod.BLOCK_PAD):
        out.append(
            "the last checkbox of a run carries no `spacing3`, so nothing "
            "closes a block off below it -- and `_block_height` reserves "
            "room for a pad that is not drawn.")

    # And the height itself, against the rows a column really holds.
    line = tkfont.Font(font=mod.ROW_FONT).metrics("linespace")
    for title, rows in mod.columns_for({}, None, 0, None):
        if not rows:
            continue
        keys = [key for key, _label, _widest in rows]
        want = 0
        for at, key in enumerate(keys):
            below = keys[at + 1] if at + 1 < len(keys) else None
            tags = mod._row_tags(key, below)
            want += line + px(mod.ROW_TAG_PITCH[tags[0]])
            if "boxlast" in tags:
                want += px(mod.BLOCK_PAD)
        got = mod.ChecklistTab._block_height(keys)
        if got != want:
            out.append(
                f"the {title!r} column reserves {got}px for {len(keys)} "
                f"rows where their own pitches come to {want}px. A short "
                f"block clips its last row and nothing reports it.")
    return out


def _checklist_columns_come_first(tab):
    """The Checklist tab's columns frame must be its FIRST child.

    `ui/spacing_registry.py` reaches all four Checklist entries through
    `winfo_children()[0]`, which is CREATION order. Anything built on
    the tab ahead of the columns takes that slot, and the audit then
    reports four skips -- which reads like a green run, since a
    resolver that matches nothing is not a failure.

    The temporary mission listing is what makes this worth pinning: it
    is packed above the columns in the pack order and has to be created
    after them.

    Returns a list of complaints.
    """
    from ui.tabs.checklist_tab import COLUMNS as CHECKLIST_COLUMNS

    children = tab.get_frame().winfo_children()
    if not children:
        return ["the Checklist tab built no children at all"]
    first = children[0]
    columns = [child for child in first.winfo_children()
               if child.winfo_class() in ("TFrame", "Frame")]
    if len(columns) != len(CHECKLIST_COLUMNS):
        return [
            f"the Checklist tab's first child holds {len(columns)} column "
            f"frame(s), not {len(CHECKLIST_COLUMNS)}. The audit reaches "
            f"every Checklist gap through that child, and a resolver that "
            f"finds nothing SKIPS rather than failing -- so the four "
            f"entries would go quiet with the run still green."
        ]
    return []


def _setup_columns_hold_their_shape(tab):
    """The Setup & Settings tab's two columns, and what each is pinned to.

    The LEFT column is fixed to what the instructions need to read
    unwrapped, and `Setup Status`, the buttons and `Setup Instructions`
    all take that width. The RIGHT takes the rest, and its three panels
    share one width and one x.

    **None of that survives a stray `fill` or a lost
    `pack_propagate`.** A column that resumes sizing to its children
    still LOOKS laid out -- the panels are all still there, at widths
    nobody chose -- so the pinning is checked here rather than on a
    screen.

    Structural, because rendered geometry needs a mapped window: the
    configured width, the propagation flag, and which panels sit in
    which column. Returns a list of complaints.
    """
    from ui.scaling import px
    from ui.tabs.setup_tab import INSTRUCTIONS, SetupTab

    out = []

    def panels_in(widget, found=None):
        found = {} if found is None else found
        for child in widget.winfo_children():
            if child.winfo_class() == "TLabelframe":
                found[child.cget("text")] = child
            panels_in(child, found)
        return found

    # main_frame -> [header..., columns]; the columns frame is the one
    # holding two plain frames and nothing else.
    columns = None
    for frame in tab.get_frame().winfo_children():
        for child in frame.winfo_children():
            kids = child.winfo_children()
            if (len(kids) == 2
                    and all(k.winfo_class() == "TFrame" for k in kids)
                    and panels_in(child)):
                columns = child
    if columns is None:
        return ["the Setup & Settings tab has no two-column frame; the layout that "
                "pins Setup Instructions' width has gone."]

    left, right = columns.winfo_children()
    want = px(SetupTab._instructions_width())
    if int(left.cget("width")) != want:
        out.append(
            f"the Setup & Settings tab's left column is {left.cget('width')}px wide, "
            f"not the {want} the instructions need. That width is what "
            f"keeps the block from wrapping, and a wrapped line is not a "
            f"crash -- it just reads wrong.")
    left_panels = set(panels_in(left))
    right_panels = list(panels_in(right))
    if left_panels != {"Setup Status", "Setup Instructions", "Links"}:
        out.append(
            f"the Setup & Settings tab's left column holds {sorted(left_panels)}, not "
            f"Setup Status, Setup Instructions and Links. Those three "
            f"share the column's fixed width; anything else in there is "
            f"pinned to a width chosen for something it is not.")
    if set(right_panels) != {"Restore Defaults", "Update Status", "Settings",
                             "Application Information"}:
        out.append(
            f"the Setup & Settings tab's right column holds {sorted(right_panels)}, "
            f"not Restore Defaults, Update Status, Settings and "
            f"Application Information. The four are stacked so they share "
            f"one width and one x.")

    # The two bottom panels are held to ONE height, so the row they
    # make ends on a straight edge. The linking runs on an idle
    # callback the build never reaches, so it is called here -- it is
    # idempotent, and calling it is what makes the reading mean
    # anything.
    tab.link_bottom_heights()
    heights = {name: int(panels_in(columns)[name].cget("height"))
               for name in ("Links", "Application Information")
               if name in panels_in(columns)}
    if len(heights) == 2 and len(set(heights.values())) != 1:
        out.append(
            f"Links and Application Information are {heights} tall. They "
            f"sit on one row and are pinned to the taller of the two, so "
            f"a mismatch is a `_link_heights` that no longer runs -- and "
            f"a ragged bottom edge is the only symptom.")

    text = None
    for widget in _descendants(tab.get_frame()):
        if (widget.winfo_class() == "Text"
                and str(widget.cget("wrap")) == "word"):
            text = widget
    if text is not None:
        lines = len(INSTRUCTIONS.splitlines())
        if int(text.cget("height")) != lines:
            out.append(
                f"the instructions are {lines} lines and their Text asks "
                f"for {text.cget('height')}. The panel is meant to end "
                f"where the text does -- a taller one leaves dead space "
                f"and a shorter one hides a line behind a scrollbar.")
    return out


def _descendants(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _descendants(child)


def _materials_figures_fit(tab):
    """No figures block may draw past the frame it is pinned inside.

    A block is a frame fixed to the pixel with its propagation off, so
    a column that lands too far right is CLIPPED rather than making the
    frame wider -- and a clipped figure looks like a shorter one, which
    is not a state the eye can tell apart from the truth.

    Two things push a column right, and both are silent. A stop exactly
    one reservation past the one before it leaves no room for the tab
    that reaches it, so Tk starts the text a tab floor further along
    and the overshoot ACCUMULATES across a row of columns. And a value
    wider than the reservation -- a five-digit total against four
    digits of column -- takes the same path on its own.

    Simulated from the fonts rather than measured off the screen: the
    pen starts at zero, each field is right-aligned to its stop unless
    that would put it less than a tab floor past the field before it.

    A value is measured at the WIDER of what it draws and what its
    column reserves, so the structural case is caught with no snapshot
    loaded -- every figure reads `-` before one arrives, and a row of
    dashes fits inside a layout that a row of `400%` would not.
    Returns a list of complaints.
    """
    from tkinter import font as tkfont
    from ui.tabs.materials_tab import (
        COLUMN_SEP, MaterialsTab, STAT_FONT, TAB_FLOOR_PX)

    out = []
    stat = tkfont.Font(font=STAT_FONT)
    reserved = MaterialsTab._value_column_px()
    blocks = [(key, row[0]) for key, row in tab.material_stats.items()]
    blocks += [(("advanced", index), figures)
               for index, (figures, _ids) in tab.advanced_stats.items()]
    if getattr(tab, "gacha_figures", None) is not None:
        blocks.append((("gacha",), tab.gacha_figures))

    for key, text in blocks:
        width = int(text.master.cget("width"))
        stops = [int(x) for x in text.cget("tabs") if str(x).isdigit()]
        for line in text.get("2.0", "end-1c").splitlines():
            pen = 0
            for index, field in enumerate(line.split(COLUMN_SEP)[1:]):
                span = stat.measure(field)
                if index:
                    span = max(span, reserved)
                stop = stops[index] if index < len(stops) else width
                pen = max(stop - span, pen + TAB_FLOOR_PX) + span
            if pen > width:
                out.append(
                    f"{key} draws {line.strip()!r} out to {pen}px inside a "
                    f"{width}px block, so its last column is clipped by "
                    f"{pen - width}px. Either a stop sits less than a tab "
                    f"floor past the one before it, or a figure is wider "
                    f"than the column reserved for it -- a fixed-width "
                    f"holder cannot grow to take either.")
    return out


def _materials_rows_each_register(tab):
    """Every Materials row must own a figures block, and its own.

    The blocks are keyed by (column, row name) and filled in a loop
    whose variable once SHADOWED the row's name parameter -- so every
    row registered under the last figure's label instead, the keys
    collided, and nineteen rows became five. Nothing raised: the tab
    built, the icons drew, and only the rows that happened to win a key
    ever updated their numbers.

    Also holds each checkbox to its OWN column. One variable shared
    across the three would move all of them together, which reads as
    working until you own different amounts of the three generics.

    Returns a list of complaints.
    """
    from ui.tabs.materials_tab import (
        COLUMNS, COLUMN_SEP, TOTAL_LABEL)

    out = []
    want = sum(len(spec.names) + (1 if spec.levelling else 0)
               for spec in COLUMNS)
    if len(tab.material_stats) != want:
        out.append(
            f"the Materials tab registered {len(tab.material_stats)} figure "
            f"blocks for {want} rows. Keys are (column, row name) and a "
            f"collision loses a row silently -- it still draws, it just "
            f"stops updating."
        )

    for spec_index, spec in enumerate(COLUMNS):
        for name in spec.names:
            key = (spec_index, name)
            if key not in tab.material_stats:
                out.append(f"no figures registered for {key}")
                continue
            # A block is ONE Text, so its figures are read off its lines
            # rather than off a dict of widgets. Every column in it is a
            # right-aligned tab stop, the label's included, so the line
            # OPENS with a tab and the label is the field after it.
            figures = tab.material_stats[key][0]
            drawn = [line.split(COLUMN_SEP)[1] for line
                     in figures.get("2.0", "end-1c").splitlines()]
            wanted = [TOTAL_LABEL] + [word for word, _cost in spec.targets]
            if drawn != wanted:
                out.append(
                    f"{key} carries figures {drawn}, not {wanted}"
                )
            if not tab.material_stats[key][6]:
                out.append(
                    f"{key} is a promotion row that refuses the column's "
                    f"generic. Its stand-in IS that family's bottom tier, "
                    f"so the checkbox has nothing left to do."
                )
        if spec.levelling and tab.material_stats.get(
                (spec_index, spec.levelling[0]), (None,) * 7)[6]:
            out.append(
                f"the {spec.key} column's EXP row takes the generic into "
                f"its total. A Certificate raises a level ceiling and buys "
                f"no exp, so the checkbox would inflate a figure that has "
                f"nothing to do with it -- and it would still look like a "
                f"number."
            )

    # What makes a column's icons line up is that every row is pinned
    # by its RIGHT edge, since every row ends in its icons. Centred
    # instead, a row reserving a different width is centred on less or
    # more and its icons land off the tier column above -- the generic
    # row had no figures block at all and sat 52px out that way, and
    # three rows now differ in width on purpose.
    holders = tab.get_frame().winfo_children()
    from ui.tabs.materials_tab import ICON_GAP_HALF, icon_size
    cell = icon_size()[0] + 2 * ICON_GAP_HALF
    for column in (holders[0].winfo_children() if holders else ()):
        parts = column.winfo_children()
        if len(parts) < 2:
            continue
        title = str(parts[0].cget("text"))
        for position, row in enumerate(parts[1].winfo_children()):
            halves = row.winfo_children()
            if not halves:
                continue
            if str(row.pack_info().get("anchor")) != "e":
                out.append(
                    f"{title!r} row {position} is anchored "
                    f"{row.pack_info().get('anchor')!r}, not 'e'. The rows "
                    f"are pinned by the right edge because that is where "
                    f"their icons are; anchored any other way, a row of a "
                    f"different width puts its icons off the column."
                )
            # And each row's icon half has to be a whole number of icon
            # cells wide, or the icons inside it sit off the tier
            # columns even with the row itself in the right place.
            span = halves[-1].winfo_reqwidth()
            if span % cell:
                out.append(
                    f"{title!r} row {position} has an icon block {span}px "
                    f"wide, which is not a multiple of an icon cell's "
                    f"{cell}px."
                )

    # The gaps ACROSS the block have to stay equal, and what keeps them
    # equal is where the tab's leftover width goes. Given to the content
    # cells it lands unequally -- the widest column keeps the least --
    # and the gaps ran 31, 19 and 5 that way. So: content columns take
    # no weight, and the odd columns between them share one uniform
    # group. Checked as configuration because the geometry that would
    # show it needs a mapped window.
    if holders:
        grid = holders[0]
        wanted = 2 * len(COLUMNS) + 1
        for index in range(wanted):
            weight = int(grid.grid_columnconfigure(index)["weight"])
            uniform = str(grid.grid_columnconfigure(index)["uniform"] or "")
            spacer = index % 2 == 1
            if spacer and (weight != 1 or not uniform):
                out.append(
                    f"Materials grid column {index} sits between two of the "
                    f"block's columns and is weight {weight}, uniform "
                    f"{uniform!r}. It has to take an equal share of the "
                    f"leftover width or the gaps across the block go uneven."
                )
            if not spacer and weight != 0:
                out.append(
                    f"Materials grid column {index} holds content and is "
                    f"weight {weight}. Leftover width given to a content "
                    f"cell is absorbed inside it, unequally."
                )

    variables = {id(var) for var in tab.include_generic_vars.values()}
    if len(variables) != len(COLUMNS):
        out.append(
            f"the {len(COLUMNS)} `Add to totals` checkboxes share "
            f"{len(variables)} variable(s). A column's generic stands in "
            f"for that column's bottom tier and no other's, so one switch "
            f"per column is the whole point of them."
        )
    return out


def _popup_sample_drives_its_own_width(root):
    """The audit's contributions sample must be wider than the button row.

    The popup's text field is packed to EXPAND, so whichever child asks
    for the most width sets the window and the field stretches to it.
    Where that child is the Close button, every horizontal reading
    inside the field describes the button's width instead of the
    field's own inset -- and reads as a plain miss at the site, which is
    the wrong place to look.

    A window manager's minimum width for a titled window is the other
    floor and cannot be queried; a sample wide enough to clear the
    button clears that too by a distance.

    Returns a list of complaints.
    """
    from tkinter import ttk
    from tkinter import font as tkfont
    from ui.spacing_registry import POPUP_SAMPLE
    from ui.utils.button_width import BUTTON_W_SMALL

    button = ttk.Button(root, text="Close", width=BUTTON_W_SMALL)
    try:
        root.update_idletasks()
        needs = button.winfo_reqwidth()
    finally:
        button.destroy()

    face = tkfont.Font(font=("Consolas", 10))
    lines = POPUP_SAMPLE.split("\n")
    # The field's own `padx` twice, and its pack pad twice.
    widest = max(face.measure(line) for line in lines) + 16
    out = []
    if widest <= needs:
        out.append(
            f"the audit's popup sample is {widest}px wide against a "
            f"{needs}px button row, so the text field stretches and every "
            f"horizontal gap measured inside it reads the stretch. Widen "
            f"POPUP_SAMPLE in ui/spacing_registry.py."
        )
    if not lines[0][:1].isupper():
        out.append(
            f"the popup sample's first line starts {lines[0][:1]!r}, not a "
            f"capital. Its top inset is read from the first CAPITAL."
        )
    if lines[-1][-1:] in tuple("gjpqy"):
        out.append(
            f"the popup sample's last line ends {lines[-1][-1]!r}, a "
            f"descender. Its bottom inset is read from the baseline, and a "
            f"descender reports three tighter than the rule asks."
        )
    return out


def _restore_dialog_frames_follow_the_rules(tab, root):
    """The Restore Defaults dialog's two panels, built without a window.

    Nothing else reaches inside this dialog: it exists only while the
    user has it open, so `setup_ui` never builds it and a name deleted
    from under it raises on a click rather than on a launch. The two
    frame builders take a plain parent, which is what lets them be
    exercised here -- building the real `Toplevel` would put a window on
    the maintainer's screen mid-check.

    What it holds them to is the pair of rules that share a lever
    everywhere else: a LabelFrame `padding` insets its All/None buttons
    and its content alike, so the left and right components stay 0 and
    the row comes from `make_all_none_row` rather than being built again
    by hand.

    Returns a list of complaints.
    """
    import tkinter as tk
    from tkinter import ttk

    parent = ttk.Frame(root)
    out = []
    try:
        missing_data, changed_data = {}, {}
        tab._build_missing_frame(
            parent, [("a", "Alpha"), ("b", "Beta")], missing_data)
        tab._build_changed_frame(
            parent, [("c", "Gamma")], changed_data, True)

        panels = [w for w in parent.winfo_children()
                  if w.winfo_class() == "TLabelframe"]
        if len(panels) != 2:
            return [f"the restore dialog built {len(panels)} panels, not 2"]

        for panel in panels:
            title = str(panel.cget("text"))
            padding = panel.cget("padding")
            parts = (padding if isinstance(padding, (tuple, list))
                     else str(padding).split())
            sides = [int(str(p)) for p in parts] or [0]
            left = sides[0]
            right = sides[2] if len(sides) > 3 else left
            if left or right:
                out.append(
                    f"the restore dialog's {title!r} panel carries "
                    f"padding {left} left / {right} right. That insets its "
                    f"All/None buttons and its rows alike, so `border edge "
                    f"-> button` and `border edge -> first non-button "
                    f"element` stop being separately settable."
                )
            labels = []
            for child in panel.winfo_children():
                for w in child.winfo_children():
                    if w.winfo_class() == "TButton":
                        labels.append(str(w.cget("text")))
            if sorted(labels) != ["All", "None"]:
                out.append(
                    f"the restore dialog's {title!r} panel holds buttons "
                    f"{sorted(labels)} rather than one All/None row. Every "
                    f"such row comes from `make_all_none_row`; a hand-built "
                    f"one is how the four tab panels drifted apart."
                )
    except Exception as e:                                # noqa: BLE001
        out.append(f"the restore dialog's frames raised while building: "
                   f"{type(e).__name__}: {e}")
    finally:
        try:
            parent.destroy()
        except tk.TclError:
            pass
    return out


def run():
    failures = []
    add_source_to_path()

    failures.extend(_every_popup_closes_on_escape())
    failures.extend(_breakdown_text_stays_ascii())

    if not _make_checkbox_forces_its_window():
        failures.append(
            "make_checkbox no longer calls winfo_id(). Tk defers creating "
            "a widget's window until it is mapped, and a tk.Checkbutton's "
            "is erased to the system default before Tk paints it -- so "
            "every checkbox grid flashes light grey the first time its tab "
            "is shown. The call looks like dead code and is not."
        )

    try:
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
    except Exception as e:                    # no display, headless CI
        raise Skip(f"Tk will not start here ({type(e).__name__})")

    work = Path(tempfile.mkdtemp())
    try:
        root.withdraw()
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        live = SOURCE_ROOT / "settings"
        if live.exists():
            shutil.copytree(live, work / "settings")

        import czn_optimizer_gui as gui
        complaint = _scrolled_text_packs_the_pair(root, dict(gui.COLORS))
        if complaint:
            failures.append(complaint)
        import ui.tabs as tabs_pkg
        from ui.context import AppContext
        from optimizer.optimizer import GearOptimizer
        import preset_manager, character_preset_manager
        import optimizer_settings_manager, settings_manager
        import log_presets_manager
        from config import AppConfig
        from ._harness import newest_snapshot

        optimizer = GearOptimizer()
        snap = newest_snapshot()
        if snap:
            optimizer.load_data(snap)

        def _load(cls):
            m = cls(work)
            m.load()
            return m

        sm = _load(settings_manager.SettingsManager)
        ctx = AppContext(
            root=root, notebook=None, optimizer=optimizer,
            capture_manager=None, config=AppConfig(sm),
            colors=dict(gui.COLORS), style=style,
            load_file_callback=None, load_data_callback=None,
            switch_tab_callback=None, refresh_callback=None,
            inventory_tab=None, heroes_tab=None, scoring_tab=None,
            optimizer_tab=None,
            preset_manager=_load(preset_manager.PresetManager),
            character_preset_manager=_load(
                character_preset_manager.CharacterPresetManager),
                settings_manager=sm,
            optimizer_settings_manager=_load(
                optimizer_settings_manager.OptimizerSettingsManager),
            log_presets_manager=_load(log_presets_manager.LogPresetsManager),
            recompute_upgrade_line_callback=None,
        )

        notebook = ttk.Notebook(root)
        ctx.notebook = notebook
        built = {}
        for attr in TAB_ATTRS:
            cls = getattr(tabs_pkg, attr, None)
            if cls is None:
                failures.append(f"{attr} is not exported from ui.tabs")
                continue
            try:
                built[attr] = cls(notebook, ctx)
            except Exception as e:
                failures.append(
                    f"{attr} raised while building: "
                    f"{type(e).__name__}: {e}"
                )

        if "OptimizerTab" in built:
            failures.extend(_percent_fields_are_clamped(built["OptimizerTab"]))
            failures.extend(
                _level_stepper_offers_auto(built["OptimizerTab"]))
        failures.extend(_all_none_panels_carry_no_left_padding(built))
        failures.extend(_character_card_lines_fit())
        if "ScoringTab" in built:
            failures.extend(_weight_fields_are_clamped(built["ScoringTab"]))
        if "HeroesTab" in built:
            failures.extend(
                _combatant_selection_survives_a_rebuild(built["HeroesTab"]))
            failures.extend(
                _show_missing_adds_rather_than_replaces(built["HeroesTab"]))
            failures.extend(
                _hero_columns_line_up(built["HeroesTab"]))
        failures.extend(_popup_sample_drives_its_own_width(root))
        if "MaterialsTab" in built:
            failures.extend(
                _materials_rows_each_register(built["MaterialsTab"]))
            failures.extend(
                _materials_figures_fit(built["MaterialsTab"]))
        if "SetupTab" in built:
            failures.extend(_restore_dialog_frames_follow_the_rules(
                built["SetupTab"], root))
            failures.extend(
                _setup_columns_hold_their_shape(built["SetupTab"]))
        if "ChecklistTab" in built:
            failures.extend(
                _checklist_columns_come_first(built["ChecklistTab"]))
            failures.extend(
                _checklist_redraw_replaces_nothing(built["ChecklistTab"]))
            failures.extend(
                _checklist_block_is_tall_enough(built["ChecklistTab"]))
        if "CaptureTab" in built:
            failures.extend(
                _capture_log_colours_its_values(built["CaptureTab"]))
            failures.extend(
                _log_preset_columns_leave_the_gap(built["CaptureTab"]))
            failures.extend(
                _log_presets_redraw_replaces_nothing(built["CaptureTab"]))
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
