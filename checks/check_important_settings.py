"""Important Settings: every slider stops on every integer, and the panel
is as wide as its widest row.

Both fail without a sound. A drag that skips a percent shows only to
someone hunting for that percent, and a panel a caption has widened
steals the width Have at Least is meant to get -- at 200% only, where
the first caption outgrows the rows.

1. **`_least_scale_length` is the least length that works.** A 0-100
   Scale is swept pixel by pixel at that length, and at one pixel
   shorter, at both UI scales: every integer at the first, not at the
   second. The thumb grows with the scale and the trough's border does
   not, so a length that holds at 100% says nothing about 200%.
2. **`_requested_width` is Tk's own figure.** The panel's width is
   worked out before the layout runs, so each row's sum is held to the
   `winfo_reqwidth` Tk gives the row once it has.
3. **The panel is its widest row.** Mapped at alpha 0 at the default
   window size: Important Settings at its requested width, no caption
   wider than the widest row, and Have at Least out to Set
   Configuration's right edge.
4. **The Potential 7 button raises and never lowers** a Have-at-least
   minimum, with a combatant's minimums stood in.

**Each UI scale is measured in a process of its own.** Tk caches a font
given as a tuple per display rather than per interpreter, so a second
root in one process lays some of its text out at the first root's
size, and every width read off it is wrong.

Settings managers read a COPY of `Vribbels/settings/`. Skips itself
where Tk cannot open a display.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from ._harness import add_source_to_path, REPO_ROOT, SOURCE_ROOT, Skip

NAME = "Important Settings: sliders stop on every integer, panel as wide as its rows"

SCALES = ("100%", "200%")


def _integers_reached(root, length):
    """How many of 0..100 a drag over a Scale of `length` can stop on."""
    import tkinter as tk
    from tkinter import ttk

    scale = ttk.Scale(root, from_=0, to=100, orient=tk.HORIZONTAL,
                      length=length)
    try:
        scale.place(x=0, y=0)
        root.update_idletasks()
        width, height = scale.winfo_width(), scale.winfo_height()
        reached = {int(float(scale.get(x, height // 2)))
                   for x in range(width)}
        return len(reached & set(range(101)))
    finally:
        scale.destroy()


def _least_length_is_least(root, scale_name, ot):
    out = []
    least = ot._least_scale_length(root)
    at, short = (_integers_reached(root, least),
                 _integers_reached(root, least - 1))
    if at != 101:
        out.append(
            f"At {scale_name} a Scale of `_least_scale_length`'s "
            f"{least}px stops on {at} of the 101 integers 0-100, so a "
            f"drag on a slider at its least length skips a percent. "
            f"The run is the trough less the thumb, and Tk's value is "
            f"its fraction times 100, truncated by the tab -- see "
            f"`_least_scale_length` in ui/tabs/optimizer_tab.py.")
    if short == 101:
        out.append(
            f"At {scale_name} a Scale one pixel shorter than "
            f"`_least_scale_length`'s {least}px still stops on every "
            f"integer, so the length is not the least. The panel is "
            f"sized from it, and Have at Least loses the difference.")
    return out


def _build_tab(scale_name, work):
    """The Optimizer tab at `scale_name`, mapped at alpha 0."""
    import tkinter as tk
    from tkinter import ttk

    from ui import scaling
    scaling.set_scale(scale_name)

    import czn_optimizer_gui as gui
    import ui.tabs as tabs_pkg
    from ui.context import AppContext
    from optimizer.optimizer import GearOptimizer
    from config import AppConfig
    import settings_manager, preset_manager, character_preset_manager
    import optimizer_settings_manager, log_presets_manager

    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    scaling.apply_font_scaling(root)
    style = ttk.Style()
    style.theme_use("clam")
    gui.OptimizerGUI.configure_styles(SimpleNamespace(
        style=style, colors=dict(gui.COLORS)))

    def load(cls):
        manager = cls(work)
        manager.load()
        return manager

    sm = load(settings_manager.SettingsManager)
    notebook = ttk.Notebook(root)
    context = AppContext(
        root=root, notebook=notebook, optimizer=GearOptimizer(),
        capture_manager=None, config=AppConfig(sm), colors=dict(gui.COLORS),
        style=style, load_data_callback=None, refresh_callback=None,
        inventory_tab=None, heroes_tab=None, scoring_tab=None,
        optimizer_tab=None, recompute_upgrade_line_callback=None,
        settings_manager=sm,
        preset_manager=load(preset_manager.PresetManager),
        character_preset_manager=load(
            character_preset_manager.CharacterPresetManager),
        optimizer_settings_manager=load(
            optimizer_settings_manager.OptimizerSettingsManager),
        log_presets_manager=load(log_presets_manager.LogPresetsManager),
    )
    tab = tabs_pkg.OptimizerTab(notebook, context)
    notebook.add(tab.get_frame(), text="Optimizer")
    notebook.pack(fill=tk.BOTH, expand=True)
    root.geometry("%dx%d" % (scaling.px(scaling.WINDOW_W),
                             scaling.px(scaling.WINDOW_H)))
    root.deiconify()
    # Window events as well as idle work: the notebook and everything
    # in it is mapped on the root's <Map>, which `update_idletasks`
    # never delivers, and an unmapped panel measures 1px. No timers.
    from ui.utils.presettle import _drain
    _drain(root, time.monotonic() + 30)
    return root, tab


def _panel(tab, title):
    from tkinter import ttk
    stack = [tab.get_frame()]
    while stack:
        widget = stack.pop()
        if isinstance(widget, ttk.LabelFrame) and widget.cget("text") == title:
            return widget
        stack.extend(widget.winfo_children())
    return None


def _panel_is_its_widest_row(tab, scale_name, ot):
    out = []
    important = _panel(tab, "Important Settings")
    hal = _panel(tab, "Have at least this much of a stat")
    sets = _panel(tab, "Set Configuration")
    if not (important and hal and sets):
        return [f"At {scale_name} the Optimizer tab has no Important "
                f"Settings, Have at Least or Set Configuration panel to "
                f"measure -- was one renamed? The titles here must match."]
    rows = [w for w in important.winfo_children()
            if w.winfo_class() == "TFrame"]
    captions = [w for w in important.winfo_children()
                if w.winfo_class() == "TLabel"]
    for row in rows:
        summed, tk_says = ot._requested_width(row), row.winfo_reqwidth()
        if summed != tk_says:
            out.append(
                f"At {scale_name} `_requested_width` makes an Important "
                f"Settings row {summed}px and Tk {tk_says}px. The "
                f"captions wrap at the widest row's sum, worked out "
                f"before Tk lays the rows out, so a wrong sum widens or "
                f"squeezes the panel. The row may use a layout the "
                f"helper does not handle.")
    widest = max((row.winfo_reqwidth() for row in rows), default=0)
    for caption in captions:
        if caption.winfo_reqwidth() > widest:
            text = str(caption.cget("text"))[:40]
            out.append(
                f"At {scale_name} the caption {text!r}... asks for "
                f"{caption.winfo_reqwidth()}px, wider than the widest "
                f"row's {widest}px, so it widens Important Settings "
                f"and Have at Least loses the difference. Captions wrap "
                f"at the widest row -- see _build_important_settings.")
    if important.winfo_width() != important.winfo_reqwidth():
        out.append(
            f"At {scale_name} Important Settings is "
            f"{important.winfo_width()}px wide and asks for "
            f"{important.winfo_reqwidth()}px. It is as wide as its "
            f"widest row and no wider; Have at Least takes the rest of "
            f"the column.")
    hal_right = hal.winfo_rootx() + hal.winfo_width()
    sets_right = sets.winfo_rootx() + sets.winfo_width()
    if hal_right != sets_right:
        out.append(
            f"At {scale_name} Have at Least ends at x={hal_right} and "
            f"Set Configuration at x={sets_right}. Have at Least takes "
            f"what Important Settings leaves of the column, out to the "
            f"panel below's right edge.")
    least = ot._least_scale_length(important)
    for widget in _descendants(important):
        if widget.winfo_class() == "TScale":
            length = int(str(widget.cget("length")))
            if length != least:
                out.append(
                    f"At {scale_name} an Important Settings slider asks "
                    f"for {length}px where `_least_scale_length` says "
                    f"{least}px. The panel's width is its rows' at that "
                    f"length: shorter and a squeezed window skips "
                    f"percents, longer and the panel is wider than the "
                    f"rule.")
    return out


def _fill_button_at_foot(tab, scale_name, ot):
    """The Potential 7 fill: its caption, then `Minimum` and `Full
    Effect` side by side at Have at Least's foot and left edge, at the
    height a button asks for."""
    from ui.scaling import px
    hal = _panel(tab, "Have at least this much of a stat")
    buttons = [tab.p7_buttons.get(key) for key in ("minimum", "full")]
    if hal is None or None in buttons:
        return [f"At {scale_name} Have at Least has no Minimum and Full "
                f"Effect buttons."]
    row = buttons[0].master
    if row.master is not hal or buttons[1].master is not row:
        return [f"At {scale_name} the Potential 7 buttons are not one row "
                f"in the Have at Least panel."]
    out = []
    if [b.cget("text") for b in buttons] != ["Minimum", "Full Effect"]:
        out.append(f"At {scale_name} the Potential 7 buttons read "
                   f"{[b.cget('text') for b in buttons]}.")
    for button in buttons:
        if button.winfo_height() != button.winfo_reqheight():
            out.append(
                f"At {scale_name} {button.cget('text')!r} is "
                f"{button.winfo_height()}px tall and asks for "
                f"{button.winfo_reqheight()}px: a button keeps every "
                f"other button's height, and the panel grows instead.")
    # The panel's left content edge, where its text starts.
    left = min(w.winfo_x() for w in hal.winfo_children() if w is not row)
    if row.winfo_x() - left != px(1):
        out.append(
            f"At {scale_name} the Potential 7 buttons start "
            f"{row.winfo_x() - left}px past the panel's text, not "
            f"{px(1)}: the button rule's 3 is the text inset's 2 and one.")
    below = hal.winfo_height() - row.winfo_y() - row.winfo_height()
    caption = [w for w in hal.winfo_children()
               if w.winfo_class() == "TLabel"
               and w.cget("text") == ot.P7_FILL_CAPTION]
    if below > px(3) + 2:
        out.append(
            f"At {scale_name} the Potential 7 buttons sit {below}px above "
            f"the panel's bottom: the row's slack opens above the "
            f"caption, not under the buttons.")
    if not caption or caption[0].winfo_y() + caption[0].winfo_height() \
            != row.winfo_y():
        out.append(
            f"At {scale_name} the caption {ot.P7_FILL_CAPTION!r} is "
            f"missing or not straight above the buttons.")
    return out


def _hal_labels_fit(tab, scale_name, ot):
    """Have at least's stat labels: each holds its text, a column's
    spinboxes line up, and its widest label is the lever's distance
    from its spinbox.

    Sized in characters, a label rounds up to whole `0`s: `CDMG%`, as
    wide as `Crit%` by count, lost its `%`, and the remainder landed in
    the gap -- 10px after `ATK` where the rule asks 5."""
    import tkinter.font as tkfont
    from ui.scaling import px
    hal = _panel(tab, "Have at least this much of a stat")
    if hal is None:
        return []
    font = tkfont.nametofont("TkDefaultFont")
    out = []
    columns = {}
    for row in _descendants(hal):
        kids = row.winfo_children()
        labels = [k for k in kids if k.winfo_class() == "TLabel"]
        spins = [k for k in kids if k.winfo_class() == "Spinbox"]
        if len(labels) != 1 or len(spins) != 1:
            continue
        label, spin = labels[0], spins[0]
        text = str(label.cget("text"))
        if font.measure(text) > label.winfo_width():
            out.append(
                f"At {scale_name} the Have at least label {text!r} needs "
                f"{font.measure(text)}px and has {label.winfo_width()}px: "
                f"its end is clipped.")
        columns.setdefault(str(row.master), []).append((text, label, spin))
    for rows in columns.values():
        lefts = {spin.winfo_rootx() for _t, _l, spin in rows}
        if len(lefts) != 1:
            out.append(
                f"At {scale_name} the spinboxes beside "
                f"{[t for t, _l, _s in rows]} start at {sorted(lefts)}: a "
                f"column's line up.")
        # Held to the rule's 5 to the INK (docs/ui_spacing.md), less the
        # label's own inset -- never to the tab's constant: a check
        # reading the lever it guards passes whatever the lever says.
        # Scaled whole like every label's pad.
        from ui.utils.label_width import LABEL_REQUEST_INSET
        text, label, spin = max(rows, key=lambda r: font.measure(r[0]))
        want = px(5 - LABEL_REQUEST_INSET // 2)
        got = spin.winfo_rootx() - label.winfo_rootx() - label.winfo_width()
        if got != want:
            out.append(
                f"At {scale_name} {text!r}, its column's widest label, "
                f"ends {got}px from its spinbox, not the {want} that "
                f"inks it `label ↔ its element`'s 5 away at 100%.")
    return out


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _p7_values_read_the_table():
    """What the two buttons write, off the Potential 7 table: the lowest
    threshold on each checked stat, and where the highest tops out."""
    from game_data.potential_7 import (potential_7_minimums,
                                       potential_7_switch_ons)
    out = []
    for rid, who, on, full in (
            (30075, "Sereniel", {"CRate": 20}, {"CRate": 40}),
            (1018, "Rin", {"ATK": 600}, {"ATK": 1000}),
            (1008, "Khalipe", {"ATK": 700, "DEF": 300},
             {"ATK": 700, "DEF": 300})):
        got = (potential_7_switch_ons(rid), potential_7_minimums(rid))
        if got != (on, full):
            out.append(
                f"{who}'s Potential 7 fills read Minimum {got[0]} and Full "
                f"Effect {got[1]}, not {on} and {full}: Minimum is each "
                f"checked stat's lowest threshold, Full Effect where its "
                f"highest tops out.")
    return out


def _fill_sets_only_checked(tab):
    """The fill buttons' handler, with a check on ATK stood in: each
    button SETS that stat -- up or down -- and touches no other."""
    out = []
    hal = tab.have_at_least_vars
    saved = {stat: var.get() for stat, var in hal.items()}
    stood_in = {False: {"ATK": 600}, True: {"ATK": 1000.4}}
    tab._potential_7_values = lambda _name, full: stood_in[full]
    try:
        for full, start, want in ((False, 900, 600), (True, 700, 1001)):
            for stat, var in hal.items():
                var.set(7)
            hal["ATK"].set(start)
            tab._fill_potential_7(full)
            which = "Full Effect" if full else "Minimum"
            if hal["ATK"].get() != want:
                out.append(
                    f"{which} took an ATK minimum of {start} to "
                    f"{hal['ATK'].get()}, not {want}: it sets the checked "
                    f"stat outright, a whole number rounded up.")
            moved = [stat for stat, var in hal.items()
                     if stat != "ATK" and float(var.get()) != 7]
            if moved:
                out.append(f"{which} moved {moved} as well; only the "
                           f"stats Potential 7 checks change.")
    finally:
        del tab._potential_7_values
        for stat, value in saved.items():
            hal[stat].set(value)
    return out


def _measure(scale_name):
    """Every complaint at one UI scale. Run in a process of its own."""
    add_source_to_path()
    import ui.tabs.optimizer_tab as ot

    failures = []
    work = Path(tempfile.mkdtemp())
    live = SOURCE_ROOT / "settings"
    if live.exists():
        # A COPY: building a tab is not reliably read-only.
        shutil.copytree(live, work / "settings")
    try:
        root, tab = _build_tab(scale_name, work)
        try:
            failures.extend(_least_length_is_least(root, scale_name, ot))
            failures.extend(_panel_is_its_widest_row(tab, scale_name, ot))
            failures.extend(_fill_button_at_foot(tab, scale_name, ot))
            failures.extend(_hal_labels_fit(tab, scale_name, ot))
            if scale_name == SCALES[0]:
                failures.extend(_fill_sets_only_checked(tab))
                failures.extend(_p7_values_read_the_table())
        finally:
            root.destroy()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return failures


def run():
    add_source_to_path()
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception as exc:                # noqa: BLE001
        raise Skip(f"Tk cannot open a display here ({exc})")

    failures = []
    for scale_name in SCALES:
        done = subprocess.run(
            [sys.executable, "-m", __name__, scale_name], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        lines = done.stdout.strip().splitlines()
        if done.returncode != 0 or not lines:
            failures.append(
                f"Measuring the Optimizer tab at {scale_name} failed "
                f"(exit {done.returncode}): "
                f"{(done.stderr.strip() or done.stdout.strip())[-1200:]}")
            continue
        # The last line: whatever the app prints while it builds comes
        # before it.
        failures.extend(json.loads(lines[-1]))
    return failures


if __name__ == "__main__":
    print(json.dumps(_measure(sys.argv[1])))
