# Changelog

All notable changes to Vribbels CZN Optimizer (Ikkoru) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This fork was branched from [Vorbroker/Vribbels-CZN-Optimizer](https://github.com/Vorbroker/Vribbels-CZN-Optimizer) at v1.7.0 (2026-02-07) and restarts versioning from v1.0.0. For the pre-fork history, see the upstream repository's CHANGELOG.

## [2.2.0] - unreleased

### Added

- **A fifth Checklist column, `Galactic Disaster`**, holding the Seasonal Shop's season-long shelves. Its heading says how long the season has left, and the shop's own row no longer repeats it; between seasons the shelves go and a line saying roughly when the next one opens stands where the shop's own heading did. `Galactic Disaster (Seasonal)` has left the `Other` column, the new heading saying the same thing.

- An item the shop sells on more than one of its three pages is one row, counting down from their caps together, in the order the pages themselves imply. Where one page charges more for the same material, that shelf is a row of its own with the price after its name.

- A Seasonal Shop row turns orange once everything on sale has been bought and the rest is on a page that has not opened yet. Red means there is something to buy today; green would say the row was finished when another page is still to come.

- The shelves are there only while the shop is. They go when the season ends, and stay away through the three weeks before the next one starts, where the game has neither the shop nor its currency. The heading stays either way.

- Hovering the Seasonal Shop says what the season has paid you so far, then what a whole one pays at one Chaos run a day, claiming everything. A season nobody has counted yet shows no estimate.

- Which Seasonal Shop rows you have ticked survives the season ending. The game renames every one of that shop's products each season, so the answers are kept against the item and its price instead.

- A tooltip's figures line up by their last digit rather than their first, and sit closer to their labels.

### Fixed

- The Checklist fits a narrower window. Every column with a shop in it was reserving room twice for the same deadline.

- **The Seasonal Shop counted only the last three weeks of buying.** Its shelves were measured against the Sortie season instead of the Galactic Disaster's own, so purchases made earlier in the season read as never made and the shop's total asked for far more than was actually left.

- The mouse wheel scrolls a Checklist column when the pointer is over a checkbox. It only worked over the gaps before, which is how a column too tall for the window hid its last rows.

- The Weekly column's Seasonal Shop was underlined as if it had a tooltip. It has none: everything it sells is free, so there is no bill and no rate.

- **A login event's reward never reached the Capture Log**, and its count never updated. The claim reports the item under a key nothing was reading.

- **A run's reward was listed twice.** A run reports its payout once where it is paid and again on the clear, and the Capture Log printed both — identical figures, one reward. Counts were never affected: the second report writes the same total the first did. A run whose clear only restates its payout keeps its `Total rewards` line.

- A login event on its first day read `1/1+?`, which says finished. The ceiling now starts at seven, the fewest any login event has ever paid, and still counts up from there.

## [2.1.0] - Checklist of in-game activities, capture archiving

### Added

- **Combatants: a `Sortie` column.** Each combatant's Sortie Data progress, the two ladders added together, beside the preset they are assigned. It reads `-` until a capture has carried the data.

- A Sortie run's full payout is listed. After a run the Capture Log adds a `Total rewards:` line with everything the run paid, on its own line beneath the individual receipts.

- **Old captures are archived instead of piling up.** At launch, in the background, everything but the newest few captures and debug logs is folded into `archived_captures.tar.xz` beside them. A file is deleted only after its archived copy has been read back and matched byte for byte. Controls are in `Setup & Settings` → `Settings`: `Compression` (`Off`, `Balanced`, `Strongest`), the archive's size beside the loose folder's, and `Delete Archive`, which goes to the Recycle Bin.

- The Capture tab says when something failed while you were elsewhere. A failure that stops a background task puts a red dot on the `Capture` tab until you open it, then pulses the `Capture Log` title. Anything that retries and carries on stays an ordinary line in the log.

- **A capture can be left running.** The debug log is compressed as it is written and stays readable, and a new snapshot starts each time the game is relaunched.

- Materials tab: the hardest target on each block is coloured — red under 50%, yellow to 100%, green once covered. The steps on the way keep the ordinary colour.

- An item whose name is only a guess is drawn red in the Capture Log. An id with no name at all stays dim yellow, as before.

- **Each shop on the Checklist says what clearing it costs.** The currency you hold against the bill for its ticked products, green once you can afford the lot. A shop whose products are free, or priced in more than one currency, shows nothing.

- A shop heading's total is inked a shade apart from the products under it, so the block's own total does not read as one more row.

- `Multidimensional Alignment Material` is shortened on the Checklist, with the full name on the row's tooltip. The tip follows the product wherever ticking sorts it.

- **Hovering a shop on the Checklist says what its currency earns, and what a full period of it costs.** Rates are in that shop's own rotation, over two spans: `recent` is the last four rotations, `long run` the last year. A gap between them means something changed, and only the long-run line shows while the record is too young to tell them apart.

- That record starts full rather than empty. It is anchored at the day the account was made, so a year's reading is there on the first capture.

- The Seasonal Shop shows no rates. Its currency is wiped at the end of every season, so what was earned before says nothing about now.

- The launch login event reads `7/7`. If the game ever adds an eighth reward, the row goes back to counting days with a `+?`.

- **You can tell the Checklist an event is finished.** Rows the game never marks carry a `Finished?` checkbox: tick it and the tally goes green and sorts down. If another reward turns up, or another is claimed, the box unticks itself.

- The Checklist reads a point larger. Every row, reading, deadline and checkbox on the tab is up one size; the Daily / Weekly / Monthly / Other headings are unchanged.

- The Checklist's deadlines line up. `Ends in ...` now sits in a column of its own rather than starting wherever the reading beside it ended — one column for the rows above the Sortie shop, one for the Events block.

- An event shaped like a grid says how big it is on its first day, reading `3/21` on the opening afternoon instead of `3/3+?`. Events that are not rectangular are left alone.

- An event can take its total from the last time it ran. Where two past instalments agree, a live one reads `~1/20` instead of `1/3+?`. It still goes green only on the game's own word, and a live event that has issued more than its predecessors held keeps its own figure.

- An event row says when its total is only a guess, reading `16/20+?`. The `+?` comes off, and the row goes green, once the game says the event is finished.

- An event goes green once its final reward is claimed.

### Fixed

- A Sortie's rewards reach the Capture Log, along with the entry deposit coming back. A Chaos report screen and a town calamity had the same problem, each under a key of its own.

- A charge no longer reads as a gift. Entering a Sortie costs Aether and is charged through the same envelope a reward arrives in, so the log said `Received Aether -10`. The wording now follows which way the figures moved.

- The Memory Fragments filters stop blinking during a capture. The Sets panel and the unknown-main-stats row now rebuild only when a set name, one of the counts beside them, or an unknown main changes.

- A fresh install opens with its panels filled, at the size a loaded one uses.

- An event mission's rewards are recorded. They pay under a key nothing read, so the items landed nowhere and the Capture Log reported no receipt.

- A story episode's rewards reach the Capture Log. They arrive nested deeper than anything else pays under, so nothing reported them.

- Memory Fragments won as rewards are kept. Anything a Chaos week reward or a Simulation run paid was missing from the inventory until the next login.

- A doubled Simulation run is counted. The Overclock row is fed by a record inside the stage reply rather than at its top level, so the row sat at its login value all session.

### Changed

- The capture log stopped repeating itself. `Saved:` now appears when the file or the counts change, and a save that fails says so instead of arriving as a bare `Error:`.

- The Log Presets checklist no longer blinks while a capture runs. It was rebuilt from scratch on every snapshot save, and logging in saves several times in a few seconds.

- Daily rows come back on their own. The coffee and the Communication Passes reset with the clock like every other daily row, with or without a capture running.

- **An Overclock event counts the runs you have taken, not the ones left.** A repeating event's finished cycle reads orange rather than green.

- An Overclock event's daily total is read from the runs already played. The game runs these at two a day and at six, and the row assumed two — so a six-a-day event called the day finished after the second run.

- An event that looks finished but cannot be proved finished reads orange. Where the only number available is the rewards handed out so far, a row that has sat at its own total for two days is neither red nor green.

- An event row says what it can prove. Where the game states a total, the row counts against it and can go green; where the only number available is the missions handed out so far, it shows that and stays red.

- The Monthly column counts down on a fresh install, instead of waiting for the first capture to state the month's bounds.

- Combatant Trial events count three trials per Combatant banner running, not three flat, so a second banner doubles them.

- Combatant Trial events count the rewards you have claimed. Which trials an event offers is stated only when you claim one, so the pairing is learned from the claim and remembered; until then the row shows its deadline alone.

## [2.0.0] - Checklist tab, region detection, Materials tab

**The Checklist tab and the UI work are both unfinished.** They are in this release because what is there already works, not because either is done.

### Added

- **Olga and Emilie.**
- **A Checklist tab.** Four columns — Daily, Weekly, Monthly and Other — listing missable tasks. Green means nothing left, red means something is, and a dash means the capture does not carry the answer yet.
  - Each heading counts its own period down, and colours the time by how much of it is left.
  - **Shop rows are read from the game**, so a product the game adds appears on its own.
  - **Live events are listed with their deadline**, and where the game says so, how much of the event is claimed. Login-streak events count the days taken; Overclock events count the doubled Simulation runs left today.
- Combatants tab: `Show missing characters`.
- Memory Fragments tab: `Highest GS/Potential: Upgrade Log Settings`. With it on, the two Highest columns judge a fragment using the settings in Capture tab's `Upgrade Log Settings` panel.

### Changed

- **Default settings improved.**
- **Agony damage can crit.** The game changed; the optimizer follows.
- The **Server Region** is now **automatically detected**.
- The **Materials tab** now counts all upgrade materials.
  - `Total` shows the common-tier equivalent sum of all items in its row.
  - An Element's stones score against three levels of ambition — a best-node build, one that also takes the Neutrals, and one that adds nodes 5.1 and 5.2.
  - The checkbox next to each column's generic item adds its amount to each of that column's **Total**.
- Typing more than one letter with a list or dropdown focused narrows the search, the way Windows Explorer does. Works in the combatant list, the preset list and both dropdowns.
- **Combatants tab:**
  - Added a `Nodes` column, the sum of a combatant's Potential node levels against the maximum.
  - The list keeps the combatant you are looking at through an in-game upgrade or a re-sort.
  - The `Character` panel now lists all Potential nodes, as well as `Excursion Types` at the bottom. `Excursion Types` can't tell if a Combatant with an outfit has 10 or 11 Excursions, but will self-correct when you get the 11th.
  - Moving through the character list is faster.
  - An Equipped Memory Fragments cell's text can be selected and copied like the Character card's.
  - The Combatants list no longer remembers the currently selected row through program restarts.
- **Capture tab:**
  - The Log Presets checklist automatically changes its number of columns to fit the panel.
  - Improved readability of the Capture Log's MF-related lines. A Highest Potential range shows its floor dimmed and its ceiling green, or yellow where the ceiling is 40 or below.
- The `Escape` key closes every window the app opens over the main one — the Stat Contributions popup, the three Restore Defaults dialogs, and a hover tooltip.
- Adjusted popup window style to match the rest of the app.
- Changed font in several places.

### Fixed

- Gear Score weights reject letters and out-of-range numbers.
- Repeated "snapshot saved" messages are condensed into one when there is nothing breaking them up.
- Snapshots are no longer read half-written.
- A capture that records nothing says so, and names the likely cause, rather than reporting the previous capture's file as freshly written.
- Removed bright flashes when a tab first opens: Capture Log, About tab's link buttons, Gear Score spinboxes.
- The Memory Fragments tab's Main Stats filters and the Optimizer tab's Exclude Combatant's MFs list are drawn like every other checkbox.
- The app refreshes its information on every snapshot save.
- Drinking the daily coffee is noticed right away, rather than waiting until some other town action mentions it.
- A combatant with a placeholder id is kept out of the settings files.

## [1.5.0] - Arabella, Fracture, UI update ongoing

### Added

- **Arabella and Licinia**, plus Janet's data.
- **Fracture and Scorched damage.** Important Settings has three damage-type sliders instead of two: Extra, Agony (formerly called DoT) and Fracture, which Scorched shares. Set each to the share of a combatant's damage it accounts for. Agony can't crit and isn't affected by buffs; Fracture and Scorched do both. Existing combatants keep their old setting as Agony, and Fracture starts at 0%.
- **The Upgraded log lines hide presets that can't use the fragment.** Four checkboxes in the Capture tab's Upgrade Log Settings drop a preset when none of its combatants wants that fragment's main stat: an element that isn't theirs, an ATK% main on a DEF-scaling combatant or the reverse, and HP% or Ego mains for damage dealers. Combatants mid-split, and those the program doesn't know, are never filtered. All four on by default.

### Changed

- **The Combatants tab's character list is a real table.** It resizes faster, its columns stay lined up, and each row is coloured by its Element. New Affinity column, and Partner level has its own.
- Combatants tab: Sets and build stats moved into the Character card. The separate Build Stats strip is gone and the card's text can be selected and copied. Total GS is not repeated there — the list's GS column shows it.
- **More things are coloured by Element:** the Memory Fragments tab's elemental Main Stat filters and Sets list, and the Capture tab's Log Preset checkboxes.
- One text size and one checkbox style across the app, with tighter and more consistent spacing on every tab. Gear cells put the slot name on the same row as the main stat.
- Capture tab: `Upgrade Log Presets` is now `Upgrade Log Settings`, wider, with its checkboxes in five columns.
- Removed the Support on Ko-Fi button and the empty strip it sat in, so the tabs start at the top of the window. The message is still on the About tab.

### Fixed

- Capture missed anything the game sent in a batch — most of what arrives after the loading screen, including the reply that says you obtained a new combatant.
- Snapshot and hosts-file reads and writes state their encoding. On a Japanese or Korean system a snapshot with non-ASCII text could fail to load or come back mangled. The hosts file is left exactly as found.
- A failure to install the bundled default settings is reported, rather than leaving the program looking healthy with no presets and no per-combatant settings.

## [1.4.1] - Eunie + Minor Fixes and Improvements

### Added

- **Eunie.**
- Memory Fragments tab: the active Gear Score preset is named below the Slots filter. Reads `Default` when every weight is 1.0 and `Custom` for an unsaved set.
- Optimizer tab: Selected Build has its own LVL column, to the right of Main.
- **The game data files are checked at launch.** A misspelled stat name, an unlisted grade-and-class combination or a duplicated entry all leave the program working with wrong scores. Any such problem now appears in a message box on startup, naming the file, the line and the entry — e.g. `characters.py | Ln: 412 | Hilde (30113) | node_50 'CritRate' is not one of HP%, ATK%, DEF%, CRate, CDmg`. A file that won't parse gives the file, line and column. Every message says which file to edit to widen a check.

### Changed

- The Combatants tab does not redraw for capture events that don't concern it — upgrading, forging or dismantling a fragment nobody has equipped.
- Generating the certificate is quicker. `Generate & Install Cert` continues as soon as the certificate appears, usually well under a second, rather than waiting a fixed three.

### Fixed

- Memory Fragments: the selection really does follow the fragment. The previous fix worked when re-sorting, but an upgrade arriving from a live capture cleared the list before the highlight could be noted.
- Capture can no longer start with the proxy pointed at itself. A capture that ended without cleaning up left its redirect in the Windows hosts file, and the next Start Capture then told the proxy its own address was the game server — filling the Capture Log with thousands of `GET https://127.0.0.1:13701/api/` lines, capturing nothing, and leaving the game hung or erroring. A leftover redirect is removed at launch with a note in the Capture Log, Start Capture removes one and re-checks rather than trusting it, and refuses to start while the game server still resolves locally.
- A capture that fails to start leaves the Server Region dropdown enabled.
- Failures to flush the DNS cache are reported; a cache still holding the old address is another way a capture ends up on the wrong server.
- The Setup tab no longer gets stuck on `Checking...`, with the Capture tab's prerequisite lines missing and an error printed to the console.
- Re-equipping a Partner keeps the rest of the roster. The game's reply lists only the Partner and the two combatants involved, and that short list replaced the whole roster — so gearless combatants vanished from the Combatants tab and from Exclude Combatant's MFs, exclusion checkmarks appeared cleared, and the optimizer stopped excluding. Updates like this are merged rather than replacing. Your choices were never altered on disk; re-capture and they reappear.

## [1.4.0] - Off-Element Filter and Fixes

### Added

- **Hilde.**
- **Two new sets: Battlefield Evolution and Sanguine Thorn.** Both conditional Crit DMG sets, so each gets its own Effect % in Set Configuration.
- Ruixiang is recognized as a partner.
- **`Ignore off-Element MFs` filter.** Excludes Slot V fragments whose main stat is an element DMG% not matching the combatant's element. ATK% and HP% Slot V mains are always considered, and combatants whose element the program doesn't know are never filtered. On by default, one setting shared by all combatants.

### Changed

- Dismissing the Windows Administrator prompt shows no `Elevation Failed` warning — declining is a choice. Genuine failures still report.
- Capture tab: Log Presets are laid out in three columns.
- **The Results status line reports the run differently**, reading e.g. `Done in 0.4s! 1,728,000 builds compared (slots 12×12×12×10×10×10)`. The six numbers are how many fragments were considered for each slot, which is the quickest way to see what a filter or exclusion changed. Where a run finds nothing, the same numbers show which slot was empty.
- Some combatants' default optimizer settings were adjusted. Only affects combatants you haven't configured yourself.
- **`Ignore MFs below level` starts at 4.** Set it to 0 to consider everything; an existing choice is untouched.
- **`Optimize for LVL` defaults to 60 and follows the combatant's own level.** When a combatant is levelled past the highest level the program has seen for them, the setting moves up to match — once, so a lower value set on purpose stays put.

### Fixed

- A newly obtained combatant appears immediately. One that had never unlocked a potential node was mistaken for a partner card and stayed missing from the Combatants tab until an MF was equipped to it. Characters and partner cards are now told apart by the shape of the data the game sends, which doesn't depend on progression.
- Memory Fragments: the selection follows the fragment it's on, and scrolls back into view.
- The window opens in front when launched from a folder without administrator rights.
- The Optimizer tab does not shift when opened for the first time. Every tab settles during startup, like the one shown first.
- Equipping an MF does not change the stats shown for a proposed build. The Results list and the Stats Comparison `New` column were re-computed at the combatant's actual level while everything else used `Optimize for LVL`.
- A fully levelled Rare fragment shows no leftover Potential. Remaining upgrades are counted from the fragment's level against its rarity's cap rather than inferred from roll counts.
- Startup is roughly three seconds faster. Only the tab that needs preparing is prepared.

## [1.3.0] - Optimizer Set Effect Selection Improvement

### Added

- **`Ignore MFs below level` filter.** A spinbox (0–5) excluding fragments below the selected level from the optimizer's candidate pool. One setting shared by all combatants; 0 is the default and matches the previous behaviour.
- Combatants list: Partner column, with each combatant's equipped partner and its level.
- Potential 7 Extra DMG% / DoT% / Ego rows in the Stat Contributions popup and the Stats Comparison panel.
- **Capture tab: Log Presets.** A checklist of the presets assigned to your combatants. Upgraded lines report a fragment's Highest Potential for the top 5 checked presets only. Toggling a preset re-writes the last Upgraded line in place. Remembered per combatant; newly seen combatants start checked.
- **Fei.**

### Changed

- **Each conditional set has its own `Effect %` spinbox**, replacing the global slider. It sets what percent of this combatant's damage benefits from that set's effect; at 0 the effect is ignored but the set's fragments still count for their stats. Unconditional sets always apply and have no spinbox. Existing configurations migrate at your old global percentage; newly added combatants start at 0.
- Set Configuration polish. Hovering a set shows its bonus description, and the three averages spinboxes moved up beside Max Flex Slots.
- The Capture Log hides WebSocket keepalive lines. With `Debug WebSocket traffic` on they still appear — a stalled keepalive is a useful hint when diagnosing a dead capture.
- Ego is shown without decimals in the Stat Contributions popup, matching the Stats Comparison panel.

### Fixed

- The window does not assemble itself in view on startup. It stays hidden until built, loaded and settled, then appears complete.
- Loading a snapshot is faster. The Memory Fragments and Combatants tabs were each rebuilt twice per load.

## [1.2.0] - Multi-core

### Added

- **Partner passives can contribute Crit Rate, DoT% and Ego to builds**, alongside the ATK%/DEF%/HP%, Crit DMG and Extra DMG% they already did. Takes effect per partner as the entries are added.
- **Multi-core optimization.** Large runs are split across worker processes, defaulting to all cores minus one, producing exactly the same builds and ordering. Small runs stay single-threaded, Stop still cancels mid-run, and any failure falls back to the single-threaded run. `optimizer_workers` controls it: 0 auto, 1 off, N exactly N — re-read at every Start, so edits apply without restarting.
- **Results: the build you already have equipped is tagged `(E)`**, so it is clear at a glance whether the optimizer is proposing a change and what the alternatives are worth.
- **Tenebria and Aria.**

### Changed

- **The Optimizer Score column runs 0–100, with the top build at 100.** The damage and shielding/healing sides are each measured against the best value found in the run, then blended by the Shielding & Healing slider — so the slider means "how much a 1% gain in one is worth against the other". Equipping better gear can lower a build's number, because the yardstick moved. Builds and ordering are unchanged; only the numbers are rescaled, to one decimal place.
- **Partner passive bonuses no longer count toward `Have at least` or the Potential 7 rows.** The in-game Potential 7 checks ignore every Partner passive bonus; the Partner's flat class stats still count. Partner bonuses still count fully toward Final stats and the optimizer score.
- **Buffs are not applied to shielding and healing.** Avg Mult Buff% and Avg Add Buff% never affect shields or heals in game. No build's rank or displayed score moves.
- Optimizer tab: the `Have at least` Crit% / CDMG% / Extra% / DoT% minimums accept one decimal place, and the mouse wheel steps them by 0.1 where the buttons step by 1.
- Stat Contributions popup: `Potential 7 CRate` and `Potential 7 CDMG` rows — the final crit values minus everything the in-game checks can't see, which is what `Have at least` compares against.
- Stats Comparison: `Pot7 Crit%` and `Pot7 CDMG` rows, comparable between the current and selected builds.
- Combatants tab: an unknown partner shows its res_id as the name (e.g. `#173021`), so a missing entry is easy to report.
- Materials tab: growth-stone images display before any capture is loaded, with quantities at 0 until data arrives.
- Runs report their wall time and rate, and equal-score builds order deterministically.

### Fixed

- Solia's Extra Attack bonus and Aria's Swelling Melody Crit DMG affect optimization. Their stat names didn't match the optimizer's vocabulary and were silently ignored; Solia's passive description renders its ATK% number again.
- `Have at least` minimums cannot be satisfied by conditional set bonuses. Conditional procs never appear on the in-game stat sheet, so a build meeting a Crit minimum only through them looked valid and fell short in game. The score still models them; only the minimum check ignores them.
- The Important Settings and Set Effect sliders reach every integer 0–100. The wheel steps by exactly 1, and the Extra and DoT sliders moved onto their own full-width rows so dragging lands on every value.
- Excluding or including a combatant's MFs keeps the not-yet-captured combatants. Toggling any checkbox rewrote the list from the checkboxes alone, dropping uncaptured entries that then arrived un-excluded.
- Start is disabled while an optimization is running. Stop then Start in quick succession could revive the cancelled run and leave two workers racing, with the loser's late results overwriting the winner's. Start also refuses when no capture data is loaded.
- A `config.json` with unrecognized entries no longer resets the whole config to defaults.
- Newly released combatants default to excluded again in `Exclude Combatant's MFs`. One added to the program's own character table was treated as already known and skipped, so her equipped fragments were silently up for grabs. Existing unchecks are preserved.
- The Stats Comparison `Now` column agrees with the Stat Contributions popup. The current build was read at the combatant's actual level while everything else used the `Optimize for LVL` stepper.

### Removed

- `capture/addon.py` — superseded by the addon template embedded in `capture/manager.py`.

## [1.1.0] - Optimizer rework

Major Optimizer-tab overhaul. The Optimizer becomes hands-off: instead of dialling priority sliders per build, each character carries a saved profile of build assumptions — damage-type shares, ATK/DEF scaling, shielding/healing weight, set choices, stat biases — and the engine works out the best gear combination on its own. Per-character settings persist between launches, keyed by `res_id` so renames don't lose data.

### Added

- **Adelheid and Clara.**
- `docs/game_formulas.md` — canonical reference for the in-game formulas the optimizer uses. Code disagreements with in-game math are resolved by updating this file first, then the code.
- `MAIN_STAT_VALUES` in `game_data/constants.py` — the max main-stat value per slot and stat for a Legendary fragment. Reference data; the optimizer reads the captured value.
- **Per-character optimizer settings**, persisted and keyed by `res_id` so renames don't lose data. Every known character gets a default entry at startup.
- Element override dropdown in the Optimizer tab, shown only while the selected character's element is Unknown, and hidden once they have a real one.
- Per-character `Optimize for LVL` stepper (60 / 61 / 62). Each character remembers its own, and the value is authoritative — the optimizer is an endgame planning tool, so it is not clamped to the character's actual max level.
- **`Have at least` hard constraints** — eight spinboxes (ATK, DEF, HP, Ego, CRate, CDmg, Extra DMG%, DoT%) acting as minimums on final stat values. Builds missing any are excluded; if all fail, a popup suggests lowering one.
- All / None buttons on the Exclude Combatant's Gear panel.
- **Bundled defaults system.** A `default_settings/` folder ships canonical preset, per-character preset and optimizer-settings files, merged into your `settings/` folder on every launch: first-install seeding, and per-entry additions on update. A tombstone record means a default you deleted does not silently reappear. Documented in `docs/how_to_maintain_default_settings.md`.
- New combatants released in program updates default to excluded in `Exclude Combatant's MFs`, without maintainer intervention per release.
- **Restore Defaults UI** in the Setup tab. Three buttons — Presets, Combatant Presets, Combatant Settings — each opening a dialog with Restore Missing and Replace Changed lists. The Presets dialog adds `Also Rename and Keep Current`, keeping your version aside while accepting the default under the original name. Dependent tabs refresh after a restore.

### Changed

- **Optimizer tab fully overhauled**, rebuilt around per-character persistent settings:
  * **Important Settings**: Extra% and DoT% sliders, ATK↔DEF scaling, Shielding/Healing weight, and four force-main checkboxes.
  * **Have at Least**: eight minimum-threshold spinboxes acting as hard constraints.
  * **Set Configuration**: Maximum Flex Slots, set-effect %, three Average buff spinboxes, and one combined checklist of all sets, 4-piece first. The separate 4-piece and 2-piece multi-selects are gone — select any usable sets and the optimizer finds the best shape.
  * Every per-character widget saves on change and is restored when you re-select that character.
- `SLOT_MAIN_STATS` corrected — DEF% was listed for slots 4 and 5; it only exists on slot 6.
- A set's `stat` type is renamed `unconditional` in `sets.py`, covering four sets. The old label suggested a category distinct from conditional even though some conditional sets also contribute to final stats.
- Optimizer-tab toolbar redesigned: Combatant → Optimize-for-LVL stepper → Start → Stop, with the status label on the right and a three-line help strip below.
- **Optimizer scoring formula rewritten** to match the in-game damage and shield-heal model: ATK-scaling and DEF-scaling damage blended by the ATK/DEF split, Extra and DoT shares applied as multipliers, conditional DMG sets contributing to the damage card multiplier only, Element DMG% picked up from slot-5 mains matching the character's attribute, CRate capped at 100%, and the result blended with shield/heal by the heal-share slider.
- The `Have at least` constraint is applied during enumeration, skipping failing builds before scoring. The `0 builds matched` popup distinguishes "no candidates satisfied set requirements" from "all candidates failed minimums".
- Set-combo search rewritten around a single locked-slot rule covering all six combo shapes (4+2, 4+wild2, 2+2+2, 2+2+wild2, 2+wild4, wild6): a build is valid when the slots not locked into a chosen set's bonus fit the flex cap. Overflow pieces don't count past the threshold — six of a 4-piece set still locks four slots.
- The slot pre-filter keeps at least 10 fragments per slot. Sparse inventories were ending up with one or two candidates per slot, starving the optimizer.
- **The character's assigned preset drives the Optimizer tab**, not the globally active one: both the Selected Build detail tree's GS and Potential columns and the slot pre-filter now use the Combatants-tab assignment, falling back to the active preset and then to all-1.0 weights.
- Three rounds of UI refinement across the Optimizer, Combatants and Memory Fragments tabs: mouse-wheel on every spinbox, type-to-jump on the dropdowns, fixed-ratio panels in place of draggable splits, Maximum Flex Slots auto-raised with a notice where the chosen sets cannot leave a valid build, a reorganized Stats Comparison panel, a right-click `Show all stat contributions` breakdown, a flow layout for Exclude Combatant's MFs, a note under `Have at least` saying its figures are the ones the in-game Combatants menu shows, and a Combatants detail panel sized from the whole roster so switching combatants never shifts the layout.
- **Optimizer Results scores are normalized by a per-character buff baseline**, so a low-scoring roster member reflects weaker fragments and sets rather than lower assumed buffs. Within one list, order and ratio gaps are exact; across characters it is approximate while conditional DMG sets are active. The ranking is untouched.
- A preset assigned to a combatant survives them becoming known. An assignment made while they were captured only as a number stays put once they are named.

### Fixed

- Duplicate placeholder keys in `partners.py` silently dropped a partner. Five partners without known ids shared overlapping negative keys, so Clara was lost entirely.
- Newly released characters vanished when their gear was unequipped. A captured character not yet in `characters.py` only appeared via equipped gear; they now persist regardless.
- The optimizer's `Found N` progress counter jumped wildly, because the in-flight results list is trimmed periodically. The progress line shows search-space progress only; the accurate count appears when the run completes.
- Live updates no longer blank or stale-reference the Optimizer results. A reload re-maps results onto the newly loaded fragments, recomputes each build's stats and score so an upgrade shows immediately, preserves the selected row, and marks a deleted fragment `(deleted)` rather than dropping the build.
- Newly released partners no longer show as character entries. The roster carries characters and partner cards in one array with no type field; the classifier now combines four signals in order rather than relying on a partner being already known. A res_id range rule was deliberately avoided — some new characters also use 5-digit ids.
- The Exclude Combatant's MFs list does not blink when the combatant changes. Only the two affected rows update; the full rebuild fires when the roster or the excluded set actually changes.
- The `How Gear Score Works` frame does not flash white on first load, nor does the Setup tab's instructions frame.
- The Combatants tab loads faster, the character-name lookup being built once rather than once per combatant per refresh.

### Removed

- **Optimizer tab:**
  - Stat Priority sliders — replaced by per-character Important Settings.
  - The Main Stats checkbox grid — replaced by the force-main checkboxes plus an internal per-slot choice.
  - The Top % Filter slider — now an internal performance setting.
  - The Include Equipped Items checkbox — replaced by the per-character exclude list. Equipped fragments are always available except those owned by excluded characters, and the current character's own gear is always available.
  - The Reset button — every setting saves per character, so reset has no clear meaning.

## [1.0.0](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases/tag/v1.0.0) - 2026-05-24

Initial release of this fork.

### Added

- **Per-character Gear Score presets** — the Combatants tab assigns a GS rubric per combatant, and the Equipped MFs frame and the list's GS column both use it.
- Link-icon marker on assigned presets — the Scoring tab shows a 🔗 beside a preset at least one character points at, so it is clear that editing or deleting it changes their GS.
- **Letter-key list navigation** — Windows-Explorer-style type-ahead on the Scoring tab preset list and the Combatants character list.
- **Highest Pot. range on the upgrade log** — Upgraded lines end with the post-upgrade Highest Pot. range across every defined preset, e.g. `Upgraded Line of Justice Denial (+3). Highest Pot.: 42-58`.
- `Unequip All` capture handler — the in-game bulk unequip is tracked. Its response shares a key shape with the create flow, which the dedup logic had mistaken for existing pieces.
- **Inventory tab `Highest GS` and `Highest Pot.` columns**, with an `Assigned Presets Only` filter narrowing the search to presets in use, and a tooltip on every column header.
- Main stat and set filters on the Inventory tab.
- **Memory Fragment lifecycle capture** — create and disassemble events tracked, completing the set alongside the equip, unequip, swap and upgrade already covered. Batch operations supported.
- **Right-click level checkpoints** — confirm a combatant's or partner's in-game level, anchoring the exp-to-level table. Combatants 1–62, partners 1–60.
- Character selection memory — the last selected combatant is restored on the next launch.
- Single-instance lock — a second launch is rejected.
- Active preset auto-highlight in the Scoring tab list.
- Level 62 infrastructure — placeholders until the real bonus values land.
- About tab update check against this fork's releases, with no third-party dependencies, no popups, and the cached result restored on the next launch.

### Changed

- **Damage formula overhauled** to layered Final ATK/DEF/HP:
  * `inner = (Base + Partner_flat) × (1 + MF% + Potential%) + Gear_flat + Affection_flat`
  * `Final = inner × (1 + Partner% + Equipment%) + Equipment_flat`
  * Equipment legendary constants: ATK 82, DEF 31, HP 83.
- **Gear Score normalized to 0–100** per preset.
- **Gear Score is normalized per fragment.** A fragment's bounds exclude its own main stat from the substat pool, so 100 is reachable whatever the main stat is. Two fragments with identical substats can score differently: the one whose main is weighted higher under the active preset scores higher, which reflects the build value it actually carries.
- Partner card display is three-state — known partner, unknown res_id, or no partner.
- Internal `friendship` renamed `affection` to match the in-game term.
- About tab links repointed to this fork.
- The Scoring tab preset list gained a gutter column for the assigned-preset link icon, keeping preset names aligned across linked and unlinked rows.
- **First launch opens the Setup tab** rather than the Optimizer tab: the program does nothing useful without captured data, so it lands on the certificate and proxy flow first. Subsequent launches open at the leftmost tab.

### Fixed

- Partner data audited against prydwen.gg; corrections applied.
- `CHARACTER_EXP_TABLE`: Amir 300000 → 320000; levels 41–49, 55 and 61 firmed up from estimates to confirmed checkpoints (45 was 200000 → 213000, 55 was 481000 → 480800, 61 is new at 778200).
- `PARTNER_EXP_TABLE`: Yvonne 110000 → 93500, Zatera 4000 → 1800, max 360000 → 346000.
- Partner max level returns 60 at the cap.
- Elemental DMG% excluded from the substat roll pool — main-stat only.
- Affection bonus at level 41+ uses a closed form.
- 5-digit potential node ids are parsed correctly.
- A set name is lit only when the equipped set is actually complete.
- The addon-script writer is forced to UTF-8, fixing a codec error on non-ASCII paths under cp932.
- Gear Score documentation corrected: 100 requires the fragment's substats to be the preset's top four weighted stats, not just any perfect roll.
- The Optimizer tab refreshes after a live capture, so a newly captured combatant appears without a manual reload.
- User data persists in frozen builds. Presets, level checkpoints, settings and per-character assignments resolved into PyInstaller's read-only temporary directory, which is wiped on exit, silently losing every save.

### Removed

- `update_checker.py` and its consumers, along with the third-party `requests` and `packaging` dependencies.
- Heuristic damage stats (EHP, Average Damage, Max Crit Damage, Bruiser) from results, superseded by the Final ATK/DEF/HP model.
- The Load Data button from the Optimizer toolbar — data loads at startup and after each live capture update.

### Refactored

- A substantial documentation pass across the game data, model, optimizer and tab modules.
- The Gear Score and Potential helpers extracted as pure functions, with per-preset bounds computed once and reused.
