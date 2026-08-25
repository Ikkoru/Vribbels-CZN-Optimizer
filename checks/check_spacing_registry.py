"""The spacing registry has to survive being imported.

Every entry is built by `register_all()` at import time, and nothing
else in this project imports that module -- the audit does, and the
audit only runs when the maintainer launches the GUI with a flag and
the window in front of them. So a registry that raises, or registers a
malformed entry, stays broken until someone sets up a screenshot run.

That is exactly the shape of failure `checks/` exists for: quiet, and
discovered at the worst moment.

What it enforces beyond "it imports":

  * every gap states its AXIS, so the table can be read one direction
    at a time. `track` rejects anything but "h"/"v"; this is what makes
    sure the rejection is reached without a GUI.
  * every NAME is unique. Names are the baseline's keys, so a duplicate
    silently drops one entry's reading and reports the other twice.
  * every RULE is one the docs table spells, the same constraint the
    marker check applies to the widget code.
  * importing twice does not double the registry, which `register_all`
    would happily do.
"""

import importlib

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "spacing registry"

VALID_AXES = ("h", "v")
VALID_SOURCES = ("rule", "observed", "inferred")


def run():
    add_source_to_path()
    failures = []

    from ui import spacing_audit as sa
    importlib.import_module("ui.spacing_registry")

    if not sa.REGISTRY:
        return ["the registry is empty -- register_all() did not run on "
                "import, so the audit would measure nothing and report a "
                "clean table"]

    rules = {v for k, v in vars(
        importlib.import_module("ui.spacing_registry")).items()
        if k.startswith("RULE_") and isinstance(v, str)}

    seen = {}
    for g in sa.REGISTRY:
        if g.axis not in VALID_AXES:
            failures.append(f"{g.name!r} has axis {g.axis!r}, not h or v")
        if g.target_source not in VALID_SOURCES:
            failures.append(
                f"{g.name!r} has target_source {g.target_source!r}; "
                f"expected one of {VALID_SOURCES}")
        if not isinstance(g.target, int):
            failures.append(
                f"{g.name!r} has a non-integer target {g.target!r}")
        if g.rule not in rules:
            failures.append(
                f"{g.name!r} names rule {g.rule!r}, which has no RULE_ "
                f"constant -- the marker check compares those against the "
                f"docs table, so a rule invented here escapes it")
        key = (g.name, g.scenario)
        if key in seen:
            failures.append(
                f"{g.name!r} is registered twice in scenario "
                f"{g.scenario!r}; names are the baseline's keys, so one "
                f"reading would be lost silently")
        seen[key] = g

    # register_all() appends, so calling it again doubles everything.
    # Re-importing must not: the module body runs once.
    before = len(sa.REGISTRY)
    importlib.import_module("ui.spacing_registry")
    if len(sa.REGISTRY) != before:
        failures.append(
            f"re-importing the registry grew it from {before} to "
            f"{len(sa.REGISTRY)} entries")

    return failures
