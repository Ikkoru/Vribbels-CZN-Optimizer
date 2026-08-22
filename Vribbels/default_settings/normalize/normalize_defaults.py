"""Strip per-user state out of the shipped optimizer_settings.json.

Run after bootstrapping `default_settings/` from your own `settings/`
(the `_0` marker's step). That copy takes your working state wholesale,
so the file arrives carrying which combatants YOU exclude, which res_ids
your exclude bootstrap has already seen, what level each of your
combatants has reached, and whichever levels you happen to optimize at.
None of that belongs in a new user's first run.

What it does, all of it idempotent:

1. Empties `excluded_gear_chars`, `exclude_seen_rids` and
   `optimize_level_seen`.
2. Sets `excluded_default_initialized` to false, so the first run seeds
   the exclude lists itself.
3. Sets every combatant's `optimize_for_level` to 60, which is what
   makes the Optimizer tab's numbers match the in-game stat sheet out
   of the box.

It also puts the top-level keys in a fixed order, with `characters`
last, so the file reads as a short header over a long body. Keys it does
not recognise are kept and sorted in ahead of `characters` -- dropping
an unknown key is how user state gets lost, and this file is the one
that seeds everyone's.

    python "default_settings/normalize/normalize_defaults.py"

Curated per-combatant values -- a recommended set, a HAL threshold --
are deliberately left alone. See docs/how_to_maintain_default_settings.md.
"""

import json
import sys
from pathlib import Path

# One level up: this script sits in its own subfolder so that clearing
# the shipped JSONs by hand cannot delete it along with them.
TARGET = Path(__file__).resolve().parents[1] / "optimizer_settings.json"

# Emptied wholesale: per-user state the first run seeds for itself.
EMPTY_LIST_KEYS = ("excluded_gear_chars", "exclude_seen_rids")
EMPTY_DICT_KEYS = ("optimize_level_seen",)

DEFAULT_OPTIMIZE_LEVEL = 60

# Everything not named here is sorted in just before `characters`.
KEY_ORDER = (
    "version",
    "excluded_default_initialized",
    "excluded_gear_chars",
    "exclude_seen_rids",
    "optimize_level_seen",
)


def normalize(data: dict) -> list:
    """Apply every rule in place. Returns a line per thing changed."""
    changed = []

    for key in EMPTY_LIST_KEYS:
        before = data.get(key)
        if before != []:
            count = len(before) if isinstance(before, list) else "non-list"
            changed.append(f"{key}: emptied ({count} entries)")
        data[key] = []

    for key in EMPTY_DICT_KEYS:
        before = data.get(key)
        if before != {}:
            count = len(before) if isinstance(before, dict) else "non-dict"
            changed.append(f"{key}: emptied ({count} entries)")
        data[key] = {}

    if data.get("excluded_default_initialized") is not False:
        changed.append(
            f"excluded_default_initialized: "
            f"{data.get('excluded_default_initialized')!r} -> False"
        )
    data["excluded_default_initialized"] = False

    characters = data.get("characters")
    if not isinstance(characters, dict):
        raise SystemExit("`characters` is missing or not an object -- "
                         "is this the right file?")
    levelled = [
        key for key, entry in characters.items()
        if isinstance(entry, dict)
        and entry.get("optimize_for_level") != DEFAULT_OPTIMIZE_LEVEL
    ]
    for key in levelled:
        characters[key]["optimize_for_level"] = DEFAULT_OPTIMIZE_LEVEL
    if levelled:
        changed.append(
            f"optimize_for_level: {len(levelled)} combatant(s) set to "
            f"{DEFAULT_OPTIMIZE_LEVEL}"
        )

    return changed


def reorder(data: dict) -> dict:
    """Fixed header order, unknown keys next, `characters` last."""
    known = set(KEY_ORDER) | {"characters"}
    ordered = {key: data[key] for key in KEY_ORDER if key in data}
    for key in sorted(k for k in data if k not in known):
        ordered[key] = data[key]
    ordered["characters"] = data["characters"]
    return ordered


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"not found: {TARGET}")

    try:
        data = json.loads(TARGET.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{TARGET.name} does not parse: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"{TARGET.name}: root is not an object")

    before = json.dumps(data, indent=2, ensure_ascii=False)
    changed = normalize(data)
    text = json.dumps(reorder(data), indent=2, ensure_ascii=False)

    if text == before:
        print(f"{TARGET.name}: already normalized, nothing written")
        return 0

    # Atomic, matching how the managers write: an interrupted run leaves
    # the old file whole rather than half of a new one.
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(TARGET)

    for line in changed:
        print(f"  {line}")
    if not changed:
        print("  key order only")
    print(f"{TARGET.name}: written, "
          f"{len(data['characters'])} combatant entries kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
