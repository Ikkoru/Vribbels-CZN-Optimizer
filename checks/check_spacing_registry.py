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
    marker check applies to the widget code -- OR, for a gap flagged
    `target unique`, a string some `# spacing: unique -- <what>` in the
    widget code spells and the doc's uniques table prices. A unique
    names no rule, so without that pair it could not be tracked at all;
    with it, it is checked against two copies exactly as a rule is.
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
VALID_SOURCES = ("rule", "exception", "inferred", "unique")

UNIQUES_HEADING = "## The uniques, as a table"

# What a uniques row puts in its Distance column to say "no entry may
# measure this". An em dash, so a hyphen typed by hand does not pass for
# it -- the whole point of the mark is that leaving a number out has to
# be a deliberate act.
UNTRACKED_MARK = "—"


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


def _unique_rows():
    """The doc's uniques table, as ({what: target}, {what not tracked}).

    A `unique` names no rule, so the registry carries the marker's own
    `<what>` in its rule field. This table is the second copy that makes
    that field checkable -- without it any string at all would pass, and
    the guard that catches a drifted rule name would have a hole in it
    exactly the shape of a typo.

    A row's Distance is either a plain `<n>px`, which says an entry must
    measure it, or the em dash, which says none may. There is no third
    reading: a unique that ought to be tracked and quietly never was
    would otherwise look exactly like one that cannot be, which is the
    hole this table exists to close.
    """
    doc = io.open(REPO_ROOT / "docs" / "ui_spacing.md",
                  encoding="utf-8").read()
    section = doc.split(UNIQUES_HEADING, 1)
    if len(section) < 2:
        return None, None, None
    targets, untracked, malformed = {}, set(), {}
    for row in section[1].split("\n## ")[0].splitlines():
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 6:
            continue
        what = re.fullmatch(r"`([^`]+)`", cells[1])
        if not what:
            continue
        plain = re.fullmatch(r"(\d+)px", cells[3])
        if plain:
            targets[what.group(1)] = int(plain.group(1))
        elif cells[3] == UNTRACKED_MARK:
            untracked.add(what.group(1))
        else:
            malformed[what.group(1)] = cells[3]
    return targets, untracked, malformed


def _unique_whats():
    """Every `<what>` a `unique` marker in the widget code spells."""
    whats = set()
    for path in glob.glob(str(SOURCE_ROOT / "**" / "*.py"), recursive=True):
        if "__pycache__" in path or "_capture_addon" in path:
            continue
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"#\s*spacing:\s*unique -- (.+?)\s*$",
                             text, re.M):
            whats.add(m.group(1).rsplit(" -- ", 1)[0])
    return whats


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
    unique_targets, untracked, malformed = _unique_rows()
    unique_whats = _unique_whats()
    if unique_targets is None:
        failures.append(
            f"docs/ui_spacing.md no longer contains {UNIQUES_HEADING!r}. "
            f"That table is the second copy of every unique's number; "
            f"without it the rule field accepts any string at all. Update "
            f"UNIQUES_HEADING in checks/check_spacing_registry.py to match "
            f"the doc.")
        unique_targets, untracked, malformed = {}, set(), {}

    measured = {g.rule for g in sa.REGISTRY if g.target_source == "unique"}
    for what in sorted(unique_whats):
        if what not in unique_targets and what not in untracked:
            failures.append(
                f"the unique {what!r} is marked in the widget code but has "
                f"no row in the doc's uniques table. Give it a distance and "
                f"an entry, or the {UNTRACKED_MARK} and a reason -- an "
                f"unmarked one is indistinguishable from one nobody got "
                f"round to tracking")
    for what, cell in sorted(malformed.items()):
        failures.append(
            f"the uniques table gives {what!r} a Distance of {cell!r}, "
            f"which is neither `<n>px` nor {UNTRACKED_MARK}. Prose there "
            f"reads as a reason and is treated as neither tracked nor "
            f"deliberately untracked")
    for what in sorted(set(unique_targets) | untracked):
        if what not in unique_whats:
            failures.append(
                f"the uniques table has a row for {what!r}, which no "
                f"marker in the widget code spells. Either the marker was "
                f"reworded or the site is gone")
    for what, target in sorted(unique_targets.items()):
        if what not in measured:
            failures.append(
                f"the uniques table prices {what!r} at {target}px and "
                f"nothing measures it. A number no entry reads is a claim "
                f"about the screen that never gets tested")
    for what in sorted(untracked):
        if what in measured:
            failures.append(
                f"{what!r} carries {UNTRACKED_MARK} in the uniques table, "
                f"which says no entry may measure it, and one does. Give "
                f"the row its distance instead")

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
        # A rule field outside the rules table is allowed for ONE thing:
        # a `unique`, which by definition has no rule to name. It has to
        # be spelled by a marker in the widget code AND priced by the
        # doc's uniques table, so it is checked against two copies just
        # as a rule name is -- see `_unique_targets`.
        if g.rule not in rules:
            if g.target_source != "unique":
                failures.append(
                    f"{g.name!r} names rule {g.rule!r}, which has no RULE_ "
                    f"constant -- the marker check compares those against "
                    f"the docs table, so a rule invented here escapes it. "
                    f"A gap no rule covers is flagged `target unique`")
            elif g.rule not in unique_whats:
                failures.append(
                    f"{g.name!r} is flagged `target unique` and names "
                    f"{g.rule!r}, which no `# spacing: unique -- ...` "
                    f"marker in the widget code spells. A unique with no "
                    f"site is a string nothing can be greppped back to")
            elif g.rule not in unique_targets:
                failures.append(
                    f"{g.name!r} names unique {g.rule!r}, which has no row "
                    f"with a plain `<n>px` distance in the doc's uniques "
                    f"table. That table is what makes this number "
                    f"checkable; without a row it is unreviewed")
            elif g.target != unique_targets[g.rule]:
                failures.append(
                    f"{g.name!r} carries {g.target} where the doc's uniques "
                    f"table gives {unique_targets[g.rule]} for {g.rule!r}. "
                    f"One of the two has drifted")
        elif g.target_source == "unique":
            failures.append(
                f"{g.name!r} is flagged `target unique` but names "
                f"{g.rule!r}, which IS a rule. A gap a rule covers is on "
                f"the rule or an `exception` to it, never a unique")
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
