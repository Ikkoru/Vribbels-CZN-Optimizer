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

**A pad is not always exactly double**, and the range is what makes
this readable. A hardcoded distance doubles exactly. One built partly
from a MEASURED font metric grows by whatever the font grew by, which
is not 2 -- Segoe UI 9's linespace goes 15 to 32 -- because hinting
rounds each size to whole pixels. So the band runs from twice to the
font's own ratio, and both ends are failures worth catching: below it
is a `px()` that was never applied, above it is one applied to a
measurement that had already scaled itself.

One pad is exempt outright, in `MEASURED`, for being a widget's own
height rather than a chosen distance.

**`width` and `height` are NOT compared.** They are characters on an
Entry, Spinbox, Combobox, Button and Label, lines on a Text, rows on a
Treeview, and pixels only on a Frame -- so a blanket rule over them
would demand doubling from the ones the font already carries.

Skips itself where Tk cannot open a display.
"""

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

# The one pad that is a WIDGET's own requested height rather than a
# distance anyone chose: the Materials tab's reserved column has no
# heading, and pads its rows down by the height of the heading it does
# not have so they land level with the columns beside it. That height
# scales by whatever a ttk.Label scales by -- part font, part theme
# element -- which is under two, and no `px()` is involved either way.
#
# Keyed by tree path, so a restructure that moves it reports rather
# than silently keeping the exception.
MEASURED = {
    "MaterialsTab/TFrame[0]/TFrame[3]/TFrame[0]:pack_info:pady",
}


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
        if not was or key in MEASURED:
            continue
        if len(was) != len(now) or any(
                b and not (b * 2 <= a <= math.ceil(b * ratio))
                for a, b in zip(now, was)):
            wrong.append((key, was, now))

    if wrong:
        shown = ", ".join(f"{key} {was}->{now}" for key, was, now in wrong[:4])
        failures.append(
            f"{len(wrong)} distance(s) did not double at 200%: {shown}. "
            f"A pad left at its 100% value is half the size of its "
            f"neighbours on a scaled screen, and the spacing audit runs "
            f"at 100% only -- so nothing else looks at this. Wrap the "
            f"value in `px()` at the geometry call (never on the "
            f"constant); see `ui/scaling.py`.")

    return failures
