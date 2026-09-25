# Shared game facts — [IMPLEMENTED] 2026-09-25

Some of what a player's captures hold is a fact about the GAME rather than their account: a banner's rates, which Combatant Trial slots an event offers, how many rewards a finished event run held, each Great Rift division's top, how many players a season ranked. The game stops listing most of it, so a player who installs late or never opened the right screen can never read it. The program now ships those facts in `default_settings/shared_facts.json`, reads them beside the account's own, and lets any player export what it lacks from `Setup & Settings → Share Game Data`.

Where it lives now: `shared_facts.py` (the whitelist, the rules, the readers' helpers), `default_settings/normalize/fold_shared_facts.py` (the maintainer's merge, run by the build), `docs/settings_architecture.md` and `docs/how_to_maintain_default_settings.md`, *Shared game facts*. Kept here for the rulings, and for the two that were reversed.

## Constraints that shaped it

- **Nothing that identifies or describes an account leaves the machine.** The export is published in a GitHub issue. A whitelist names every field copied; `check_shared_facts` plants an id, a name and the account's own standing beside the facts and holds that none survive.
- **The user's files stay the user's.** The shipped facts are an overlay read at runtime, never merged into `settings/` — no tombstones, and a wrong shipped fact leaves with the release that fixes it.
- **Rankings are per server.** The capture stamps each ranking reading with its `detected_region`; an older reading takes the newest snapshot's.
- **Contributed files are untrusted.** Folding one goes through the same `clean`, and the maintainer reviews the diff.

## Rulings

**The file sits in `default_settings/`**, found by `resolve_defaults_dir` in the source tree and the frozen build alike. `defaults_sync` bootstraps per file from its own list of three, so it never touches this one. Rejected: `game_data/` (hand-written tables the launch validator checks) and a folder of its own (a second resolver for one file).

**The Offensive's field is shared to the hundred.** It is worked out from the account's own rank over the percentage the game states; to more precision than the Stats list shows, the two would give the rank back.

**A later reading is news only for a season that is over** — older than the newest either side knows of. A running season's figures move weekly, and counting them would ask every active player to send the same season every week. A later reading that says the same thing is never news, and the fold does not replace on one either, so the build does not rewrite the file for a timestamp.

**The export holds only what the shipped file lacks**, with the program's version, the server and the date.

**The status line is a count on one line**; the kinds are named when exporting. A wrapped list made the panel taller than Update Status, and the row stretches the other panel's bottom gap by the difference. The note gives back its label's bottom inset for the same reason; `check_tabs_build` holds the panel's natural height to Update Status'.

**The fold only adds, and stops rather than lose anything**: a shipped file that will not read or holds entries `clean` drops is refused (folding into it would rebuild it from the maintainer's captures alone), and `lost()` refuses any fold that leaves out a held entry. No backup beyond git: the write is atomic and nothing is ever removed.

**The panel is `Share Game Data`**: "Info" reads as personal information, which is what the file does not hold. Its button sits under Window Size; `align_share_button` sizes Update Status to put it there and wraps Update Status' verdict to that width.

## Reversed

- *Only fill, never add columns* (2026-09-25, planned). The Stats lists would have shown only seasons the account played, shipped facts filling their field figures. Reversed the same day: the point is the history a newcomer cannot read, so every shipped season on the account's server gets a column, its own rows empty. A season the account read keeps its own reading whole, so its share of the field is always of one moment.
- *Sortie and Full-Scale Offensive not shared* (2026-09-25, planned), because a column needed the account's own reading and so there was nothing to fill. Reversed with the ruling above: the players and the Sortie's top score are a comparison worth having for any season.

## Left open

- Is a banner's rates reply ever different between servers for one banner id? The fold refuses a differing entry and reports it, so the first Asia export would show it.
- Only rankings reach the share out of old debug logs, through `stats_history.json`. Rates and trial pairings in those logs would need the reading to take client-side lines too.
- A season counts as over only once a newer one is known, so readings taken between seasons of the last one wait for the next season before they turn a line yellow.
