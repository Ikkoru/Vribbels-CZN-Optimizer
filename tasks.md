# tasks.md — triaged backlog

Potential issues, user reports and improvement ideas, triaged. Completed
items are removed; parked ones live in TBD at the bottom. Conventions:
`docs/repo_conventions.md`. Archived plans: `past_plans/*.md`.

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

- **I33 — What the server has not shown yet, for after the maintenance.** Each needs the maintainer in game; `check_base_stats_on_wire` passes on everything filed so far.

  1. **Base stats, from any plain battle** (Simulation, Abyss Battle Missions, the Tower, the Basin, the Great Rift, the Full-Scale Offensive; not a Sortie, a Chaos, a Combatant Trial or the Bartender story). Potential 7 doesn't matter for any of them.
     - **Never settled** -- the ones `check_base_stats_on_wire`'s note counts: Haru, Luke, Mei Lin and Renoa, at their current level; Hugo and Kayron whenever the account has them.
     - **Chaos-worked only**, which a plain battle confirms: Adelheid, Maribell and Mika.
     - **Level 62**: no combatant has been read at it; any that reaches 62, once.
  2. **Potential 7 parts no sheet has shown**, same kind of battle, node 7 taken: Tressa at DoT 30% or more (her second +4%; only the first was seen, at 0 DoT), and Owen at HP 700 or more (his second +4% ATK and DEF). The rest of the table matches the server, growth part-way included.
  3. **What a loss looks like**, with capture on, in as many modes as convenient: a Simulation stage, a Battle Mission, the Basin, the Great Rift, the Full-Scale Offensive, a Sortie. The Tower's and a Chaos run's have been seen: `clear_stage` answered `FAIL`, and in Chaos a `battle_end` saying `BATTLE_RESULT_TYPE_STAGE_FAILED`. For each: what the close and the `battle_end` say, and whether anything the capture keeps moves on it -- stage limits, rewards, the Checklist's counts, the standings.

