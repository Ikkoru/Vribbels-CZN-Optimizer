---
name: release
description: Cut a release — bump the version, close the CHANGELOG section, write RELEASE_NOTES.md for players, and re-check the README. Use when the maintainer says they are releasing a version, names a version number to release as, asks for release notes, or asks whether the CHANGELOG is ready to ship. Covers the order the steps must run in, how the player-facing register differs from the CHANGELOG's, and how to verify nothing was dropped.
---

# Release

Maintainer-invoked. Never start this because a release "seems due".

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

Verify by diffing the bolded lead of every entry before and after, and name each delta. A rewrite that silently loses an entry looks exactly like a rewrite that tightened one.

## RELEASE_NOTES.md

**Not a shorter CHANGELOG.** It is what a player installing this version is told; `docs/repo_conventions.md` has the cut rules and the two overrides. Gitignored, rewritten per release, pasted into the GitHub release, and it always links the CHANGELOG — that link is what licenses every cut.

Expect most entries not to survive, and expect `Fixed` and `Changed` to come out empty or nearly so. That is the normal shape of this document, not a sign of a missed step.

The judgement calls worth slowing down for:

- **Is it unmissable, or merely visible?** Unmissable goes. A player meets a `Delete Archive` button by opening the panel; they do not meet a behaviour that only shows in one state.
- **Does the absence of something read as broken?** One case behaving unlike every comparable case, with nothing on screen explaining it, earns a line. Apply strictly.
- **Could this be over-read?** Say what the change does not do. That is what the relaunch line is for.

Write what survives as **what, then where**. Group by tab, order by importance inside each group. A little whimsy is welcome.

## README

Checked at release, **reported, not edited**. `docs/repo_conventions.md` § README has the policy — note that its first two sections are exempt from the self-evident filter, because a stranger deciding whether to download cannot see the UI.

Re-check these rather than re-deriving them — all five were open at v2.1.0:

1. What "Generate & Install Cert" does — it adds a root CA machine-wide, and neither the README nor the UI says so or how to remove it.
2. That nothing leaves the machine except the GitHub release check.
3. Running from source (`requirements.txt`, `zRUN.bat`) — absent, and the people most likely to want it are the ones hesitating over point 1.
4. SmartScreen and antivirus on a one-file PyInstaller exe that asks for Administrator.
5. Where user data lives — beside the exe, so the install folder is what gets backed up or moved.

## Verifying

- Entry counts per section, CHANGELOG against release notes, with every difference named and intended.
- No bullet in the notes carrying a second sentence.
- `version.py` matches the new section header.
- `run_all.py` green, including `check_repo_root.py` — it fails both ways, and a new root file needs an allowlist line while a gitignored one must NOT have one.

## Related

- `docs/repo_conventions.md` — the CHANGELOG and release-notes rules this follows.
- `.claude/skills/doc-audit/SKILL.md` — step 2.
