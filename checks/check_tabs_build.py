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

from types import SimpleNamespace

from ._harness import (add_source_to_path, SOURCE_ROOT, Skip,
                       newest_snapshot, note)

NAME = "tabs build"

# About is static and out of the spacing work's scope, but it is cheap
# to build and a missing name would break the notebook the same way, so
# it is here too.
TAB_ATTRS = ("SetupTab", "CaptureTab", "InventoryTab", "OptimizerTab",
             "HeroesTab", "ScoringTab", "MaterialsTab",
             "ChecklistTab", "GachaHistoryTab")


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


def _title_bar_takes_its_colours(root):
    """Windows takes every title bar attribute the app sets.

    DWM answers an attribute id, size or value it does not know with an
    error code rather than an exception, and the caption simply stays
    Windows' default -- nothing else would ever say so. Set on a window
    at alpha 0, which is mapped and so has a frame, but never seen.

    Returns a list of complaints.
    """
    import sys
    import tkinter as tk
    from ui.title_bar import FIRST_DARK_BUILD, style_title_bar
    if sys.platform != "win32":
        return []
    top = tk.Toplevel(root)
    try:
        top.attributes("-alpha", 0.0)
        top.update_idletasks()
        results = style_title_bar(top, "#cdd6f4")
    finally:
        top.destroy()
    build = sys.getwindowsversion().build
    if build >= FIRST_DARK_BUILD and not results:
        return [f"Windows build {build} takes a title bar colour, and "
                f"`style_title_bar` set nothing."]
    failed = [hex(r & 0xFFFFFFFF) for r in results if r != 0]
    if failed:
        return [f"Windows refused title bar attributes with {failed}: the "
                f"caption stays its default colour and nothing says so. "
                f"Check the attribute ids and sizes in `ui/title_bar.py`."]
    return []


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
    # A row can stand for SEVERAL products -- see `shop_display_rows`
    # -- and it reads as tracked while any of them does, so the whole
    # group has to flip for the row to change at all.
    products = set(mod._products_of(shop_keys[-1]))
    original = tab._tracked
    tab._tracked = lambda p, _f=original, _ps=products: (
        not _f(p) if p in _ps else _f(p))

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


def _set_filters_redraw_replaces_nothing(tab):
    """The Memory Fragments filters rebuild only when their words change.

    Both load paths call `populate_set_filters`, and the live one runs
    on every snapshot save -- a login burst is several in a few
    seconds. Each call destroyed every set checkbox and its count, and
    the unknown-mains row with them, so the panel blinked while the
    user watched.

    **What a cell shows is what decides it**: the set names in the
    order they are laid out, each with the number owned beside it. The
    count also sets its column's width, and the column COUNT is fixed,
    so nothing else about the layout can move while those hold still.

    Widget IDENTITY is what the case reads. Comparing the labels would
    pass while every widget behind them was replaced.

    Returns a list of complaints.
    """
    def widgets(w, out):
        out.append(w)
        for child in w.winfo_children():
            widgets(child, out)
        return out

    out = []
    frame = getattr(tab, "inv_set_frame_inner", None)
    if frame is not None:
        before = widgets(frame, [])
        tab.populate_set_filters()
        after = widgets(frame, [])
        if len(before) != len(after) or any(a is not b for a, b in
                                            zip(before, after)):
            out.append(
                f"reloading with the same fragments replaced the Sets "
                f"filters ({len(before)} widgets before, {len(after)} "
                f"after). Every capture save calls this, so the panel "
                f"blinks each time.")

    # **The unknown-mains row needs an unknown main to be about.** No
    # snapshot is guaranteed to hold one, and a row of no widgets is
    # rebuilt indistinguishably from one that is left alone -- so the
    # case makes one rather than hoping for it.
    unknown = getattr(tab, "inv_main_unknown_frame", None)
    held = list(getattr(tab.optimizer, "fragments", []) or [])
    if unknown is not None and held:
        odd = SimpleNamespace(
            set_name=held[0].set_name,
            main_stat=SimpleNamespace(name="Nothing Names This%"))
        tab.optimizer.fragments = held + [odd]
        try:
            tab.populate_set_filters()
            before = widgets(unknown, [])
            tab.populate_set_filters()
            after = widgets(unknown, [])
        finally:
            tab.optimizer.fragments = held
        if len(before) < 2:
            out.append(
                f"a fragment with a main nothing names left the unknown "
                f"row holding {len(before)} widget(s). The case cannot "
                f"say anything about a row that was never built.")
        elif len(before) != len(after) or any(a is not b for a, b in
                                              zip(before, after)):
            out.append(
                f"reloading with the same fragments replaced the unknown "
                f"mains row ({len(before)} widgets before, {len(after)} "
                f"after). It is rebuilt from the same two load paths, so "
                f"it blinks on every capture save with the rest.")

    # And a CHANGE still rebuilds. A gate that never opens is a panel
    # that stops telling the truth about what is owned -- the counts in
    # the labels are read off the fragments.
    frame = getattr(tab, "inv_set_frame_inner", None)
    held = list(getattr(tab.optimizer, "fragments", []) or [])
    if frame is not None and held:
        before = widgets(frame, [])
        tab.optimizer.fragments = held[1:]
        try:
            tab.populate_set_filters()
        finally:
            tab.optimizer.fragments = held
        after = widgets(frame, [])
        if len(before) == len(after) and all(a is b for a, b in
                                             zip(before, after)):
            out.append(
                "dropping a fragment rebuilt nothing. The bracketed count "
                "beside each set name is read off the fragments, so a gate "
                "that holds through a change leaves the panel stating a "
                "number that is no longer true.")
        tab.populate_set_filters()
    return out


def _countdowns_line_up(tab):
    """Deadlines sit in a column, and the Events block has its own.

    A countdown used to follow its row's reading by two spaces, so the
    `Ends in` of five rows started at five different places. Each is
    written to a TAB STOP now -- one for the rows above the shops and
    one for the Events block below them, each measured against its own
    members, so a long reading in one does not push the other's
    deadlines across.

    **Read off the STOPS and the tab count, not off pixels.** The
    column is not mapped here, so nothing has an x; what can be read
    is that the line ends with a tab before its countdown and that the
    tag it carries declares a stop for it.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.tabs.checklist_tab import (
        COLUMN_SEP, COUNTDOWN_EVENTS, COUNTDOWN_FIXED,
        COUNTDOWN_STOP_PREFIX, ENDS_IN, EVENT_KEY_PREFIX, LINE_SEP)
    out = []
    held = tab.column_texts.get("Other")
    if held is None:
        return ["the Other column built no Text to read."]
    text, _rows = held

    # **A stop tag exists only once a row needs it**, and `tag_cget`
    # raises on one that was never configured rather than answering
    # empty. The rows above the shops are the fixed schedule and are
    # always drawn; the Events block is only there while the account
    # has events, so its stop is demanded only when its rows are.
    declared = set(text.tag_names())
    stops = {}
    for group in (COUNTDOWN_FIXED, COUNTDOWN_EVENTS):
        name = COUNTDOWN_STOP_PREFIX + group
        raw = text.tag_cget(name, "tabs") if name in declared else ()
        stops[group] = [int(float(x)) for x in
                        (raw.split() if isinstance(raw, str) else raw)]
    events = any(str(row[0][0]).startswith(EVENT_KEY_PREFIX)
                 for row in tab._rendered.get("Other") or ())
    if (len(stops[COUNTDOWN_FIXED]) < 2
            or (events and len(stops[COUNTDOWN_EVENTS]) < 3)):
        return [
            f"the two deadline columns declare {stops!r}. The rows above "
            f"the shops need a stop for their countdown; the Events block "
            f"needs that and one more for the `Finished?` box at the end "
            f"of a row."]
    if events and stops[COUNTDOWN_FIXED][1] == stops[COUNTDOWN_EVENTS][1]:
        out.append(
            f"both deadline columns landed on {stops[COUNTDOWN_FIXED][1]}. "
            f"They are measured against different rows and only agree by "
            f"accident -- if this is ever a real coincidence, widen one of "
            f"the reserves rather than deleting the case.")

    # Every row that shows a countdown reaches it through a tab.
    for number, line in enumerate(
            text.get("1.0", tk.END).split(LINE_SEP), 1):
        if ENDS_IN not in line:
            continue
        tags = text.tag_names("%d.0" % number)
        if not any(str(t).startswith(COUNTDOWN_STOP_PREFIX) for t in tags):
            continue                      # a shop heading, at its own stop
        at = line.index(ENDS_IN)
        if not line[:at].endswith(COLUMN_SEP):
            out.append(
                f"a deadline is written as {line[:at][-12:]!r} + the "
                f"countdown, without a tab before it -- so it starts "
                f"wherever the reading beside it happens to end.")
            break
    return out


def _finished_boxes_ask_only_where_it_is_open(tab):
    """The `Finished?` box appears on exactly the rows it is a question for.

    A row the game has called finished is not asked about, and neither
    is one with work left to do. What is left is a tally at its own
    ceiling that nothing proves -- the one state a person looking at
    the game can settle and this program cannot.

    **Counted against the READINGS, never against the tab's own list
    of open questions.** That list is what draws the boxes, so
    comparing the two would agree however wrong both were.

    Returns a list of complaints.
    """
    from ui.tabs.checklist_tab import (
        DONE, EVENT_KEY_PREFIX, FINISHED_LABEL, unsure_ceiling)
    out = []
    drawn = tab._rendered.get("Other")
    if drawn is None:
        return ["the Other column rendered nothing to read."]
    manager = getattr(tab.context, "checklist_manager", None)
    want, carry = set(), set()
    for (key, _label, _tracked, segments, box), *_rest in drawn:
        if not str(key).startswith(EVENT_KEY_PREFIX):
            continue
        if box is not None:
            carry.add(key)
        name = key[len(EVENT_KEY_PREFIX):]
        answered = bool(manager is not None and name in manager.finished)
        if unsure_ceiling(segments) is not None or answered:
            want.add(key)
    if carry != want:
        out.append(
            f"the Events block draws `Finished?` on {sorted(carry)!r} where "
            f"the readings leave the question open on {sorted(want)!r}. The "
            f"box is the only way to answer one, and drawing it where the "
            f"GAME has already answered invites a user to contradict it.")

    boxes = [b for b in tab._boxes.get("Other", [])
             if str(b.cget("text")) == FINISHED_LABEL]
    if len(boxes) != len(carry):
        out.append(
            f"{len(carry)} row(s) carry the question and {len(boxes)} "
            f"checkbox(es) were built. A box the column forgot to keep is "
            f"a widget nothing destroys on the next rewrite.")
    shades = {str(b.cget("fg")) for b in boxes}
    if len(shades) > 1 and not any(
            row[0][4] and row[0][4][2] for row in drawn):
        out.append(
            f"the boxes are drawn in {sorted(shades)!r} with none of them "
            f"answered. Unanswered is yellow and answered is orange; two "
            f"unanswered ones cannot differ.")
    return out


def _checklist_block_is_tall_enough(tab):
    """A column's fixed height has to match what the Text lays out.

    The rows live in a Text inside a frame with `pack_propagate(False)`
    and a height in PIXELS, so nothing pushes back when the sum is
    wrong: Tk clips whatever does not fit off the bottom and the column
    simply ends a row early. Three pitches feed it -- an ordinary row,
    a block boundary, a checkbox -- and `ROW_TAG_PITCH` is the one
    table both the tags and the height are built from.

    **And a checkbox row is TALLER than a text one**, the embedded
    widget rather than the font setting the line. Sizing every row at
    the font's `linespace` lost three pixels per checkbox and clipped
    whole shops off the foot of the Weekly and Monthly columns.

    So this holds the ends together three ways: every tag the Text
    configures carries the `spacing1` the table says, a column's
    computed height equals the pitches of the rows it contains, and
    the Text's own laid-out lines fit inside the block reserved for
    them.

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
    # **A checkbox row's own tags**, which is where this last went
    # wrong. `window_create` takes no tags, and a line reads `spacing1`
    # and its tab stops off its FIRST character -- so a checkbox row
    # was styling its words and nothing else. The pitch did nothing,
    # and changed nothing visible when it moved, which is as quiet as
    # a layout bug gets.
    for text in texts:
        last = int(text.index("end-1c").split(".")[0])
        for line in range(1, last + 1):
            start = "%d.0" % line
            if not text.dump(start, start + "+1c", window=True):
                continue                      # not a checkbox row
            tags = set(text.tag_names(start))
            if not tags & set(mod.ROW_TAG_PITCH):
                out.append(
                    f"the checkbox on line {line} carries tags {sorted(tags)}, "
                    f"with no pitch tag among them. `window_create` leaves "
                    f"an untagged character and the line takes its spacing "
                    f"from that one, so the row loses it.")
                break

    # And the height itself, against the rows a column really holds.
    line = tkfont.Font(font=mod.ROW_FONT).metrics("linespace")
    box = tab._checkbox_line()
    for title, rows in mod.columns_for({}, None, 0, None):
        if not rows:
            continue
        keys = [key for key, _label, _widest in rows]
        want, above = 0, None
        for key in keys:
            want += (box if mod._is_shop(key) else line)
            want += px(mod.ROW_TAG_PITCH[mod._row_tags(key, above)[0]])
            above = key
        got = tab._block_height(keys)
        if got != want:
            out.append(
                f"the {title!r} column reserves {got}px for {len(keys)} "
                f"rows where their own pitches come to {want}px. A short "
                f"block clips its last row and nothing reports it.")

    return out


