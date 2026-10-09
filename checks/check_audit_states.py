"""Every rendered run works in a copy, never the live folders.

`--audit-state=<state>` points the app at a scratch folder rebuilt for
the run (`Vribbels/audit_states.py`), and a rendered run naming no
state at a copy of the maintainer's own data -- which is what lets it
skip the single-instance lock. The ways this goes wrong are all quiet,
and two of them write to the maintainer's own data:

  * the two data roots disagree. Snapshots hang off
    `capture.constants.BASE_DIR` and settings off
    `czn_optimizer_gui._user_data_dir()`; a state that moved one would
    read the copy's settings beside the live captures, or write the
    live settings while reading no captures -- and look like the state
    it was asked for. The tabs that import the snapshots folder by name
    have to follow too.
  * the shipped defaults move with the data. The copy has no
    `default_settings/`, so `fresh` would install nothing and audit an
    app no user ever sees.
  * the rebuild deletes or copies the wrong thing. It deletes a folder,
    so it has to refuse one that holds the live data.

And the audit's half: a state has a baseline of its own, its rows that
measured nothing are listed apart from the ones that measured, and a
locator not finding its widget reads as a refusal, not as an error.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "audit states run against a copy"

# Imported in a fresh interpreter, since the data root is fixed when
# `capture.constants` is first imported.
ROOTS_PROBE = r"""
import json, sys
from pathlib import Path
sys.argv = ["czn_optimizer_gui.py"] + sys.argv[1:]
import czn_optimizer_gui as gui
from capture.constants import BASE_DIR, OUTPUT_DIR
import ui.tabs.checklist_tab as checklist
import ui.tabs.gacha_history_tab as gacha
from ui.tabs.setup_tab import SetupTab
print(json.dumps({
    "user data": str(gui._user_data_dir()),
    "base": str(BASE_DIR),
    "snapshots": str(OUTPUT_DIR),
    "checklist snapshots": str(checklist.OUTPUT_DIR),
    "gacha snapshots": str(gacha.OUTPUT_DIR),
    "defaults": str(gui._defaults_dir()),
    "restore defaults": str(SetupTab._defaults_file_path(None, "x").parent),
}))
"""


def _roots(*argv):
    run = subprocess.run(
        [sys.executable, "-c", ROOTS_PROBE, *argv], cwd=str(SOURCE_ROOT),
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=120)
    if run.returncode:
        return None, (run.stderr.strip().splitlines() or ["?"])[-1]
    return json.loads(run.stdout.strip().splitlines()[-1]), ""


def _digest(folder):
    h = hashlib.sha256()
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(folder)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def _roots_follow_the_state(audit_states):
    out = []
    source = SOURCE_ROOT.resolve()
    want_defaults = str(source / "default_settings")
    # A rendered run with no state named works in the maintainer's own
    # data COPIED: it takes no single-instance lock, so the live folders
    # must be out of its reach.
    for argv, root in ((("--audit-state=fresh",),
                        audit_states.root_for("fresh").resolve()),
                       (("--spacing-audit",),
                        audit_states.root_for(audit_states.OWN).resolve()),
                       (("--font-gauge",),
                        audit_states.root_for(audit_states.OWN).resolve()),
                       ((), source)):
        roots, err = _roots(*argv)
        said = " ".join(argv) or "no state"
        if roots is None:
            out.append(f"importing the app with {said} raised: {err}")
            continue
        for key in ("user data", "base"):
            if Path(roots[key]).resolve() != root:
                out.append(
                    f"with {said}, {key} is {roots[key]}, not {root}. The "
                    f"settings and the snapshots must move together -- "
                    f"see audit_states.")
        for key in ("snapshots", "checklist snapshots", "gacha snapshots"):
            if Path(roots[key]).resolve() != root / "snapshots":
                out.append(f"with {said}, the {key} folder is {roots[key]}, "
                           f"not under {root}")
        for key in ("defaults", "restore defaults"):
            if str(Path(roots[key]).resolve()) != want_defaults:
                out.append(
                    f"with {said}, the {key} folder is {roots[key]}. The "
                    f"shipped defaults come from the program, or a fresh "
                    f"state installs nothing.")
    return out


def _flag_is_read(audit_states):
    out = []
    for argv, want in ((["x", "--audit-state=empty"], "empty"),
                       (["x", "--audit-state=fresh"], "fresh"),
                       (["x", "--spacing-audit"], None)):
        if audit_states.requested(argv) != want:
            out.append(f"{argv[1:]} reads as state "
                       f"{audit_states.requested(argv)!r}, not {want!r}")
    try:
        audit_states.requested(["x", "--audit-state=bogus"])
        out.append("an unknown state was accepted. Carrying on would run "
                   "against the live folders.")
    except SystemExit:
        pass
    sys.frozen = True
    try:
        if audit_states.requested(["x", "--audit-state=empty"]) is not None:
            out.append("a frozen build honours --audit-state. A released "
                       "exe must not be pointable away from its user's "
                       "data.")
    finally:
        del sys.frozen
    return out


def _prepare_builds_a_copy(audit_states):
    out = []
    real = audit_states.STATES_DIR
    work = Path(tempfile.mkdtemp())
    live = work / "live"
    (live / "settings").mkdir(parents=True)
    (live / "settings" / "settings.json").write_text('{"a": 1}',
                                                     encoding="utf-8")
    (live / "snapshots").mkdir()
    (live / "snapshots" / "memory_fragments_1.json").write_text(
        "{}", encoding="utf-8")
    before = _digest(live)
    audit_states.STATES_DIR = work / "states"
    try:
        empty = audit_states.prepare(audit_states.EMPTY, live)
        (empty / "snapshots" / "left_over.json").write_text(
            "{}", encoding="utf-8")
        empty = audit_states.prepare(audit_states.EMPTY, live)
        if not (empty / "settings" / "settings.json").is_file():
            out.append("the empty state did not copy the live settings")
        if list((empty / "snapshots").iterdir()):
            out.append("the empty state's snapshots folder is not empty "
                       "after a rebuild: a run would see what the last "
                       "one left")
        own = audit_states.prepare(audit_states.OWN, live)
        (own / "snapshots" / "left_over.json").write_text(
            "{}", encoding="utf-8")
        own = audit_states.prepare(audit_states.OWN, live)
        if _digest(own / "settings") != _digest(live / "settings") or \
                _digest(own / "snapshots") != _digest(live / "snapshots"):
            out.append("the own copy is not the live settings and "
                       "snapshots as they are: a rendered run would "
                       "measure something else, or what the last one left")
        fresh = audit_states.prepare(audit_states.FRESH, live)
        if (fresh / "settings").exists():
            out.append("the fresh state has a settings folder before the "
                       "app starts, so the shipped defaults are not what "
                       "it audits")
        if not (fresh / "snapshots").is_dir():
            out.append("the fresh state has no snapshots folder")
        tag = audit_states.STATES_DIR / "CACHEDIR.TAG"
        if not tag.is_file() or not tag.read_bytes().startswith(
                b"Signature: 8a477f597d28d172789f06886806bc55"):
            out.append("the states' folder carries no valid CACHEDIR.TAG")
        if _digest(live) != before:
            out.append("preparing a state changed the live folder")
        try:
            audit_states.prepare(audit_states.EMPTY,
                                 audit_states.root_for(audit_states.EMPTY))
            out.append("prepare rebuilt a folder that holds the live data "
                       "it was given. It deletes what it rebuilds.")
        except ValueError:
            pass
    finally:
        audit_states.STATES_DIR = real
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return out


def _audit_reads_a_state(sa):
    out = []
    if sa.baseline_path(None) != sa.BASELINE_PATH:
        out.append("the maintainer's own run no longer uses "
                   "docs/spacing_baseline.json")
    if os.path.basename(sa.baseline_path("empty")) != \
            "spacing_baseline_empty.json":
        out.append(f"the empty state's baseline is "
                   f"{sa.baseline_path('empty')}")
    measured = ("Measured row", 4, 4, "", "Tab", "h", False, False)
    nothing = ("Refusing row", 4, None, "not found: no Label", "Tab", "h",
               False, False)
    lines = []
    sa._print_table([measured, nothing], lines.append, skips_apart=True)
    text = "\n".join(lines)
    head, _sep, tail = text.partition("measured nothing")
    if "Refusing row" in head or "Refusing row" not in tail:
        out.append("in a state run a row that measured nothing is not "
                   "listed apart from the table:\n" + text)
    for exc, want in ((LookupError("no Label"), "not found"),
                      (IndexError("list index"), "error"),
                      (KeyError("k"), "error")):
        if not sa._raised_note(exc).startswith(want + ":"):
            out.append(f"a resolver raising {type(exc).__name__} reads "
                       f"as {sa._raised_note(exc)!r}, not {want}. Only a "
                       f"locator's own LookupError is a refusal.")
    return out


def _state_targets_name_entries(audit_states, sa):
    """A state's own target is matched by entry NAME, so one naming an
    entry that was renamed, or a state that does not exist, applies to
    nothing and says nothing."""
    from ui import spacing_registry  # noqa: F401  (registers)
    out = []
    names = {g.name for g in sa.REGISTRY}
    if not sa.STATE_TARGETS:
        out.append("no state targets registered, so this part checked "
                   "nothing")
    for state, own in sa.STATE_TARGETS.items():
        if state not in audit_states.STATES:
            out.append(f"state targets for {state!r}, which is no state")
        for name, (target, _why) in own.items():
            if name not in names:
                out.append(f"the {state} state's target for {name!r} names "
                           f"no registered entry, so it applies to nothing")
                continue
            moved = [g for g in sa._for_state(sa.REGISTRY, state)
                     if g.name == name]
            if any(g.target != target or g.target_source != "state"
                   for g in moved):
                out.append(f"the {state} state's target for {name!r} is "
                           f"not what a run in that state measures against")
    return out


def _scale_is_its_own(audit_states, sa):
    """An audit run at a scale is asked for on the command line, held
    to every target scaled as `px` scales it, and compared with a
    baseline of its own -- one baseline for every scale would report
    every gap as changed."""
    from ui import scaling
    out = []
    if tuple(audit_states.SCALES) != tuple(scaling.SCALE_CHOICES):
        out.append(f"audit_states.SCALES {audit_states.SCALES} is not the "
                   f"Settings dropdown's {scaling.SCALE_CHOICES}")
    for argv, want in ((["x", "--audit-scale=200%"], "200%"),
                       (["x", "--spacing-audit"], None)):
        if audit_states.requested_scale(argv) != want:
            out.append(f"{argv[1:]} asks for scale "
                       f"{audit_states.requested_scale(argv)!r}, not {want!r}")
    try:
        audit_states.requested_scale(["x", "--audit-scale=130%"])
        out.append("an unknown audit scale was accepted, and the run would "
                   "lay out at a scale nothing measures against")
    except SystemExit:
        pass
    for state, factor, name in ((None, 2, "spacing_baseline_200.json"),
                                (None, 1.25, "spacing_baseline_125.json"),
                                ("empty", 2,
                                 "spacing_baseline_empty_200.json"),
                                ("fresh", 1, "spacing_baseline_fresh.json")):
        got = os.path.basename(sa.baseline_path(state, factor))
        if got != name:
            out.append(f"the baseline for state {state} at "
                       f"{round(factor * 100)}% is {got}, not {name}")
    gap = sa.TrackedGap("probe", "Tab", "rule", 5, None, hand=2)
    was = scaling.SCALE_CHOICES[0]
    # 200% doubles exactly; 125% lands 5 on 6.25 and 2 on a HALF, which
    # `px` rounds up where Python's `round` would go to the even 2.
    for scale, want in (("200%", (10, 4)), ("125%", (6, 3)),
                        ("150%", (8, 3))):
        widths = [49, 350, 32, 34, 34, 37, 51, 42, 41, 38, 26]
        try:
            scaling.set_scale(scale)
            got = sa.scaled([gap])[0]
            pair = scaling.px((1, 2))
            spans = scaling.px_spans(widths)
            whole = scaling.px(sum(widths))
        finally:
            scaling.set_scale(was)
        if sum(spans) != whole:
            out.append(f"at {scale} a row of columns scaled by px_spans "
                       f"adds up to {sum(spans)}, not px of its total "
                       f"{whole}: rounded one by one, a dozen columns run "
                       f"past the space they were sized for")
        if (got.target, got.hand) != want:
            out.append(f"at {scale} a 5px target with a hand reading of 2 "
                       f"becomes {got.target} and {got.hand}, not "
                       f"{want[0]} and {want[1]}: a target is the 100% "
                       f"distance as `px` puts it on screen, halves up")
        if not all(isinstance(v, int) for v in pair):
            out.append(f"px((1, 2)) at {scale} is {pair!r}: Tk and the "
                       f"arithmetic done on a distance need whole pixels")
    return out


def _launchers_name_their_scale():
    """Every audit run a launcher starts names its scale.

    A run without `--audit-scale` takes the SAVED UI scale. With 200%
    saved, a launcher's "100%" run ran at 200%: two 200% tables, and a
    freeze that never wrote the 100% baseline -- with nothing on screen
    to say so but the heading.
    """
    out = []
    for bat in sorted(SOURCE_ROOT.parent.glob("zRUN Spacing Audit*.bat")):
        for line in bat.read_text(encoding="utf-8").splitlines():
            if ("czn_optimizer_gui.py" in line
                    and "--audit-scale=" not in line):
                out.append(f"{bat.name} starts an audit with no "
                           f"--audit-scale: `{line.strip()}`. It runs at "
                           f"whatever scale the maintainer has saved.")
    return out


def run():
    add_source_to_path()
    import audit_states
    from ui import spacing_audit as sa
    failures = []
    failures.extend(_launchers_name_their_scale())
    failures.extend(_scale_is_its_own(audit_states, sa))
    failures.extend(_flag_is_read(audit_states))
    failures.extend(_prepare_builds_a_copy(audit_states))
    failures.extend(_roots_follow_the_state(audit_states))
    failures.extend(_audit_reads_a_state(sa))
    failures.extend(_state_targets_name_entries(audit_states, sa))
    return failures
