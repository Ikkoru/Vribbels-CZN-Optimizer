"""A settings file that will not read is repaired at launch, or set
aside, and never saved over.

Three layers, each held on its own, since each covers what the others
cannot:

* `settings_repair.Reader` reads past what a hand edit or a cut-off save
  leaves: trailing and missing commas, comments, a line break inside a
  string, a file that ends early. Every case in `READS` comes back
  holding what it should, with the damage where it was.
* `settings_repair.repair_folder` mends each kind of file the way its
  manager reads it. A damaged scoring preset or combatant entry is left
  out whole, never kept in part with defaults standing in for what was
  lost; a byte-order mark or an ANSI save is re-saved as UTF-8 with
  nothing lost; the original is always kept beside it, never over an
  earlier one; a file with nothing readable is set aside, so the sync
  puts the shipped default in its place; a file that will not open is
  left alone.
* Without the repair, nothing writes over a file it could not read: not
  the defaults sync, not `SettingsManager.apply_layout`, not any store's
  save. What stands where the repair could not act.

Never touches `Vribbels/settings/`. Everything happens in a temp folder.
"""

import json
import locale
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, note

NAME = "a settings file that will not read is repaired, never saved over"

# What the reader must make of each: (what it is, text, value, damage,
# where it was cut).
READS = (
    ("a trailing comma", '{"a": 1, "b": [1, 2,],}',
     {"a": 1, "b": [1, 2]}, [], None),
    ("a missing comma", '{"a": 1\n "b": 2}', {"a": 1, "b": 2}, [], None),
    ("comments", '{"a": 1, // why\n "b": /* x */ 2}',
     {"a": 1, "b": 2}, [], None),
    ("single quotes, bare keys and Python's words",
     "{'a': True, b: None, c: False}",
     {"a": True, "b": None, "c": False}, [], None),
    ("a member that does not read", '{"a": 1, "b": 1..0, "c": 3}',
     {"a": 1, "c": 3}, [("b",)], None),
    ("a string never closed", '{"a": "x,\n "b": 2}', {"b": 2},
     [("a",)], None),
    ("the end inside an object", '{"a": 1, "b": {"x": 1, "y": 2',
     {"a": 1, "b": {"x": 1}}, [("b", "y")], ("b", "y")),
    ("the end after a number", '{"a": 1, "b": 12', {"a": 1},
     [("b",)], ("b",)),
    ("an escape pair for one character", '{"a": "\\ud83d\\ude00"}',
     {"a": "\U0001F600"}, [], None),
)

PRESETS = {"presets": {
    "Alpha": {"Flat ATK": 1.0, "ATK%": 1.5},
    "Beryl": {"Flat ATK": 0.5, "ATK%": 2.0},
    "Cass": {"Flat ATK": 0.25, "ATK%": 1.0}}}
COMBATANTS = {"version": 1, "excluded_gear_chars": ["1003", "1004"],
              "characters": {
                  "1003": {"name_hint": "Nia", "extra_pct": 100,
                           "have_at_least": {"Ego": 70}},
                  "1004": {"name_hint": "Luke", "extra_pct": 0}}}
POINTS = [[1027, 0], [1352, 36043], [1400, 40000]]
# Shipped defaults for the sync to work against: each with an entry
# the user's copy has not seen, so a sync that merged into a broken
# file would have something to write over it.
SHIPPED = {
    "presets.json": {"presets": {"Shipped": {"ATK%": 1.0},
                                 "Newer": {"ATK%": 2.0}}},
    "character_preset.json": {"version": 2,
                              "assignments": {"1001": None, "1002": None},
                              "name_hints": {"1001": "a", "1002": "b"}},
    "optimizer_settings.json": {"version": 1, "excluded_gear_chars": [],
                                "characters": {"1001": {}, "1002": {}}},
}
SEEN = {"presets": ["Shipped"], "character_preset": ["1001"],
        "optimizer_settings": ["1001"]}


def _dump(data):
    return json.dumps(data, indent=2)