def _tooltip_columns_align(root, colors):
    """A two-column tip's values line up, and its payload can be lazy.

    Two things that fail QUIETLY. A value column drawn as one Label per
    row would align only while every label happened to be the same
    width, and the wrong reading would look like the right one beside a
    different name. And a tip bound to something that changes has to
    read its content at HOVER time -- a callable resolved when the
    binding was made would freeze the figures that were on screen then,
    and a stale tooltip looks exactly like a fresh one.

    Built against an unmapped frame and measured there. Putting a real
    tip up to check it would mean a window on the maintainer's screen.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.scaling import px
    from ui.utils.tooltip import Tooltip, ROW_GAP
    out = []
    tips = Tooltip(colors)

    if Tooltip.content(lambda: "late") != "late":
        out.append(
            "Tooltip.content does not call a callable payload, so a tip "
            "bound to something that changes shows whatever it said when "
            "the binding was made.")
    if Tooltip.content("plain") != "plain":
        out.append("Tooltip.content mangles a plain string payload.")

    holder = tk.Frame(root)
    rows = (("Average per week:", "776 Policy Point"),
            ("Average per year:", "40467 Policy Point"))
    body = tips._columns(holder, rows)
    labels = [w for w in body.winfo_children() if isinstance(w, tk.Label)]
    if len(labels) != len(rows[0]):
        out.append(
            f"a two-column tip built {len(labels)} labels for "
            f"{len(rows[0])} columns. One Label per COLUMN is what makes "
            f"the values line up without anything being measured; one per "
            f"cell aligns only by accident.")
    else:
        for at, (label, column) in enumerate(zip(labels, zip(*rows))):
            if label.cget("text") != "\n".join(column):
                out.append(
                    f"column {at} reads {label.cget('text')!r}, not its own "
                    f"cells joined by newline. A column out of step with "
                    f"the other puts a value beside the wrong label.")
            if int(label.cget("wraplength") or 0):
                out.append(
                    f"column {at} wraps. A wrapped cell takes one column "
                    f"out of step with the other and nothing on screen "
                    f"says which line belongs to which.")
        gap = str(labels[1].pack_info().get("padx"))
        if gap != str(px((ROW_GAP, 0))):
            out.append(
                f"the value column sits {gap!r} from the labels where "
                f"ROW_GAP asks for {px((ROW_GAP, 0))!r}. That pad IS the "
                f"`label -> its element` gap for every tip drawn this way.")
        # **And nothing of the Labels' own sits in that gap.** A
        # tk.Label's box is wider than its words by its padding and
        # its border, on each side -- so any left on these two lands
        # between the columns and the pad above stops being what the
        # eye measures.
        for at, label in enumerate(labels):
            slack = [int(label.cget(option) or 0)
                     for option in ("padx", "borderwidth")]
            if any(slack):
                out.append(
                    f"tip column {at} carries padx/borderwidth {slack}, "
                    f"which widens its box past its words. Six pixels "
                    f"of that fall between the columns, on top of the "
                    f"{px(ROW_GAP)} ROW_GAP is asking for.")
        # **Labels read left, values read RIGHT.** The rows above are
        # a four-figure sum under a five-figure one, which is the case
        # it is for: left-justified they start together and the digits
        # land in the wrong places.
        want = {0: "left", 1: "right"}
        for at, label in enumerate(labels):
            if str(label.cget("justify")) != want[at]:
                out.append(
                    f"tip column {at} is justified "
                    f"{str(label.cget('justify'))!r}, not {want[at]!r}. "
                    f"A value column ragged on the RIGHT puts a shorter "
                    f"figure's digits out of line with a longer one's.")
    holder.destroy()
    return out


def _a_seasonal_tick_outlives_its_season(tab):
    """A Galactic Disaster tick must survive the season turning over.

    Every one of that shop's product ids carries its season --
    `disaster_s04_14` becomes `disaster_s05_14` -- so a tick stored
    under one is lost the day the next season opens, and every shelf
    the user had unticked comes back ticked. Nothing about that looks
    broken: the rows are all there, reading their defaults.

    So the settings store the OFFER -- the item, how many a purchase
    gives, and the price -- and this renames a whole season's
    products to prove the answers follow.

    Returns a list of complaints.
    """
    from ui.tabs import checklist_tab as mod

    out = []
    shop = (mod.SEASONAL_SHOP_CATEGORY, mod.shop_stock.ALL_SCREENS)
    live = (tab._definitions or {}).get(mod.SEASONAL_SHOP_CATEGORY) or {}
    season = mod._live_season(getattr(tab.optimizer, "raw_data", None) or {})
    mine = {product: define for product, define in live.items()
            if season and str(product).startswith(season)}
    if not mine:
        return ["no seasonal shop products to rename, so this is "
                "watching nothing."]

    # The same shelves under next season's spelling.
    ahead = season[:-2] + "%02d" % (int(season[-2:]) + 1)
    renamed = {product.replace(season, ahead): dict(define, id=product.replace(
        season, ahead)) for product, define in mine.items()}

    was = tab._definitions
    try:
        for product in sorted(mine):
            tab._definitions = {mod.SEASONAL_SHOP_CATEGORY: mine}
            here = tab._tracking_id(product)
            tab._definitions = {mod.SEASONAL_SHOP_CATEGORY: renamed}
            later = tab._tracking_id(product.replace(season, ahead))
            if here != later:
                out.append(
                    f"{product} is stored under {here!r} and its {ahead} "
                    f"twin under {later!r}. Every tick on this shop is "
                    f"lost the day the season turns.")
                break
            if season in str(here):
                out.append(
                    f"{product} is stored under {here!r}, which names "
                    f"the season. The id changes every season and the "
                    f"tick goes with it.")
                break
    finally:
        tab._definitions = was
    # And a shop whose ids outlive a season is still stored under them.
    for product in ("town_shop_goods_005", "card_factor_4"):
        if tab._define_of(product) and tab._tracking_id(product) != product:
            out.append(
                f"{product} is stored under "
                f"{tab._tracking_id(product)!r} rather than its own id. "
                f"Only the seasonal shop renames its products, and "
                f"rewriting the others' keys would lose their ticks "
                f"instead.")
    return out


def _checklist_short_names_keep_their_tip(tab):
    """A row whose name is cut short has to carry the full one.

    `SHORT_NAMES` trades words for column width, and the only thing
    giving them back is the checkbox's own tooltip. A shortened row
    with no tip is a product named by an ellipsis, which is worse than
    the long name it replaced -- and nothing about it looks wrong.

    The tip is bound to the WIDGET rather than to a line, so it follows
    the product wherever ticking sorts it; that is what this reads.

    Returns a list of complaints.
    """
    from ui.tabs import checklist_tab as mod
    out = []
    for res_id, short in mod.SHORT_NAMES.items():
        full = mod.ITEM_NAMES.get(res_id)
        if not full:
            out.append(
                f"SHORT_NAMES shortens item {res_id}, which `item_names` "
                f"does not name -- so the tip would have nothing to say "
                f"and the row would read as an ellipsis with no product.")
        elif len(short) >= len(full):
            out.append(
                f"SHORT_NAMES turns {full!r} into {short!r}, which is no "
                f"shorter. The table costs a tooltip and buys nothing.")
    shortened = set(mod.SHORT_NAMES.values())
    seen = 0
    for boxes in tab._boxes.values():
        for box in boxes:
            words = str(box.cget("text"))
            if not any(words.startswith(short) for short in shortened):
                continue
            seen += 1
            if not box.bind("<Enter>"):
                out.append(
                    f"the shop row {words!r} is a shortened name with no "
                    f"hover binding, so the full name is nowhere on the "
                    f"tab.")
                break
    if mod.SHORT_NAMES and tab._boxes and not seen:
        out.append(
            "no shop row on the Checklist carries a shortened name, so "
            "nothing here was checked. Either SHORT_NAMES no longer "
            "matches anything the shops sell, or the labels stopped "
            "going through `product_label`.")
    return out


def _checklist_recalls_a_finished_streak(tab):
    """A streak the game ended reads finished on the next session too.

    `completed` arrives on one wire reply and never again -- the login
    that follows sends a row identical to a streak merely claimed for
    today. So the tab records it and hands it back, and this is both
    halves: a row carrying the flag is remembered, and a row without
    it gets the flag back.

    Returns a list of complaints.
    """
    from ui.tabs import checklist_tab as mod
    manager = getattr(tab.context, "checklist_manager", None)
    if manager is None:
        return ["the Checklist tab was built with no manager, so the "
                "streak memory was never reached."]
    out = []
    was = dict(manager.streaks)
    try:
        # The claim's row, carrying the flag.
        raw = {mod.ATTENDANCE_FIELD: [
            {"event_id": "check_streak", "received_days": 7,
             "current_days": 7, mod.ATTENDANCE_OVER: True}]}
        tab._recall_streaks(raw)
        if not manager.streak_finished("check_streak"):
            out.append(
                "a streak arriving with `completed` was not remembered. It "
                "is said once, so a session that does not record it loses "
                "the answer for the rest of the event.")

        # The next session's row, without it.
        raw = {mod.ATTENDANCE_FIELD: [
            {"event_id": "check_streak", "received_days": 7,
             "current_days": 7}]}
        tab._recall_streaks(raw)
        if not raw[mod.ATTENDANCE_FIELD][0].get(mod.ATTENDANCE_OVER):
            out.append(
                "a remembered streak did not get its `completed` back, so "
                "it reads as unfinished from the next login onwards.")

        # And a streak nobody finished stays unfinished.
        raw = {mod.ATTENDANCE_FIELD: [
            {"event_id": "check_other", "received_days": 3,
             "current_days": 3}]}
        tab._recall_streaks(raw)
        if raw[mod.ATTENDANCE_FIELD][0].get(mod.ATTENDANCE_OVER):
            out.append(
                "a streak nobody has finished came back finished.")
    finally:
        manager.streaks = was
        manager._write()
    return out


def _checklist_heading_totals_are_marked(tab):
    """A shop heading's name and total carry the hover; the tail does not.

    Three claims, and each fails invisibly. The hover has to reach BOTH
    the shop's name and its figures, since either is what a reader
    points at. It must NOT reach what follows them -- the Sortie shop's
    heading also carries a countdown, and a tip about currency rates
    over a deadline is an answer to a question nobody asked. And the
    total takes its own shade of the two verdicts, which is the only
    thing separating a heading's answer from its products'.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.tabs import checklist_tab as mod
    out = []
    seen = 0
    for title, (text, rows) in tab.column_texts.items():
        for at, (key, _label, _widest) in enumerate(rows):
            if not key.startswith(mod.SHOP_HEAD_PREFIX):
                continue
            line = at + 1
            tab_at = text.search("\t", "%d.0" % line, "%d.end" % line)
            if not tab_at:
                continue                    # no total and no countdown
            # **A heading with nothing to count draws `NO_DATA`**, and a
            # placeholder has no verdict to shade and no rates to
            # explain. Demanding the marks on it reports faults against
            # a heading that is drawn exactly right -- which is every
            # shop heading when no capture has been loaded.
            if text.get(tab_at + "+1c",
                        "%d.end" % line).startswith(mod.NO_DATA):
                continue
            want = mod.SHOP_TIP_PREFIX + key
            seen += 1
            words = set(text.tag_names("%d.0" % line))
            total = set(text.tag_names(tab_at + "+1c"))
            if want not in words or want not in total:
                out.append(
                    f"the {title!r} heading {key!r} carries its hover on "
                    f"{sorted(words & {want})} of its name and "
                    f"{sorted(total & {want})} of its total. Both are what "
                    f"a reader points at.")
            shades = total & set(mod.HEAD_STATE_TAGS.values())
            if not shades:
                out.append(
                    f"the {title!r} heading {key!r} draws its total in "
                    f"{sorted(total)}, with none of HEAD_STATE_TAGS among "
                    f"them -- so a heading's verdict is inked the same as "
                    f"the rows it answers for.")
            tail = text.search("\t", tab_at + "+1c", "%d.end" % line)
            if tail and want in set(text.tag_names(tail + "+1c")):
                out.append(
                    f"the {title!r} heading {key!r} puts its currency hover "
                    f"on the countdown after its total, which the rates say "
                    f"nothing about.")
    if not seen:
        said = ("no shop heading on the Checklist showed a total, so "
                "nothing here was checked. A check that cannot fail is "
                "not watching anything.")
        # With nothing captured there is nothing to total, and that is
        # the one case where the silence is honest.
        if newest_snapshot() is None:
            note(said)
        else:
            out.append(said)
    return out


