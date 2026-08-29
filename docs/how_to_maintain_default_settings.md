# Maintaining `default_settings/`

Maintainer workflow: what ships, what to hand-edit before a release, and
how to get out of trouble. How it WORKS at runtime — merge stages,
tombstone gate, manager APIs, the Restore Defaults dialog — is
`settings_architecture.md`, and this file deliberately does not restate
it.

## Before a release

1. If a character was released, or existing defaults need changing, edit
   the Optimizer settings for every character that needs them.
2. Check every character has a preset assigned.
3. Check `zCreate exe.bat` reports a successful `optimizer_settings.json`
   cleanup.
4. Run the release build in `dist\`.

## What ships

Three files, bundled from `default_settings/`. Everything else under
`settings/` is the user's own and is never shipped.

| File                      | Holds                            |
| ------------------------- | -------------------------------- |
| `presets.json`            | Gear Score scoring presets       |
| `character_preset.json`   | Which preset each combatant uses |
| `optimizer_settings.json` | Per-combatant Optimizer config   |

Deleting the three from `default_settings/` and running the program
copies your own `settings/` across — that is step 1, and it fires only
while `default_settings/` is empty.

`zCreate exe.bat` then runs `normalize_defaults.py`, which strips the
per-user state that copy brings with it: exclude lists, the level-seen
map, the levels you optimize at. Its line in the build output is step 3.

**Review the diff before committing** — the copy takes your working
state wholesale, so watch for anything you were mid-experiment on. The
build fails outright on an empty `default_settings/`, so you cannot ship
without this.

## Getting a user unstuck

**Point them at Restore Defaults first.** The Setup tab's panel has one
button per shipped file, each opening a dialog listing what they are
missing and what differs from defaults. It bypasses the tombstone gate,
which makes it the sanctioned way back to a deleted or changed default.

Deleting `settings/.defaults_sync.json` also works but is worse: two
runs rather than one, and to pull back a CHANGED value they must also
delete their own copy of that entry. Only if the dialog cannot reach the
case.
