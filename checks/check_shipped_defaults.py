"""The shipped defaults must not carry the maintainer's own state.

`default_settings/` is bootstrapped by copying the maintainer's
`settings/` wholesale, which brings their exclude lists, the res_ids
their exclude bootstrap has seen, their level-seen map and whatever
levels they optimize at. `normalize/normalize_defaults.py` strips all of
that, and `zCreate exe.bat` runs it before building.

Two ways that goes wrong quietly. The normalizer finds its target by
walking up from its own file, so moving it -- it lives in a subfolder
precisely so that clearing the JSONs by hand cannot delete it -- points
it at nothing. And a defaults file edited by hand after the last
normalize run looks fine in a diff while carrying one res_id nobody
meant to ship.

Neither shows up in the program. A new user just starts with combatants
excluded that they never excluded, and Optimizer levels they never set.
"""

import copy
import importlib.util
import json

from ._harness import SOURCE_ROOT, Skip, add_source_to_path

NAME = "shipped defaults carry no user state"

NORMALIZER = SOURCE_ROOT / "default_settings" / "normalize" / "normalize_defaults.py"
SHIPPED = SOURCE_ROOT / "default_settings" / "optimizer_settings.json"


def _load_normalizer():
    spec = importlib.util.spec_from_file_location("_normalize_defaults", NORMALIZER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    failures = []

    if not NORMALIZER.exists():
        raise Skip(f"no normalizer at {NORMALIZER.name}")
    if not SHIPPED.exists():
        raise Skip("default_settings/optimizer_settings.json is absent")

    module = _load_normalizer()

    # It resolves its own target relative to its file, so a move breaks
    # it -- and the build then either aborts or, without the bat's
    # guard, ships whatever was already there.
    if module.TARGET != SHIPPED:
        failures.append(
            f"The normalizer targets {module.TARGET}, but the shipped "
            f"file is {SHIPPED}. It has been moved without its TARGET "
            f"following."
        )
        return failures

    data = json.loads(SHIPPED.read_text(encoding="utf-8"))

    # Run it over a COPY: this check never writes to the shipped file.
    changed = module.normalize(copy.deepcopy(data))
    if changed:
        failures.append(
            "default_settings/optimizer_settings.json still carries user "
            "state -- run default_settings/normalize/normalize_defaults.py. "
            + "; ".join(changed)
        )

    failures.extend(_priced_minimums(data))
    return failures


def _priced_minimums(data):
    """No shipped Have-at-least minimum for a combatant whose Potential 7
    the score prices in full.

    The score already pays for meeting such a threshold, so a minimum
    only hides the builds that miss it. The normalizer leaves curated
    minimums alone, and the release copies the maintainer's own
    settings in, so this is what catches one coming back with them.
    """
    add_source_to_path()
    from game_data.potential_7 import PRICED, get_potential_7

    found = []
    characters = data.get("characters")
    for key, entry in (characters.items() if isinstance(characters, dict)
                       else ()):
        hal = entry.get("have_at_least") if isinstance(entry, dict) else None
        set_ = {stat: value for stat, value in (
            hal.items() if isinstance(hal, dict) else ()) if value}
        if not set_ or not str(key).isdigit():
            continue
        effects = get_potential_7(int(key))
        if effects and all(e.get("grants") in PRICED for e in effects):
            found.append(f"{key} {set_}")
    if not found:
        return []
    return [f"default_settings/optimizer_settings.json ships Have-at-least "
            f"minimums for combatants whose Potential 7 the score prices "
            f"in full, where the default is 0: {'; '.join(found)}. Zero "
            f"them in your own Optimizer settings too, or the next "
            f"release copy brings them back."]
