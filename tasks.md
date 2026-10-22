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

  Seen already, in the Tower and in a Chaos run: `clear_stage` answered `FAIL`. The Chaos run also sent a `battle_end` saying `BATTLE_RESULT_TYPE_STAGE_FAILED`. So did a lost Nebula Distortion fight (`disaster/enter_disaster_penalty_stage`), with `finished_condition` `default1`; its close said `FAIL` with state `finish` and `curr_floor` 0, carried no `disaster_boss_penalty_result`, and paid nothing.

- **I37 — Anika's and Arabella's level curves.** The client puts both Strikers on another class's level-61/62 gains: Anika on Vanguard grade 4's (`c_lv_vanguard_sr`), Arabella on Ranger grade 5's (`c_lv_ranger_ssr`), `level_curve` in `characters.py`. No reading has either past level 60: the 2026-10-12 capture's one Anika battle, a Chaos run, states her at 60, and Arabella is in none of its battles. With capture on, a plain battle with either at level 61 or 62; `check_base_stats_on_wire` then holds the server's base to the curve.

- **I39 — A Trauma Code's rewards on the Checklist.** The client gives Blade Poised Against the Cycle (`evn_trc_30134_1`, Rossweisse's code) 6 rewards of 50 Crystals and its sticker after them (`trauma_code_06_01`–`06`, `style_link_item_id` 9300337, Memories Made With Rossweisse): 06_01 for the code's synchronization, 06_02–06 for each event battle's achievements. The capture keeps `trauma_code_entities` and the code's event tables (`docs/unread_stats.md`).
  - **Seen on 2026-10-21:** unlocking the code (`trauma_code/unlock_trauma_code`, a Special Security Code), and claiming 06_02 (`trauma_code/get_reward_mission` with `event_trauma_code_id` and `mission_id`), whose reply carries `mission_entity` {`event_code_id`, `res_id`, `score`, `complete_time`}. The login came before the claim, so its `mission_trauma_code_event_entities` was still `{}`.
  - **Needs:** the next login's `mission_trauma_code_event_entities`, the first to hold a claimed mission, for its shape. Then the addon folds a claim's `mission_entity` into it, and a reader in `EVENT_READERS` for `EVENT_TRAUMA_CODE` counts the claims; later the sticker's record. Until then the row asks `Finished?`.

- **I35 — After the 2026-09-30 patch.** What the patch's plan left open. The rest is in `past_plans/patch_2026_09_30.md`.

  1. **Season 5.** Its Chaos, Celestial Bulwark, is stage 100000, and Relic of a Frozen Civilization (3920032) is its currency, off the build-126 client. Its shop pages open on the client's own offsets, 21, 42 and 63 days into the season's schedule: 10-21, 11-11, 12-02. `SEASON_ESTIMATE["disaster_s05"]` is in, from `python docs/client_tables.py --season disaster_s05`.
     - **At the 11-11 and 12-02 patches**, re-read that and update the entry: the client lists a part's story and achievements with the patch that opens it, so build 126 holds chapter 1's alone, and the entry takes it three times for the story. The Great Rift terms are season 4's until the client lists season 5's; its weekly tiers' table still names season 4's currency.
     - `chaos_estimate.SHIPPED["disaster_s05"]` is at base: bosses 144 on floors 17 and 28, 60 on floor 31, the Rare Species 48. Its mark rates rest on 3 whole runs of part 1, as of the 2.6.0 release; refresh the entry from `python docs/chaos_runs.py` as runs come in.
     - **At the 11-11 patch**, see that `from_client.SEASON_NODES["disaster_s05"]` grows to two parts, the total under the one layout becoming part 2's (`game_client.grown_season_nodes`).

