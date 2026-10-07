"""At 200% every distance has to double, and nothing may be left behind.

The spacing audit reads the scaled window too, but only at the gaps it
has registered, and only when it is run; a distance that stayed at its
100% value anywhere else is invisible. It is also the most likely
mistake by far: one `padx=4` that never got its `px()` reads as a gap
half the size of its neighbours on a screen the maintainer may not be
developing on.

So the tabs are built twice, once at each scale, and every option that
carries pixels is compared: the geometry managers' pads, what a widget
or a Text tag holds for itself (border, padding, line spacing, tab
stops), a Treeview's column widths and a frame's pinned size. A
distance that is not double at 200% is either unwrapped or wrapped
twice. A widget laid out with `place()` carries no pads, so the
Exclude panel's distances are read off where its names land:
`_placed_distances`.

**A distance is not always exactly double**, so the test is not "did
it double". A hardcoded one does; a MEASURED one -- a font width, a
`winfo_reqheight` -- grows by whatever the font grew by, which is near
two and not on it, because hinting rounds each size to whole pixels.
Demanding double of those would be a wall of false alarms.

What is unambiguous is each failure's own signature:

* a `px()` that was never applied leaves the value **exactly equal**,
  because nothing else in the app is scale-independent;
* a `px()` applied to something already scaled puts it **past the
  font's own ratio**, since it multiplies a grown value again.

So those two are what get flagged, and everything between them is a
distance that scaled by some honest amount.

**`width` and `height` are compared on frames alone.** They are
characters on an Entry, Spinbox, Combobox, Button and Label, lines on a
Text and rows on a Treeview -- so a blanket rule over them would demand
doubling from the ones the font already carries.

Skips itself where Tk cannot open a display.
"""

import ast
import math
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip

NAME = "every distance doubles at 200%"

# The geometry options that are pixels wherever they appear. `ipadx`
# and `ipady` are in the same class and are read off the same call.
PIXEL_OPTIONS = ("padx", "pady", "ipadx", "ipady")
# A Treeview column's `minwidth` where nothing sets one.
TK_MINWIDTH = 20
# Pixel options a widget, or a Text's tag, holds for itself.
WIDGET_PIXEL_OPTIONS = ("borderwidth", "padx", "pady", "highlightthickness",
                        "spacing1", "spacing2", "spacing3", "tabs",
                        "selectborderwidth", "insertwidth", "padding")
TAG_PIXEL_OPTIONS = ("spacing1", "spacing2", "spacing3", "tabs",
                     "lmargin1", "lmargin2", "rmargin", "offset")
TAB_ALIGNMENTS = ("left", "right", "center", "numeric")

TAB_ATTRS = ("SetupTab", "CaptureTab", "InventoryTab", "OptimizerTab",
             "HeroesTab", "ScoringTab", "MaterialsTab",
             "ChecklistTab", "GachaHistoryTab")

# The width handed to every label that rewraps itself on `<Configure>`.
# Past every handler's floor even at 200%, so a wraplength wider than
# this can only have come from scaling the measured width.
PROBE_WIDTH = 1000


def _shadowed_helper():
    """No module may bind `px` to anything but the scaling helper.

    A local called `px` shadows the import for the rest of its scope,
    and the failure is a `TypeError: 'int' object is not callable` that
    waits for that code to RUN -- so a helper reached only when a
    snapshot loads, or a panel repopulates, gets through every build
    the checks do. One did: a loop variable in `populate_set_filters`.

    Source-level for exactly that reason: it needs no code path.
    Returns a list of complaints.
    """
    out = []
    for path in sorted((SOURCE_ROOT / "ui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = any(
            isinstance(node, ast.ImportFrom)
            and node.module in ("ui.scaling", "scaling", "..scaling")
            and any(alias.name == "px" for alias in node.names)
            for node in ast.walk(tree))
        if not imports:
            continue
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, (ast.Assign, ast.For, ast.comprehension)):
                targets = ([node.target] if hasattr(node, "target")
                           else node.targets)
            elif isinstance(node, ast.arguments):
                targets = [ast.Name(id=a.arg) for a in
                           node.posonlyargs + node.args + node.kwonlyargs]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and name.id == "px":
                        out.append(
                            f"{path.name} binds the name `px` at line "
                            f"{getattr(name, 'lineno', node.lineno)}, "
                            f"shadowing the scaling helper it imports. "
                            f"Every `px(...)` after it in that scope "
                            f"raises `'int' object is not callable` -- "
                            f"when it RUNS, which for a populate-on-load "
                            f"helper is not during any check that only "
                            f"builds the tabs.")
    return out