- **I35 — After the 2026-09-30 patch.** What the patch's plan left open; the rest is `past_plans/patch_2026_09_30.md`.

  1. **Mutation numbers, at the next reroll**: write down each Mutation shown, in order, with capture on. The wire's `pick_corruption` replies come in the same order, which pairs each number with its row in `docs/mutations.tsv`. Read so far: 3, 9, 13, 101 and 102. They fit the game numbering the update note's families in its order -- Enhanced Attack 1-5, Defense 6-10, Card Damage Amount 11-17 -- with the seven rows of the families the update left alone somewhere before Shuffle, which ends the list at 101-103.
  2. **10-06 18:00 UTC, the Nightmare Carnival countdown** (`countdown_attendance_1st`, to 10-21): a login capture once it starts gives its record, which `LOBBY_COUNTDOWN`'s reader waits for, and its day-7 claim feeds I23.3.
  3. **10-13, Nine & Alcea's Normal Rescue rerun and Nine's trial**: a capture confirms `RERUN_BANNERS`' dates and the trial's pairing.
  4. **10-21, season 5's part 1**: from its notice, `SUPPLY_ROUNDS["disaster_s05"]` in `checklist_tab.py`; `SEASON_ESTIMATE["disaster_s05"]`, hand-counted off the screens (`past_plans/seasonal_shop.md`); from its first run, the new Chaos's stage id in `chaos_estimate.CHAOS_NAMES` (90000 and `chaos_10` if the seasons' pattern holds), and the season currency's id in `docs/chaos_runs.py` `CURRENCY`, then `SHIPPED` refreshed from `python docs/chaos_runs.py` -- reading its by-spot lines, since the season's maps hold fewer ordinary battles (its docstring).
  5. **To confirm on the next captures**: Peko's banner reads Seasonal (open its Rescue Records once); a pull is kept off its reply and its record replaces it; a level-up, a Potential node and a gift move the Combatants tab live.
  6. **The Vacation's total, the maintainer's call**: keep `WRITTEN_TOTALS["event_nodelist_8"]` at 13, or read the floor and the Node Lists' past, which says `~1/25`.
  7. **An Aether Cell's id**, whenever one charges: the Recharge Aether popup's.

- **I31 — The Chaos estimate's loose ends.** Built as the maintainer specified: `Vribbels/chaos_estimate.py` has the model and the four rules, `version.RELEASED_ON`/`RELEASED_IN` date the shipped figures, a lost run counts when a boss had paid and no non-boss fight was left, and `chaos_runs_per_day` sets the runs a day. What is left:

  1. **Season 4's part 1 was never captured**, so it borrows part 2's bosses (172 + 172). If part 1 paid something else, the season-4 estimate is off by 21 days of the difference. The maintainer does not remember what it paid, so it stays borrowed unless a capture of it turns up. Can be replaced with s05's data once it is available.
  2. **A Zero System run outside a season**: recorded, but none captured yet. It pays no currency, so it must stay out of any payout figure -- it does, being a past Chaos -- while its marks might one day count for rates, if the rates prove the same across Chaoses; `docs/chaos_runs.py` lists other Chaoses' rates apart to show whether they are.

- **I23 — Where an event's total comes from: two open questions.** The sources and their order are in `docs/events.md`, *The sources for a total, strongest first*.

  1. **A grid under-reads a Node List until its last index is issued.** `event_nodelist_007`'s grid came to 8 on its third day, against the 25 it held, and three finished lists on record say 25. A grid is this instalment speaking and outranks the family's past, so the smaller number wins -- right for the devil event, whose grid is whole on day one, wrong here. Decide which wins when the two disagree: the bigger (never reads done early, but a family that shrinks would read long) or the grid (as now). `docs/events.md`, *Still open*; how stable each type has been is its *Instalments on record, by type* -- the Node Lists themselves have come in two shapes, 15 to 19 and 25.

  2. **The per-unit census: one RULE per event family.** The design is in `docs/events.md`, *A reward has a SOURCE, and sources can be counted*. An event's total is a sum over its pages; a ladder page is already exact (ladders arrive whole), and a per-unit page needs the census — how many units of content the event has, counted off the event's own table. `{page prefix: (which table counts its units, rewards per unit)}` is the whole of what a family needs, and a rule survives an instalment changing length where a number does not. Falsifiable like the write-down: a page past its census total drops back to the floor.

     **What it is waiting on:** a table that is issued WHOLE, and none seen yet is. The bartender's guestbook looked like one and gains a row as each day is played, so it is a floor like the missions -- `docs/events.md`, *The bartender keeps its own per-day record*. A new event's tables are captured from its first login: count their rows then and again a day later, and a table that did not move is the census this needs. A rule checked only against the event it was written from is not checked at all, so it wants two instalments of the family.

  3. **A login streak's length from its day-7 reward.** Golden Autumn's Invitation (`event_161`, 15 days) paid Rescue Anchor x3 on day 7 without completing; Rei's Gift (`event_143`, 7 days) paid Prism Lens x3 on day 7, its last, with `completed`. Its days 1 and 6 paid Prism Lens x1, so its day 7 is its own reward tripled; Golden Autumn's day 7 is an item its other days did not pay (Abyssal Core x2, Colorless Core x2, Delegation Module x2, the day-1 Rabbit Veronica). Those are the only two streaks whose day-7 claim any log holds -- `attendance_entities` keeps the 10-, 14- and 21-day streaks' lengths but no rewards -- so neither "x3 on day 7" nor "a new item on day 7" can be told apart as a length signal yet. Wanted: the day-7 claim of the next few streaks, with their lengths. If a streak longer than 7 always pays something new on day 7, that is a week's warning.

  **How the next round runs, for I23 and C1 alike:** the maintainer keeps making a debug capture every day. Once the next batch of events is live, Claude analyses the captures -- `docs/events_replay.py`, `docs/wire_hunt.tsv` -- for when each record arrives and what it carries, and writes a list of client readings wanted: which event or row, which screen, which number, and when to read it (right after login, just before and just after a claim). The maintainer notes what the client shows, with the time, in `_tmp/client_readings.md` (gitignored); Claude matches the readings to that day's capture and writes the next list. The aim, in order: an exact total, else a good estimate, else a lower bound.

- **C1 — Finish the Checklist tab.** Every row that still shows no value, with its suspect and what would settle it, is in `docs/wire_hunt.md` and `docs/wire_hunt.tsv` — that TSV is the live list and this is only what it costs. What is left:

  | #   | To do                                                                                                                                                                                                                                                                                                                                                                                                                              | Needs from the maintainer                                                                                                                                                                                                                                   |
  | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | 1   | How a step track's record reads. The code takes `reward_step` as the steps CLAIMED, on the evidence in `docs/events.md` (*`reward_step` and `version`*); if it is the track's SIZE instead, several events gain a real denominator and `_step_progress` changes as that section says                                                                                                                                               | on the next LIVE step track -- most likely the next Love event: with a capture running, how many rewards its screen lists and how many are claimed; or claim ONE step. The Sortie has no such track: `event_chaos_assault_1` is its launch event, long over |
  | 2   | The Coronomicon Gift row — claimed today, and days left on the pass. **Deferred by the maintainer**; the research is done. `issued_limit_entities[subscription_1]` rides the login burst and the claim answers with the same record as `issued_entities`, so the capture keeps it either way -- `expire_time` dates the pass and `vi1` names the day the gift was last taken; `docs/wire_hunt.md`, *The monthly pass*, has the lot | nothing. It needs a ROW, not a capture: a Daily entry, claimed-today plus days remaining                                                                                                                                                                    |

- **I6 — A setting in `Upgrade Log Settings` that would filter out presets that don't match the MF Set Effect's Element.** Default OFF. Consider if it would work for all set effects, not just Element restricted ones.

- **I1 — Don't show presets with Shielding/Healing above [spinbox]% for DPS MFs**. Default to 69%. Consider DPS MF to be Crit%, CDMG, ATK% on Slot IV; ATK%, Element% on Slot V; ATK% (this one's complicated T_T) on Slot VI. Use the Optimizer's Shielding/Healing value to figure this out. Ask me for any info that you need.

