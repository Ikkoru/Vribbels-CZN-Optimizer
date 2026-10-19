"""Write `default_settings/presets_history.json`: every value each shipped
Gear Score preset has held, read off the git history of
`default_settings/presets.json` and the file as it stands.

The startup sync reads it for a player's copy no sync has recorded a
shipped value for -- an install from before the sync recorded values:
a copy that matches one of these was never edited, and follows the
release (`defaults_sync._merge_presets`). Run by `zCreate exe.bat`
before every build, so the bundled file holds the release's own values
too; `checks/check_presets_history.py` fails while it lags the presets.

Run from anywhere. Where git cannot be run, the file is left as it is
and the build goes on: it was committed with the history it had.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = HERE.parent
SOURCE = DEFAULTS.parent
sys.path.insert(0, str(SOURCE))

from defaults_sync import PRESETS_HISTORY_FILE                # noqa: E402
from preset_manager import weights_equal                      # noqa: E402

PRESETS = DEFAULTS / "presets.json"
OUT = DEFAULTS / PRESETS_HISTORY_FILE


def _git(*args):
    return subprocess.run(["git", *args], cwd=SOURCE, capture_output=True,
                          check=True).stdout


def revisions():
    """[(commit, path in that commit, from the repository's root)] of
    presets.json, newest first, across renames."""
    out = _git("log", "--follow", "--format=%H", "--name-only", "--",
               PRESETS.relative_to(SOURCE).as_posix())
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


def presets_at(commit, path):
    """{name: weights} of presets.json as `commit` held it at `path`
    (relative to the repository's root), {} where it does not read."""
    try:
        data = json.loads(_git("show", f"{commit}:{path}").decode("utf-8"))
    except (subprocess.CalledProcessError, ValueError):
        return {}
    presets = data.get("presets") if isinstance(data, dict) else None
    return presets if isinstance(presets, dict) else {}


def main():
    try:
        versions = [presets_at(c, p) for c, p in revisions()]
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"WARNING: git could not be run ({exc}); "
              f"{OUT.name} is left as it is.")
        return 0
    current = json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]
    history = {}
    for presets in [current] + versions:
        for name, weights in presets.items():
            if not isinstance(weights, dict):
                continue
            seen = history.setdefault(name, [])
            if not any(weights_equal(weights, past) for past in seen):
                seen.append(weights)
    text = json.dumps({"presets": dict(sorted(history.items()))}, indent=1,
                      sort_keys=True) + "\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        OUT.write_text(text, encoding="utf-8")
        print(f"{OUT.name}: {sum(map(len, history.values()))} values of "
              f"{len(history)} presets, from {len(versions)} revisions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