def _minsizes(widget, out, path=""):
    """Every grid row/column `minsize` under `widget`, keyed by path.

    Separate from `_distances` because a minsize belongs to the
    CONTAINER's grid rather than to any child, so it appears in no
    child's `grid_info()` -- and it is pixels like a pad is.
    """
    for index, child in enumerate(widget.winfo_children()):
        here = f"{path}/{child.winfo_class()}[{index}]"
        try:
            columns, rows = child.grid_size()
        except Exception:                   # not a grid container
            columns = rows = 0
        for axis, count, getter in (("col", columns, "grid_columnconfigure"),
                                    ("row", rows, "grid_rowconfigure")):
            for slot in range(count):
                try:
                    info = getattr(child, getter)(slot)
                except Exception:
                    continue
                value = _numbers(info.get("minsize", 0))
                if value and value != (0,):
                    out[f"{here}:{axis}{slot}:minsize"] = value
        _minsizes(child, out, here)
    return out


def _placed_distances(tab, problems):
    """The Exclude panel's distances, read off where its reflow PLACED
    each name, in both of its modes.

    `place()` coordinates are in no pack or grid info, so `_distances`
    cannot see them, and they are a measured width plus hardcoded
    distances -- only the differences are comparable. Laid out with no
    row justified, every gap is the lever: the gap between neighbours,
    the first name's inset, the row pitch past the tallest widget, and
    the frame's height short of its rows.

    The roster is the game's own names, not a capture's, so this runs on
    a fresh clone; the optimizer's is put back after.
    """
    from game_data import CHARACTERS_BY_NAME
    optimizer = tab.optimizer
    roster, mode = optimizer.characters, tab.exclude_order_var.get()
    optimizer.characters = {name: [] for name in sorted(CHARACTERS_BY_NAME)}
    tab.exclude_justify = False
    found = {}
    try:
        for ordered, widgets in ((False, tab._exclude_widgets),
                                 (True, tab._order_widgets)):
            tab.exclude_order_var.set(ordered)
            tab.refresh_exclude_heroes()
            tab._reflow_exclude_heroes(force=True)
            places, rows = tab._exclude_places, tab._exclude_partition
            gaps = [places[b][0] - places[a][0] - places[a][2]
                    for row in rows for a, b in zip(row, row[1:])]
            if not gaps:
                problems.append(
                    "the Exclude panel placed no two names side by side, "
                    "so none of its placed distances was read.")
                continue
            tallest = max(widgets[h].winfo_reqheight() for h in places)
            height = int(tab.exclude_heroes_frame.cget("height"))
            key = "exclude:%s" % ("order" if ordered else "checks")
            found[key + ":gap"] = (min(gaps),)
            found[key + ":inset"] = (min(x for x, _y, _w in places.values()),)
            found[key + ":pitch"] = (tab._exclude_row_h - tallest,)
            found[key + ":height"] = (len(rows) * tab._exclude_row_h
                                      - height,)
    finally:
        optimizer.characters = roster
        tab.exclude_justify = True
        tab.exclude_order_var.set(mode)
        tab.refresh_exclude_heroes()
    return found


def _numbers(value):
    """A geometry option's pixels, as a tuple of ints.

    **A pair comes back as a real tuple from `pack_info` and as a
    space-separated string from `grid_info`**, and a reader that
    handled only one of those would skip every asymmetric pad on half
    the widgets in the app -- which is most of them. `()` means the
    value is not numbers at all and the caller leaves it alone.
    """
    parts = value if isinstance(value, (tuple, list)) else str(value).split()
    try:
        return tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        return ()


