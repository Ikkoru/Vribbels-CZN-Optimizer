"""Settings survive a save/load round-trip, on a COPY.

Three things are checked. First that every manager writes atomically --
temp file plus replace -- because a settings file half-written during a
crash is unrecoverable user state. Second that
`OptimizerSettingsManager.load()` preserves top-level keys it does not
know about: a load that re-reads only the keys it recognises silently
drops the exclude bootstrap's state and the level-seen map, and the
symptom appears runs later as combatants quietly un-excluding
themselves.

Third that every key in `DEFAULT_CHARACTER_SETTINGS` survives both
`_fresh_character_settings` and `get_character_data`. Those two spell
their keys out one per line rather than iterating the defaults, so a
per-character setting added to the defaults and missed in either one is
accepted, written, and then read back as its default forever -- a
slider that will not stay where it is put, with nothing logged.

Fourth that every key the app reads or writes appears in
`SettingsManager.LAYOUT`. A key missing from it still works: it is
created on first write and appended after everything else. What it
loses is the file -- it is absent until something sets it, and then
lands past the `#N` section markers rather than under the one it
belongs to, so a user reading `settings.json` to find a switch does not
see it.

Never touches `Vribbels/settings/`. Everything happens in a temp copy.
"""

import ast
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip

NAME = "settings round-trip"

MANAGERS = [
    "settings_manager.py",
    "preset_manager.py",
    "optimizer_settings_manager.py",
    "character_preset_manager.py",
    "log_presets_manager.py",
    "checklist_manager.py",
]

