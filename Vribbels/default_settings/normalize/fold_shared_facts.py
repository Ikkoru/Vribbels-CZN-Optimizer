"""Fold game facts into the shipped `default_settings/shared_facts.json`.

Always folds in the facts your own captures hold -- which is what
`zCreate exe.bat` runs it for. Name files after it and it folds those in
too: the `Export Facts` files players attach to a GitHub issue.

    python "default_settings/normalize/fold_shared_facts.py" [file ...]

Every file goes through `shared_facts`' whitelist on the way in, so
nothing but the five kinds of game fact can land in the shipped copy
whatever a file holds. A file that is not an export stops the run
before anything is written. What each fold added is printed, and so is
anything it refused -- a banner whose rates differ from the ones held
is a question to settle by hand, not an update.

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


def main(paths) -> int:
    contributed = []
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit("cannot read %s: %s" % (path, exc))
        facts = shared_facts.read_document(data)
        if facts is None:
            raise SystemExit("%s is not a shared facts export" % path)
        contributed.append((Path(path).name, facts))

    before = shared_facts.load(TARGET)
    held, report = before, []
    for name, facts in [("your captures", shared_facts.collect_from(SOURCE))
                        ] + contributed:
        held, added, refused = shared_facts.fold(held, facts)
        report.append((name, added, refused))

    for name, added, refused in report:
        print("%s: %d added, %d refused" % (name, len(added), len(refused)))
        for line in added:
            print("  + " + line)
        for line in refused:
            print("  ! " + line)

    if held == before and TARGET.exists():
        print("%s: nothing new, nothing written" % TARGET.name)
        return 0
    shared_facts.write(TARGET, shared_facts.document(held))
    counts = shared_facts.tally(held)
    print("%s: written, holding %s" % (
        TARGET.name, shared_facts.describe(counts) or "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