def _checklist_rows_are_all_drawn(tab):
    """Every Checklist row has to FIT the block reserved for it.

    The two readings above agree with each other by sharing a formula.
    This one asks Tk what it actually laid out, which is the only way
    to catch the formula being wrong about a row -- as it was about a
    checkbox's height, losing three pixels a row until whole shops
    fell off the foot of a column with nothing to show for it.

    **`count -ypixels` answers only for a MAPPED widget**, so the
    window goes up at alpha 0 -- the app's own `_hide_until_ready`
    trick, and what `check_ui_scales` already measures through. It is
    mapped, so Tk lays it out; it is invisible, so nothing appears on
    the maintainer's screen.

    Returns a list of complaints.
    """
    import tkinter as tk
    out = []
    if not tab.column_texts:
        return out
    root = tab.frame.winfo_toplevel()
    notebook = tab.frame.master
    try:
        root.attributes("-alpha", 0.0)
        if str(tab.frame) not in notebook.tabs():
            notebook.add(tab.frame, text="Checklist")
        notebook.pack(fill=tk.BOTH, expand=True)
        notebook.select(tab.frame)
        root.deiconify()
        root.update_idletasks()
    except tk.TclError as e:
        return [f"the Checklist could not be laid out for measuring: {e}"]
    try:
        for title, (text, _rows) in tab.column_texts.items():
            holder = text.master
            last = int(text.index("end-1c").split(".")[0])
            drawn = 0
            for line in range(1, last + 1):
                tall = text.count("%d.0" % line, "%d.0" % (line + 1),
                                  "ypixels")
                tall = tall[0] if isinstance(tall, tuple) else tall
                drawn += tall or 0
            if not drawn:
                out.append(
                    f"the {title!r} column laid out no pixels, so nothing "
                    f"here was measured. Either the block is empty or the "
                    f"window never mapped -- and a check that cannot fail "
                    f"is not watching anything.")
                continue
            reserved = int(holder.cget("height"))
            if drawn > reserved:
                out.append(
                    f"the {title!r} column's {last} rows lay out to "
                    f"{drawn}px inside a block reserved for {reserved}px. "
                    f"`pack_propagate(False)` clips the difference without "
                    f"a word, so the rows at the foot of that column are "
                    f"simply not drawn.")
    finally:
        root.withdraw()
    return out


# Short enough that a Checklist column cannot fit, which is the
# condition the wheel binding exists for. Under the app's own minimum
# on purpose -- see the function below.
SHORT_H = 400


