# tasks.md — triaged backlog

Potential issues, user reports and improvement ideas, triaged. Completed items are removed; parked ones live in TBD at the bottom. Conventions: `docs/repo_conventions.md`. Archived plans: `past_plans/*.md`.

---

## 1) Bugs

### 1a) Can fix without maintainer input

*N/A*

### 1b) Needs maintainer assistance figuring out

*N/A*

---

## 2) Improvements

### 2a) Can improve without maintainer input

*N/A*

### 2b) Needs maintainer assistance figuring out

- **I33 — What a loss looks like.** Needs the maintainer in game. With capture on, lose in as many modes as convenient: a Simulation stage, a Battle Mission, the Basin, the Great Rift, the Full-Scale Offensive, a Sortie. For each:

  - what the close and the `battle_end` say;
  - whether anything the capture keeps moves: stage limits, rewards, the Checklist's counts, the standings.

  Seen already, in the Tower and in a Chaos run: `clear_stage` answered `FAIL`. The Chaos run also sent a `battle_end` saying `BATTLE_RESULT_TYPE_STAGE_FAILED`.

- **I35 — After the 2026-09-30 patch.** What the patch's plan left open. The rest is in `past_plans/patch_2026_09_30.md`.

  1. **10-13: Nine & Alcea's Normal Rescue rerun, and Nine's trial.** A capture confirms `RERUN_BANNERS`' dates and the trial's pairing.
  2. **10-21: season 5's part 1.**
     - From its notice: `SUPPLY_ROUNDS["disaster_s05"]` in `checklist_tab.py`, and `SEASON_ESTIMATE["disaster_s05"]`, hand-counted off the screens (`past_plans/seasonal_shop.md`).
     - From its first run: the new Chaos's stage id in `chaos_estimate.CHAOS_NAMES`, and the season currency's id in `docs/chaos_runs.py` `CURRENCY`. The client puts `chaos_10` in the season (`disaster_chaos_list`), but build 88 holds no stage id (90000 if the pattern holds), name or currency for it yet; a client read after the next patch may.
     - Then refresh `chaos_estimate.SHIPPED` from `python docs/chaos_runs.py`. Read its by-spot lines: the season's maps hold fewer ordinary battles (its docstring).
  3. **To confirm on the next capture:** a level-up, a Potential node and a gift move the Combatants tab live.

- **I31 — The Chaos estimate's loose end.** Built as the maintainer specified:

  - `Vribbels/chaos_estimate.py` has the model and the four rules;
  - `version.RELEASED_ON` / `RELEASED_IN` date the shipped figures;
  - a lost run counts when a boss had paid and no non-boss fight was left;
  - `chaos_runs_per_day` sets the runs a day.

  **What is left: season 4's part 1 was never captured.** It borrows part 2's bosses (172 + 172). If part 1 paid something else, the season-4 estimate is off by 21 days of the difference. The maintainer does not remember what it paid, so it stays borrowed unless a capture turns up. Season 5's data can replace it once available.

- **C1 — Finish the Checklist tab.** `docs/wire_hunt.md` and `docs/wire_hunt.tsv` hold every row that still shows no value, with its suspect and what would settle it. The TSV is the live list; this is only what it costs. What is left:

  1. **How a step track's record reads.** The code takes `reward_step` as the steps CLAIMED, on the evidence in `docs/events.md`, *`reward_step` and `version`*. If it is the track's SIZE instead, `_client_steps` and `_step_progress` change as that section says, and a track at the top of its ladder stops waiting for its flag to go green.
     - Needs, on the next LIVE step track, with a capture running: its `reward_step` against the size the client gives it, while steps are still unclaimed. The next Love event, `event_love_05`, is already in the client.
     - The Sortie has no such track: `event_chaos_assault_1` is its launch event, long over.
  2. **The Coronomicon Gift row: claimed today, and days left on the pass.** Deferred by the maintainer; the research is done.
     - `issued_limit_entities[subscription_1]` rides the login burst, and the claim answers with the same record as `issued_entities`, so the capture keeps it either way. `expire_time` dates the pass; `vi1` names the day the gift was last taken. `docs/wire_hunt.md`, *The monthly pass, and what it would take to show it*, has the lot.
     - Needs nothing from the maintainer. It needs a ROW, not a capture: a Daily entry, claimed-today plus days remaining.

  **How the next round runs:**

  1. The maintainer keeps making a debug capture every day.
  2. Once the next batch of events is live, Claude analyses the captures (`docs/events_replay.py`, `docs/wire_hunt.tsv`): when each record arrives, and what it carries.
  3. Claude writes a list of client readings wanted: which event or row, which screen, which number, and when to read it (right after login, just before and just after a claim).
  4. The maintainer notes what the client shows, with the time, in `_tmp/client_readings.md` (gitignored).
  5. Claude matches the readings to that day's capture and writes the next list.

  The aim, in order: an exact reading, else a good estimate, else a lower bound.

