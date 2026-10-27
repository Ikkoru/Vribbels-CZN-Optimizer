"""Say which shipped default files differ from the maintainer's own
settings, as the first two steps of `zCreate exe.bat`'s reminder.

    python default_settings/normalize/compare_defaults.py [SETTINGS DEFAULTS]

Run from `Vribbels/`; the two folders default to `settings/` and
`default_settings/`. A shipped file is refreshed by deleting it and
launching the program, which copies the maintainer's own across
(`docs/how_to_maintain_default_settings.md`). This names the ones that
copy would change: orange steps where any would, green where none.

**Compared as the build will ship them**: the Optimizer settings go
through `normalize_defaults.normalize` first, so the per-user state it
strips (exclude lists, levels seen) never reads as a difference. The
`name_hints` / `name_hint` labels are left out too: the program writes
them for every combatant it meets, so they differ after any capture
and change nothing a player gets.

Always exits 0: a reminder, not a gate. The build fails by itself
while one of the three is missing.
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize_defaults                                   # noqa: E402

FILES = ("presets.json", "character_preset.json", "optimizer_settings.json")

ORANGE = "\x1b[38;5;208m"
GREEN = "\x1b[92m"
RESET = "\x1b[0m"

# The labels the program writes for a reader of the file, and nothing
# reads back as a setting.
LABELS = ("name_hints", "name_hint")


def _without_labels(value):
    if isinstance(value, dict):
        return {k: _without_labels(v) for k, v in value.items()
                if k not in LABELS}
    if isinstance(value, list):
        return [_without_labels(v) for v in value]
    return value


def comparable(name, data):
    """`data` as the build would ship it, labels left out."""
    data = copy.deepcopy(data)
    if name == "optimizer_settings.json":
        normalize_defaults.normalize(data)
    return _without_labels(data)


def differing(settings_dir, defaults_dir):
    """[(file, why)] for each shipped file a copy would change: one
    that differs, or one already deleted. None where there is no
    settings folder to copy from."""
    settings_dir, defaults_dir = Path(settings_dir), Path(defaults_dir)
    if not settings_dir.is_dir():
        return None
    out = []
    for name in FILES:
        mine, shipped = settings_dir / name, defaults_dir / name
        if not shipped.exists():
            out.append((name, "already deleted"))
            continue
        if not mine.exists():
            continue
        try:
            a = json.loads(mine.read_text(encoding="utf-8"))
            b = json.loads(shipped.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.append((name, f"unreadable: {exc}"))
            continue
        if comparable(name, a) != comparable(name, b):
            out.append((name, None))
    return out


def steps(found):
    """The reminder's two lines, and their colour."""
    if found is None:
        return ORANGE, ["1. No settings folder to compare the defaults "
                        "with", "2. zRUN Vribbels"]
    if not found:
        return GREEN, ["1. Delete nothing", "2. Take a deep breath"]
    names = ", ".join(name + (f" ({why})" if why else "")
                      for name, why in found)
    return ORANGE, [f"1. Delete default json files: {names}",
                    "2. zRUN Vribbels"]


def _ask_for_colour():
    """Switch the console to drawing ANSI sequences; False where it
    will not, as in `build_tools/colour_output.py`."""
    if not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)             # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))


def main(argv):
    settings_dir, defaults_dir = (argv + ["settings", "default_settings"]
                                  [len(argv):])[:2]
    colour, lines = steps(differing(settings_dir, defaults_dir))
    coloured = _ask_for_colour()
    for line in lines:
        print(colour + line + RESET if coloured else line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