- **I31 — The Chaos estimate's loose end.** Built as the maintainer specified:

  - `Vribbels/chaos_estimate.py` has the model and the five rules;
  - `version.RELEASED_ON` / `RELEASED_IN` date the shipped figures;
  - a lost run counts when a boss had paid and no non-boss fight was left;
  - `chaos_runs_per_day` sets the runs a day.

  **What is left: season 4's part 1 was never captured.** It borrows part 2's bosses (144 + 144 at base, so 163 each at part 1's 13 nodes); parts 2 and 3 share that base, so what could differ is how many bosses part 1 had. If part 1 paid something else, the season-4 estimate is off by 21 days of the difference. The maintainer does not remember what it paid, so it stays borrowed unless a capture turns up. Season 5's data can replace it once available. Note: Season 5 may be an exception (at least partially), because it seems like it will feature a Core of Discord boss starting from the first part.

- **C1 — Finish the Checklist tab.** `docs/wire_hunt.md` and `docs/wire_hunt.tsv` hold every row that still shows no value, with its suspect and what would settle it. The TSV is the live list; this is only what it costs. What is left:

  1. **How a step track's record reads.** The code takes `reward_step` as the steps CLAIMED, on the evidence in `docs/events.md`, *`reward_step` and `version`*. If it is the track's SIZE instead, `_client_steps` and `_step_progress` change as that section says, and a track at the top of its ladder stops waiting for its flag to go green.
     - Needs, on the next LIVE step track, with a capture running: its `reward_step` against the size the client gives it, while steps are still unclaimed. The next Love event, `event_love_05`, is already in the client.
     - The Sortie has no such track: `event_chaos_assault_1` is its launch event, long over.

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

  1. **Card data is the whole cost.** Each card's coefficient per hit and per damage type, its scaling stat, what triggers Extra damage, DoT stacks and durations, heal and shield coefficients, cost, upgrades and Epiphanies. The wire sends a deck as card ids (`stage_info.deck`), never what a card does. The program reads the client already (`Vribbels/game_client.py`), which holds a `card(<group>)@card`, `@skill_eff` and `@card_r_spark` table set per developer group, several Combatants to a group, read again each patch. What is left is mapping their columns to the calculator's terms. T23 builds the card catalogue and the deck model this reads.
  2. **"An average turn" needs a model.** Draw order, energy, generated cards, exhaust and retain decide what gets played. The candidates:
     - every card's coefficients averaged over one cycle of the deck: simple and stable, but blind to sequencing;
     - a simulated shuffle-and-play loop: faithful, at the price of many assumptions;
     - play counts per card entered by the user: honest, tedious.
  3. **Buffs split two ways** (T16): general against card-only, and which damage types each reaches (Agony takes none; Fracture and Scorched take general ones only). The calculator needs that distinction in the settings, or its output folds into today's single bucket.
  4. **The shield/heal weight is a judgement, not a share.** A deck says how much it heals and shields beside its damage. How much a player values the one against the other is theirs, so the calculator proposes and the player decides. Heals that scale off damage (some of Rei's cards) count as damage for what they scale with.
  5. **A combatant played with several decks** gets a settings set per deck. A shipped default then needs the averaging the presets already use: each deck weighed by its share of the meta.

- **T23 — The Deck Builder tab.** Pick three Combatants as a team, owned or not, and pick or build each one's deck. The tab shows whether the team's deck draws itself and has the AP to play every card each turn, for the team and per deck. Saved decks and teams, comparisons, and the game's deck codes come with it. The plan, its research and the open questions are in `plan.md`.

  - The deck model and the card catalogue are UI-free (`Vribbels/decks/`), so T20 adds damage to the same model.
  - **Once the feature is complete, a cleanup pass:** remove from `plan.md` and the docs whatever turned out not to be needed, move the reference material into `docs/`, and archive the plan.

- **T26 — A tab for the paid packages.** The Shop's Starshine Package (`shop_package_event`) and Protos Supply (`shop_package`): what each period sells, at what price and limit, what each package holds, and what the account bought. The maintainer's basis for what to make: `https://docs.google.com/spreadsheets/d/1hlWGKlHVD9BSMX55wGJMYnZ9FxEeYZaUJs43Wqn52H8/edit?gid=0#gid=0` (it needs a sign-in to read). Every package seen so far is in `docs/items_shops.tsv`.
  - **Each banner period's packages are new items**, three tiers at prices 98, 328 and 648 with the same contents as the period before's (10 Signal Amplification Anchors; 20 and 2,480 Crystals; 30, 6,480 Crystals and 3 Multidimensional Alignment Material), plus extras some periods add. Their products are new ids too, and each names its period in `link_shop_schedule_id` (`pick_up_261021`).
  - **On the wire:** the shelf, `shop_res_data[shop]`, lists each product's item (`product_link_item_id`), price (`price_count`, `price_type` `CASH`), limit and period, but only while it is on sale. The purchase record, `shop_list[product id]` (`count`, `total_count`, `reset_time`), stays after the product leaves: the account's from 2026-01 on are all still there. So a past purchase's item and price are known only from a capture made while it was listed, which the capture archive holds back to 2026-09-08.
  - **In the client:** what a package holds (`reward_box_fixed`, its item's `multiple_link`), and the payment event points a product pays (`shop_product_point`).
  - **A past package can carry today's name.** Imp's Mischief II and III (4501086, 4501087) were named by the text ids of 4501094 and 4501095, which build 126 rewrote for the Nightmare Carnival Chests, so the client now names those two as the chests too. A period's packages are named right by the client build of their period (`client_archive`).

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

  - consistent dark mode on Windows, which may darken the native dialogs and message boxes. On 9.0 a message box is light, and at 200% its text looks washed out. If 9.1 fixes neither, the alternative is drawing the program's own message boxes (the file dialogs would stay native);
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