- **I6 — A setting in `Upgrade Log Settings` that would filter out presets that don't match the MF Set Effect's Element.** Default OFF. Consider if it would work for all set effects, not just Element restricted ones.

---

## 3) Big changes

- **T8 — Simulated-leveling mode: score MFs at their projected level 5.** A separate, clearly labeled optimizer mode that levels every under-5 fragment on paper before enumerating. The user sees what their inventory could become, not only what it is. It must stay visibly distinct from a normal run: the builds it produces aren't equippable today.

  **Model:** for each fragment below level 5, take the 2 substats worth most to the selected combatant. Add to each `(that substat's average roll / 2) × levels remaining × k`. Summed across the two, that is exactly one average roll per remaining level.

  **`k` is the model's central parameter, not a fudge factor.** This models average roll SIZE with perfect TARGETING. It does not model average luck, which would spread rolls across all four substats. That is the intent (it highlights potential), but it systematically favours unlevelled fragments over levelled ones, whose real rolls landed wherever they landed. `k` starts at 1.0 and comes down if testing shows simulated fragments beating levelled ones too easily; calibrate against real levelled MFs. **Expose it in the UI as an assumption the user can state**, not an opaque multiplier.

  **"Worth most" proxy:** rank substats by the combatant's assigned preset weights, which the Highest Potential column already uses. Ranking by marginal optimizer score would be more faithful, but costs a scoring pass per candidate substat.

  **Ruling on added substats:** a level-up ADDS a substat while the fragment has fewer than four (`docs/game_formulas.md` §2). So a level-0 Legendary spends 1 of its 5 level-ups gaining a 4th, and a level-0 Rare spends 2. Those future substats are unknown at simulation time. **Simulate each added substat as the 2nd-best still available**: best-available would double up on the substat already being targeted.

  **The primary use dictates a requirement.** This mode exists to find which MFs are worth leveling: the user reads the result, levels a fragment, and comes back. So the program must react to a level-up while simulated results are on screen: re-simulate that fragment (it may still be below 5), re-score every combo containing it, and re-sort. The existing live-update path re-maps results by fragment id after an upgrade. This extends it with a re-simulate step and a genuine re-sort, rather than the row-order-preserving refresh the normal mode uses.

  **Implementation:** transform the candidate lists once per run inside `get_gear_by_slot`, parent-side and before enumeration. The hot loop, the parallel workers and the scoring math stay untouched, and the cost is one pass over the inventory. Simulated fragments must be COPIES: never mutate the real objects, which every other consumer shares.

- **T8+ — Extra simulation.** Simulate an MF in each slot for each other set selected in the Optimizer tab, of similar quality to the best MFs already in inventory. A user with a lopsided inventory (from farming some sets harder) then sees that a set they dismissed may be worth farming.

