# Repo conventions

How `tasks.md`, `plan.md`, `CHANGELOG.md` and `RELEASE_NOTES.md` are kept. Nothing here affects the program.

## `tasks.md` — the triaged backlog

Taxonomy: **1a/1b** (bugs — fixable without / needing maintainer input), **2a/2b** (improvements, likewise), **3** (big changes), **TBD** (parked, with bug / improvement / change subsections).

Completed items are REMOVED, not struck through, and answered questions go with them. Parked ideas move to TBD. An empty section keeps its heading and reads `*N/A*`.

## `plan.md` — created when a task needs planning

Lives at the repo root while the work is live. The test of a plan is whether someone else can pick it up and follow it. The usual shape serves that: constraints → options with pros/cons → recommendation → phases. Acceptance criteria, a decisions log and per-phase status tags are available structure, not requirements.

- **Reference data does not belong in a plan.** A table the CODE points at outlives the plan that produced it, and archiving the plan takes the table out of reach. Put it in the matching `docs/` file and link.
- **Finished phases collapse.** Leave the ruling and the reasoning; drop the status tables and per-file bookkeeping.

When the work finishes the file moves to `past_plans/<topic>.md`, keeping the measurements and the reasoning behind rejected options. `past_plans/` is an archive: its dated entries and `[IMPLEMENTED]` tags are the record, not staleness to clean up.

## Who reads what

Three documents, one audience, three depths. **The reader is a mobile or PC gacha player running this program on Windows who cares about optimizing stats** — assume that much domain knowledge and do not explain it.

|                    | Reader                                     | Depth                                         |
| ------------------ | ------------------------------------------ | --------------------------------------------- |
| `README.md`        | someone who has just heard of the program  | how to run it, and what it is for             |
| `RELEASE_NOTES.md` | a player installing this version           | what changed that they would notice or act on |
| `CHANGELOG.md`     | a player who wants the smaller changes too | everything worth knowing about                |

**The commit history is the complete record; these three are not.** They are written to be read, so a document nobody finishes is a document that failed — length is spent on what a reader will act on, and anything else belongs in the log.

**None of the three argues.** They notify. No entry defends a change, justifies a design, or says why an alternative was rejected — not in the notes, and not in the CHANGELOG either. Reasoning lives in `docs/`, in `past_plans/`, and in the code.

**Default to one line per change in all three.** Length is earned by a reader needing it, and most changes do not earn it. "Fixed fresh install UI being unfilled" is a complete entry.

Several small changes of one kind become one entry. "Adjusted popup window style to match the rest of the app", not four lines about a popup's size, its tick glyphs, a dialog's spacing and a tooltip's colours. Three questions decide it, in order:

1. **Is the change purely visual?** If anything about what the program DOES moved, it keeps its own entry.
2. **Would missing it cause a mistake?** A change nobody notices, and which costs nothing when unnoticed, did not need announcing.
3. **Do the specifics help anyone use the program better** — or would they be hard to work out unaided? If yes, name them; if no, the general line is the entry.

Prefer the noun where it reaches the subject sooner. "The sum of a combatant's Potential node levels" beats "a combatant's Potential node levels summed"; "Removed bright flashes when a tab first opens" beats "Nothing flashes light grey when a tab first opens". Not at the cost of plainness — a nominalisation that makes the sentence harder to read has lost the only argument for it.

## `README.md` — the front door

Order matters, because a stranger reads top-down and stops early.

1. **How to get it running.** Prerequisites, install, first-run setup.
2. **What it does** — the main features, briefly. Repeating what the UI makes obvious is CORRECT here: someone deciding whether to download it cannot see the UI.
3. **What the UI does not make obvious.** Settings whose meaning is not self-explanatory, and anything the program does to the system.

Only section 3 takes the self-evident filter. Sections 1 and 2 exist for a reader who has never opened the program.

## `CHANGELOG.md` — Keep a Changelog format

Active work goes under the top `## [X.Y.Z] - unreleased` section as it lands: new features → `### Added`, polish → `### Changed`, bug fixes → `### Fixed`.

Summarize at USER-FACING level in simple English, not implementation detail. "Memory Fragments tab: the Highest Potential column shows the preset used for the score" — not "refactored `_presets_for_highest_gs` to return tuples".

**Write the entry in that register when it LANDS.** An entry written from the implementation and rewritten at release costs the rewrite and loses detail nobody can recover months later.

