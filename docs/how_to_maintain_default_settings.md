# Maintaining `default_settings/`

Maintainer workflow: what ships, what to hand-edit before a release, and how to get out of trouble. How it WORKS at runtime — merge stages, tombstone gate, manager APIs, the Restore Defaults dialog — is `settings_architecture.md`, not restated here.

## Before a release

1. If a character was released, or existing defaults need changing, edit the Optimizer settings for every character that needs them.
2. Check every character has a preset assigned.
3. Check `zCreate exe.bat` reports a successful `optimizer_settings.json` cleanup.
4. Run the release build in `dist\`.
5. Review `shared_facts.json`'s diff: the build folded your own captures' game facts into it.

## The shipped files

Three files, bundled from `default_settings/`, and a fourth that is not a setting: `shared_facts.json`, below. Everything else under `settings/` is the user's own and is never shipped.

| File                      | Holds                            |
| ------------------------- | -------------------------------- |
| `presets.json`            | Gear Score scoring presets       |
| `character_preset.json`   | Which preset each combatant uses |
| `optimizer_settings.json` | Per-combatant Optimizer config   |

Deleting the three from `default_settings/` and running the program copies your own `settings/` across — that is step 1, and it fires only for the ones missing there.

`zCreate exe.bat` then runs `normalize_defaults.py`, which strips the per-user state that copy brings with it: exclude lists, the level-seen map, the levels you optimize at. Its line in the build output is step 3.

**Review the diff before committing** — the copy takes your working state wholesale, so watch for anything you were mid-experiment on. The build fails outright while any of the three is missing, so you cannot ship without this.

## Shared game facts

`shared_facts.json` is built rather than copied. `zCreate exe.bat` runs `normalize/fold_shared_facts.py`, which folds the game facts your own captures hold into it and prints each one it adds. What the file is and how the program reads it: `settings_architecture.md`, *Shared game facts*.

A player's `Export Facts` file arrives attached to a GitHub issue. Save it anywhere and fold it in, from `Vribbels/`:

    python "default_settings/normalize/fold_shared_facts.py" path/to/shared_facts_2026-09-25.json

The file goes through the same whitelist as your own facts, so nothing but game facts can land in the shipped copy, and a file that is not an export stops the run before anything is written. **Read what it prints, then the diff.** A `!` line is a banner whose rates differ from the ones held; the held ones stay, and replacing them is a hand edit once you know which are right. A later reading of a Great Rift top replacing an earlier one, and a bigger instalment total replacing a smaller one, are the fold working.

## Getting a user unstuck

**Point them at Restore Defaults first.** The Setup & Settings tab's panel has one button per shipped file, each opening a dialog listing what they are missing and what differs from defaults. It bypasses the tombstone gate, which makes it the sanctioned way back to a deleted or changed default.

Deleting `settings/.defaults_sync.json` also works but is worse: two runs rather than one, and to pull back a CHANGED value they must also delete their own copy of that entry. Only if the dialog cannot reach the case.
