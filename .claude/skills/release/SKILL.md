---
name: release
description: Cut a release — bump the version, close the CHANGELOG section, write RELEASE_NOTES.md for players, and re-check the README. Invoked by hand only. Anything typed after the command is read as part of the request: a version number, a theme for the release name, a step to skip.
---

# Release

**Invoked by hand, never on inference.** A release is a judgement about what shipped, so nothing here starts because one seems due.

**Read what was typed after the command before starting.** It is part of the request, not a comment — a version number, a release name, a step to skip, a section to leave alone. Say which of the steps below it changes, then run the rest as written. Where no version is given, ask; do not infer one from the last tag.

The conventions are in `docs/repo_conventions.md`; this is the procedure and the judgement.

## Order

Run the doc audit first (`doc-audit` skill) — it moves facts between files, and doing it after the CHANGELOG pass means auditing prose you have just rewritten.

1. **Commit whatever is uncommitted** before touching anything.
2. **Doc audit.** At minimum, the sweeps.
3. **CHANGELOG pass** — accuracy, then register.
4. **`version.py`**, and the section header: `## [X.Y.Z] - <short release name>`, no date. The name is one or two themes, not a list.
5. **`RELEASE_NOTES.md`** — a different document, see below.
6. **README re-check** — report only; it is not edited as part of a release.
7. `python checks/run_all.py`, then commit.

## CHANGELOG pass

**Accuracy first.** Every entry describes the shipped build, not the intent at the time it was written. An entry whose feature changed later in the cycle is wrong, and nothing will have flagged it.

Then the register. The CHANGELOG is written for a player who wants the smaller changes too — not for a maintainer. Cut, in this order of frequency:

- **Anything that argues.** A figure defending a decision, worth-it framing, the reason an alternative was rejected. These documents notify; they never persuade. This applies to the CHANGELOG as much as to the notes.
- **Internal mechanism a user cannot act on** — "three pixels short per shop product and Tk clipped the difference".
- **Words.** Default to one line per entry. Most changes need no more, and a paragraph where a line would do is the most common defect in this file.
- **The program's word where the game has one.** Check `CLAUDE.md` § Naming, and check the game's own screens for anything it does not cover. Where the game names a thing nowhere recognisable, describe it instead of inventing a name.

**An entry earns its place by the confusion it prevents**, not by the size of the edit — `docs/repo_conventions.md` has the test. The commit history is the complete record, so nothing is kept here merely to be thorough.

**Read the section as a whole before tightening its entries.** Most of what a pass can win is structural, and none of it is visible one entry at a time:

- **Entries that generalise together.** A popup resized, a tick glyph swapped, a dialog respaced, a tooltip recoloured — four entries and one line. Run `repo_conventions`' three questions over any run of small visual changes. A first pass that tightened each one separately still left four.
- **Entries that group under a tab.** Three or more naming the same tab become a parent with sub-bullets.
- **Bold that has stopped marking anything.** Count the bolded leads against the entries: near 1:1 in a `Fixed` section means the bold is decoration.
- **Entries that should not exist.** A settings-file shape, a build fix caught before release, churn inside a feature the last release called unfinished, and a FIX to anything this release adds — that is the Added entry not having been true yet. Check a `Fixed` entry's feature against the last release's own CHANGELOG section before keeping it: the Seasonal Shop's purchase count read as a fix and was inside shelves new that release.

**Then check each surviving entry states the whole fix.** Tightening is where half a claim goes missing: a guard against both a typed `1e9` and a typed `abc` reads as one or the other unless the line is written to cover both.

Verify by diffing the bolded lead of every entry before and after, and name each delta. A rewrite that silently loses an entry looks exactly like a rewrite that tightened one.

## RELEASE_NOTES.md

**Not a shorter CHANGELOG.** It is what a player installing this version is told; `docs/repo_conventions.md` has the cut rules and the two overrides. Gitignored, rewritten per release, pasted into the GitHub release, and it always links the CHANGELOG — that link is what licenses every cut.

Expect most entries not to survive, and expect `Fixed` and `Changed` to come out empty or nearly so. That is the normal shape of this document, not a sign of a missed step.

**Read the maintainer's annotated drafts first**: `.old/RELEASE_NOTES_*_with_notes.md` are past drafts with every edit and cut explained, and they calibrate these calls better than any rule here.

The judgement calls worth slowing down for:

- **Is it unmissable, or merely visible?** Unmissable goes. A player meets a `Delete Archive` button by opening the panel; they do not meet a behaviour that only shows in one state.
- **Does the absence of something read as broken?** One case behaving unlike every comparable case, with nothing on screen explaining it, earns a line. Apply strictly.
- **Could this be over-read?** Say what the change does not do. That is what the relaunch line is for.
- **Does the player have to DO something for it to work?** Then give the steps whole — what to open, how far, how often: open a banner's Rescue Records while capturing, go to its last page, and do it for every banner. Name the way in for someone whose data is elsewhere, such as an import.
- **Would a player ever notice it?** A guarantee they cannot observe ("your own readings always win") is implementation, however true.
- **Is it a fix to something they never had?** A fix inside a feature this release adds, or one the last release called unfinished, is news to nobody installing.
- **Is it the player's word?** "Player count", not "field size"; an event family's internal name ("Love events") is not what the game shows. Where unsure what the game calls it, say it generally ("more events").
- **Is it what they will see?** "Arrive faster", not "arrive as they happen": say the effect, not an absolute the next slow line disproves.

Write what survives as what, then where. Group by tab, order by importance inside each group, and fold lines about one thing into one bullet — a column and its tooltip. Two short sentences read better than one long one. Where the release asks something of players, such as sharing data, ask it in the maintainer's own voice. A little whimsy is welcome.

## README

Checked at release, reported, not edited. `docs/repo_conventions.md` § README has the policy — note that its first two sections are exempt from the self-evident filter, because a stranger deciding whether to download cannot see the UI.

Re-check these rather than re-deriving them — all five were open at v2.1.0:

1. What "Generate & Install Cert" does — it adds a root CA machine-wide, and neither the README nor the UI says so or how to remove it.
2. That nothing leaves the machine except the GitHub release check.
3. Running from source (`requirements.txt`, `zRUN.bat`) — absent, and the people most likely to want it are the ones hesitating over point 1.
4. SmartScreen and antivirus on a one-file PyInstaller exe that asks for Administrator.
5. Where user data lives — beside the exe, so the install folder is what gets backed up or moved.

## Verifying

- Entry counts per section, CHANGELOG against release notes, with every difference named and intended.
- `version.py` matches the new section header.
- `run_all.py` green, including `check_repo_root.py` — it fails both ways, and a new root file needs an allowlist line while a gitignored one must NOT have one.

## Related

- `docs/repo_conventions.md` — the CHANGELOG and release-notes rules this follows.
- `.claude/skills/doc-audit/SKILL.md` — step 2.