def _distances(widget, out, path=""):
    """Every pack/grid pixel option under `widget`, keyed by tree path."""
    for index, child in enumerate(widget.winfo_children()):
        here = f"{path}/{child.winfo_class()}[{index}]"
        # A widget whose pad is a difference of measured widths says so
        # (`pad_measured`): the difference has no bound to hold it to.
        getters = (() if getattr(child, "pad_measured", False)
                   else ("pack_info", "grid_info"))
        for getter in getters:
            try:
                info = getattr(child, getter)()
            except Exception:               # not managed by that manager
                continue
            if not info:
                continue
            for option in PIXEL_OPTIONS:
                if option not in info:
                    continue
                out[f"{here}:{getter}:{option}"] = _numbers(info[option])
        cls = child.winfo_class()
        # Pixels, wherever they are given: a Treeview column's width,
        # and a frame's when it is pinned rather than left to its
        # children. Neither is a pack option, and both have gone
        # unscaled -- every column of four trees at their 100% width,
        # and a column pinned to twice the text it was measured from.
        if cls == "Treeview":
            for column in child["columns"]:
                for option in ("width", "minwidth"):
                    value = _numbers(child.column(column, option))
                    # Tk's own default minimum, which nothing here sets
                    # and a drag is all it bounds.
                    if option == "minwidth" and value == (TK_MINWIDTH,):
                        continue
                    out[f"{here}:column:{column}:{option}"] = value
        elif cls in ("Frame", "TFrame", "TLabelframe", "Labelframe"):
            for option in ("width", "height"):
                pinned = _numbers(child.cget(option))
                # 1 is a frame held shut until its content sizes it, a
                # placeholder rather than a distance.
                if any(value > 1 for value in pinned):
                    out[f"{here}:{option}"] = pinned
        # A widget's own pixels: its border, padding, line spacing and
        # tab stops, and a Text tag's. Given outright they override
        # every default `ui/scaling.py` scales, so each one given
        # without `px` stays its 100% size -- a cell's tab stops left a
        # column at its 100% place in a cell twice as wide.
        for option in WIDGET_PIXEL_OPTIONS:
            # A checkbox's padding is not twice its 100% value on
            # purpose: it carries Tk's unscaled focus inset and height
            # trim as well. `ui/utils/checkbox.py` says how.
            if cls == "Checkbutton" and option in ("padx", "pady"):
                continue
            try:
                value = _stated(child.cget(option))
            except Exception:               # the class has no such option
                continue
            if value:
                out[f"{here}:{option}"] = value
        if cls == "Text":
            for tag in child.tag_names():
                for option in TAG_PIXEL_OPTIONS:
                    value = _stated(child.tag_cget(tag, option))
                    if value:
                        out[f"{here}:tag:{tag}:{option}"] = value
        _distances(child, out, here)
    return out


def _stated(value):
    """The pixel counts in a widget option, alignment words dropped.

    A tab stop list mixes the two -- `50 right 58 left` -- and reads as
    no numbers at all to `_numbers`. `()` for anything in another unit.
    """
    parts = value if isinstance(value, (tuple, list)) else str(value).split()
    out = []
    for part in parts:
        if str(part) in TAB_ALIGNMENTS:
            continue
        try:
            out.append(int(str(part)))
        except ValueError:
            return ()
    return tuple(out)


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _rewraps(frame, scale, tab_name):
    """A wraplength worked out from a `<Configure>` width takes no `px()`.

    The width the event carries is MEASURED -- it has already grown with
    the scale -- so scaling it again sets a wraplength wider than the
    space the label was given, twice as wide at 200%, and the text stops
    wrapping where it should. The pads never show it: a wraplength is
    not a pack option, and at 100% the two are the same number.

    So every widget with a wraplength is handed a `<Configure>` of a
    known width, on itself and on its parent, wherever either binds one.
    A wraplength that MOVES and lands past that width is the failure;
    one that does not move has no handler and is left alone.

    Returns a list of complaints.
    """
    import tkinter as tk

    out = []
    for widget in _walk(frame):
        try:
            before = int(str(widget.cget("wraplength")))
        except (tk.TclError, ValueError):
            continue
        if not before:
            continue
        for target in (widget, widget.master):
            if target is None or "<Configure>" not in target.bind():
                continue
            target.winfo_id()      # an unrealised window takes no events
            target.event_generate("<Configure>", width=PROBE_WIDTH,
                                  height=PROBE_WIDTH)
            after = int(str(widget.cget("wraplength")))
            if after != before and after > PROBE_WIDTH:
                text = str(widget.cget("text"))[:40]
                whose = "own" if target is widget else "parent's"
                out.append(
                    f"{tab_name} at {scale}: {text!r}... rewraps to "
                    f"{after}px when its {whose} <Configure> says "
                    f"{PROBE_WIDTH}px. The event's width is measured and "
                    f"already scaled; wrapping it in `px()` sets the "
                    f"wraplength wider than the label, so the text runs "
                    f"past its space. `px()` the constants around it "
                    f"instead -- see `ui/scaling.py`.")
    return out


def _font_ratio():
    """How much a FONT grows between the two scales.

    The upper end of the band. Read off the app's own faces rather than
    assumed to be 2: Tk rounds each point size to whole pixels, so the
    scaled metric is near double and not on it -- and by a different
    amount at each size, so a distance worked out from a 10pt line can
    grow past what the 9pt body's does.
    """
    import tkinter as tk
    from tkinter import font as tkfont

    from ui import scaling

    faces = (("Segoe UI", 9), ("Segoe UI", 10), ("Segoe UI", 11),
             ("Segoe UI", 14, "bold"), ("Segoe UI Variable Small", 11))
    sizes = []
    for scale in ("100%", "200%"):
        scaling.set_scale(scale)
        root = tk.Tk()
        root.attributes("-alpha", 0.0)
        scaling.apply_font_scaling(root)
        sizes.append([tkfont.Font(font=face).metrics("linespace")
                      for face in faces])
        root.destroy()
    scaling.set_scale("100%")
    return max([2.0] + [high / low for low, high in zip(*sizes)])