def _a_wheel_over_a_checkbox_scrolls_its_column(tab):
    """The wheel has to reach the Text under an embedded checkbox.

    A column taller than the tab scrolls, and that is the only way to
    reach a row its foot has clipped. But a checkbox in a line is a
    WINDOW and the wheel stops at whatever the pointer is over, which
    on this tab is a checkbox for most of the column -- so the scroll
    works everywhere except where the user is likely to be pointing.

    Needs a MAPPED window, an unmapped Text having no view to move,
    and a SHORT one: a column with room for all its rows has nowhere
    to scroll and nothing to prove. The height here is deliberately
    under what the app allows, because what is being exercised is the
    binding rather than the layout -- at a supported size the tallest
    column happens to fit, and a check that waits for that to stop
    being true is a check that never runs.

    Goes up at alpha 0, like `_checklist_rows_are_all_drawn`.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.scaling import px, WINDOW_MIN_W
    root = tab.frame.winfo_toplevel()
    notebook = tab.frame.master
    out = []
    try:
        root.attributes("-alpha", 0.0)
        if str(tab.frame) not in notebook.tabs():
            notebook.add(tab.frame, text="Checklist")
        notebook.pack(fill=tk.BOTH, expand=True)
        notebook.select(tab.frame)
        root.geometry("%dx%d" % (px(WINDOW_MIN_W), px(SHORT_H)))
        root.deiconify()
        root.update_idletasks()
    except tk.TclError as e:
        return [f"the Checklist could not be laid out for measuring: {e}"]
    try:
        # A column the tab is too short for, which is the only one
        # with anywhere to scroll TO.
        for title, (text, _rows) in (tab.column_texts or {}).items():
            boxes = (tab._boxes or {}).get(title) or ()
            if not boxes or text.yview() == (0.0, 1.0):
                continue
            text.yview_moveto(0.0)
            root.update_idletasks()
            before = text.yview()
            # Delivered SYNCHRONOUSLY -- `event_generate` with no
            # `when` runs the binding before it returns. A full
            # `update()` here would also run every pending `after`,
            # and the Capture Log's own arrive on one.
            boxes[0].event_generate("<MouseWheel>", delta=-120)
            root.update_idletasks()
            after = text.yview()
            text.yview_moveto(0.0)
            if after == before:
                out.append(
                    f"a wheel turn over a checkbox in the {title!r} "
                    f"column moved nothing. The rows its foot clips can "
                    f"only be reached by scrolling, and a checkbox "
                    f"swallows the turn unless it is handed on.")
            return out
        out.append(
            "no Checklist column both overflows and holds a checkbox, so "
            "this is watching nothing.")
    finally:
        root.withdraw()
    return out


def _the_checklist_fits_its_window(tab):
    """Every Checklist column has to fit the DEFAULT window.

    The columns are fixed-width and the grid cannot shrink them, so a
    tab that outgrows the window does not reflow -- the last column
    simply runs off the right edge, and what is missing is invisible
    because there is nothing beside it to look short.

    **A column reserves more than it draws, and that is the trap.** A
    shop heading's line hangs off its own words rather than standing
    in the column of readings, so a heading counted in BOTH places
    reserves its widest countdown twice and the tab grows wider than
    anything on it. Nothing about that is visible until the total
    crosses the window's width.

    Measured with the window at the size the layout is designed for,
    mapped at alpha 0 like `_checklist_rows_are_all_drawn`.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.scaling import px, WINDOW_H, WINDOW_W

    root = tab.frame.winfo_toplevel()
    notebook = tab.frame.master
    out = []
    try:
        root.attributes("-alpha", 0.0)
        if str(tab.frame) not in notebook.tabs():
            notebook.add(tab.frame, text="Checklist")
        notebook.pack(fill=tk.BOTH, expand=True)
        notebook.select(tab.frame)
        root.geometry("%dx%d" % (px(WINDOW_W), px(WINDOW_H)))
        root.deiconify()
        root.update_idletasks()
    except tk.TclError as e:
        return [f"the Checklist could not be laid out for measuring: {e}"]
    try:
        holders = tab.frame.winfo_children()
        if not holders:
            return ["the Checklist tab built no children at all"]
        columns = sorted(holders[0].winfo_children(),
                         key=lambda w: w.winfo_rootx())
        if not columns:
            return ["the Checklist tab built no columns"]
        edge = root.winfo_rootx() + root.winfo_width()
        last = columns[-1]
        over = (last.winfo_rootx() + last.winfo_width()) - edge
        if over > 0:
            out.append(
                f"the Checklist's last column runs {over}px past the "
                f"right edge of a default-sized window. The columns are "
                f"fixed-width and the grid cannot shrink them, so what "
                f"is off the edge is simply not drawn.")
        # And they do not overlap each other, which is the other way a
        # tab too wide for its window shows up.
        for at in range(len(columns) - 1):
            gap = (columns[at + 1].winfo_rootx()
                   - (columns[at].winfo_rootx() + columns[at].winfo_width()))
            if gap < 0:
                out.append(
                    f"Checklist columns {at} and {at + 1} overlap by "
                    f"{-gap}px. Every column is as wide as its own widest "
                    f"row, so an overlap is the tab asking for more "
                    f"width than the window has.")
    finally:
        root.withdraw()
    return out


