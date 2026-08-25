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
  * a gap flagged `target rule` really is the number the rule
    derives, and one flagged `exception`/`inferred` really is not. The
    flag decides whether a later reader may "correct" the number from
    the rule, so a target that lies about where it came from is worse
    than a wrong number -- it is a wrong number nobody is allowed to
    question. This has been wrong once: the flag was derived from
    membership of the overrides table rather than stated, which marked
    Restore Defaults' perfectly ordinary 3 as a hand reading.
  * importing twice does not double the registry, which `register_all`
    would happily do.
"""

import glob
import importlib
import io
import re

from ._harness import REPO_ROOT, SOURCE_ROOT, add_source_to_path

NAME = "spacing registry"

VALID_AXES = ("h", "v")
VALID_SOURCES = ("rule", "exception", "inferred")


def _rule_targets():
    """{marker: target} for every rule the docs table gives ONE number.

    Read from the table rather than restated here, for the same reason
    the marker check reads the marker column from it: a second copy of a
    number does not fail when it drifts, it just disagrees quietly.

    A trailing qualifier is fine: "5px, all edges" still names one
    number. What is left out is a target with an ALTERNATIVE -- "2px
    (5px where the title has no descender)", "16px, or min 16px where
    the distance varies" -- because there the condition is what decides
    and the registry derives it per entry.
    """
    doc = io.open(REPO_ROOT / "docs" / "ui_spacing.md",
                  encoding="utf-8").read()
    targets = {}
    for row in doc.splitlines():
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 5:
            continue
        marker = re.fullmatch(r"`([^`]+)`", cells[3])
        plain = re.fullmatch(r"(\d+)px(?:,(?! or ).*)?", cells[2])
        if marker and plain:
            targets[marker.group(1)] = int(plain.group(1))
    return targets


def _excepted_rules():
    """Rules the widget code says some site deliberately breaks.

    Only the `exception` form counts. A `unique` site has no rule at
    all, so it never produces a registry entry naming one -- accepting
    it here would let any unique marker anywhere excuse every miss.
    """
    excepted = set()
    for path in glob.glob(str(SOURCE_ROOT / "**" / "*.py"), recursive=True):
        if "__pycache__" in path or "_capture_addon" in path:
            continue
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"#\s*spacing:\s*exception -- (.+?)\s*$",
                             text, re.M):
            excepted.add(m.group(1).rsplit(" -- ", 1)[0])
    return excepted


def run():
    add_source_to_path()
    failures = []

    from ui import spacing_audit as sa
    registry = importlib.import_module("ui.spacing_registry")

    if not sa.REGISTRY:
        return ["the registry is empty -- register_all() did not run on "
                "import, so the audit would measure nothing and report a "
                "clean table"]

    rules = {v for k, v in vars(registry).items()
             if k.startswith("RULE_") and isinstance(v, str)}
    rule_targets = _rule_targets()
    excepted = _excepted_rules()

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
        # Every rule with one number in the docs table is compared
        # against THAT, including the title and tab-list rules. They
        # used to derive a target per string, and this check called the
        # very function that produced it -- so the comparison could not
        # fail, whatever either side said. Correcting the reading rather
        # than the target made both constants, which puts them back
        # under the table like everything else.
        expected = rule_targets.get(g.rule)
        where = "the docs table gives for that rule"
        if expected is not None and g.target != expected:
            # A target that misses its rule means the site breaks the
            # rule, and a site that breaks a rule carries an `exception`
            # or a `unique` saying so. This finds the marker for the
            # RULE, not for this panel -- nothing ties an entry to a
            # call site -- so it catches a miss nobody marked anywhere,
            # not a miss marked on the wrong panel.
            if g.rule not in excepted:
                failures.append(
                    f"{g.name!r} carries {g.target} where its rule asks "
                    f"{expected}, but no `exception` or `unique` marker in "
                    f"the widget code says that rule is broken. A miss with "
                    f"nothing marking it reads as a target someone typed "
                    f"wrong")
        if expected is not None:
            if g.target_source == "rule" and g.target != expected:
                failures.append(
                    f"{g.name!r} is flagged `target rule` but carries "
                    f"{g.target}, where {expected} is what {where}. Either "
                    f"the number is a hand reading and should say so, or it "
                    f"is wrong")
            if g.target_source != "rule" and g.target == expected:
                failures.append(
                    f"{g.name!r} is flagged `target {g.target_source}` but "
                    f"carries {expected}, exactly what {where}. A target "
                    f"claiming to be a reading cannot be corrected from the "
                    f"rule by a later reader -- do not spend that on a number "
                    f"the rule already gives")
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
