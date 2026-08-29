"""The Optimizer tab must start with NO combatant selected.

Every per-combatant setting on that tab is written through `_save_int`
and its siblings, and all of them return early while `_current_res_id`
is None. So with nothing selected, moving a slider or ticking a checkbox
changes the screen and touches no file.

**The spacing audit relies on that.** A slider's percent readout is a
fixed-width label with `anchor=tk.E`: a short value leaves its slack on
the left, which is the side the gap to the slider is measured on, so the
gap is 12px wider at 0% than at 100% for no reason but the width of the
digits. The audit's `max_readouts` scenario drives every percent slider
to 100 to measure that gap at a value it actually has -- and it can only
do that safely while the saves are no-ops. (It raises `_loading_settings`
as well; this is the other half of the same guarantee, not a substitute
for it.)

It is also simply convenient: the tab opens in a state where nothing the
maintainer clicks while poking at it is persisted.

What would break this is an auto-select -- picking the first combatant
on load, or restoring the last one from settings. That reads as a
friendly change and would silently give the audit write access to the
maintainer's optimizer settings, so the invariant is pinned here rather
than left to a comment.
"""

import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip, newest_snapshot

NAME = "optimizer starts with no combatant"


def run():
    failures = []
    add_source_to_path()

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
        import log_presets_manager
        from config import AppConfig

        optimizer = GearOptimizer()
        snap = newest_snapshot()
        if snap:
            optimizer.load_data(snap)

        def _load(cls):
            m = cls(work)
            m.load()
            return m

        sm = _load(settings_manager.SettingsManager)
        notebook = ttk.Notebook(root)
        ctx = AppContext(
            root=root, notebook=notebook, optimizer=optimizer,
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

        tab = tabs_pkg.OptimizerTab(notebook, ctx)
        # Loading data is part of starting up whenever a snapshot exists,
        # and it is the step most likely to grow an auto-select.
        if snap:
            tab.refresh_after_load()
        root.update_idletasks()

        chosen = tab.selected_character.get()
        if chosen:
            failures.append(
                f"a combatant is selected on startup ({chosen!r}). Every "
                "per-combatant setting on this tab would then be written "
                "to the maintainer's optimizer settings by anything that "
                "moves a control -- including the spacing audit's "
                "max_readouts scenario, which drives the percent sliders "
                "to 100. See this file's docstring."
            )
        if tab._current_res_id is not None:
            failures.append(
                f"_current_res_id is {tab._current_res_id!r} on startup, "
                "not None. That is the flag the settings writes check, so "
                "it is the one that has to be clear -- an empty dropdown "
                "beside a set res_id still writes."
            )
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)

    return failures