def _a_marked_shop_heading_has_something_to_say(tab):
    """A shop heading is underlined only where a tip will appear.

    The underline and the query cursor are what the tab uses to say
    "there is more to read here", and `Tooltip.bind_tag` lays both on
    whatever tag it is given -- so a heading tagged out of habit
    advertises a tip that never comes. The free shelves are the case:
    a shop selling for no single currency has no rates and no bill, so
    there is nothing behind the mark.

    Nothing about it is visible from the data: the words look the same
    and the tip's absence reads as a slow hover.

    Returns a list of complaints.
    """
    import tkinter as tk
    from ui.tabs.checklist_tab import SHOP_HEAD_PREFIX, SHOP_TIP_PREFIX

    out = []
    marked = 0
    for title, (widget, rows) in (tab.column_texts or {}).items():
        for key, _label, _widest in rows:
            if not key.startswith(SHOP_HEAD_PREFIX):
                continue
            try:
                under = bool(int(widget.tag_cget(
                    SHOP_TIP_PREFIX + key, "underline") or 0))
            except (tk.TclError, ValueError):
                under = False
            has = key in (tab._shop_tips or {})
            marked += under
            if under and not has:
                out.append(
                    f"{key!r} in the {title!r} column is underlined and "
                    f"has no tip to show. The underline and the query "
                    f"cursor are the tab's promise of one.")
            if has and not under:
                out.append(
                    f"{key!r} in the {title!r} column has a tip and is "
                    f"not marked, so nothing on screen says to hover it.")
    if not marked:
        out.append(
            "no shop heading is marked as carrying a tip, so this is "
            "watching nothing -- either the tips stopped being bound or "
            "the tab built no shops.")
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

    wanted = len(CHECKLIST_COLUMNS)
    children = tab.get_frame().winfo_children()
    if not children:
        return ["the Checklist tab built no children at all"]
    first = children[0]
    columns = [child for child in first.winfo_children()
               if child.winfo_class() in ("TFrame", "Frame")]
    if len(columns) != wanted:
        return [
            f"the Checklist tab's first child holds {len(columns)} column "
            f"frame(s), not {wanted}. The audit reaches every Checklist "
            f"gap through that child, and a resolver that finds nothing "
            f"SKIPS rather than failing -- so the four entries would go "
            f"quiet with the run still green."
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


def _gacha_history_draws_its_rows(tab):
    """The Stats & Gacha History tab draws what its folder holds, by
    rarity.

    Built against a history of its own, never the maintainer's: the tab
    reads through `_folder`, which is pointed at a temp folder here. A
    unit nobody knows the rarity of must be drawn LOUDLY -- every pity
    after it rests on it -- and the `5-star only` filter must show
    nothing else.

    Returns a list of complaints.
    """
    import json as _json
    import time as _time
    from datetime import datetime as _datetime
    from tkinter import ttk
    import gacha_history as gh
    from ui.tabs.gacha_history_tab import (
        BEHIND_NOTE, BEHIND_TAG, FILTERS, TREE_STYLE, URGENT_NOTE,
        URGENT_TAG)

    out = []
    banner = "gacha_pickup_combatant_990002"
    partner_banner = "gacha_pickup_supporter_990021"
    five, four, three, nobody = 990002, 990011, 990021, 990099
    record = {"id": "1", "gacha_id": banner, "createAt": "1000",
              "reward": _json.dumps([three, four, five, nobody])}
    partner_record = {"id": "2", "gacha_id": partner_banner,
                      "createAt": "1000", "reward": _json.dumps([three])}
    rates = {"pools": {"ssr_rate_up_success_pool_ids":
                       ["pickup_c_1_rateup_ssr_c_%d" % five],
                       "sr_combatant_pool_ids":
                       ["pickup_c_1_sr_c_%d" % four],
                       "r_pool_ids": ["general_r_s_%d" % three]}}
    now = _time.time()

    def days_ago(days):
        # Local time, as the addon stamps a read.
        return _datetime.fromtimestamp(now - days * 86400).isoformat(
            timespec="seconds")

    def pity(pool):
        return {"res_id": "gacha_pity_" + pool, "pity_ssr_count": 1,
                "createAt": "1", "updateAt": str(int(now))}

    work = Path(tempfile.mkdtemp())
    try:
        folder = gh.folder_in(work)
        folder.mkdir(parents=True)
        (folder / gh.CAPTURED).write_text(_json.dumps({
            "kind": gh.STORE_KIND, "records": [record, partner_record],
            "rates": {banner: rates},
            # The game counted a pull after the newest record held on
            # both banners: behind, and each must say so -- urgently
            # where the records were last read longer ago than the
            # pulls it is missing can safely wait.
            "pity": {"gacha_pity_pickup_combatant":
                     pity("pickup_combatant"),
                     "gacha_pity_pickup_supporter":
                     pity("pickup_supporter")},
            "read": {banner: days_ago(gh.URGENT_AFTER_DAYS + 1),
                     partner_banner: days_ago(1)}}),
            encoding="utf-8")
        tab._folder = lambda: folder
        tab.refresh()
        rows = tab.summary_tree.get_children()
        want = {"pickup_combatant": (URGENT_TAG, tab.urgent_label,
                                     URGENT_NOTE),
                "pickup_supporter": (BEHIND_TAG, tab.behind_label,
                                     BEHIND_NOTE)}
        if sorted(rows) != sorted(want):
            out.append(f"the Gacha History's banner list holds {list(rows)} "
                       f"for a history of a Combatant and a Partner "
                       f"rate-up")
        else:
            for row, (tag, label, note) in want.items():
                tags = tuple(tab.summary_tree.item(row)["tags"])
                if tags != (tag,) or label.cget("text") != note \
                        or label not in label.master.pack_slaves():
                    out.append(
                        f"{row}, behind and last read "
                        f"{'over' if tag == URGENT_TAG else 'under'} "
                        f"{gh.URGENT_AFTER_DAYS} days ago, is drawn with "
                        f"tags {tags} and the status line "
                        f"{label.cget('text')!r}. The row's colour and "
                        f"its line are the only sign that its records "
                        f"need reading again before the game forgets them.")
        # A selected row keeps its tag's colour. The shared list style
        # maps `selected` to a foreground of its own, which outranks any
        # tag, so this tab's style must answer for `selected` itself.
        style = ttk.Style()
        saved = style.map("Treeview", "foreground")
        style.map("Treeview", foreground=[("selected", "#010203")])
        try:
            chosen = str(style.lookup(TREE_STYLE, "foreground",
                                      ["selected"]))
        finally:
            style.map("Treeview", foreground=saved)
        if chosen.lower() == "#010203":
            out.append(
                f"{TREE_STYLE} takes its selected-row foreground from "
                f"the shared Treeview style, so a selected row drops its "
                f"rarity or warning colour. Its own empty foreground map "
                f"is what stops that, and looks like a no-op.")
        out.extend(_gacha_overall_fits(tab, gh))
        pulls = [tab.pulls_tree.item(i) for i in tab.pulls_tree.get_children()]
        tags = [tuple(p["tags"]) for p in pulls]
        if tags != [("stars_unknown",), ("stars_5",), ("stars_4",),
                    ("stars_3",)]:
            out.append(
                f"the pulls list draws tags {tags}, newest first. A unit "
                f"of unknown rarity has to stand out, not pass as a 3-star "
                f"-- which is how a new 5-star broke every pity after it.")
        # A unit's stars index the rarity table: 5 Mythic, 4 Legendary,
        # 3 Rare. Unknown takes a colour no rarity has, or it passes for
        # one of them.
        from game_data.constants import RARITY_COLORS
        for stars in (5, 4, 3):
            got = str(tab.pulls_tree.tag_configure(f"stars_{stars}",
                                                   "foreground"))
            if got.lower() != RARITY_COLORS[stars].lower():
                out.append(f"{stars}-star pulls are drawn in {got}, not the "
                           f"rarity table's {RARITY_COLORS[stars]}")
        unknown = str(tab.pulls_tree.tag_configure("stars_unknown",
                                                   "foreground")).lower()
        if unknown in {c.lower() for c in RARITY_COLORS.values()}:
            out.append(f"pulls of unknown rarity are drawn in {unknown}, a "
                       f"rarity's own colour -- they read as that rarity")
        tab.filter_var.set(FILTERS[-1][0])
        tab._fill_pulls()
        shown = [tab.pulls_tree.item(i)["tags"][0]
                 for i in tab.pulls_tree.get_children()]
        if shown != ["stars_5"]:
            out.append(f"the 5-star-only filter shows {shown}; it "
                       f"must show the 5-stars and nothing else")
    finally:
        tab.filter_var.set(FILTERS[0][0])
        shutil.rmtree(work, ignore_errors=True)
    return out


def _sheet_complaints(label, text, holder):
    """(complaints, the lines set as headings) for one Stats & Gacha
    History sheet as it is written.

    A sheet is a Text in a holder sized in pixels, with tab stops
    measured from its rows, and three things fail it without a word: a
    field reaching its next stop, where Tk falls through to a tab
    spacing of its own; a holder narrower than a line, which clips the
    line's end; and one shorter than the lines, which clips the last
    rows.

    Every line carries exactly one pitch tag -- the first line the one
    that charges nothing above it, a heading its own, every other row
    the row's: the audit reads the gaps by those tags.
    """
    import tkinter.font as tkfont
    from ui.tabs.gacha_history_tab import (
        BOLD_TAG, HEADING_FONT, HEADING_TAG, ROW_TAG, TOP_TAG)

    out, headings = [], []
    normal = tkfont.nametofont("TkDefaultFont")
    bold = tkfont.Font(font=HEADING_FONT)
    stops = [int(str(s)) for s in text.tk.splitlist(text.cget("tabs"))
             if str(s).isdigit()]
    count = int(text.index("end-1c").split(".")[0])
    width = int(holder.cget("width"))
    for n in range(1, count + 1):
        line = text.get(f"{n}.0", f"{n}.end")
        tags = text.tag_names(f"{n}.0")
        heading = BOLD_TAG in tags
        if heading:
            headings.append(line)
        pitch = [t for t in tags if t in (ROW_TAG, HEADING_TAG, TOP_TAG)]
        want = (TOP_TAG if n == 1 else HEADING_TAG if heading else ROW_TAG)
        if pitch != [want]:
            out.append(f"{label} line {n} {line!r} carries pitch tags "
                       f"{pitch}, not [{want!r}]: every line takes one, "
                       f"the first {TOP_TAG!r}.")
        font = bold if heading else normal
        fields = line.split("\t")
        # A line setting two sections side by side carries stops of its
        # own, on a tag of its own.
        own = [[int(str(v)) for v in text.tk.splitlist(text.tag_cget(t, "tabs"))
                if str(v).isdigit()] for t in tags
               if str(text.tag_cget(t, "tabs"))]
        starts = [0] + (own[0] if own else stops)
        for i, field in enumerate(fields):
            if i + 1 < len(fields) and i + 1 >= len(starts):
                out.append(f"{label} line {n} {line!r} has more fields "
                           f"than the sheet has stops, {stops}")
                break
            end = starts[i] + font.measure(field)
            limit = starts[i + 1] if i + 1 < len(fields) else width
            if end > limit:
                out.append(f"{label} line {n}: {field!r} ends at {end}px, "
                           f"past {limit}, the "
                           f"{'next stop' if i + 1 < len(fields) else 'holder'}"
                           f" -- clipped, or tabbed to where Tk chooses.")
    need = text.count("1.0", "end", "update", "ypixels")
    need = need[0] if isinstance(need, (tuple, list)) else need
    have = int(holder.cget("height"))
    if need > have:
        out.append(f"the {label} sheet's lines need {need}px and its "
                   f"holder is {have}: the last rows are clipped.")
    return out, headings


def _gacha_overall_fits(tab, gh):
    """The Overall Gacha Stats sheet shows all it holds.

    The stops and the holder are worked out again on every fill, so the
    history is handed a streak of three different units here -- wider
    than anything the sheet held before it. `_sheet_complaints` says
    what a fill can get wrong.

    A record's ties sit beside it, as many as fit the sheet's share of
    the Banners list's width and the oldest first; forty are handed
    over here.

    Returns a list of complaints.
    """
    from datetime import datetime
    from ui.tabs.gacha_history_tab import (
        ALL_BANNERS, OVERALL_TITLE, PRISM_ONLY, WITHOUT_PRISM)

    out = []
    pulls = [pull for pool in tab.history.ordered() for pull in pool.pulls]
    units = {pull.res_id: pull for pull in pulls}
    if len(units) < 3:
        return ["the Gacha History test history has too few units to "
                "build a three-unit streak from"]
    tab.history.overall.streak = [
        gh.Standout(3, list(units.values())[:3])]
    # More ties than the sheet's share of the Banners list's width can
    # hold, a day apart and handed over oldest first, as the history
    # lists them.
    day = 86400
    first = pulls[0]
    tab.history.overall.fastest = [
        gh.Standout(1, [gh.Pull(res_id=first.res_id, at=1000 + i * day,
                                number=i)]) for i in range(40)]
    tab._fill_overall()
    text = tab.overall_text
    available = tab.summary_tree.master.winfo_reqwidth()
    if int(tab.overall_holder.cget("width")) > available:
        out.append(f"the {OVERALL_TITLE} sheet is "
                   f"{tab.overall_holder.cget('width')}px wide, past the "
                   f"Banners list's {available}: it widens their column "
                   f"and squeezes the pulls list.")
    row = text.get("5.0", "5.end").split("\t")
    dates = row[3::2]
    oldest = datetime.fromtimestamp(1000).strftime("%Y-%m-%d")
    if len(dates) < 2 or dates != sorted(dates) or dates[0] != oldest:
        out.append(f"forty tied fastest 5-stars show the dates {dates}: "
                   f"as many as fit, oldest first from {oldest}.")
    problems, headings = _sheet_complaints(OVERALL_TITLE, text,
                                           tab.overall_holder)
    out.extend(problems)
    # Every banner's section sits beside the first, on its heading's line.
    if headings != [WITHOUT_PRISM + "\t" + ALL_BANNERS, PRISM_ONLY]:
        out.append(f"the {OVERALL_TITLE} sheet's headings read {headings}")
    # The spacing audit finds this panel by its exact title and these
    # rows by their words. A rename the registry does not follow leaves
    # those rows reading nothing, and only an audit would say so.
    from ui import spacing_registry as registry
    title = str(tab.overall_holder.master.cget("text"))
    if registry.GACHA_OVERALL_TITLE != title:
        out.append(f"the spacing registry looks for a panel titled "
                   f"{registry.GACHA_OVERALL_TITLE!r}; the tab's is "
                   f"{title!r}. Update `GACHA_OVERALL_TITLE`.")
    for needle in registry.GACHA_FIGURE_ROWS:
        if not text.search(needle, "1.0", "end"):
            out.append(f"the spacing registry reads the {OVERALL_TITLE} "
                       f"row {needle.strip()!r}, which the sheet no longer "
                       f"has. Update `GACHA_RECORD_ROWS` or "
                       f"`GACHA_FIGURE_ROWS`.")
    # The tab's help text, found by its opening words the same way.
    from ui import spacing_audit as sa
    if sa.find_descendant_text(tab.frame, registry.GACHA_HELP_PREFIX) is None:
        out.append(f"the spacing registry finds the tab's help text by "
                   f"{registry.GACHA_HELP_PREFIX!r}, which it no longer "
                   f"starts with. Update `GACHA_HELP_PREFIX`.")
    # A unit that came more than once is named once and counted, in the
    # order the units first came.
    from ui.tabs.gacha_history_tab import _units
    a, b = list(units.values())[:2]
    got = _units([a, b, a])
    want = "%s x2, %s" % (gh.unit_name(a.res_id), gh.unit_name(b.res_id))
    if got != want:
        out.append(f"a streak of A, B, A names its units {got!r}, not "
                   f"{want!r}")
    tab.refresh()
    return out


def _standings(seasons):
    """A snapshot's standings: `seasons` of the Sortie, the Great Rift
    and the Full-Scale Offensive, the newest Great Rift season's second
    half still running with its division tops read. The account stands
    in Diamond II in every half."""
    def rift(season, half):
        rank_id = "disaster_s%02d_rank_best_%d_24" % (season, half)
        running = (season, half) == (seasons, 2)
        return {"rank": 2481, "best_score": 1115731, "rank_id": rank_id,
                "last_rank": 0 if running else 2500,
                "last_rank_id": None if running else rank_id}
    live = "disaster_s%02d" % seasons
    return {
        "chaos_assault_rankings": {
            "assault_1_s%d" % s: {"readings": [{
                "tab": "ongoing" if s == seasons else "complete",
                "total_count": 24684, "rank": 1914, "score": 42343,
                "top_score": 66265, "read_at": s}]}
            for s in range(1, seasons + 1)},
        "disaster_boss_rank_entities": {
            "disaster_s%02d" % s: {"disaster_s%02d_rank_%02d" % (s, h):
                                   rift(s, h) for h in (1, 2)}
            for s in range(1, seasons + 1)},
        "disaster_boss_rank_tops": {live: {live + "_rank_02": {
            "%s_rank_best_2_%d" % (live, n): [
                {"rank": rank, "best_score": score, "read_at": 1}]
            for n, rank, score in ((30, 1, 1635631), (25, 941, 1219348),
                                   (5, 35368, 416283))}}},
        "remnants_rankings": {
            "remnants_boss_penalty_%03d" % s: {
                "stages": {"a": 1130418, "b": 1060877, "c": 1255815},
                "readings": [{"rank": 441, "rank_percent": 0.83,
                              "read_at": s}]}
            for s in range(1, seasons + 1)},
    }


def _standings_lists_fit(tab):
    """The standings lists show every season read, newest first, and fit
    the room under the gacha sheet in the default window.

    The Great Rift's list has the Banners list's width; the two under
    it share that width, half each. Each is as wide as its seasons up to
    its room. Handed more seasons than that room holds, a list
    must stop at its edge and scroll the rest, the newest in view: one
    that grows past it widens the column and takes the difference from
    the pulls list, and one cut off anywhere simply stops drawing.
    Measured at the worst the tab gets -- the gacha sheet at its widest,
    every banner family listed, every list scrolling, and the warning
    lines the test history raises showing -- mapped at alpha 0 like
    `_the_checklist_fits_its_window`, and written AFTER mapping, as the
    tab's first show writes them.

    **A mapped Treeview asks for a new size only on `configure`, never
    on a column's new width**, so a list written while mapped has to
    configure itself after its widths or keep its old size. The lists
    are written here twice while mapped, the row names' widest changing
    between the two, and every list's size is held to its columns'.

    The spacing audit finds these panels by their exact titles, which
    their labelwidgets hold.

    Returns a list of complaints.
    """
    import tkinter as tk
    import gacha_history as gh
    import stats_history as sh
    from ui import spacing_audit as sa
    from ui import spacing_registry as registry
    from ui.scaling import px, WINDOW_H, WINDOW_W
    from ui.tabs.gacha_history_tab import (
        BANNER_ROWS, NO_VALUE, OFFENSIVE_TITLE, RIFT_TITLE, SORTIE_TITLE)

    out = []
    lists = ((SORTIE_TITLE, tab.sortie_list, sh.sortie_table,
              registry.GACHA_SORTIE_TITLE),
             (RIFT_TITLE, tab.rift_list, sh.rift_table,
              registry.GACHA_RIFT_TITLE),
             (OFFENSIVE_TITLE, tab.offensive_list, sh.offensive_table,
              registry.GACHA_OFFENSIVE_TITLE))
    optimizer = tab.optimizer
    saved = getattr(optimizer, "raw_data", None), tab.stats
    families = len(tab._shown_pools())
    history = tab.history
    fastest = history.overall.fastest if history is not None else None
    root = tab.frame.winfo_toplevel()
    notebook = tab.frame.master
    before = notebook.select()
    added = str(tab.frame) not in notebook.tabs()

    def shown(parts):
        """(headings, [row name, cells...] per row) as the lists draw
        them, spacers left out."""
        data = parts.data
        seasons = [c for c in data["columns"]
                   if not str(c).startswith("gap")]
        heads = [str(data.heading(c)["text"]) for c in seasons]
        rows = [[str(parts.labels.item(a)["values"][0])]
                + [str(v) for v in data.item(b)["values"][::2]]
                for a, b in zip(parts.labels.get_children(),
                                data.get_children())]
        return heads, rows

    try:
        # Nothing read: one empty column, so the list reads as a table.
        optimizer.raw_data, tab.stats = {}, None
        tab._fill_standings()
        for title, parts, table, _registered in lists:
            heads, rows = shown(parts)
            if heads != [NO_VALUE] or any(r[1:] != [NO_VALUE] for r in rows):
                out.append(f"the {title} list with nothing read shows "
                           f"{heads} over {rows}; one {NO_VALUE!r} column.")
        try:
            root.attributes("-alpha", 0.0)
            if added:
                notebook.add(tab.frame, text="Stats & Gacha History")
            notebook.pack(fill=tk.BOTH, expand=True)
            notebook.select(tab.frame)
            tab._show_banner_rows(len(gh.POOL_ORDER))
            root.geometry("%dx%d" % (px(WINDOW_W), px(WINDOW_H)))
            root.deiconify()
            root.update_idletasks()
        except tk.TclError as e:
            return out + [f"the Stats & Gacha History tab could not be laid "
                          f"out for measuring: {e}"]
        # The window's spare width is the two lists' to share, half each,
        # in their last columns. The body's <Configure> delivers it in the
        # app; `update` would too, but it also runs every pending `after`
        # -- the Capture tab's prerequisite check among them, which
        # writes into the log a later check reads line by line -- so the
        # handler is handed the body's width directly.
        body = tab.summary_tree.master.master
        tab._share_excess(SimpleNamespace(width=body.winfo_width()))
        root.update_idletasks()
        (b_col, b_nat, _b), (p_col, p_nat, _p) = (
            tab._natural[str(tab.summary_tree)],
            tab._natural[str(tab.pulls_tree)])
        gained = (int(tab.summary_tree.column(b_col, "width")) - b_nat,
                  int(tab.pulls_tree.column(p_col, "width")) - p_nat)
        if gained[0] <= 0 or gained[1] != 0:
            out.append(f"in a default-sized window the Banners and Pulls "
                       f"lists' last columns gained {gained}px: the width "
                       f"both leave is the Banners list's, which the "
                       f"standings under it grow into.")
        # A resize, with the list mapped. The first share lands before
        # the list is, when Tk still follows its columns; after that a
        # Treeview asks for a new width only on `configure`, and its
        # stretching last column fills the old width back out.
        # A step inside the spare width, so none of it is clamped.
        step = min(px(20), gained[0])
        wide = tab.summary_tree.winfo_reqwidth()
        tab._share_excess(SimpleNamespace(width=body.winfo_width() - step))
        root.update_idletasks()
        if wide - tab.summary_tree.winfo_reqwidth() != step:
            out.append(f"{step}px off the window took "
                       f"{wide - tab.summary_tree.winfo_reqwidth()}px off "
                       f"the Banners list, not all of it: a mapped list "
                       f"keeps its size through a new column width. "
                       f"`_fit_banners`' `configure` is what makes it ask "
                       f"again.")
        tab._share_excess(SimpleNamespace(width=body.winfo_width()))
        root.update_idletasks()
        # With one column to show, every list is as narrow as it.
        tab._fill_standings()
        root.update_idletasks()
        for parts, title in ((tab.rift_list, RIFT_TITLE),
                             (tab.offensive_list, OFFENSIVE_TITLE),
                             (tab.sortie_list, SORTIE_TITLE)):
            if int(parts.holder.cget("width")) != tab._columns_width(
                    parts.data):
                out.append(f"with nothing read the {title} list's seasons "
                           f"are {parts.holder.cget('width')}px wide across "
                           f"{tab._columns_width(parts.data)}px of columns; "
                           f"it is as wide as its seasons up to its room.")
        # The gacha sheet at its widest: more ties than it holds.
        if history is not None and any(pool.pulls
                                       for pool in history.ordered()):
            first = next(pull for pool in history.ordered()
                         for pull in pool.pulls)
            history.overall.fastest = [
                gh.Standout(1, [gh.Pull(res_id=first.res_id,
                                        at=1000 + i * 86400, number=i)])
                for i in range(40)]
        raw = _standings(12)
        optimizer.raw_data = raw
        tab._fill_overall()
        tab._fill_standings()
        root.update_idletasks()
        for title, parts, table, registered in lists:
            rows, columns = table(raw, None)
            heads, drawn = shown(parts)
            want = [[name] + [cells[n] or NO_VALUE for _h, cells in columns]
                    for n, name in enumerate(rows)]
            if heads != [h for h, _cells in columns] or drawn != want:
                out.append(f"the {title} list draws {heads} over {drawn}, "
                           f"not its table's {[h for h, _c in columns]} "
                           f"over {want}: every season, newest first.")
            for tree, what in ((parts.labels, "row names"),
                               (parts.data, "seasons")):
                need = tab._columns_width(tree)
                if tree.winfo_reqwidth() != need:
                    out.append(
                        f"the {title} list's {what} ask for "
                        f"{tree.winfo_reqwidth()}px across columns of "
                        f"{need}px, written while mapped. A mapped "
                        f"Treeview re-asks only on `configure`; the "
                        f"`configure(height=...)` after the widths is "
                        f"what does it, and looks redundant.")
            if sa.find_labelframe(tab.frame, registered) is not parts.frame:
                out.append(f"the spacing registry looks for a panel titled "
                           f"{registered!r} and does not find the {title} "
                           f"list's.")
        edge = tab.summary_tree.master
        right = edge.winfo_rootx() + edge.winfo_width()
        bottom = tab.frame.winfo_rooty() + tab.frame.winfo_height()
        if int(tab.summary_tree.cget("height")) > BANNER_ROWS or \
                not tab.summary_scroll.winfo_ismapped():
            out.append(f"with every banner family listed the Banners list "
                       f"shows {tab.summary_tree.cget('height')} rows, "
                       f"scrollbar mapped: "
                       f"{bool(tab.summary_scroll.winfo_ismapped())}. It "
                       f"shows {BANNER_ROWS} and scrolls past them, or the "
                       f"standings under it run off the window.")
        rift = tab.rift_list.frame
        if rift.winfo_rootx() + rift.winfo_width() != right:
            out.append(f"past its room the {RIFT_TITLE} list ends at "
                       f"{rift.winfo_rootx() + rift.winfo_width()}, the "
                       f"Banners list at {right}: it grows up to that "
                       f"list's width and stops there.")
        half = tab._banners_width() // 2 - px(2) - tab._panel_edges()
        for parts, title in ((tab.offensive_list, OFFENSIVE_TITLE),
                             (tab.sortie_list, SORTIE_TITLE)):
            used = tab._columns_width(parts.labels) + int(
                parts.holder.cget("width"))
            if used > half:
                out.append(f"the {title} list is {used}px wide, past the "
                           f"{half}px half of the Banners list's width each "
                           f"of the two side by side has.")
        # Both past their room, the pair takes the banners' whole width
        # between them: half each, less what a title wider than its half
        # takes from its neighbour.
        pair = tab.sortie_list.frame
        if pair.winfo_rootx() + pair.winfo_width() != right:
            out.append(f"with both lists past their room, the "
                       f"{OFFENSIVE_TITLE} and {SORTIE_TITLE} lists end at "
                       f"{pair.winfo_rootx() + pair.winfo_width()}, the "
                       f"Banners list at {right}: between them they take "
                       f"its whole width.")
        for title, parts, _table, _registered in lists:
            frame = parts.frame
            over = frame.winfo_rootx() + frame.winfo_width() - right
            if over > 0:
                out.append(f"the {title} list runs {over}px past the Banners "
                           f"list's right edge in a default-sized window, "
                           f"widening their column into the pulls list.")
            short = max(frame.winfo_reqheight() - frame.winfo_height(),
                        frame.winfo_rooty() + frame.winfo_height() - bottom)
            if short > 0:
                out.append(f"the {title} list is cut {short}px short at the "
                           f"bottom of a default-sized window.")
            wide = tab._columns_width(parts.data) > int(
                parts.holder.cget("width"))
            if not wide:
                out.append(f"the {title} list holds twelve seasons without "
                           f"scrolling; the test no longer reaches its edge.")
            if wide != bool(parts.scroll.winfo_ismapped()):
                out.append(f"the {title} list's scrollbar is "
                           f"{'hidden' if wide else 'shown'} with its "
                           f"seasons {'past' if wide else 'inside'} its "
                           f"room.")
            if parts.data.xview()[0] != 0:
                out.append(f"the {title} list opens scrolled to "
                           f"{parts.data.xview()}; the newest season, at "
                           f"its left, belongs in view.")
    finally:
        optimizer.raw_data, tab.stats = saved
        if history is not None:
            history.overall.fastest = fastest
        tab._show_banner_rows(families)
        tab._fill_overall()
        tab._fill_standings()
        if added:
            notebook.forget(tab.frame)
        if before:
            notebook.select(before)
        root.withdraw()
    return out


def _materials_catches_up_when_shown(tab):
    """The Materials tab skips a redraw while hidden and makes it up.

    A capture reloads the snapshot after every save, and every Capture
    Log line waits behind that reload -- so the Materials redraw, the
    costliest part of it after the fragment list, is skipped while
    another tab is showing. What that risks is quiet: a tab that never
    catches up shows the counts of whenever it was last visible. So the
    redraw must NOT happen while hidden, and MUST happen when the tab
    is selected.

    Returns a list of complaints.
    """
    from tkinter import ttk

    if not tab.optimizer.raw_data:
        return []                       # nothing loaded to redraw from
    notebook = tab.context.notebook
    other = ttk.Frame(notebook)
    notebook.add(tab.frame, text="Materials")
    notebook.add(other, text="Other")
    drawn = []
    real = tab._render_icons
    tab._render_icons = lambda quantities: drawn.append(quantities)
    try:
        notebook.select(other)
        tab.refresh_materials()
        while_hidden = len(drawn)
        notebook.select(tab.frame)
        # Handled at once rather than queued, so no other pending
        # timer of the tabs runs with it.
        notebook.event_generate("<<NotebookTabChanged>>")
        when_shown = len(drawn) - while_hidden
    finally:
        tab._render_icons = real
        notebook.forget(other)
        notebook.forget(tab.frame)
    out = []
    if while_hidden:
        out.append("the Materials tab redrew while another tab was "
                   "showing. That redraw sits in every capture reload, "
                   "and every Capture Log line waits behind it.")
    if when_shown != 1:
        out.append(f"the Materials tab redrew {when_shown} times when "
                   f"selected after a skipped refresh, not once. It would "
                   f"show the counts of whenever it was last visible.")
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


# Which buttons each `messagebox` helper actually draws. A `default`
# naming anything else raises `invalid default button` from Tk -- at
# the moment the user clicks, never at import, never in a build.
MESSAGEBOX_BUTTONS = {
    "askyesno": {"yes", "no"},
    "askretrycancel": {"retry", "cancel"},
    "askokcancel": {"ok", "cancel"},
    "askyesnocancel": {"yes", "no", "cancel"},
    "showinfo": {"ok"},
    "showwarning": {"ok"},
    "showerror": {"ok"},
}

def _default_word(node):
    """The button a `default=` argument names, or None.

    Parsed rather than matched: the call spans lines and holds nested
    calls of its own, and a regex that walks parens is wrong the moment
    an argument carries two levels of them -- which the delete
    confirmation's `_megabytes(book.stat().st_size)` does.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.lower()
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    return None


def _a_tooltip_marks_what_it_is_bound_to(root):
    """Anything carrying a tip says so before anyone hovers it.

    A tip nobody knows about is a tip nobody reads, and there is no way
    to see from the screen that a widget has one. Both marks are made
    inside `Tooltip.bind`, so that adding a tip is the only thing a
    caller has to remember -- this is what holds that: the underline,
    the cursor, and that neither costs the widget any size.

    Returns a list of complaints.
    """
    import tkinter as tk
    from tkinter import font as tkfont, ttk

    from ui.utils.tooltip import HOVER_CURSOR, Tooltip

    out = []
    tips = Tooltip({"bg": "#1e1e2e", "fg": "#cdd6f4", "accent": "#89b4fa",
                    "bg_light": "#313244"})
    label = ttk.Label(root, text="Archive: 1.3 MB")
    was = (label.winfo_reqwidth(), label.winfo_reqheight())
    tips.bind(label, "how much history it holds")
    face = tkfont.Font(font=label.cget("font"))
    if not int(face.cget("underline")):
        out.append(
            "a tip was bound to a label and its words were not underlined. "
            "Nothing else on screen says a widget has one.")
    if str(label.cget("cursor")) != HOVER_CURSOR:
        out.append(
            f"a tip was bound and the cursor stayed {label.cget('cursor')!r}, "
            f"not {HOVER_CURSOR!r}.")
    if (label.winfo_reqwidth(), label.winfo_reqheight()) != was:
        out.append(
            f"marking a tip changed the widget from {was} to "
            f"{(label.winfo_reqwidth(), label.winfo_reqheight())}. An "
            f"underline is drawn, not spaced: anything else moves every "
            f"gap registered around it.")

    held = len(tips._fonts)
    tips.bind(label, "rebound on a refresh")
    if len(tips._fonts) != held:
        out.append(
            "rebinding a tip derived a second font. The archive readings "
            "rebind on every tab select, and Tk keeps every named font it "
            "is given.")

    text = tk.Text(root)
    text.insert("1.0", "hello")
    text.tag_add("probe", "1.0", "1.5")
    tips.bind_tag(text, "probe", "a tip on a range")
    if not int(text.tag_cget("probe", "underline") or 0):
        out.append(
            "a tip bound to a Text RANGE left it unmarked. A Text draws "
            "what would otherwise be several widgets, and the tag is the "
            "only thing that can carry the underline.")
    label.destroy()
    text.destroy()
    return out


def _upgraded_line_marks_what_beats(tab):
    """An Upgraded line draws a beaten ceiling in the Mythic colour.

    Only the ceiling of the preset named, and only where the name ENDS
    the entry: `Nine` must not take the number before `Nine (Line of
    Justice)`. And the Mythic tag has to outrank the value tag already
    on that number, or the ceiling keeps its ordinary colour and nothing
    says the fragment beats anything.

    Returns a list of complaints.
    """
    from ui.tabs.capture_tab import MYTHIC_TAG

    out = []
    log = tab.capture_log
    line = ("[LIVE] Upgraded Set Slot IV +3. Highest Potential: "
            "10-89 Nine (Line of Justice), 9-87 Nine, 12-84 Amir")
    tab.log_upgrade_msg(line, "info", None, {"Nine"})
    row = int(log.index("end-2l").split(".")[0])

    def top(needle):
        col = line.index(needle)
        names = log.tag_names(f"{row}.{col}")
        return names[-1] if names else None

    if top("87 Nine") != MYTHIC_TAG:
        out.append(
            f"the ceiling of `Nine` in {line!r} is drawn by "
            f"{top('87 Nine')!r}, not {MYTHIC_TAG!r}: the Mythic tag has "
            f"to be created after the value tags to outrank them.")
    for needle in ("89 Nine", "84 Amir", "10-"):
        if MYTHIC_TAG in log.tag_names(f"{row}.{line.index(needle)}"):
            out.append(
                f"{needle.split()[0]!r} in {line!r} is marked Mythic; only "
                f"the ceiling of the preset named `Nine` beats its wearer.")
    return out


def _capture_hand_offs_never_wait(tab):
    """Another thread hands the Capture tab a line without waiting.

    The capture's reader thread passes every line, the status and the
    region to this tab. tkinter hands a Tk call made from another
    thread to the UI thread and WAITS for it -- `root.after` included
    -- so a reader that scheduled its lines sat behind every snapshot
    reload, a second at a time, reading nothing off the proxy's pipe:
    lines arrived seconds late and the proxy itself could stall once
    the pipe filled. Nothing failed; the log was just slow.

    So the UI thread is held here while a worker hands over all three,
    and the worker must be done long before it is free. Held OUTSIDE
    the event loop, which a Tk call from another thread waits on just
    the same -- a second, and then it raises -- without running every
    other timer the tabs have pending. Then the tab's own drain has to
    write the line.

    Returns a list of complaints.
    """
    import threading
    import time as _time

    out = []
    took = {}
    held = 0.5

    def worker():
        start = _time.perf_counter()
        tab.capture_log_msg("[LIVE] handed over from another thread", "info")
        tab.set_capture_status("handed over from another thread")
        tab.set_detected_region(None)
        took["secs"] = _time.perf_counter() - start

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    _time.sleep(held)
    thread.join(timeout=3)
    secs = took.get("secs")
    if secs is None or secs > held / 2:
        out.append(
            f"handing the Capture tab a line from another thread took "
            f"{secs if secs is None else round(secs, 2)}s while the UI "
            f"thread was held for {held}s. The capture's reader waits "
            f"like that behind every reload, and stops reading the "
            f"proxy's pipe while it does.")
    tab.drain_inbox()
    last = tab.capture_log.get("end-2l linestart", "end-1c").strip()
    if last != "[LIVE] handed over from another thread":
        out.append(f"after the drain the log's last line reads {last!r}, "
                   f"not the line handed over.")
    if str(tab.capture_status_label.cget("text")) != \
            "handed over from another thread":
        out.append("after the drain the status readout was not the one "
                   "handed over.")
    return out


def _the_failure_mark_lights_and_clears(tab):
    """The tab's mark goes up on a failure and comes off when read.

    Every way this breaks is silent. A `PhotoImage` nobody holds is
    collected and the tab goes blank; a blink whose `after` is never
    cancelled keeps firing at a widget that has gone; a mark that does
    not clear on opening the tab is one the user learns to ignore.

    Returns a list of complaints.
    """
    import tkinter as tk
    from tkinter import ttk

    out = []
    alert = getattr(tab, "_alert", None)
    if alert is None:
        return ["the Capture tab built no `_alert`, so a background "
                "failure has no way to reach a user on another tab."]

    if alert.showing:
        out.append("the mark was already showing before anything failed.")

    # On the tab already: nowhere to bring anyone, and no tab change
    # coming to take a mark back off again.
    notebook = alert.notebook
    if str(tab.frame) not in notebook.tabs():
        notebook.add(tab.frame, text="Capture")
    was = notebook.select()
    notebook.select(tab.frame)
    tab._title_pending = False
    tab.flag_failure()
    if alert.showing:
        out.append(
            "a failure marked the tab the user is already reading. Nothing "
            "brings them anywhere, and `<<NotebookTabChanged>>` does not "
            "fire for the tab already selected -- so the mark blinks until "
            "they leave and come back.")
    if tab._title_blink is None:
        out.append(
            "on the tab already, nothing pulsed at all: the mark is not "
            "raised there, so the title is the only thing left to say "
            "which panel spoke.")
    tab._stop_title_blink()

    # Somewhere ELSE to be. The harness builds tabs without adding them
    # all, so restoring the previous selection can leave this one still
    # showing -- and then the off-tab case is never exercised.
    elsewhere = ttk.Frame(notebook)
    notebook.add(elsewhere, text="elsewhere")
    notebook.select(elsewhere)
    tab._title_pending = False

    tab.flag_failure()
    if not alert.showing:
        out.append(
            "`flag_failure` did not raise the mark. A failure that reports "
            "only into the Capture Log reaches nobody who is on another "
            "tab, which is everybody while a background task runs.")
    if tab._title_blink is not None:
        out.append(
            "the title's pulse started while the user was on another tab. "
            "It runs out after a few seconds, so it is spent before the "
            "mark has brought anyone over to see it.")
    if not tab._title_pending:
        out.append(
            "nothing held the title's pulse for the user's arrival, so "
            "opening the tab clears the mark and says nothing more.")
    was = alert._after
    tab.flag_failure()
    if alert._after != was:
        out.append(
            "a second failure started a second blink, so two `after` "
            "chains now drive one mark and only one can be cancelled.")
    for name in ("_dot", "_blank"):
        image = getattr(alert, name, None)
        if not isinstance(image, tk.PhotoImage):
            out.append(
                f"`{name}` is {type(image).__name__}, not a PhotoImage held "
                f"on the alert. An image with no Python reference is "
                f"garbage-collected and the tab goes blank.")
    if tab._log_frame.cget("style") not in ("TLabelframe",
                                            "Alert.TLabelframe"):
        out.append(
            f"the log frame carries style {tab._log_frame.cget('style')!r}, "
            f"which the blink neither sets nor restores.")

    alert.clear()
    if alert.showing or alert._after is not None:
        out.append(
            "`clear` left the blink running. Its `after` fires at a widget "
            "that may be gone by then.")
    # The tab has to be its own width again. A tab carrying an image is
    # wider than one without, so leaving the blank behind holds a
    # dot-shaped hole open and shoves the label right for the rest of
    # the session.
    if notebook.tab(tab.frame, "image"):
        out.append(
            f"the tab still carries an image after `clear` "
            f"({notebook.tab(tab.frame, 'image')!r}). Blinking swaps the "
            f"dot for a blank of the same size so the strip does not "
            f"shuffle; clearing has to take the image off entirely.")
    tab._stop_title_blink()
    if tab._title_blink is not None:
        out.append("`_stop_title_blink` left its `after` pending.")
    if tab._log_frame.cget("style") != "TLabelframe":
        out.append(
            "the log frame kept the alert style after its blink stopped, "
            "so the title stays red for the rest of the session.")
    try:
        notebook.forget(elsewhere)
        if was:
            notebook.select(was)
    except tk.TclError:
        pass
    return out


def _archive_size_carries_its_tooltip(tab):
    """The archive reading says on hover what the figure does not.

    `Archive: 1.3 MB` is the file on disk; what it HOLDS is the number
    that decides whether deleting it is worth anything, and that only
    fits on hover. A tooltip that was never bound looks exactly like
    one nobody hovered.

    Returns a list of complaints.
    """
    out = []
    label = getattr(tab, "_archive_size_label", None)
    if label is None:
        return ["the Setup tab has no `_archive_size_label` to hover."]
    if not label.bind("<Enter>"):
        out.append(
            "the archive size reading has no `<Enter>` binding, so its "
            "tooltip never appears. The figure on its own does not say "
            "how much history the archive holds.")
    held = getattr(tab, "_archive_held", None)
    if not isinstance(held, tuple) or len(held) != 2:
        out.append(
            f"`_archive_held` is {held!r}, not the (count, bytes) pair the "
            f"tooltip and the delete confirmation both read.")
    return out


def _messagebox_defaults_name_their_own_buttons():
    """A dialog's `default` has to be one of the buttons it draws.

    `askyesno(..., default="cancel")` passes every check the repo has:
    it imports, it builds, and it raises `TclError` the first time a
    user presses the button that opens it. Scanned rather than called,
    because calling one would put a modal dialog on the maintainer's
    screen.
    """
    out = []
    seen = 0
    for path in sorted((SOURCE_ROOT / "ui").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8",
                                            errors="replace"))
        except SyntaxError as exc:
            out.append(f"{path.name} will not parse: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "messagebox"):
                continue
            want = MESSAGEBOX_BUTTONS.get(func.attr)
            if want is None:
                continue
            for keyword in node.keywords:
                if keyword.arg != "default":
                    continue
                seen += 1
                chosen = _default_word(keyword.value)
                if chosen and chosen not in want:
                    out.append(
                        f"{path.name}:{node.lineno} calls {func.attr} with "
                        f"default={chosen!r}, which is not one of the "
                        f"buttons it draws ({sorted(want)}). Tk raises "
                        f"`invalid default button` when the dialog opens, "
                        f"so nothing sees this until a user clicks.")
    if not seen:
        out.append(
            "no `messagebox` call under `ui/` passes a `default`, so this "
            "checked nothing. A check that cannot fail is not watching "
            "anything.")
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
        # The app's own styles, so the geometry measured below is what
        # the app draws -- its row heights, its borderless panels. Built
        # on the theme alone, every panel grows a border the app has
        # not, and a fit read here is wrong by that much.
        gui.OptimizerGUI.configure_styles(SimpleNamespace(
            style=style, colors=dict(gui.COLORS)))
        complaint = _scrolled_text_packs_the_pair(root, dict(gui.COLORS))
        if complaint:
            failures.append(complaint)
        failures.extend(_tooltip_columns_align(root, dict(gui.COLORS)))
        failures.extend(_title_bar_takes_its_colours(root))
        import ui.tabs as tabs_pkg
        from ui.context import AppContext
        from optimizer.optimizer import GearOptimizer
        import preset_manager, character_preset_manager
        import optimizer_settings_manager, settings_manager
        import log_presets_manager
        import checklist_manager
        from config import AppConfig

        optimizer = GearOptimizer()
        snap = newest_snapshot()
        if snap:
            optimizer.load_data(snap)
        else:
            # Construction still gets checked without data -- a name
            # deleted from under a `setup_ui` raises either way. Every
            # assertion ABOUT a row does not: with no captured data the
            # tabs build empty, zero rows satisfy every claim made about
            # them, and this reports the same `ok` as a full run.
            note("no snapshot in Vribbels/snapshots/, so the tabs built "
                 "empty: construction was checked, nothing about rows "
                 "was")

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
            # The Checklist's own store. Without it the tab still
            # builds -- every reader of it is guarded -- and the
            # floor clock and the currency ledger are never reached,
            # so the checks below would pass over both.
            checklist_manager=_load(checklist_manager.ChecklistManager),
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
            failures.extend(_a_tooltip_marks_what_it_is_bound_to(root))
            failures.extend(
                _the_failure_mark_lights_and_clears(built["CaptureTab"]))
            failures.extend(_messagebox_defaults_name_their_own_buttons())
            failures.extend(_archive_size_carries_its_tooltip(
                built["SetupTab"]))
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
            failures.extend(
                _materials_catches_up_when_shown(built["MaterialsTab"]))
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
            failures.extend(
                _a_seasonal_tick_outlives_its_season(built["ChecklistTab"]))
            failures.extend(
                _checklist_short_names_keep_their_tip(built["ChecklistTab"]))
            failures.extend(
                _checklist_recalls_a_finished_streak(
                    built["ChecklistTab"]))
            failures.extend(
                _checklist_heading_totals_are_marked(
                    built["ChecklistTab"]))
            failures.extend(
                _checklist_rows_are_all_drawn(built["ChecklistTab"]))
            failures.extend(
                _the_checklist_fits_its_window(built["ChecklistTab"]))
            failures.extend(
                _a_marked_shop_heading_has_something_to_say(
                    built["ChecklistTab"]))
            failures.extend(
                _a_wheel_over_a_checkbox_scrolls_its_column(
                    built["ChecklistTab"]))
            failures.extend(_countdowns_line_up(built["ChecklistTab"]))
            failures.extend(_finished_boxes_ask_only_where_it_is_open(
                built["ChecklistTab"]))
        if "InventoryTab" in built:
            failures.extend(
                _set_filters_redraw_replaces_nothing(built["InventoryTab"]))
        if "GachaHistoryTab" in built:
            failures.extend(
                _gacha_history_draws_its_rows(built["GachaHistoryTab"]))
            failures.extend(
                _standings_lists_fit(built["GachaHistoryTab"]))
        if "CaptureTab" in built:
            failures.extend(
                _capture_log_colours_its_values(built["CaptureTab"]))
            failures.extend(
                _log_preset_columns_leave_the_gap(built["CaptureTab"]))
            failures.extend(
                _log_presets_redraw_replaces_nothing(built["CaptureTab"]))
            failures.extend(
                _capture_hand_offs_never_wait(built["CaptureTab"]))
            failures.extend(
                _upgraded_line_marks_what_beats(built["CaptureTab"]))
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
