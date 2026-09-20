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

Then the register. Cut, in this order of frequency:

- **Figures that argue rather than inform.** "280 MB of captures came to 1.3 MB in under five seconds" defends a decision nobody is disputing.
- **Worth-it framing** — "Three things changed to make that worth doing", "which is exactly what made it hard to notice".
- **Internal mechanism a user cannot act on** — "three pixels short per shop product and Tk clipped the difference".
- **The program's word where the game has one.** Check `CLAUDE.md` § Naming, and check the game's own screens for anything it does not cover: an internal pairing like "achievements and titles" can be accurate and still appear nowhere in the game.

**The CHANGELOG keeps everything.** Nothing is dropped for being small or internal. The filtering happens once, in the release notes — drop it here and the record is gone.

Verify by diffing the bolded lead of every entry before and after, and name each delta. A rewrite that silently loses an entry looks exactly like a rewrite that tightened one.

## RELEASE_NOTES.md

**Not a shorter CHANGELOG.** It is what a player is told, in a player's register — second person and contractions are right here and wrong in the CHANGELOG. Gitignored; rewritten per release; pasted into the GitHub release.

Most entries do not survive. The filters, in the order they remove the most:

- **Self-evident from the UI.** Opening the tab teaches it faster. The exception that keeps a line: where the ABSENCE of something would read as a bug. "The Seasonal Shop shows no rates" stays for that alone — and the reason it shows none does not.
- **Not actionable.** Exact figures, timing, control names, internal mechanism, the reason a thing works as it does.
- **Never really released.** A fix to a feature the previous release shipped as unfinished belongs to the CHANGELOG only. Judge against what that release SAID — `## [2.0.0]` says "The Checklist tab and the UI work are both unfinished" — not against the commit history.
- **Too minor to be news**, even when real and user-visible.

What survives is written as **what, then where**, with no excess: *"Archive info and settings are in Setup & Settings → Settings."* Group by tab, and give a new tab one line saying what it is for. `Fixed` and `Changed` may end up empty; that is a normal outcome, not a sign of a missed step.

Two things to add that the CHANGELOG has no place for: a **limitation a player will hit** (relaunching the program still needs the capture started by hand), and a one-line **state-of-the-UI notice** where a surface is still settling.

## README

Checked at release, **reported, not edited**. The standing policy: nothing that is evident from the UI, except a list of the main features someone would install for.

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
