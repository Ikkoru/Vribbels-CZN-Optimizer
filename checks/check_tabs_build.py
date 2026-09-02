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
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip

NAME = "tabs build"

# About and Materials are static and out of the spacing work's scope, but
# they are cheap to build and a missing name would break the notebook the
# same way, so they are here too.
TAB_ATTRS = ("SetupTab", "CaptureTab", "InventoryTab", "OptimizerTab",
             "HeroesTab", "ScoringTab", "MaterialsTab", "AboutTab")


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

    The line most likely to do it is the potential node's, because its
    bracket comes from the game data: a stat with a longer display name,
    or a bonus that reaches three digits, lengthens it without anything
    in this file changing.

    Returns a list of complaints.
    """
    from tkinter import font as tkfont
    from game_data.characters import (
        CHARACTERS, get_potential_stat, get_potential_stat_bonus)
    from game_data.constants import DISPLAY_NAMES
    from ui.tabs.heroes_tab import CHAR_CONTENT_PX, CHAR_SUBLIST_INDENT

    measure = tkfont.nametofont("TkDefaultFont").measure
    worst, worst_px = "", 0
    for res_id, data in CHARACTERS.items():
        if not isinstance(data, dict):
            continue
        for node in (50, 60):
            for level in range(0, 6):
                stat, bonus = get_potential_stat_bonus(res_id, node, level)
                if stat is None:
                    stat, bonus = get_potential_stat(res_id, node), None
                if stat is None:
                    continue
                what = DISPLAY_NAMES.get(stat, stat)
                if bonus:
                    what = f"{what} +{bonus:g}%"
                line = (f"{CHAR_SUBLIST_INDENT}Node {node // 10}: "
                        f"Lv{level} ({what})")
                if measure(line) > worst_px:
                    worst, worst_px = line, measure(line)

    if worst_px > CHAR_CONTENT_PX:
        return [
            f"the Character card's widest potential line is {worst_px}px "
            f"({worst!r}) against CHAR_CONTENT_PX = {CHAR_CONTENT_PX}. The "
            f"panel is a fixed width and the Text does not wrap, so this "
            f"clips silently. Raise CHAR_CONTENT_PX or shorten the bracket."
        ]
    return []


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

    Returns a list of complaints.
    """
    log = tab.capture_log
    line = ("[LIVE] Upgraded Set Slot IV +3. "
            "Highest Potential: 21-80 Fast, 15-38 Bulk")
    single = "[LIVE] Upgraded Set Slot I +5. Highest GS: 82 Fast, 31 Bulk"
    deleted = "[LIVE] Deleted Set Slot VI +0"
    created = "[LIVE] Created Set Slot III +0"
    for msg in (line, single, deleted, created):
        tab.capture_log_msg(msg, "info")

    out = []

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
    rules can no longer be set independently. The last time one moved,
    all four `All` buttons followed the content a pixel off target.

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
        failures.extend(_all_none_panels_carry_no_left_padding(built))
        failures.extend(_character_card_lines_fit())
        if "ScoringTab" in built:
            failures.extend(_weight_fields_are_clamped(built["ScoringTab"]))
        if "HeroesTab" in built:
            failures.extend(
                _combatant_selection_survives_a_rebuild(built["HeroesTab"]))
            failures.extend(
                _show_missing_adds_rather_than_replaces(built["HeroesTab"]))
        if "SetupTab" in built:
            failures.extend(_restore_dialog_frames_follow_the_rules(
                built["SetupTab"], root))
        if "CaptureTab" in built:
            failures.extend(
                _capture_log_colours_its_values(built["CaptureTab"]))
            failures.extend(
                _log_preset_columns_leave_the_gap(built["CaptureTab"]))
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