# The two ways a settings key is spelled in this source: a literal
# handed to the manager, and a module constant holding one. The
# receiver names are listed rather than matching any `.get(` -- a dict
# lookup is spelled the same way, and `flags.get("attribute")` is not a
# settings key.
KEY_CALL = re.compile(
    r"\b(?:sm|settings_manager|_settings)\s*\.\s*(?:get|set)"
    r"\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
KEY_CONST = re.compile(
    r"^[A-Z][A-Z0-9_]*_KEY\s*=\s*['\"]([a-z_][a-z0-9_]*)['\"]", re.M)


def _layout_covers_every_key():
    """Complaints for settings keys the app uses and LAYOUT omits.

    The four Upgrade Log filters are added from their own tuple: they
    are read by iterating it, so no source line spells one.
    """
    import settings_manager
    from upgrade_log_filters import UPGRADE_LOG_FILTERS

    used = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in (KEY_CALL, KEY_CONST):
            for found in pattern.finditer(text):
                used.setdefault(found.group(1), path.name)
    for key in UPGRADE_LOG_FILTERS:
        used.setdefault(key, "upgrade_log_filters.py")

    listed = {key for key, _default in settings_manager.SettingsManager.LAYOUT}
    return [
        f"settings key {key!r} ({where}) is not in "
        f"SettingsManager.LAYOUT. settings.json will not carry it until "
        f"something writes it, and it then lands past the last section "
        f"marker instead of under the section it belongs to."
        for key, where in sorted(used.items()) if key not in listed
    ]


def _writes_atomically(path: Path) -> bool:
    """True when the module's `_write` goes through a temp file."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write":
            body = ast.dump(node)
            return "replace" in body and "tmp" in body.lower()
    return False


def _currency_ledger_keeps_its_shape(root):
    """The Checklist's currency ledger, on a temp root.

    Every reading off it is a subtraction between two points, so
    anything that puts a wrong point in produces a rate that is a
    number and nothing else. Four ways in:

    * a day with six captures recording six points, which would make
      the ledger answer "per day" six times over for that day;
    * an OLD snapshot -- opening a capture file is an ordinary thing to
      do -- written against today, which reads as weeks of earnings
      undone;
    * the creation seed missing, which costs the whole first year of
      readings their far end;
    * a second reading of a day coming back LOWER -- a capture that
      caught the shop payloads mid-purchase -- taking the day with it.

    Returns a list of complaints.
    """
    import checklist_manager as cm
    out = []
    m = cm.ChecklistManager(root)
    m.load()

    # Two captures the same day, the second higher.
    m.record_currency(2000031, 100, 1350, cm.FROM_WIRE, since=1000)
    points = m.record_currency(2000031, 140, 1350, cm.FROM_WIRE, since=1000)
    if points != [(1000, 0), (1350, 140)]:
        out.append(
            f"two captures on one day left {points!r}, not the seed and "
            f"one point at 140. A day is one point however many times it "
            f"is read, and the seed is what a year is measured against.")

    # An older snapshot goes to its OWN day rather than to today's.
    points = m.record_currency(2000031, 120, 1340, cm.FROM_WIRE, since=1000)
    if points != [(1000, 0), (1340, 120), (1350, 140)]:
        out.append(
            f"an older capture left {points!r}. It belongs to the day it "
            f"was taken -- written against today it reads as ten days of "
            f"earnings undone, and every rate off the ledger goes with "
            f"it.")

    # A day read twice, the second lower. A lifetime total only rises,
    # so the lower reading is a capture that caught the shop payloads
    # mid-purchase rather than a day that went backwards.
    m.record_currency(3920007, 800, 1351, cm.FROM_SHOPS, since=1340)
    points = m.record_currency(3920007, 500, 1351, cm.FROM_SHOPS, since=1340)
    if points != [(1340, 0), (1351, 800)]:
        out.append(
            f"a day read 800 then 500 left {points!r}, not 800. A lifetime "
            f"total does not fall, so the lower reading is a capture taken "
            f"between the two shop payloads -- and letting it win would "
            f"put a dip in the record that every rate across it divides "
            f"by.")

    # And it survives the file.
    m._write()
    again = cm.ChecklistManager(root)
    again.load()
    if again.currency_points(2000031) != m.currency_points(2000031):
        out.append(
            f"the ledger came back as {again.currency_points(2000031)!r} "
            f"where it was written as {m.currency_points(2000031)!r}.")

    # Rot in the file costs the rows it is in, and nothing else.
    path = Path(root) / "settings" / "checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["currency"]["9999"] = {"kind": "total", "points": [[1, "x"], [2, 3]]}
    data["currency"]["8888"] = {"kind": "nonsense", "points": [[1, 2]]}
    path.write_text(json.dumps(data), encoding="utf-8")
    rotted = cm.ChecklistManager(root)
    rotted.load()
    if rotted.currency_points(2000031) != m.currency_points(2000031):
        out.append(
            "a malformed row cost the ledger its good rows too. A bad "
            "byte in a settings file must not take the tab with it.")
    if rotted.currency_points(9999) != [(2, 3)]:
        out.append(
            f"a row with one bad point came back as "
            f"{rotted.currency_points(9999)!r}, not its good point alone.")
    if rotted.currency_points(8888):
        out.append("a row of an unknown kind survived the load.")
    return out


def _streak_memory_survives_the_file(root):
    """A finished login streak is remembered across sessions.

    `completed` rides one wire reply and is never sent again -- the
    login that follows carries a row identical to a streak merely
    claimed for today. So the answer has to outlive the session, and
    the only place it can is here: `settings/`, which is not the
    directory a user clears when tidying up captures.

    Returns a list of complaints.
    """
    import checklist_manager as cm
    out = []
    m = cm.ChecklistManager(root)
    m.load()
    if m.streak_finished("event_143"):
        out.append("a fresh manager already calls event_143 finished.")
    m.remember_streak("event_143")
    if not m.streak_finished("event_143"):
        out.append("remembering a finished streak did not take.")

    again = cm.ChecklistManager(root)
    again.load()
    if not again.streak_finished("event_143"):
        out.append(
            "a finished streak was forgotten across a reload. `completed` "
            "is said once and never again, so a memory that does not "
            "reach the file is no memory at all.")
    if again.streak_finished("event_1"):
        out.append("a streak nobody finished came back finished.")

    # **In `settings/`, not `snapshots/`.** The snapshots directory is
    # the one a user clears; this must not be in it.
    where = str(Path(m.file).parent.name)
    if where != "settings":
        out.append(
            f"the streak memory lives in {where!r}. It belongs beside the "
            f"other things the program works out for itself, in the "
            f"directory a capture cleanup never touches.")
    return out


def _event_totals_survive_the_file(root):
    """What a finished instalment held outlives the rows it was counted from.

    The game purges old instalments, so the count is only readable
    while they are there -- and the whole value of it is to a live
    event that starts AFTER they are gone. A record that does not
    reach the file records nothing that matters.

    Returns a list of complaints.
    """
    import checklist_manager as cm
    out = []
    m = cm.ChecklistManager(root)
    m.load()
    m.record_event_total("event_probe", "event_probe_1", 20)
    if m.event_total("event_probe", "event_probe_9") is not None:
        out.append(
            "one instalment on record answered for the family. One is a "
            "number, not a pattern -- the twenty-four login-streak rows "
            "on this account run 7, 10, 14 and 21 days between them.")
    m.record_event_total("event_probe", "event_probe_2", 20)

    again = cm.ChecklistManager(root)
    again.load()
    if again.event_total("event_probe", "event_probe_9") != 20:
        out.append(
            f"two agreeing instalments came back as "
            f"{again.event_total('event_probe', 'event_probe_9')!r} after a "
            f"reload. The rows they were counted from are purged; this "
            f"record is what is left of them.")

    # **A purge must not shrink what was seen whole.** The rows go a
    # few at a time, so a smaller count later is fewer rows rather than
    # a better reading.
    again.record_event_total("event_probe", "event_probe_1", 4)
    if again.events.get("event_probe", {}).get("event_probe_1") != 20:
        out.append(
            f"a later, smaller count overwrote the full one: "
            f"{again.events.get('event_probe')!r}. A count only ever grows "
            f"-- what shrinks is the rows still on the account.")

    # Rot costs the entries it is in and nothing else.
    path = Path(root) / "settings" / "checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # `setdefault`, because a run where nothing was written at all is
    # exactly one of the faults this is here to report -- as a
    # complaint, not as a KeyError from the line that injects the rot.
    rows = data.setdefault("events", {})
    rows["broken"] = {"event_x": "twenty"}
    rows["worse"] = "not a table at all"
    path.write_text(json.dumps(data), encoding="utf-8")
    rotted = cm.ChecklistManager(root)
    rotted.load()
    if rotted.event_total("event_probe", "event_probe_9") != 20:
        out.append(
            "a malformed entry cost the record its good families too.")
    if rotted.events.get("broken") or rotted.events.get("worse"):
        out.append(
            f"rot survived the load: {rotted.events!r}. A count that is "
            f"not a count would be compared against a row tally.")
    return out


def _final_rewards_survive_the_file(root):
    """Which families pay a final reward outlives the record it was read off.

    The completion record that says so is purged some weeks after its
    instalment ends, and the whole value of remembering it is to the
    NEXT instalment -- which starts after the record is gone.

    Returns a list of complaints.
    """
    import checklist_manager as cm
    out = []
    m = cm.ChecklistManager(root)
    m.load()
    if m.pays_final("event_nodelist"):
        out.append("a fresh manager already says event_nodelist pays a "
                   "final reward.")
    m.remember_final("event_nodelist", "event_nodelist_006")
    m.remember_final("event_nodelist", "event_nodelist_006")

    again = cm.ChecklistManager(root)
    again.load()
    if again.finals.get("event_nodelist") != ["event_nodelist_006"]:
        out.append(
            f"the final-reward record came back as {again.finals!r}. It is "
            f"read off a completion record the game purges, so what does "
            f"not reach the file is gone before the next instalment "
            f"needs it.")
    if again.pays_final("event_devil"):
        out.append("a family nobody saw pay a final reward came back as one.")

    # Rot costs the entry it is in and nothing else.
    path = Path(root) / "settings" / "checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.setdefault("finals", {})
    rows["broken"] = "not a list"
    rows["worse"] = [7, None]
    path.write_text(json.dumps(data), encoding="utf-8")
    rotted = cm.ChecklistManager(root)
    rotted.load()
    if not rotted.pays_final("event_nodelist"):
        out.append("a malformed entry cost the record its good families too.")
    if rotted.pays_final("broken") or rotted.pays_final("worse"):
        out.append(f"rot survived the load: {rotted.finals!r}.")
    return out


def _finished_answers_survive_the_file(root):
    """The user's `Finished?` answers outlive the session.

    They are the only word anything has on whether most events are
    over, so losing them costs the user the answer AND the question --
    the row goes back to red and asks again.

    Returns a list of complaints.
    """
    import checklist_manager as cm
    out = []
    m = cm.ChecklistManager(root)
    m.load()
    m.call_finished("event_devil_1", 21, 21)

    again = cm.ChecklistManager(root)
    again.load()
    if not again.called_finished("event_devil_1", 21, 21):
        out.append(
            "an answer did not survive a reload. Nothing else on the tab "
            "says an event is over, so a forgotten answer is a row that "
            "goes back to red for the rest of the event's run.")
    if again.called_finished("event_devil_1", 22, 21):
        out.append(
            "an answer given for 21 of 21 answered for 22 of 21 as well. "
            "It is about the reading it was given for: another reward "
            "claimed is a different question.")
    if again.called_finished("event_devil_1", 21, 22):
        out.append(
            "an answer given for 21 of 21 answered for 21 of 22 as well. "
            "Another reward to claim is a different question.")

    again.call_finished("event_devil_1", 0, 0, done=False)
    third = cm.ChecklistManager(root)
    third.load()
    if third.called_finished("event_devil_1", 21, 21):
        out.append("unticking did not reach the file.")

    # Rot costs the entry it is in and nothing else.
    path = Path(root) / "settings" / "checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("finished", {})["good"] = [3, 3]
    data["finished"]["bad"] = ["three", 3]
    data["finished"]["worse"] = 7
    path.write_text(json.dumps(data), encoding="utf-8")
    rotted = cm.ChecklistManager(root)
    rotted.load()
    if not rotted.called_finished("good", 3, 3):
        out.append("a malformed answer cost the record its good ones too.")
    if "bad" in rotted.finished or "worse" in rotted.finished:
        out.append(
            f"rot survived the load: {rotted.finished!r}. An answer that is "
            f"not a pair of counts cannot be compared against a reading, "
            f"and one that cannot be checked is worse than none.")
    return out


def run():
    failures = []
    add_source_to_path()

    for fname in MANAGERS:
        path = SOURCE_ROOT / fname
        if not path.exists():
            failures.append(f"{fname} is missing")
            continue
        if not _writes_atomically(path):
            failures.append(
                f"{fname}: _write does not look atomic (no temp file + "
                f"replace). A crash mid-write loses the user's state."
            )

    failures.extend(_layout_covers_every_key())

    ledger_root = Path(tempfile.mkdtemp())
    try:
        failures.extend(_currency_ledger_keeps_its_shape(ledger_root))
        failures.extend(_streak_memory_survives_the_file(ledger_root))
        failures.extend(_event_totals_survive_the_file(ledger_root))
        failures.extend(_final_rewards_survive_the_file(ledger_root))
        failures.extend(_finished_answers_survive_the_file(ledger_root))
    finally:
        shutil.rmtree(ledger_root, ignore_errors=True)

    live = SOURCE_ROOT / "settings" / "optimizer_settings.json"
    if not live.exists():
        raise Skip("no settings/optimizer_settings.json to round-trip")

    tmp_root = Path(tempfile.mkdtemp())
    try:
        work = tmp_root / "settings"
        work.mkdir(parents=True)
        shutil.copy2(live, work / "optimizer_settings.json")

        import optimizer_settings_manager as osm
        before = json.loads(live.read_text(encoding="utf-8"))

        m = osm.OptimizerSettingsManager(tmp_root)
        m.load()
        m._write()
        after = json.loads((work / "optimizer_settings.json")
                           .read_text(encoding="utf-8"))

        for key in before:
            if key not in after:
                failures.append(
                    f"optimizer_settings.json: top-level key {key!r} was "
                    f"dropped by load() + _write(). User state is lost."
                )

        defaults = osm.DEFAULT_CHARACTER_SETTINGS
        fresh = osm._fresh_character_settings("probe")
        for key in defaults:
            if key not in fresh:
                failures.append(
                    f"_fresh_character_settings omits {key!r}. A new "
                    f"character's entry would never carry it."
                )

        # A round-trip through the store, so the reader is exercised on a
        # written entry rather than on the defaults dict.
        probe_id = 999999
        m.ensure_character(probe_id, name="probe")
        for key, value in defaults.items():
            if isinstance(value, int) and not isinstance(value, bool):
                m.set(probe_id, key, value + 1)
        m._write()

        reread = osm.OptimizerSettingsManager(tmp_root)
        reread.load()
        stored = reread.get_character_data(probe_id)
        for key, value in defaults.items():
            if key not in stored:
                failures.append(
                    f"get_character_data omits {key!r}. It is saved to "
                    f"disk and then read back as its default."
                )
            elif isinstance(value, int) and not isinstance(value, bool) \
                    and stored[key] != value + 1:
                failures.append(
                    f"{key!r} did not survive the round-trip: wrote "
                    f"{value + 1}, read back {stored[key]!r}."
                )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return failures
