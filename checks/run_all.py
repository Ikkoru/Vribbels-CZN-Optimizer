#!/usr/bin/env python3
"""Run every check. Exit 1 if any of them found something.

    python checks/run_all.py            fast checks; parity runs on a
                                        synthetic inventory
    python checks/run_all.py --full     parity runs the newest snapshot,
                                        each combatant on its real
                                        settings (hours, not seconds)
    python checks/run_all.py --list     names only, run nothing

A check either passes, fails with reasons, or SKIPS with a reason --
skipping is what happens on a fresh clone with no captured snapshot, and
is not an error.
"""

import argparse
import gc
import multiprocessing
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Rule names carry arrows, and this prints them. A Windows console
# on a cp932 / cp949 / cp1252 codepage cannot encode those, and the
# failure lands as a UnicodeEncodeError from print() -- reporting the
# checker as broken when the check itself worked fine.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from checks._harness import Skip, take_notes           # noqa: E402
from checks import (                                    # noqa: E402
    check_addon_template,
    check_archive,
    check_audit_states,
    check_bmp_glyphs,
    check_breakdown_reconciles,
    check_capital_band,
    check_certificate_removal,
    check_capture_banners,
    check_capture_batching,
    check_capture_coffee,
    check_capture_always_on,
    check_capture_event_state,
    check_capture_history,
    check_capture_chaos_runs,
    check_base_stats_on_wire,
    check_chaos_estimate,
    check_stats_history,
    check_capture_lag,
    check_capture_live_records,
    check_capture_one_account,
    check_capture_region_routing,
    check_capture_rewards,
    check_capture_saves_once,
    check_capture_session_file,
    check_checklist_readings,

    check_affinity,
    check_day_index,
    check_dot_types,
    check_event_shapes,
    check_excursions,
    check_expiry_captions,
    check_fringe_lightness,
    check_gacha_history,
    check_game_data,
    check_important_settings,
    check_instruction_files,
    check_item_art,
    check_lazy_tabs,
    check_materials_targets,
    check_no_flash,
    check_optimizer_parity,
    check_optimizer_starts_unselected,
    check_period_items,
    check_potential_nodes,
    check_presettle,
    check_repo_root,
    check_runner_collects,
    check_runner_temp,
    check_settings_roundtrip,
    check_shared_facts,
    check_shipped_defaults,
    check_sortie_progress,
    check_spacing_markers,
    check_spacing_registry,
    check_style_once,
    check_tabs_build,
    check_type_ahead,
    check_ui_scales,
    check_unowned_combatants,
    check_upgrade_log_filters,
    check_upgraded_beats,
    check_potential_mean,
    check_potential_band,
    check_preset_weights,
    check_theme_scaling,
    check_window_render,
    check_dpi_hold,
)

# Cheapest and most locally-caused first, so a broken edit reports
# against the thing that broke it rather than after a minute of search.
CHECKS = [
    check_repo_root,
    check_instruction_files,
    check_sortie_progress,
    check_spacing_markers,
    check_spacing_registry,
    check_fringe_lightness,
    check_capital_band,
    check_addon_template,
    check_capture_batching,
    check_capture_coffee,
    check_capture_always_on,
    check_capture_event_state,
    check_capture_history,
    check_capture_chaos_runs,
    check_base_stats_on_wire,
    check_chaos_estimate,
    check_stats_history,
    check_capture_lag,
    check_capture_live_records,
    check_capture_banners,
    check_certificate_removal,
    check_capture_one_account,
    check_capture_region_routing,
    check_capture_rewards,
    check_capture_saves_once,
    check_capture_session_file,
    check_gacha_history,
    check_archive,
    check_game_data,
    check_potential_nodes,
    check_item_art,
    check_materials_targets,
    check_excursions,
    check_dot_types,
    check_shipped_defaults,
    check_shared_facts,
    check_settings_roundtrip,
    check_runner_collects,
    check_runner_temp,
    check_no_flash,
    check_bmp_glyphs,
    check_presettle,
    check_lazy_tabs,
    check_style_once,
    check_optimizer_starts_unselected,
    check_period_items,
    check_expiry_captions,
    check_day_index,
    check_checklist_readings,
    check_event_shapes,
    check_audit_states,
    check_window_render,
    check_dpi_hold,
    check_theme_scaling,
    check_tabs_build,
    check_type_ahead,
    check_ui_scales,
    check_important_settings,
    check_upgrade_log_filters,
    check_upgraded_beats,
    check_potential_mean,
    check_potential_band,
    check_preset_weights,
    check_unowned_combatants,
    check_affinity,
    check_breakdown_reconciles,
    check_optimizer_parity,
]

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")

