"""At 200% every distance has to double, and nothing may be left behind.

The spacing audit is 100%-only -- its targets are physical pixels -- so
nothing photographs the scaled window and a distance that stayed at its
100% value is invisible. It is also the most likely mistake by far: the
scaling reaches ~360 call sites, and one `padx=4` that never got its
`px()` reads as a gap half the size of its neighbours on a screen the
maintainer may not be developing on.

So the tabs are built twice, once at each scale, and every geometry
option that carries pixels is compared. A pad that is not exactly
double at 200% is either unwrapped or wrapped twice.

**A distance is not always exactly double**, so the test is not "did
it double". A hardcoded one does; a MEASURED one -- a font width, a
`winfo_reqheight` -- grows by whatever the font grew by, which is under
two because hinting rounds each size to whole pixels. Demanding double
of those would be a wall of false alarms.

What is unambiguous is each failure's own signature:

* a `px()` that was never applied leaves the value **exactly equal**,
  because nothing else in the app is scale-independent;
* a `px()` applied to something already scaled puts it **past the
  font's own ratio**, since it multiplies a grown value again.

So those two are what get flagged, and everything between them is a
distance that scaled by some honest amount.

**`width` and `height` are NOT compared.** They are characters on an
Entry, Spinbox, Combobox, Button and Label, lines on a Text, rows on a
Treeview, and pixels only on a Frame -- so a blanket rule over them
would demand doubling from the ones the font already carries.

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

TAB_ATTRS = ("SetupTab", "CaptureTab", "InventoryTab", "OptimizerTab",
             "HeroesTab", "ScoringTab", "MaterialsTab", "AboutTab")


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
        for getter in ("pack_info", "grid_info"):
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
        _distances(child, out, here)
    return out


def _font_ratio():
    """How much a FONT grows between the two scales.

    The upper end of the band. Read off the app's own body face rather
    than assumed to be 2: Tk rounds each point size to whole pixels, so
    the scaled metric is near double and not on it.
    """
    import tkinter as tk
    from tkinter import font as tkfont

    from ui import scaling

    sizes = []
    for scale in ("100%", "200%"):
        scaling.set_scale(scale)
        root = tk.Tk()
        root.attributes("-alpha", 0.0)
        scaling.apply_font_scaling(root)
        sizes.append(tkfont.Font(font=("Segoe UI", 9)).metrics("linespace"))
        root.destroy()
    scaling.set_scale("100%")
    return max(2.0, sizes[1] / sizes[0])


def _build(scale, work):
    """Every tab built at one scale, and the distances under them."""
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
        style=ttk.Style(), load_file_callback=None, load_data_callback=None,
        switch_tab_callback=None, refresh_callback=None, inventory_tab=None,
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

    single = _build("100%", work)
    double = _build("200%", work)
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
            f"having already grown with the font. The spacing audit runs "
            f"at 100% only, so nothing else looks at either. See "
            f"`ui/scaling.py`.")

    return failures
