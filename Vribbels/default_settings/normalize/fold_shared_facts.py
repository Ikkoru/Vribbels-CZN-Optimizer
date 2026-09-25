"""Fold game facts into the shipped `default_settings/shared_facts.json`.

Always folds in the facts your own captures hold -- which is what
`zCreate exe.bat` runs it for. Name files after it and it folds those in
too: the `Export Facts` files players attach to a GitHub issue.

    python "default_settings/normalize/fold_shared_facts.py" [file ...]

Every file goes through `shared_facts`' whitelist on the way in, so
nothing but the kinds of game fact it names can land in the shipped
copy whatever a file holds. What each fold added is printed, and so is
anything it refused -- a banner whose rates differ from the ones held
is a question to settle by hand, not an update.

**It stops, writing nothing, rather than lose anything.** A shipped
file that will not read, or holds entries the whitelist drops, is
refused: rebuilding it from your captures alone would throw away every
fact players have sent. So is a file named that is not an export, and
so is a fold that would leave out anything the shipped file held --
which the fold's own rules never do, so it would be a bug. A non-zero
exit stops the build.

**Review the diff before committing.** This is the one file every
player's copy reads facts from. See
docs/how_to_maintain_default_settings.md.
"""

import json
import sys
from pathlib import Path

# The source root, two levels up: this script sits in its own
# subfolder of `default_settings/`, like `normalize_defaults.py`.
SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))

import shared_facts  # noqa: E402

TARGET = shared_facts.shipped_path(SOURCE / "default_settings")


def _read_export(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    facts = shared_facts.read_document(data)
    if facts is None:
        raise SystemExit("%s is not a shared facts export" % path)
    return facts


def _read_shipped():
    """The shipped facts, or empty where there is no file yet. Refuses
    one that is there and not whole."""
    if not TARGET.exists():
        return shared_facts.empty()
    try:
        data = json.loads(TARGET.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            "%s will not read (%s). Nothing written: folding into it would "
            "rebuild it from your captures alone. Restore it from git."
            % (TARGET.name, exc))
    if not shared_facts.whole(data):
        raise SystemExit(
            "%s is not a whole shared facts file: another kind or version, "
            "or entries the whitelist drops. Nothing written; compare it "
            "with git before folding into it." % TARGET.name)
    return shared_facts.read_document(data)


def main(paths) -> int:
    contributed = [(Path(path).name, _read_export(path)) for path in paths]
    before = _read_shipped()

    own = shared_facts.collect_from(SOURCE)
    if not any(shared_facts.tally(own).values()):
        print("your captures: no game facts found -- no snapshots, "
              "settings or gacha history under %s?" % SOURCE)
    held, report = before, []
    for name, facts in [("your captures", own)] + contributed:
        held, added, refused = shared_facts.fold(held, facts)
        report.append((name, added, refused))

    for name, added, refused in report:
        print("%s: %d added, %d refused" % (name, len(added), len(refused)))
        for line in added:
            print("  + " + line)
        for line in refused:
            print("  ! " + line)

    gone = shared_facts.lost(before, held)
    if gone:
        raise SystemExit(
            "the fold would drop what %s holds -- %s. Nothing written; "
            "this is a bug in shared_facts.fold." % (TARGET.name,
                                                     "; ".join(gone)))
    if held == before and TARGET.exists():
        print("%s: nothing new, nothing written" % TARGET.name)
        return 0
    shared_facts.write(TARGET, shared_facts.document(held))
    print("%s: CHANGED, review its diff -- now holding %s" % (
        TARGET.name, shared_facts.describe(shared_facts.tally(held))
        or "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
