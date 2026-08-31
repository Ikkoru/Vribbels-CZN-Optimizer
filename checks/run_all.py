#!/usr/bin/env python3
"""Run every check. Exit 1 if any of them found something.

    python checks/run_all.py            fast checks; parity is bounded
    python checks/run_all.py --full     parity uses each combatant's
                                        real settings (minutes, not
                                        seconds)
    python checks/run_all.py --list     names only, run nothing

A check either passes, fails with reasons, or SKIPS with a reason --
skipping is what happens on a fresh clone with no captured snapshot, and
is not an error.
"""

import argparse
import multiprocessing
import sys
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

from checks._harness import Skip                       # noqa: E402
from checks import (                                    # noqa: E402
    check_addon_template,
    check_breakdown_reconciles,
    check_capture_banners,
    check_capture_batching,
    check_capture_one_account,
    check_capture_region_routing,
    check_capture_session_file,
    check_dot_types,
    check_fringe_lightness,
    check_game_data,
    check_no_flash,
    check_optimizer_parity,
    check_optimizer_starts_unselected,
    check_repo_root,
    check_settings_roundtrip,
    check_shipped_defaults,
    check_spacing_markers,
    check_spacing_registry,
    check_tabs_build,
)

# Cheapest and most locally-caused first, so a broken edit reports
# against the thing that broke it rather than after a minute of search.
CHECKS = [
    check_repo_root,
    check_spacing_markers,
    check_spacing_registry,
    check_fringe_lightness,
    check_addon_template,
    check_capture_batching,
    check_capture_banners,
    check_capture_one_account,
    check_capture_region_routing,
    check_capture_session_file,
    check_game_data,
    check_dot_types,
    check_shipped_defaults,
    check_settings_roundtrip,
    check_no_flash,
    check_optimizer_starts_unselected,
    check_tabs_build,
    check_breakdown_reconciles,
    check_optimizer_parity,
]

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--full", action="store_true",
                    help="unbounded optimizer parity run")
    ap.add_argument("--list", action="store_true", help="list checks only")
    args = ap.parse_args(argv)

    if args.list:
        for mod in CHECKS:
            print(f"  {mod.NAME}")
        return 0

    failed = skipped = 0
    started = time.time()
    for mod in CHECKS:
        t = time.time()
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
        elapsed = f"{time.time() - t:.1f}s"
        if problems:
            print(f"{RED}FAIL{RESET} {mod.NAME} {DIM}{elapsed}{RESET}")
            for p in problems:
                print(f"       {p}")
            failed += 1
        else:
            print(f"{GREEN}ok{RESET}   {mod.NAME} {DIM}{elapsed}{RESET}")

    total = len(CHECKS)
    print(f"\n{total - failed - skipped}/{total} passed, {failed} failed, "
          f"{skipped} skipped in {time.time() - started:.1f}s")
    if not args.full:
        print(f"{DIM}parity ran bounded; --full for the unbounded run{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