def _json(path):
    """What `path` holds as JSON, or None: a broken file is a finding
    here, not a reason to stop checking."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _folder(root, name, user=None, raw=None):
    """`<root>/<name>/settings` with `user` files written as JSON and
    `raw` ones as bytes, beside a `default_settings` holding `SHIPPED`
    and a sync record that has seen only part of it."""
    base = root / name
    settings, shipped = base / "settings", base / "default_settings"
    settings.mkdir(parents=True)
    shipped.mkdir()
    for file, data in SHIPPED.items():
        (shipped / file).write_text(_dump(data), encoding="utf-8")
    (settings / ".defaults_sync.json").write_text(json.dumps(SEEN),
                                                  encoding="utf-8")
    for file, data in (user or {}).items():
        (settings / file).write_text(_dump(data), encoding="utf-8")
    for file, data in (raw or {}).items():
        (settings / file).write_bytes(data)
    return base, settings, shipped


def _reads():
    import settings_repair

    out = []
    for what, text, value, damage, cut in READS:
        reader = settings_repair.Reader(text)
        got = reader.read()
        if got != value or reader.damage != damage or reader.cut != cut:
            out.append(
                f"the lenient reader, on {what}: read {got!r} with damage "
                f"{reader.damage} and cut {reader.cut}, not {value!r} with "
                f"{damage} and {cut}. A repair keeps what this reads and "
                f"names what it says was lost.")
    return out


def _repairs(root):
    """Each kind of damage, through the launch's own order: repair,
    sync, then the manager's load."""
    import character_preset_manager
    import checklist_manager
    import defaults_sync
    import preset_manager
    import settings_manager
    import settings_repair

    out = []

    # A damaged preset is left out whole; the rest keep every weight,
    # and the original is kept beside them.
    text = _dump(PRESETS).replace('"ATK%": 2.0', '"ATK%": 2..0')
    base, settings, shipped = _folder(
        root, "presets", raw={"presets.json": text.encode()})
    repairs = settings_repair.repair_folder(settings)
    defaults_sync.sync_defaults(settings, shipped)
    manager = preset_manager.PresetManager(base)
    manager.load()
    want = {k: v for k, v in PRESETS["presets"].items() if k != "Beryl"}
    kept = settings / "presets_corrupted.json"
    if [r.outcome for r in repairs] != [settings_repair.REPAIRED] \
            or "Beryl" not in repairs[0].lost:
        out.append(f"a presets.json with one preset damaged came back as "
                   f"{[(r.outcome, r.lost) for r in repairs]}, not repaired "
                   f"with Beryl named as lost.")
    elif manager.is_corrupted() or {
            k: v for k, v in manager.presets.items() if k in PRESETS[
                "presets"]} != want:
        out.append(f"the repaired presets.json loads as "
                   f"{manager.corruption_error or manager.presets}, not "
                   f"the undamaged presets whole: {want}. A preset kept "
                   f"in part scores with 1.0 for every weight it lost.")
    if not kept.exists() or kept.read_bytes() != text.encode():
        out.append("the repair did not keep the damaged presets.json "
                   "beside the repaired one, byte for byte.")

    # Nothing readable: set aside, never over the copy set aside before,
    # and the sync puts the shipped default in its place.
    (settings / "presets.json").write_bytes(b"\x00" * 64)
    repairs = settings_repair.repair_folder(settings)
    defaults_sync.sync_defaults(settings, shipped)
    settings_repair.note_defaults(repairs, settings)
    second = settings / "presets_corrupted2.json"
    if [(r.outcome, r.defaults) for r in repairs] != [
            (settings_repair.SET_ASIDE, True)]:
        out.append(f"a presets.json of nothing but zeros came back as "
                   f"{[(r.outcome, r.defaults) for r in repairs]}, not set "
                   f"aside with the shipped defaults in its place.")
    if _json(settings / "presets.json") != SHIPPED["presets.json"]:
        out.append("after a presets.json was set aside, the sync did not "
                   "put the shipped default in its place: the user starts "
                   "with no presets at all.")
    if not second.exists() or second.read_bytes() != b"\x00" * 64 \
            or kept.read_bytes() != text.encode():
        out.append("a second set-aside presets.json replaced the first "
                   "one's copy, or was not kept: set_aside must take the "
                   "next free _corrupted<N>.")

    # A lost bracket moves records out of place, and the file's fixed
    # shape puts them back: a preset is an object of weights, and no
    # object is anything else.
    good = _dump(PRESETS)
    no_open = good.replace('"Alpha": {', '"Alpha":')
    for what, text, keep, gone in (
            ("lost Alpha's opening brace", no_open, ("Beryl", "Cass"),
             ["Alpha"]),
            ("lost the line closing Alpha",
             good.replace('"ATK%": 1.5\n    },\n', '"ATK%": 1.5\n'),
             ("Alpha", "Beryl", "Cass"), []),
            ("lost Alpha's opening brace, and Cass a weight",
             no_open.replace('"ATK%": 1.0\n', '"ATK%": 1..0\n'),
             ("Beryl",), ["Alpha", "Cass"])):
        base, settings, shipped = _folder(
            root, "rehome_" + str(len(gone)) + str(len(keep)),
            raw={"presets.json": text.encode()})
        repairs = settings_repair.repair_folder(settings)
        manager = preset_manager.PresetManager(base)
        manager.load()
        want = {name: PRESETS["presets"][name] for name in keep}
        lost = sorted(repairs[0].lost) if repairs else None
        ends = bool(repairs and repairs[0].cut)
        if manager.presets != want or lost != gone or ends:
            out.append(
                f"a presets.json that {what} repairs to "
                f"{manager.corruption_error or sorted(manager.presets)}, "
                f"naming {lost} as lost"
                f"{' and saying it ends early' if ends else ''}: it should "
                f"hold {sorted(want)} whole and name {gone}, a damaged "
                f"preset dropped whole even where the lost bracket left "
                f"it, and a file that ends on its closing brace is whole.")

    # A damaged combatant is left out whole, by name.
    text = _dump(COMBATANTS).replace('"Ego": 70', '"Ego": 7 0')
    base, settings, shipped = _folder(
        root, "combatants", raw={"optimizer_settings.json": text.encode()})
    repairs = settings_repair.repair_folder(settings)
    data = _json(settings / "optimizer_settings.json") or {}
    if [r.lost for r in repairs] != [["Nia"]] or data.get("characters") != {
            "1004": COMBATANTS["characters"]["1004"]}:
        out.append(f"an optimizer_settings.json damaged inside Nia's entry "
                   f"came back as {data.get('characters')}, naming "
                   f"{[r.lost for r in repairs]}: Nia's entry dropped "
                   f"whole and named, Luke's kept. An entry kept in part "
                   f"runs on defaults nobody chose.")

    # The line closing one combatant lost: the next is read inside it,
    # and put back.
    text = _dump(COMBATANTS).replace('      }\n    },\n    "1004"',
                                     '      }\n    "1004"')
    base, settings, shipped = _folder(
        root, "combatants_rehomed",
        raw={"optimizer_settings.json": text.encode()})
    repairs = settings_repair.repair_folder(settings)
    data = _json(settings / "optimizer_settings.json") or {}
    costs = [r.cost_something for r in repairs]
    if data.get("characters") != COMBATANTS["characters"] or costs != [False]:
        out.append(f"an optimizer_settings.json that lost the line closing "
                   f"Nia's entry repairs to {data.get('characters')}, its "
                   f"report saying something was lost: {costs}. Both "
                   f"combatants are whole, and nothing was.")

    # A byte-order mark and a trailing comma: nothing lost.
    base, settings, shipped = _folder(root, "settings", raw={
        "settings.json": b'\xef\xbb\xbf{"ui_scale": "150%", '
                         b'"optimizer_workers": 4,}'})
    repairs = settings_repair.repair_folder(settings)
    manager = settings_manager.SettingsManager(base)
    manager.load()
    if [(r.outcome, r.cost_something) for r in repairs] != [
            (settings_repair.REPAIRED, False)] or manager.is_corrupted() \
            or manager.get("ui_scale") != "150%" \
            or manager.get("optimizer_workers") != 4:
        out.append(f"a settings.json with a byte-order mark and a trailing "
                   f"comma came back as "
                   f"{[(r.outcome, r.cost_something) for r in repairs]} "
                   f"and loads as {manager.settings}: it should be "
                   f"repaired with nothing lost.")

    # An ANSI save: re-saved as UTF-8, names intact.
    ansi = locale.getencoding() if hasattr(locale, "getencoding") \
        else locale.getpreferredencoding(False)
    name = next((n for n in ("光", "Café", "Ærø")
                 if _ansi_only(n, ansi)), None)
    if name is None:
        note(f"no test name is ANSI-only in {ansi}, so the ANSI save "
             f"went unchecked")
    else:
        data = {"version": 2, "assignments": {"1003": name},
                "name_hints": {"1003": "Nia"}}
        base, settings, shipped = _folder(root, "ansi", raw={
            "character_preset.json": json.dumps(
                data, indent=2, ensure_ascii=False).encode(ansi)})
        repairs = settings_repair.repair_folder(settings)
        manager = character_preset_manager.CharacterPresetManager(base)
        manager.load()
        if [(r.outcome, r.cost_something) for r in repairs] != [
                (settings_repair.REPAIRED, False)] \
                or manager.get_preset_by_id("1003") != name:
            out.append(f"a character_preset.json saved in {ansi} came back "
                       f"as {[(r.outcome, r.cost_something) for r in repairs]}"
                       f", Nia's preset reading "
                       f"{manager.get_preset_by_id('1003')!r}, not {name!r}.")

    # Valid JSON in the wrong types: `normalize_to_v2` compares the
    # version and copies the hints, and either raises -- at launch,
    # from the manager's load -- unless the load refuses them first.
    odd = {"version": "2", "assignments": {"1003": "Alpha"},
           "name_hints": ["Nia"]}
    base, settings, shipped = _folder(root, "odd_types",
                                      user={"character_preset.json": odd})
    manager = character_preset_manager.CharacterPresetManager(base)
    try:
        manager.load()
        refused = manager.is_corrupted()
    except Exception as exc:
        refused = f"raised {type(exc).__name__}"
    if refused is not True:
        out.append(f"CharacterPresetManager.load on a string version and "
                   f"listed name hints {refused or 'accepted them'}: it "
                   f"must refuse them, or the launch fails on a hand edit.")
    settings_repair.repair_folder(settings)
    try:
        manager.load()
        held = manager.corruption_error or manager.assignments_by_id
    except Exception as exc:
        held = f"a load that raised {type(exc).__name__}"
    if held != {"1003": "Alpha"}:
        out.append(f"a character_preset.json with a string version and "
                   f"listed name hints repairs to {held}: the assignment "
                   f"is what it holds, and is kept.")

    # Cut inside the ledger: every point before the cut survives.
    full = _dump({"version": 1, "tracked": {"goods": True},
                  "currency": {"2000031": {"kind": "total",
                                           "points": POINTS}}})
    base, settings, shipped = _folder(root, "checklist", raw={
        "checklist.json": full[:full.index("40000") + 2].encode()})
    settings_repair.repair_folder(settings)
    manager = checklist_manager.ChecklistManager(base)
    manager.load()
    if manager.currency_points("2000031") != [tuple(p) for p in POINTS[:2]] \
            or manager.tracked != {"goods": True}:
        out.append(f"a checklist.json cut inside the ledger loads "
                   f"{manager.currency_points('2000031')} and "
                   f"{manager.tracked}: every point before the cut is an "
                   f"observation the game no longer holds, and is kept.")

    # A file that will not open is left alone, by the repair, the sync
    # and its manager alike.
    base, settings, shipped = _folder(root, "unopened")
    (settings / "character_preset.json").mkdir()
    repairs = settings_repair.repair_folder(settings)
    defaults_sync.sync_defaults(settings, shipped)
    manager = character_preset_manager.CharacterPresetManager(base)
    manager.load()
    try:
        manager.set_preset_for("1003", "Alpha")
        saved = True
    except RuntimeError:
        saved = False
    if [r.outcome for r in repairs] != [settings_repair.UNREAD] or saved \
            or not (settings / "character_preset.json").is_dir():
        out.append(f"a character_preset.json that will not open came back "
                   f"as {[r.outcome for r in repairs]}, and its manager "
                   f"{'saved' if saved else 'refused'}: it is left alone, "
                   f"and nothing saves over it.")

    names = {kind.name for kind in settings_repair.KINDS if kind.shipped}
    if names != set(defaults_sync._DEFAULTABLE_FILES):
        out.append(f"settings_repair.KINDS marks {sorted(names)} as shipped, "
                   f"where the sync ships "
                   f"{sorted(defaults_sync._DEFAULTABLE_FILES)}: the report "
                   f"would say the wrong thing about what replaced a file.")
    return out