- **I0 — Alternative type of `Exclude Combatant's` MFs.** Ticking a `Order Mode` checkbox (on the right of the None button) will change how it works. Instead of checkboxes there will only be Combatant names. They can be reordered using drag-and-drop (or `Higher`/`Lower` buttons that would replace the All/None buttons). The order in this panel will decide whose MFs will be ignored: all Combatants before (sentence order) the one currently being optimized will be excluded. An explanation about how this mode works, and availability of drag-and-drop will appear to the right of the checkbox label. Ask me questions if needed.

---

## 3) Big changes

- **T8 — Simulated-leveling mode: score MFs at their projected level 5.** A separate, clearly labeled optimizer mode that levels every under-5 fragment on paper before enumerating, so the user sees what their inventory could become rather than only what it is. It must stay visibly distinct from a normal run — the builds it produces aren't equippable today.

  **Model:** for each fragment below level 5, take the 2 substats worth most to the selected combatant and add to each `(that substat's average roll / 2) × levels remaining × k`. Summed across the two, that is exactly one average roll per remaining level.

  **`k` is the model's central parameter, not a fudge factor.** What this models is average roll SIZE with perfect TARGETING — not average luck, which would spread rolls across all four substats. That is the intent (it highlights potential), but it systematically favours unlevelled fragments over levelled ones whose real rolls landed wherever they landed. `k` starts at 1.0 and comes down if testing shows simulated fragments beating levelled ones too easily; calibrate against real levelled MFs. **Expose it in the UI as an assumption the user can state**, not an opaque multiplier.

  **"Worth most" proxy:** rank substats by the combatant's assigned preset weights (what the Highest Potential column already uses). Ranking by marginal optimizer score would be more faithful but costs a scoring pass per candidate substat.

  **Ruling on added substats:** a level-up ADDS a substat while the fragment has fewer than four (`docs/game_formulas.md` §2), so a level-0 Legendary spends 1 of its 5 level-ups gaining a 4th and a level-0 Rare spends 2 — and those future substats are unknown at simulation time. **Simulate each added substat as the 2nd-best still available** (best-available would double up on the substat already being targeted).

  **The primary use dictates a requirement:** this mode exists to find which MFs are worth leveling, so the user will read the result, go and level a fragment, and come back. The program must react to a level-up while simulated results are on screen — re-simulate that fragment (it may still be below 5), re-score every combo containing it, and re-sort. The existing live-update path re-maps results by fragment id after an upgrade; this extends it with a re-simulate step and a genuine re-sort, rather than the row-order-preserving refresh the normal mode uses.

  **Implementation:** transform the candidate lists once per run inside `get_gear_by_slot`, parent-side and before enumeration, so the hot loop, the parallel workers and the scoring math are untouched and the cost is one pass over the inventory. Simulated fragments must be COPIES — never mutate the real objects, which every other consumer shares.