def _build(scale, work, problems):
    """Every tab built at one scale, and the distances under them.

    Each tab's rewrapping labels are probed while it stands -- see
    `_rewraps` -- and what that finds goes to `problems`."""
    import tkinter as tk
    from tkinter import ttk

    from ui import scaling
    scaling.set_scale(scale)

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
    ttk.Style().theme_use("clam")

    def load(cls):
        manager = cls(work)
        manager.load()
        return manager

    sm = load(settings_manager.SettingsManager)
    notebook = ttk.Notebook(root)
    context = AppContext(
        root=root, notebook=notebook, optimizer=GearOptimizer(),
        capture_manager=None, config=AppConfig(sm), colors=dict(gui.COLORS),
        style=ttk.Style(), load_data_callback=None,
        refresh_callback=None, inventory_tab=None,
        heroes_tab=None, scoring_tab=None, optimizer_tab=None,
        recompute_upgrade_line_callback=None, settings_manager=sm,
        preset_manager=load(preset_manager.PresetManager),
        character_preset_manager=load(
            character_preset_manager.CharacterPresetManager),
        optimizer_settings_manager=load(
            optimizer_settings_manager.OptimizerSettingsManager),
        log_presets_manager=load(log_presets_manager.LogPresetsManager),
    )
    found = {}
    try:
        for attr in TAB_ATTRS:
            tab = getattr(tabs_pkg, attr)(notebook, context)
            _distances(tab.get_frame(), found, attr)
            _minsizes(tab.get_frame(), found, attr)
            if attr == "OptimizerTab":
                found.update(_placed_distances(tab, problems))
            # After the distances are read: a rewrap moves requested
            # sizes, and the comparison wants the tab as built.
            problems.extend(_rewraps(tab.get_frame(), scale, attr))
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        scaling.set_scale("100%")
    return found


def run():
    add_source_to_path()
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception as exc:                # noqa: BLE001
        raise Skip(f"Tk cannot open a display here ({exc})")

    failures = []
    work = Path(tempfile.mkdtemp())
    live = SOURCE_ROOT / "settings"
    if live.exists():
        # A COPY: building a tab is not reliably read-only.
        shutil.copytree(live, work / "settings")

    failures.extend(_shadowed_helper())

    # The key has to be in `LAYOUT` or it never appears in
    # settings.json: the file is materialised from that list, and a key
    # only ever written when something SETS it would leave a user with
    # no scale to edit and no sign that one exists.
    from settings_manager import SettingsManager
    from ui import scaling
    layout = dict(SettingsManager.LAYOUT)
    if "ui_scale" not in layout:
        failures.append(
            "`ui_scale` is not in `SettingsManager.LAYOUT`, so it never "
            "appears in settings.json -- the file is materialised from "
            "that list and nothing else writes the key until the scale "
            "is changed, which cannot be done without the key.")
    elif layout["ui_scale"] != scaling.DEFAULT_SCALE:
        failures.append(
            f"`LAYOUT` defaults `ui_scale` to {layout['ui_scale']!r} and "
            f"`scaling.DEFAULT_SCALE` is {scaling.DEFAULT_SCALE!r}. The "
            f"two are spelled separately -- importing one into the other "
            f"is circular -- so they have to be held together here.")

    single = _build("100%", work, failures)
    double = _build("200%", work, failures)
    ratio = _font_ratio()

    if not single:
        return ["no geometry options were found at all -- the walk found "
                "no managed widgets, so this check is proving nothing."]

    missing = sorted(set(single) - set(double))
    if missing:
        failures.append(
            f"{len(missing)} widget(s) exist at 100% and not at 200%, e.g. "
            f"{missing[0]}. The two builds have to be the same tree for "
            f"the comparison to mean anything.")

    wrong = []
    for key, value in sorted(single.items()):
        if key not in double:
            continue
        was, now = value, double[key]
        if not was:
            continue
        if len(was) != len(now) or any(
                b and (a == b or a > math.ceil(b * ratio))
                for a, b in zip(now, was)):
            wrong.append((key, was, now))

    if wrong:
        shown = ", ".join(f"{key} {was}->{now}" for key, was, now in wrong[:4])
        failures.append(
            f"{len(wrong)} distance(s) did not scale at 200%: {shown}. "
            f"An UNCHANGED one never went through `px()` and is half the "
            f"size of its neighbours on a scaled screen; one past the "
            f"font's own ratio ({ratio:.2f}x) went through it twice, "
            f"having already grown with the font. The spacing audit sees "
            f"only the gaps it has registered, so nothing else looks at "
            f"either. See `ui/scaling.py`.")

    return failures