def _reported(root):
    """Every outcome reaches the launch's report as a paragraph naming
    its file. The report swallows what it raises, since a launch must
    not fail over it, so a broken one would tell nobody that their file
    was moved."""
    from types import SimpleNamespace

    import czn_optimizer_gui
    import settings_repair

    kind = settings_repair.KINDS[1]
    repairs = [
        settings_repair.Repair(kind, settings_repair.REPAIRED,
                               kept_as="a_corrupted.json",
                               lost=["x"] * 9, unnamed=2, cut=True,
                               replaced=True),
        settings_repair.Repair(kind, settings_repair.REPAIRED,
                               kept_as="a_corrupted.json"),
        settings_repair.Repair(kind, settings_repair.SET_ASIDE,
                               kept_as="a_corrupted.json"),
        settings_repair.Repair(kind, settings_repair.SET_ASIDE,
                               kept_as="a_corrupted.json"),
        settings_repair.Repair(kind, settings_repair.UNREAD, error="denied"),
        settings_repair.Repair(kind, settings_repair.FAILED, error="boom"),
    ]
    repairs[3].defaults = True      # and one with a default in its place
    out = []
    for repair in repairs:
        try:
            text = repair.describe()
        except Exception as exc:
            out.append(f"the {repair.outcome} paragraph of the launch's "
                       f"report raises {type(exc).__name__}: {exc}. The "
                       f"report then names no file at all.")
            continue
        if kind.name not in text:
            out.append(f"the {repair.outcome} paragraph of the launch's "
                       f"report does not name its file: {text!r}")
    shown = []
    stub = SimpleNamespace(_settings_repairs=repairs,
                           _warn=lambda title, text: shown.append(text))
    try:
        czn_optimizer_gui.OptimizerGUI._report_settings_repairs(stub)
    except Exception as exc:
        out.append(f"the launch's report of the repairs raised "
                   f"{type(exc).__name__}: {exc}. It runs in the launch, "
                   f"which then fails.")
    if len(shown) != 1:
        out.append(f"the launch's report of {len(repairs)} repairs showed "
                   f"{len(shown)} dialogs, not one.")
    return out