**An entry earns its place if someone who did not know about the change would be confused, or would act differently.** A feature that moved to another panel, a sort order that quietly changed, Gear Score reading 0–100 where it used to read 600 — all qualify, however small the edit was. Padding going from 3 to 4 does not. Nor does a change that answers itself on contact: tooltip sources are underlined now, and anyone wondering why hovers and gets the tooltip.

**Before adding an entry, search the unreleased section for its subject**, and amend the entry already there rather than appending a second. A fix to something this cycle added is not a separate change — it is the Added entry not having been true yet.

Churn inside a feature that shipped unfinished is not recorded at all. Where a release said a feature was not done — `## [2.0.0]` says "The Checklist tab and the UI work are both unfinished" — fixing and reshaping it is finishing it, not changing it, and belongs in neither document. The entries that survive are the ones a player of the LAST release would notice.

**State what the program does now; the section heading says it changed.** "The Combatants tab keeps the combatant you are looking at" is the entry. Adding "it used to drop back to the first row" spends a clause on something `### Changed` already implies, and a binary change implies its own opposite. Where the new statement alone would not say WHICH thing moved, fold the contrast into it — "counts the runs you have taken, not the ones left" — rather than adding a sentence of history. This is what makes `used to` and `previously` worth grepping for in the unreleased section.

Bold marks the few entries worth catching an eye, not every entry. A `Fixed` section usually carries none at all — a fix is expected, and bolding all of them says nothing. Where most leads are bold, none of them is.

Group a tab's entries under the tab. Three or more in one release become a bolded `**Combatants tab:**` parent with plain sub-bullets, rather than three entries each opening with the tab's name.

Nothing about hand-editing a settings file gets an entry. Editing the JSON by hand is a fallback for when something breaks, and a way for a power user to make a bulk change; it is not a feature, and its shape moving is not news.

A fix nobody could have hit gets no entry. A build that produced a broken executable, caught before a release went out, changed nothing a player ever ran — there is no version they could be coming from where it was wrong.

Use the game's own capitalisation for anything it names: Potential, Neutrals, Combatant, Memory Fragment.

At release, `unreleased` is replaced by a short release name (`- Multi-core`), which is also when `version.py` is bumped.

**A released entry is edited only to fix it**, never to restate what shipped. Correcting a mistake, an inconsistency or a dead reference is fine; changing what the entry claims happened is not, and neither is tidying prose that is merely verbose — the risk of quietly rewriting history is what the caution is for, not the wording.

## `RELEASE_NOTES.md` — what a player is told

Gitignored, rewritten per release, pasted into the GitHub release. **Always links `CHANGELOG.md`**: a reader who wants the rest will take one click, and that link is what lets everything below be cut.

Most entries do not survive. Cut an entry when any of these is true:

- **It has little practical effect** — a control resized, wording tweaked, a panel moved inside its own tab.
- **It is unmissable.** Anyone who opens the tab meets it immediately: a list now coloured by Element, a button labelled `Delete Archive` that deletes the archive.
- **It is common knowledge for this audience** — red is bad and green is good; a `+?` means the total is unknown.
- **Only someone who never saw the bug is affected.** A new user has no before-state to compare against, so a fix that only shows on a fresh install is a line at most.
- **It is too minor to be news**, even when real and user-visible.

Two things override those cuts:

- **An exception with no visible reason.** Where one case behaves unlike every comparable case and nothing on screen explains it, a player reads it as broken. Every shop's tooltip gives earning rates and the Seasonal Shop's gives estimates instead; that line stays. Apply this strictly — it is not a licence to keep anything that might confuse someone.
- **A change that invites a wrong conclusion.** Say what it does NOT do. "A capture can be left running" plus "a new snapshot starts each relaunch" reads as "capture is automatic now", so the note adds that relaunching the program still needs the button.

What survives is written as what, then where: *"Archive info and settings are in Setup & Settings → Settings."* Group by tab and order by importance within each; give a new tab one line saying what it is for. The header names one or two themes. `Added`, `Fixed` and `Changed` may end up empty.

A little whimsy is welcome here and nowhere else.

## Keeping the settings docs in step

Any change to `defaults_sync.py` or the manager APIs lands in `docs/settings_architecture.md` (mechanism) and, if it changes what the maintainer DOES, `docs/how_to_maintain_default_settings.md` (workflow). Don't restate either in the other.
