"""Write `default_settings/defaults_history.json`: every value each default
has shipped with, read off git history and the files as they stand.

    presets             {preset name: [weights, ...]}
    character_preset    {res_id: [assignment, ...]}
    optimizer_settings  {res_id: {field: [value, ...]}}
    optimizer_generic   [every fresh entry the program has made]
    settings            {settings.json key: [default, ...]}

From `default_settings/presets.json`, `character_preset.json` and
`optimizer_settings.json`, and from the code defaults in
`settings_manager.py` (`SettingsManager.LAYOUT`) and
`optimizer_settings_manager.py` (`DEFAULT_CHARACTER_SETTINGS`), in every
revision that touched them.

The startup sync reads it for an entry no sync has recorded a shipped
value for -- an install from before the sync recorded values: an entry
that matches one of these was never changed, and follows the release
(`defaults_sync`). Run by `zCreate exe.bat` before every build, so the
bundled file holds the release's own values too;
`checks/check_defaults_follow.py` fails while it lags the defaults.

Run from anywhere. Where git cannot be run, the file is left as it is
and the build goes on: it was committed with the history it had.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = HERE.parent
SOURCE = DEFAULTS.parent
sys.path.insert(0, str(SOURCE))

from defaults_sync import HISTORY_FILE, _same                 # noqa: E402
from preset_manager import weights_equal                      # noqa: E402

OUT = DEFAULTS / HISTORY_FILE


def _git(*args):
    return subprocess.run(["git", *args], cwd=SOURCE, capture_output=True,
                          check=True).stdout


def revisions(path):
    """[(commit, path in that commit, from the repository's root)] of
    `path` (under SOURCE), newest first, across renames."""
    out = _git("log", "--follow", "--format=%H", "--name-only", "--",
               Path(path).relative_to(SOURCE).as_posix())
    found, commit = [], None
    for line in out.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if commit is None:
            commit = line
        else:
            found.append((commit, line))
            commit = None
    return found


def shown(commit, path):
    """The text of `path` as `commit` held it, or None."""
    try:
        return _git("show", f"{commit}:{path}").decode("utf-8")
    except subprocess.CalledProcessError:
        return None


def versions(path, read):
    """`read(text)` of `path` now and in every revision, newest first;
    revisions that do not read left out."""
    texts = [Path(path).read_text(encoding="utf-8")]
    texts += [shown(c, p) for c, p in revisions(path)]
    out = []
    for text in texts:
        if text is None:
            continue
        try:
            value = read(text)
        except (ValueError, SyntaxError, KeyError, TypeError):
            continue
        if value is not None:
            out.append(value)
    return out


def _add(seen, value, equal):
    if not any(equal(value, past) for past in seen):
        seen.append(value)


def _json_section(name, key):
    def read(text):
        data = json.loads(text)
        section = data.get(key) if isinstance(data, dict) else None
        return section if isinstance(section, dict) else None
    return versions(DEFAULTS / name, read)


def _assignments(text):
    from character_preset_manager import normalize_to_v2
    data = json.loads(text)
    return normalize_to_v2(data).get("assignments") \
        if isinstance(data, dict) else None


def _literal(source, owner, name):
    """The literal assigned to `name` in `source` -- at module level, or
    inside class `owner` where one is named."""
    tree = ast.parse(source)
    bodies = [tree.body]
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == owner:
            bodies.append(node.body)
    for body in bodies:
        for node in body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            if any(isinstance(t, ast.Name) and t.id == name
                   for t in targets) and node.value is not None:
                return ast.literal_eval(node.value)
    return None


def build():
    history = {"presets": {}, "character_preset": {},
               "optimizer_settings": {}, "optimizer_generic": [],
               "settings": {}}
    for presets in _json_section("presets.json", "presets"):
        for name, weights in presets.items():
            if isinstance(weights, dict):
                _add(history["presets"].setdefault(name, []), weights,
                     weights_equal)
    for assignments in versions(DEFAULTS / "character_preset.json",
                                _assignments):
        for rid, preset in (assignments or {}).items():
            _add(history["character_preset"].setdefault(str(rid), []),
                 preset, _same)
    for characters in _json_section("optimizer_settings.json",
                                    "characters"):
        for rid, entry in characters.items():
            if not str(rid).isdigit() or not isinstance(entry, dict):
                continue
            fields = history["optimizer_settings"].setdefault(str(rid), {})
            for field, value in entry.items():
                if field != "name_hint":
                    _add(fields.setdefault(field, []), value, _same)
    for generic in versions(
            SOURCE / "optimizer_settings_manager.py",
            lambda text: _literal(text, None, "DEFAULT_CHARACTER_SETTINGS")):
        if isinstance(generic, dict):
            _add(history["optimizer_generic"], generic, _same)
    for layout in versions(SOURCE / "settings_manager.py",
                           lambda text: _literal(text, "SettingsManager",
                                                 "LAYOUT")):
        for pair in layout or ():
            if isinstance(pair, tuple) and len(pair) == 2 \
                    and not str(pair[0]).startswith("#"):
                _add(history["settings"].setdefault(pair[0], []), pair[1],
                     _same)
    return history


def main():
    try:
        history = build()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"WARNING: git could not be run ({exc}); "
              f"{OUT.name} is left as it is.")
        return 0
    text = json.dumps(history, indent=1, sort_keys=True) + "\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"{OUT.name} rewritten: "
              f"{sum(map(len, history['presets'].values()))} preset values, "
              f"{len(history['optimizer_settings'])} combatants' settings, "
              f"{len(history['settings'])} settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
