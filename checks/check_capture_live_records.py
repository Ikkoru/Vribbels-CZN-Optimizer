"""What the capture keeps current between logins besides the inventory:
a stage's run limit, the account's currencies, and the Galactic
Disaster's weekly Chaos score.

All three arrive whole at login and go stale as the session moves on,
and each has a second source the login's copy must take from. All fail
quietly -- the Checklist reads the stale copy as a plausible figure:

1. **A Simulation clear states the run limit it counted**, as
   `stage_limit_entity` -- singular, a list -- on its reply. Missed, the
   week's runs are not seen until the next launch, and the row reads
   last week's count as stale: every run still left
   (`websocket_debug_20260927_202839`).
2. **A lobby refresh states the currencies as a list** of the records
   the login keys by id. A weekly currency's top-up lands lazily, so the
   login's copy is last week's, and the refresh is what carries the
   topped-up record; a row reading the login's copy has to guess, and
   says so with `~`. An older record arriving late must not overwrite a
   newer one.
3. **A Chaos run states the season's weekly score** on its stage clear
   and on the next disaster reply, each one row -- see
   `_chaos_progress_moves`.

No Tk and no snapshot needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path
from .check_capture_history import _Flow, _addon_class

NAME = "capture keeps run limits and currencies current"

REASON = 2000036
BEFORE = 1789940532         # last week: the login's copies
AFTER = 1790544508          # this week, past the 2026-09-27 reset
NOW = AFTER + 7200


def _reply(addon, qid, **fields):
    addon.websocket_message(_Flow([{"res": "ok", "qid": qid, **fields}]))


def run():
    add_source_to_path()
    from ui.tabs.checklist_tab import TODO, _readings

    Addon = _addon_class()
    failures = []
    addon = Addon(Path(tempfile.mkdtemp(prefix="capture_live_")),
                  log_callback=lambda *a, **k: None)
    addon.character_data = {"currencies": {str(REASON): {
        "res_id": REASON, "amount": 5, "last_update": BEFORE,
        "version": 97}}}
    _reply(addon, 1, stage_limit_entities={"content_boss": {
        "res_id": "content_boss", "count": 3, "reset_time": BEFORE,
        "version": 184}})

    _reply(addon, 2, currencies=[{"res_id": REASON, "amount": 8,
                                  "last_update": AFTER, "version": 98}])
    _reply(addon, 3, currencies=[{"res_id": REASON, "amount": 5,
                                  "last_update": BEFORE, "version": 97}])
    _reply(addon, 4, stage_limit_entity=[{"res_id": "content_boss",
                                          "count": 1, "reset_time": AFTER,
                                          "version": 185}])

    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    out = _readings(saved, NOW)
    if out.get("simulation") != [("2/3", TODO)]:
        failures.append(
            f"after one Simulation clear this week, the row reads "
            f"{out.get('simulation')!r}, not [('2/3', {TODO!r})]. The "
            f"clear's `stage_limit_entity` is the only word of the run "
            f"until the next login.")
    if out.get("sortie_currency") != [("8/9", TODO)]:
        failures.append(
            f"with the lobby's topped-up Reason record (8, this week) "
            f"and a stale copy after it, the row reads "
            f"{out.get('sortie_currency')!r}, not [('8/9', {TODO!r})]. "
            f"The lobby's list is the fresh record; a `~` means the "
            f"login's copy was read, and a 5 that the stale copy won.")
    return failures + _chaos_progress_moves(Addon)


def _chaos_progress_moves(Addon):
    """**A Chaos run states the season's weekly score twice**: under its
    stage clear's `return_info.disaster_chaos_result.disaster_chaos_entity`
    and as the next disaster reply's `disaster_entity`. The login's
    `disaster_entities` is the only copy until the next launch without
    them (`websocket_debug_20260928_205310`: 4000 read all evening after
    a run took it to 8000)."""
    import weekly_reset
    from ui.tabs.checklist_tab import DONE, TODO, _readings
    week = weekly_reset.week_index(NOW)
    addon = Addon(Path(tempfile.mkdtemp(prefix="capture_live_")),
                  log_callback=lambda *a, **k: None)
    addon.inventory_data = {"memory_fragments": []}
    _reply(addon, 1, disaster_entities=[
        {"res_id": "disaster_s03", "week_id": week - 10,
         "week_clear_score": 8000},
        {"res_id": "disaster_s04", "week_id": week,
         "week_clear_score": 4000}])
    failures = []
    for qid, fields, want in (
            (2, {"return_info": {"disaster_chaos_result": {
                "disaster_chaos_entity": {"res_id": "disaster_s04",
                                          "week_id": week,
                                          "week_clear_score": 6000}}}},
             ("6000/8000", TODO)),
            (3, {"disaster_entity": {"res_id": "disaster_s04",
                                     "week_id": week,
                                     "week_clear_score": 8000}},
             ("8000/8000", DONE))):
        _reply(addon, qid, **fields)
        addon._save_data()
        saved = json.loads(Path(addon.saved_path).read_text(
            encoding="utf-8"))
        got = _readings(saved, NOW).get("chaos_progress")
        if got != [want]:
            failures.append(
                f"after {sorted(fields)[0]} states the season's score, "
                f"Galactic Disaster - Chaos reads {got!r}, not {[want]!r}."
                f" See the season rows in capture/manager.py.")
    return failures