- **T8+ — Extra simulation.** Simulate an MF in each slot for each other set selected in the Optimizer tab, of similar quality to the best MFs already in inventory. Lets a user with a lopsided inventory (from farming some sets harder) see that a set they dismissed may be worth farming.

- **T20 — A calculator for a combatant's Optimizer settings, from a deck.** The user builds a deck from the combatant's cards and adds the buffs they expect (e.g. +100% all DMG). The program works out what that deck deals per average turn — regular damage, Extra damage, each DoT type, healing and shielding — and turns it into the Important Settings: the Extra, Agony and Fracture shares, the ATK/DEF split, Avg Card DMG%, the two Avg Buff% fields, and a proposed shield/heal weight. First a maintainer tool for the shipped defaults, every one of which was set by eye; a tab for users if it proves easy to use.

  **Why:** `docs/game_formulas.md` §3.4 already says the shares are read off the deck, as each source's DMG% over a turn. This does that sum instead of an estimate. The default Gear Score weights are derived from these settings (`docs/preset_weights.md`), so a better setting improves both.

  **Contentions:**

  1. **Card data is the whole cost.** Each card's coefficient per hit and per damage type, its scaling stat, what triggers Extra damage, DoT stacks and durations, heal and shield coefficients, cost, and upgrades and Epiphanies. The wire sends a deck as card ids (`stage_info.deck`), never what a card does; the client holds that. Entering every card by hand is large and goes stale with each balance patch. Reading the client's data files is less work per patch, but it is datamining, with its own upkeep and questions of propriety.
  2. **"An average turn" needs a model.** Draw order, energy, generated cards, exhaust and retain decide what gets played. The candidates: every card's coefficients averaged over one cycle of the deck (simple and stable, but blind to sequencing), a simulated shuffle-and-play loop (faithful, at the price of many assumptions), or play counts per card entered by the user (honest, tedious).
  3. **Buffs split two ways** (T16): general against card-only, and which damage types each reaches (Agony takes none; Fracture and Scorched take general ones only). The calculator needs that distinction in the settings, or its output folds into today's single bucket.
  4. **The shield/heal weight is a judgement, not a share.** A deck says how much it heals and shields beside its damage, but how much a player values the one against the other is theirs, so the calculator proposes and the player decides. Heals that scale off damage (some of Rei's cards) count as damage for what they scale with.
  5. **A combatant played with several decks** gets a settings set per deck, and a shipped default then needs the averaging the presets already use: each deck weighed by its share of the meta.

---

## TBD (parked — ignore for now)

### Improvements

- **T21 — Tcl/Tk 9.1, once a Python ships it.** The program runs on the Tcl/Tk its Python bundles (9.0 with Python 3.14), and `_tkinter` is built against that version's DLLs, so 9.1 arrives only with a Python release built on it. What 9.1 offers that could matter here: consistent dark mode on Windows, which may darken the native dialogs and message boxes; the mouse wheel scrolling an entry; extended Treeview and Notebook states; faster image painting in ttk widgets. When one ships: `Vribbels/build_tcl/prepare_tcl_data.py`'s `libtcl9*` globs already match a 9.1 library, and `checks/run_all.py` at both scales is the first test.

- **T19 — Event display names.** The wire carries none: the client holds a localisation table and the server never sends it, so the Events block shows ids (`event_schedule_devil_001`). Three ways out and no decision — extract the table from the client, hand-write one in the code the way `RECORDED_NAMES` names items (one line per event as it appears), or leave the ids, which are stable and next to the deadline the row is really about.

- **T3 — Richer main-stat forcing for slots IV/V/VI** (UserA). v1.1.0 reduced the old main-stat grid to four Force HP/Ego checkboxes; the design question is which options and what form — per-slot checklists, dropdowns, or curated rules.

- **T12 — Consider excluding Upgrade Log MFs by set too.** The Upgraded-line top-5 already drops presets on an ATK/DEF or Element main-stat mismatch; the same argument applies to a fragment whose set isn't among those a combatant's Optimizer config selects. Open: whether an empty `sets_selected` means "any set" or "none", and whether flex slots make a non-selected set worth showing anyway.

- **T16 — Distinguish general buffs from card-only buffs.** The Average Multiplicative / Additive Buff% settings are one bucket and every formula reads them as GENERAL. In game the distinction matters: Fracture and Scorched take general buffs but not card-only ones, so a combatant whose buffs are card-only has its Fracture share overstated by exactly the buff fraction. Agony is unaffected — it takes no buffs at all. Open: whether this is one more slider pair or a split of the existing two, and whether the conditional-set `DMG multi` / `DMG add` effects are general or card-only (they currently ride the same path). See `docs/game_formulas.md` §3.4.

- **T17 — Consider folding `checkbox block -> All/None row` into `border edge -> first non-button element` at 4px.** Both describe the same shape: a block of checkboxes, and the thing immediately below it. They differ only in target — 5px against 4 — so collapsing them removes a rule and a number from the ledger for no change in kind.

  This has nothing to do with `border edge -> button`, which measures a different pair: that one runs from the PANEL's border to the button, where this runs from the checkboxes above to the button row below. A panel bottom edge can answer to one and the gap above the same buttons to the other, and both be right.

  Open: only whether 4 leaves the row looking crowded under the checkboxes. A measured window settles it.

- **T11 — Consider exposing `top_percent` in the UI.** The per-slot candidate cut is hardcoded at 20% with a 10-fragment floor, so on a filtered inventory every slot sits on the floor and the compared-combos total is fixed regardless of the other settings. Exposing it would trade run time against search breadth directly. Open: global or per-combatant, whether the floor stays, and how to stop a careless value turning a 2s run into minutes.

### Big changes

- **T7 — Named build loadouts** (UserA). Full per-character optimizer configuration snapshots (Important Settings, HAL, sets) saved under a name and switchable next to the Combatant selector. New persistence layer plus UI; interacts with the existing per-character auto-persistence.

- **T14 — Split the two large tab classes.** `OptimizerTab` and `HeroesTab` are the two largest tab classes; both `setup_ui` bodies run past 300 lines and mix layout, state wiring and event binding, so a layout change edits the same function as a behaviour change. `_build_set_config` and `_build_exclude_gear` are the cleanest first extractions — they own their state and touch little else. (Exact figures rot on every edit; count with `wc -l` and `grep -c "# spacing: "` when you need them.)

  **Costed in maintainer-side audit runs**, not in effort: roughly half the app's `# spacing:` markers live in these two files and the ledger names levers by where they sit, so a split rewrites both and can only be confirmed by measuring a live window — one run per iteration.

  **Not obviously worth doing.** Tk construction code is honestly linear; a 300-line `setup_ui` that builds 300 lines of widgets hides nothing, and splitting it into eight `_build_*` calls moves the reading problem rather than removing it. No defect found in the code audit traced to file size — the real ones were an encoding default, a swallowed exception and a duplicated helper. The shared helpers already pulled out of these files (`ui/utils/`) are the same move at a reviewable size; judge from those.

- **T15 — Scaling in 25% increments** (100 / 125 / 150 / 175 / 200). Indefinite: 200% is shipped and the fractional steps are the open part.

  **200% is the only clean multiple.** Every pixel doubles with no remainder, so a 4 and a 5 stay a 4 and a 5 doubled and nothing drifts. At 125% a 4 becomes exactly 5 while a 5 becomes 6.25 — two gaps that stood in a fixed relation stop doing so, and a distance built from parts (`label_stop + LABEL_TO_VALUE + value`) lands somewhere else than the same sum scaled once. The discipline that contains it is to scale the COMPUTED total and never each addend, across every site that has one.

  **The icons are the blocker.** 70 assets at 112x113 and 5 plates at 101x101, with no larger source in the repo. 200% doubles them by nearest neighbour, which is exact and reads as pixel art; 125% does not divide, so anything between is a resample and blurs. A fractional step needs art re-extracted at a higher resolution, if the game ships one.

  **One distance is a hard pixel count and needs looking at on a scaled screen.** `InventoryTab.SETS_PANEL_MIN_W` is 741 physical pixels, not scaled and not measured through the font, so at 200% it is half what it should be. It only binds when the Sets columns would otherwise be narrower than that, which is not the ordinary case — so the wrong behaviour may never show. The correct fix is to reserve room for the widest count a column could hold, which scales properly but makes the panel 815 wide at 100% against the 741 its contents need. Decide on a real 200% screen which matters more.

  **The audit is 100%-only** and stays that way: its targets are physical pixels, so at any other scale it would either read every gap wrong or need scaled targets that inherit the same rounding drift — in the checker. Re-verifying every registered gap per scale is a screenshot run each.

- **T18 — Reorder mode for the Checklist's shop rows.** A shop lists its products in the wire's own `sort`; the maintainer wants their own order, saved in `settings/checklist.json` beside the tracked flags. Waiting on the tab's layout being settled.

  **A `Treeview` in a reorder mode is the shape to build.** The column is one `Text` with the checkboxes embedded by `window_create`, so there are no per-row widgets to drag: a drop index means `text.index("@x,y")` and the insertion feedback would all be hand-written. A `Treeview` has real rows and a `move()` API, so the dragging is a solved problem, and swapping it in only while reordering leaves the normal view exactly as it is. Tk ships no drag-and-drop of its own and `tkdnd` is a separate binary, not worth adding for this.

  Two cheaper alternatives if the mode proves fussy: Ctrl+Up/Down on the focused row, or a ▲▼ pair at each row's right edge. Both map a click to a row index and need no drag machinery.

  **Ordering has to survive the wire.** The rows are rebuilt from `shop_res_data` every refresh, so a saved order is a lookup applied on top, and a product the game adds or removes must land somewhere sensible rather than dropping out — unranked products keep the shop's own order, after the ranked ones.

### Pondering

- What to do with the HAL gap.
- Should anything be added to the program from here:

| Where                                       | What                                                                                                                                                                                                                          |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `characters[]`                              | `friendship_exp` (exact Affinity progress, not just the level); `psychosis_exp` / `psychosis_exp_today`; and **where each copy came from** — `get_count`, `gacha_count`, `shop_count`, `limit_cube_count`, `omega_code_count` |
| `inventory.savedata`                        | 125 saved builds, 108 named, each with a `point` score (38850–85400), its equipment and its cards. Up to 11 per combatant                                                                                                     |
| `savedata_bookmark_entities`                | those builds' node layouts, 26 combatants                                                                                                                                                                                     |
| `characters.town_data`                      | happiness / population / politics / tourist, a 52-entry research-level map, the active policy and `next_policy_get_time`, plus today's 34-slot visit board                                                                    |
| `counseling_archive`                        | 25 combatants, 67 counseling entries with the story choices taken                                                                                                                                                             |
| `teams` / `team_presets` / `savedata_teams` | the live team, 6 named presets, 19 saved-build teams                                                                                                                                                                          |
| `user`                                      | `account_title_level`, account created 2025-10-23                                                                                                                                                                             |
| `card_archive`                              | 927 collected card ids                                                                                                                                                                                                        |
| `user_setting`                              | the in-game auto-disassemble rarity threshold, and the music-box state                                                                                                                                                        |
| `attendance_entities`                       | login-event progress, `current_days` vs `received_days`                                                                                                                                                                       |