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
        import ui.tabs as tabs_pkg
        from ui.context import AppContext
        from optimizer.optimizer import GearOptimizer
        import preset_manager, character_preset_manager
        import optimizer_settings_manager, settings_manager
        import level_data_manager, log_presets_manager
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
            level_data_manager=_load(level_data_manager.LevelDataManager),
            settings_manager=sm,
            optimizer_settings_manager=_load(
                optimizer_settings_manager.OptimizerSettingsManager),
            log_presets_manager=_load(log_presets_manager.LogPresetsManager),
            recompute_upgrade_line_callback=None,
        )

        notebook = ttk.Notebook(root)
        ctx.notebook = notebook
        for attr in TAB_ATTRS:
            cls = getattr(tabs_pkg, attr, None)
            if cls is None:
                failures.append(f"{attr} is not exported from ui.tabs")
                continue
            try:
                cls(notebook, ctx)
            except Exception as e:
                failures.append(
                    f"{attr} raised while building: "
                    f"{type(e).__name__}: {e}"
                )
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
