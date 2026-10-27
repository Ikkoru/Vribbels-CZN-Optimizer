"""A combatant's preset assignment filed under her name moves onto her
id once the program knows it.

`character_preset.json` keys assignments by res_id, and by name only
while CHARACTERS cannot resolve the name. A combatant only the game
client names is resolvable only once the client's read lands, after the
launch's snapshot has filed her by name (`ensure_characters`). Unfolded,
the name key sits beside the id key for good: nothing reads it, and a
default-settings refresh ships it to every player. Nothing on screen
shows it.

Held three ways: `fold_name_keys` on its own, a file loaded with a
stray name key, and a manager whose lookups predate the combatant
(`relink_names`). Also holds the main window to relinking after every
client read it applies.
"""

import ast
import json
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "a preset assignment filed by name moves onto the id"

GUI_SOURCE = SOURCE_ROOT / "czn_optimizer_gui.py"


def _fold_cases(cpm):
    out = []
    ids = {"Known": "1001"}
    cases = (
        ("a name key alone", {"Known": "P"}, {"1001": "P"}),
        ("a null name key beside its id", {"Known": None, "1001": "P"},
         {"1001": "P"}),
        ("a name key beside its null id", {"1001": None, "Known": "P"},
         {"1001": "P"}),
        ("both set", {"1001": "P", "Known": "Q"}, {"1001": "P"}),
        ("a name nothing resolves", {"Stranger": "P"}, {"Stranger": "P"}),
    )
    for what, given, wanted in cases:
        hints = {key: "Known" if key == "1001" else key for key in given}
        got, got_hints = cpm.fold_name_keys(given, hints, ids)
        if got != wanted:
            out.append(f"{what}: the assignments fold to {got}, not "
                       f"{wanted} (`fold_name_keys`).")
        if "1001" in got and got_hints.get("1001") != "Known":
            out.append(f"{what}: the id's name hint is "
                       f"{got_hints.get('1001')!r}, not 'Known'.")
        if any(k not in got for k in got_hints):
            out.append(f"{what}: a name hint outlived its assignment.")
    return out


def _loaded(cpm):
    """A file with a stray name key, loaded and written back."""
    from game_data.characters import CHARACTERS
    rid, char = next((str(k), v) for k, v in CHARACTERS.items()
                     if isinstance(v, dict) and v.get("name")
                     and v.get("name") != "Unknown")
    name = char["name"]
    folder = Path(tempfile.mkdtemp(prefix="cpm_"))
    path = cpm.CharacterPresetManager(folder).assignments_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 2,
        "assignments": {rid: "P", name: None},
        "name_hints": {rid: name, name: name}}), encoding="utf-8")
    manager = cpm.CharacterPresetManager(folder)
    manager.load()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    if name in manager.assignments_by_id or name in on_disk["assignments"]:
        return [f"a file holding {name!r} beside {rid!r} kept the name key "
                f"on load (`normalize_to_v2`), so it ships with the next "
                f"default-settings refresh."]
    return []


def _relinked(cpm):
    """A combatant added by name before CHARACTERS knew her."""
    out = []
    build = cpm._build_character_name_maps
    maps = [({}, {})]
    cpm._build_character_name_maps = lambda: maps[0]
    try:
        folder = Path(tempfile.mkdtemp(prefix="cpm_"))
        manager = cpm.CharacterPresetManager(folder)
        manager.load()
        manager.ensure_characters(["Newcomer"])
        if "Newcomer" not in manager.assignments_by_id:
            return ["setup: an unknown combatant was not filed by name."]
        maps[0] = ({"Newcomer": "99999"}, {"99999": "Newcomer"})
        manager.relink_names()
        on_disk = json.loads(
            manager.assignments_file.read_text(encoding="utf-8"))
        if "Newcomer" in manager.assignments_by_id \
                or "99999" not in on_disk["assignments"] \
                or "Newcomer" in on_disk["assignments"]:
            out.append("after CHARACTERS learned a combatant filed by name, "
                       "`relink_names` left her under the name, on disk or "
                       "in memory.")
    finally:
        cpm._build_character_name_maps = build
    return out


def _gui_relinks():
    """Every main-window function applying client facts relinks."""
    tree = ast.parse(GUI_SOURCE.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        attrs = [n.attr for n in ast.walk(node)
                 if isinstance(n, ast.Attribute)]
        if "use" in attrs and any(
                isinstance(n, ast.Attribute) and n.attr == "use"
                and isinstance(n.value, ast.Name)
                and n.value.id == "game_client" for n in ast.walk(node)) \
                and "relink_names" not in attrs:
            out.append(f"`OptimizerGUI.{node.name}` applies the client's "
                       f"facts without `relink_names()`: a combatant only "
                       f"the client names stays filed by name.")
    return out


def run():
    add_source_to_path()
    import character_preset_manager as cpm
    return _fold_cases(cpm) + _loaded(cpm) + _relinked(cpm) + _gui_relinks()


def _gui_without_relink():
    """Point the check at a copy of the main window that applies the
    client's read without relinking."""
    global GUI_SOURCE
    text = GUI_SOURCE.read_text(encoding="utf-8")
    copy = Path(tempfile.mkdtemp(prefix="gui_")) / GUI_SOURCE.name
    copy.write_text(text.replace(
        "        game_client.use(facts)\n"
        "        # NOT redundant",
        "        game_client.use(facts)\n"
        "        self.character_preset_manager = None\n"
        "        # NOT redundant").replace(
        "        self.character_preset_manager.relink_names()\n"
        "        self._presets_follow_client()\n"
        "        self._refresh_client_tabs()",
        "        self._presets_follow_client()\n"
        "        self._refresh_client_tabs()"), encoding="utf-8")
    GUI_SOURCE = copy


CPM = "character_preset_manager"

FAULTS = [
    ("name keys never fold",
     f"{CPM}:fold_name_keys",
     "if rid is None or rid == key:",
     "if True:",
     "a name key alone"),
    ("a null name key overwrites its id",
     f"{CPM}:fold_name_keys",
     "if rid not in assignments or (assignments[rid] is None\n"
     "                                      and value is not None):",
     "if True:",
     "a null name key beside its id"),
    ("the name hint lost",
     f"{CPM}:fold_name_keys",
     "            name_hints[rid] = hint\n",
     "            pass\n",
     "the id's name hint"),
    ("a v2 file not folded on load",
     f"{CPM}:normalize_to_v2",
     "_build_character_name_maps()[0])",
     "{})",
     "kept the name key on load"),
    ("relink keeps the stale lookups",
     f"{CPM}:CharacterPresetManager.relink_names",
     "self.invalidate_name_cache()",
     "pass",
     "left her under the name"),
    ("the client's read applied without a relink",
     _gui_without_relink, None, None,
     "without `relink_names()`"),
]