- **T20 — A calculator for a combatant's Optimizer settings, from a deck.** The user builds a deck from the combatant's cards and adds the buffs they expect (e.g. +100% all DMG). The program works out what that deck deals per average turn: regular damage, Extra damage, each DoT type, healing and shielding. It turns that into the Important Settings: the Extra, Agony and Fracture shares, the ATK/DEF split, Avg Card DMG%, the two Avg Buff% fields, and a proposed shield/heal weight. First a maintainer tool for the shipped defaults, every one of which was set by eye; a tab for users if it proves easy to use.

  **Why:** `docs/game_formulas.md` §3.4 already says the shares are read off the deck, as each source's DMG% over a turn. This does that sum instead of an estimate. The default Gear Score weights are derived from these settings (`docs/preset_weights.md`), so a better setting improves both.

  **Contentions:**

  1. **Card data is the whole cost.** Each card's coefficient per hit and per damage type, its scaling stat, what triggers Extra damage, DoT stacks and durations, heal and shield coefficients, cost, upgrades and Epiphanies. The wire sends a deck as card ids (`stage_info.deck`), never what a card does. The program reads the client already (`Vribbels/game_client.py`), which holds a `card(<combatant>)@card`, `@skill_eff` and `@card_r_spark` table set per combatant, read again each patch. What is left is mapping their columns to the calculator's terms.
  2. **"An average turn" needs a model.** Draw order, energy, generated cards, exhaust and retain decide what gets played. The candidates:
     - every card's coefficients averaged over one cycle of the deck: simple and stable, but blind to sequencing;
     - a simulated shuffle-and-play loop: faithful, at the price of many assumptions;
     - play counts per card entered by the user: honest, tedious.
  3. **Buffs split two ways** (T16): general against card-only, and which damage types each reaches (Agony takes none; Fracture and Scorched take general ones only). The calculator needs that distinction in the settings, or its output folds into today's single bucket.
  4. **The shield/heal weight is a judgement, not a share.** A deck says how much it heals and shields beside its damage. How much a player values the one against the other is theirs, so the calculator proposes and the player decides. Heals that scale off damage (some of Rei's cards) count as damage for what they scale with.
  5. **A combatant played with several decks** gets a settings set per deck. A shipped default then needs the averaging the presets already use: each deck weighed by its share of the meta.

---

## TBD (parked — ignore for now)

### Documentation Improvement

- `ui_spacing.md`:

  > In general, what do you think should be done about the rule names and the rules? They were originally designed to standardize distances between typical element pairs across the program and for the spacing audit to use them, so that:
  >
  > - I didn't have to measure something to remember what the distance is supposed to be;
  > - I didn't have to manually go through the program checking distances at each UI change;
  > - Same types of things would look the same across the program;
  > - You had a clear way of telling what distances should be like when making a new UI element or tab, and a way to tell when something was off;
  > - Creating a document that explained how distances are created, and what limitations exist.
  >   However, from a practical standpoint visual clarity is a higher priority than standardization (although a standard is still important from both a user experience and a maintenance & development perspectives).

  **On the rules in general**

  Most of your goals are met: the audit checks distances for you, the markers and registry tell me what a distance should be and when it's off, and `ui_spacing.md` explains how distances are made and their limits. Two goals fall short: remembering a distance without measuring, and making things of the same type look the same. The cause is that rules are named and split by **widget pair**, not by **relationship**. That's why the names needed "element and its label" when they're neither, and why the note could plausibly have been `label ↔ its element` (5) or `heading ↔ element` (14).

  What I'd do:

  1. **Group the rules into a few levels of relatedness on each axis.** Horizontally: within one control (5), between items of one set (8), between groups (14 and 16 merged into one number), and panel edges (3–4). Vertically, the same idea: rows of a set, a block to its buttons or explanation, then unrelated blocks. Today there are about 20 rules on 11 distances, several only 1px apart (4/5/6/7). The eye doesn't read 1px as a different relationship, so those splits make numbers harder to remember without making anything clearer.
  2. **Name rules by relationship.** The marker suffix already names the widgets (`checkbox, label ↔`), so the rule name doesn't need to.
  3. **Put a four-question procedure at the top of `ui_spacing.md`:** one control? items of one set? separate groups in a panel? separate panels? That lets either of us pick a rule without reading a 20-row table.
  4. **Keep clarity ahead of the standard with the existing `exception` markers.** Where a level's number looks wrong for one widget (spinbox borders read as ink, for example), the exception records it. The standard is the default, not a rule that can't bend.
  5. **Do it in two passes.** First a scripted rename that moves no pixels; the checks catch anything missed. Then merge the numbers one level at a time, each with an audit run and your eye on the result.

  I can draft a `plan.md` that maps every current rule to a level and lists the pixel change each merge would cause, for you to decide on.

### Improvements

- **T21 — Tcl/Tk 9.1, once a Python ships it.** The program runs on the Tcl/Tk its Python bundles (9.0 with Python 3.14). `_tkinter` is built against that version's DLLs, so 9.1 arrives only with a Python release built on it. What 9.1 offers that could matter here:

  - consistent dark mode on Windows, which may darken the native dialogs and message boxes. On 9.0 a message box is light, and at 200% its text looks washed out; if 9.1 fixes neither, the alternative is drawing the program's own message boxes (the file dialogs would stay native);
  - the mouse wheel scrolling an entry;
  - extended Treeview and Notebook states;
  - faster image painting in ttk widgets.

  When one ships: `Vribbels/build_tcl/prepare_tcl_data.py`'s `libtcl9*` globs already match a 9.1 library, and `checks/run_all.py` at both scales is the first test.

- **T22 — Rescale live when the window moves to a screen of another DPI**, as taskmaster's asks window does. Feasible only as a rebuild, not a re-configure in place:

  - every distance is scaled once, at build (`px()` at the geometry call), and nothing records it to scale again;
  - layouts are measured once and pinned in pixels: the Checklist's holders, tab stops and block heights, the checkbox probe, Materials' figure blocks;
  - fonts are tuples (`ROW_FONT`), which Tk caches per display and never measures again;
  - `tk scaling`, the theme's pixel options (`scale_theme`) and the icons (`image_utils._resample`) are set or resampled at startup.

  The rebuild: on a DPI change, debounced, set the new scale, apply `tk scaling` and the theme again, reload the icons and rebuild the notebook's tabs from the managers, carrying or dropping each tab's selection and scroll. `checks/check_ui_scales.py` and the spacing audit already cover every scale.

- **T19 — More from the game client.** Event names and reward totals, item names, Excursion type counts, the daily tasks, set effects and the node 7 and 5.1 texts are read at launch (`docs/client_data.md`, *What the program reads at launch*). The app reads what changes every patch; the maintainer tool, `docs/client_tables.py --audit`, holds the tables whose every change wants reviewing. Left:

  - **When the Galactic Disaster season's next part opens**: read the seasonal currency's name and id off its first capture. The item worklist's `Type` and `Note` on 3000009 describe Memory of Light, which the client puts at 3000006.

- **T3 — Richer main-stat forcing for slots IV/V/VI** (UserA). Main-stat forcing is four Force HP/Ego checkboxes. The design question is which options, and in what form: per-slot checklists, dropdowns, or curated rules.

- **T12 — Consider excluding Upgrade Log MFs by set too.** The Upgraded-line top-5 already drops presets on an ATK/DEF or Element main-stat mismatch. The same argument applies to a fragment whose set isn't among those a combatant's Optimizer config selects. Open:

  - whether an empty `sets_selected` means "any set" or "none";
  - whether flex slots make a non-selected set worth showing anyway.

- **T16 — Distinguish general buffs from card-only buffs.** The Average Multiplicative / Additive Buff% settings are one bucket, and every formula reads them as GENERAL. In game the distinction matters: Fracture and Scorched take general buffs but not card-only ones. So a combatant whose buffs are card-only has its Fracture share overstated by exactly the buff fraction. Agony is unaffected: it takes no buffs at all. See `docs/game_formulas.md` §3.4. Open:

  - one more slider pair, or a split of the existing two;
  - whether the conditional-set `DMG multi` / `DMG add` effects are general or card-only. They ride the same path today.

- **T17 — Consider folding `checkbox block -> All/None row` into `border edge -> first non-button element` at 4px.** Both describe the same shape: a block of checkboxes, and the thing immediately below it. They differ only in target, 5px against 4, so collapsing them removes a rule and a number from the ledger for no change in kind.

  This has nothing to do with `border edge -> button`, which measures a different pair. That one runs from the PANEL's border to the button; this runs from the checkboxes above to the button row below. A panel's bottom edge can answer to one and the gap above the same buttons to the other, and both be right.

  Open: only whether 4 leaves the row looking crowded under the checkboxes. A measured window settles it.

- **T11 — Consider exposing `top_percent` in the UI.** The per-slot candidate cut is hardcoded at 20%, with a 10-fragment floor. On a filtered inventory every slot sits on the floor, so the compared-combos total is fixed whatever the other settings. Exposing it would trade run time against search breadth directly. Open:

  - global or per-combatant;
  - whether the floor stays;
  - how to stop a careless value turning a 2s run into minutes.

### Big changes

- **T7 — Named build loadouts** (UserA). Full per-character optimizer configuration snapshots (Important Settings, HAL, sets), saved under a name and switchable next to the Combatant selector. A new persistence layer plus UI; interacts with the existing per-character auto-persistence.

### Pondering

- Should anything be added to the program from here:

| Where                                       | What                                                                                                                                                                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `characters[]`                              | `friendship_exp` (exact Affinity progress, not just the level); `psychosis_exp` / `psychosis_exp_today`; and **where each copy came from**: `get_count`, `gacha_count`, `shop_count`, `limit_cube_count`, `omega_code_count` |
| `inventory.savedata`                        | every saved build, named or not, each with a `point` score, its equipment and its cards; several per combatant                                                                                                               |
| `savedata_bookmark_entities`                | those builds' node layouts                                                                                                                                                                                                   |
| `characters.town_data`                      | happiness / population / politics / tourist, a research-level map, the active policy and `next_policy_get_time`, plus today's visit board                                                                                    |
| `counseling_archive`                        | each combatant's counseling entries, with the story choices taken                                                                                                                                                            |
| `teams` / `team_presets` / `savedata_teams` | the live team, the named team presets, the saved-build teams                                                                                                                                                                 |
| `user`                                      | `account_title_level`, and when the account was created                                                                                                                                                                      |
| `card_archive`                              | every collected card id                                                                                                                                                                                                      |
| `user_setting`                              | the in-game auto-disassemble rarity threshold, and the music-box state                                                                                                                                                       |
