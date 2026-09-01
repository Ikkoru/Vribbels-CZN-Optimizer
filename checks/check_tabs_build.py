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


def run():
    failures = []
    add_source_to_path()

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
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