# Every temporary folder a check makes lands in one folder per run,
# removed when the run ends. Most checks make theirs with `mkdtemp` and
# never remove it; left to them, every run adds dozens to %TEMP%. Pointing
# `tempfile` and the TEMP variables here covers them all at once, the
# processes they start included, without touching each check.
RUN_TEMP_PARENT = Path(tempfile.gettempdir()) / "vribbels-checks"
RUN_TEMP_ENV = "VRIBBELS_CHECKS_TEMP"
# A run killed before its cleanup leaves its folder; the next run takes
# any older than this. Longer than a `--full` run lasts.
STALE_RUN_S = 2 * 86400
CACHEDIR_TAG = ("Signature: 8a477f597d28d172789f06886806bc55\n"
                "# Temporary folders of checks/run_all.py; each run "
                "removes its own.\n")


def _remove_tree(folder):
    """rmtree that also takes read-only files -- git writes its objects
    read-only, and a plain rmtree stops at the first one on Windows."""
    def writable(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(folder, onexc=writable)


def _run_temp():
    """A fresh folder for this run's temporary files, made the default."""
    RUN_TEMP_PARENT.mkdir(exist_ok=True)
    tag = RUN_TEMP_PARENT / "CACHEDIR.TAG"
    if not tag.exists():
        tag.write_text(CACHEDIR_TAG, encoding="ascii")
    for old in RUN_TEMP_PARENT.glob("run-*"):
        try:
            if time.time() - old.stat().st_mtime > STALE_RUN_S:
                _remove_tree(old)
        except OSError:
            pass
    here = Path(tempfile.mkdtemp(prefix="run-", dir=RUN_TEMP_PARENT))
    tempfile.tempdir = str(here)
    os.environ["TEMP"] = os.environ["TMP"] = str(here)
    return here


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--full", action="store_true",
                    help="optimizer parity on the newest snapshot, "
                         "unbounded")
    ap.add_argument("--list", action="store_true", help="list checks only")
    args = ap.parse_args(argv)

    if args.list:
        for mod in CHECKS:
            print(f"  {mod.NAME}")
        return 0

    # A run inside a run -- a check exercising this runner -- keeps the
    # outer run's folder: removing its own would pull the folder out from
    # under the outer run, every later check's temp files with it.
    if os.environ.get(RUN_TEMP_ENV):
        return _run(args)
    saved = (tempfile.tempdir, os.environ.get("TEMP"), os.environ.get("TMP"))
    run_temp = _run_temp()
    os.environ[RUN_TEMP_ENV] = str(run_temp)
    try:
        return _run(args)
    finally:
        del os.environ[RUN_TEMP_ENV]
        tempfile.tempdir = saved[0]
        for name, value in (("TEMP", saved[1]), ("TMP", saved[2])):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        try:
            _remove_tree(run_temp)
        except OSError as e:
            print(f"{YELLOW}note{RESET} {DIM}could not remove {run_temp}: "
                  f"{e}{RESET}")


def _run(args):
    failed = skipped = 0
    started = time.time()
    for mod in CHECKS:
        t = time.time()
        take_notes()               # anything left by a check that raised
        try:
            kwargs = {"full": args.full} if mod is check_optimizer_parity else {}
            problems = mod.run(**kwargs)
        except Skip as why:
            print(f"{YELLOW}SKIP{RESET} {mod.NAME} {DIM}({why}){RESET}")
            skipped += 1
            continue
        except Exception as e:                     # a check itself broke
            print(f"{RED}ERROR{RESET} {mod.NAME}: "
                  f"{type(e).__name__}: {e}")
            failed += 1
            continue
        finally:
            # NOT redundant. A built tab is a reference cycle, so its Tk
            # Variables outlive the check as garbage, and the cyclic
            # collector runs on whichever thread next allocates enough.
            # On a later check's worker thread, each Variable.__del__
            # calls Tcl off the thread that made it and prints
            # "Exception ignored ... main thread is not in main loop"
            # under a check that had nothing to do with it. Collected
            # here, they go on the main thread. Pinned by
            # check_runner_collects.
            gc.collect()
            # NOT redundant either. What the server has said about the
            # game's tables is process-wide (`game_data.learned`), and
            # a check that loads data through the app installs it; left
            # in place, every later check comparing the tables with the
            # server would read the server back as the tables and pass.
            # Pinned by check_base_stats_on_wire.
            learned = sys.modules.get("game_data.learned")
            if learned is not None:
                learned.clear()
        elapsed = f"{time.time() - t:.1f}s"
        if problems:
            print(f"{RED}FAIL{RESET} {mod.NAME} {DIM}{elapsed}{RESET}")
            for p in problems:
                print(f"       {p}")
            failed += 1
        else:
            print(f"{GREEN}ok{RESET}   {mod.NAME} {DIM}{elapsed}{RESET}")
        # A pass with part of its ground unchecked says so, rather than
        # reading the same as a pass that checked everything.
        for said in take_notes():
            print(f"       {YELLOW}note{RESET} {DIM}{said}{RESET}")

    total = len(CHECKS)
    print(f"\n{total - failed - skipped}/{total} passed, {failed} failed, "
          f"{skipped} skipped in {time.time() - started:.1f}s")
    if not args.full:
        print(f"{DIM}parity ran on the synthetic inventory; --full runs "
              f"the newest snapshot{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