def _ansi_only(text, encoding):
    """Whether `text` encodes in `encoding` to bytes that are not UTF-8,
    so that only the ANSI fallback can read them back."""
    try:
        raw = text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _nothing_saves_over(root):
    """With no repair run, every reader of a broken file leaves it as it
    was: the sync with new defaults to merge, the settings layout, and a
    save through each store."""
    import character_preset_manager
    import checklist_manager
    import defaults_sync
    import log_presets_manager
    import optimizer_settings_manager
    import preset_manager
    import settings_manager

    broken = b'{"broken": '
    files = ("settings.json", "presets.json", "character_preset.json",
             "optimizer_settings.json", "checklist.json",
             "log_presets.json")
    base, settings, shipped = _folder(
        root, "unrepaired", raw={file: broken for file in files})
    defaults_sync.sync_defaults(settings, shipped)
    sm = settings_manager.SettingsManager(base)
    sm.load()
    sm.apply_layout(())
    sm.set("ui_scale", "200%")
    saves = (
        (preset_manager.PresetManager(base),
         lambda m: m.save_preset("probe", {})),
        (character_preset_manager.CharacterPresetManager(base),
         lambda m: m.set_preset_for("1003", "probe")),
        (optimizer_settings_manager.OptimizerSettingsManager(base),
         lambda m: (m.bootstrap_known_characters({1003: {"name": "Nia"}}),
                    m.set(1003, "extra_pct", 5))),
        (checklist_manager.ChecklistManager(base),
         lambda m: m.set_tracked("goods", False)),
        (log_presets_manager.LogPresetsManager(base),
         lambda m: m.set_selected(["1003"], False)),
    )
    for manager, save in saves:
        manager.load()
        try:
            save(manager)
        except RuntimeError:
            pass                            # refused, which is the point
    return [f"{file} was saved over though it could not be read. Whatever "
            f"it held is gone, with nothing kept to recover it from."
            for file in files if (settings / file).read_bytes() != broken]


def run():
    add_source_to_path()
    root = Path(tempfile.mkdtemp())
    try:
        out = _reads()
        out.extend(_repairs(root))
        out.extend(_nothing_saves_over(root))
        out.extend(_reported(root))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return out
