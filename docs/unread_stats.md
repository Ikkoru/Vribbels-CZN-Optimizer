# Stats the wire sends that nothing reads

What the game sends about the account's standings, lifetime counters, collections and mini-games, written down so that a reader for any of it starts from the fields rather than from a capture. Nothing here is shown by the program yet.

**The scope is stats a player would look up**: ranks, best scores, counts, what is collected. Left out are a run's own state, battle traffic, UI settings and other players' data -- *What is left out* at the end says which commands those are and why. `python docs/wire_catalogue.py` lists every key nothing reads; this is the part of that list worth a reader.

Event progress is in `docs/events.md`, which owns everything a Checklist event row needs; this file covers the rest.

## Whether a snapshot keeps it

A reader can only work off a snapshot if the capture wrote the field into one. Three cases:

| Case | Where | What a reader needs first |
| ---- | ----- | ------------------------- |
| **Kept whole under `characters`** | the `load/user` reply, which the capture stores entire | nothing -- read `raw["characters"][<key>]` |
| **Kept by name** | the tuple beside the `event_*` sweep in `capture/manager.py`, with `story_event_entities` and the Sortie and Offensive records | nothing |
| **Kept as history** | the lifetime tables, and the Great Rift and Sortie ranking readings, carried from one snapshot to the next by `_seed_from_previous` | nothing; `check_capture_history` pins them |
| **Not kept** | only in the debug logs | add the key to that tuple -- a login table is kept whole by one string -- and pin it in `check_capture_event_state` |

Each entry below says which. **A key that is not kept has no history**: the first snapshot to carry it is the first reading there will ever be, so a reader that wants a trend should start keeping before it starts reading.

**Other players are never kept, only their numbers.** A ranking page is twenty strangers with their names, profile cards and teams, and `load/user` carries a `friend_list`. What the capture takes from a ranking page is ranks, scores and times; `check_capture_history` fails if a name, id, profile or team reaches a snapshot.

## Standings

### The Sortie

**`chaos_assault_entity`** -- kept by name. Rides `event/get_list`, `chaos_assault/enter_assault`, and the run end's `chaos_assault_result`.

| Field | Is |
| ----- | -- |
| `schedule_id` | the Sortie season, `assault_1_s7` |
| `highest_clear_level` | the highest clear level ever reached |
| `schedule_highest_clear_level` | the same within this season; 0 before its first clear |
| `total_clear_count` | lifetime clears, one per finished run |

**`chaos_assault/get_ranking`** -- the Hardcore Rankings screen, sent only while it is open, one page per request: `tab` `ongoing` for the season running, `complete` for the one before, `page` 1 to `page_max`. **The game keeps those two seasons and no others.**

| Field | Is |
| ----- | -- |
| `schedule_id` | the season the page is of: `assault_1_s7` on `ongoing`, `assault_1_s6` on `complete` |
| `my_rank` | the account's own row: `rank`, `score`, `record_timestamp`, the four `char_res_ids` and `assault_char_titles` of the run that set it. On `complete`, `rank` is the FINAL placing |
| `chaos_assault_rank_entity` | the same standing as a record: `rank`, `best_score`, `best_score_record`, `best_record_timestamp`, `best_clear_time_sec`, `last_rank`. On a finished season `last_rank` is the final placing and `rank` is wherever the record stood when last written -- 383 beside a final 1914 |
| `total_count` | how many accounts are ranked that season -- the denominator a percentile needs, stated outright here and nowhere on the Great Rift |
| `max_rank`, `page_max` | how far the listed board goes: 100 places in pages of 20 |
| `reset_time` | when the season's board closes, epoch seconds |
| `refresh_id` | the board's generation; pages read under one `refresh_id` are one state of it |
| `rank_list` | the page of OTHER players. Only rank 1's `score`, `clear_time_sec` and `penalty_level` are kept |

**Kept as history** under `chaos_assault_rankings`, one entry per season: its `reset_time`, and a reading per change of the first page -- `tab`, `total_count`, `rank`, `score`, `last_rank`, `top_score`, `top_clear_time_sec`, `top_penalty_level`, `read_at`, `refresh_id`. Carried from snapshot to snapshot, so a season the game has dropped stays in the newest snapshot.

**`best_score_record` is the score times 10**7 plus a tie-break**: `reset_time + 8189199 − record_timestamp`, so on equal scores the earlier record sorts first. It holds on all 147 rows read, over both seasons on hand.

**`chaos_assault/get_records`** -- the Sortie Logs screen; not kept; sent when it opens. One row per attempt this season, **the best one first with `is_best: true`, then every attempt newest first -- the best one again among them**. A reader that counts attempts skips the flagged row.

| Field | Is |
| ----- | -- |
| `timestamp` | when the attempt ended; also its id for `get_record_detail` |
| `score`, `is_complete` | the score and whether all areas were cleared |
| `clear_area`, `progress_floor`, `area_max_floors` | areas cleared, floors reached, and each area's floor count |
| `penalty_level`, `hardcore_flag` | the difficulty taken |
| `duration` | seconds |
| `char_res_ids`, `assault_char_titles` | the team and the titles it wore |

`chaos_assault/get_record_detail` (`timestamp`, `schedule_id`) expands one into `record_detail`: the same fields plus `penalty_ids`, `area_stage_component_ids` and `area_spot_histories` -- every spot of the run by floor, with its type and whether it was cleared.

**The run's own breakdown** -- `score_detail` in `return_info.chaos_assault_result` -- says where a score came from: `district_score`, `card_score`, `fate_score`, `equip_score`, `total_score`, `final_score`, `bonus_multiplier`, `bonus_ratio`, `score_counts`, with `clear_area` and `is_best_score` beside it.

#### The Sortie's screens, and what each is read from

| Screen, as the game names it | On the wire |
| ---------------------------- | ----------- |
| Hardcore Rankings | `get_ranking`, above |
| Sortie Logs | `get_records`, above; the screen lists the last ten |
| Engagement Data → Sortie Data | `assault_achievement_entities`, not kept, sent with `mission/get_list`: **CLAIMED rungs only**. The screen's 23 of 35 are 23 rows, every one stamped with the date the screen shows; the 12 unfinished have no row, and their ids are the gaps in the `assault_achievement_NNN` sequence. The screen's 40/50 and 40/100 are `total_clear_count` |
| Engagement Data → Combatant Data | the two per-combatant ladders, read by `sortie_progress.py` |
| Archive | `chaos_assault_archive_entities`, not kept, from `stage/get_list`: one `collection` per category, id to count. `assault_01` is Equipment, each piece counting up to 5 -- the screen's Equipment figure is the SUM, 71 pieces at 5 for 355 of 455; `assault_02` Monsters; `assault_03` Bosses, each to 3, with one boss more on the wire than on the screen; `assault_04` Cards; `assault_05` Fates |
| Tactical Optimization | `assault_tactical_skill_node_entities`, not kept, from `chaos_assault/check_season_reset`, and one node back from `assault_tactical_skill_level_up`: `a_skill_s1_*` the permanent tree, `a_skill_s2_*` the seasonal one, `level` per node. **An unlevelled node has no row** -- 16 rows for a seasonal tree of 17 |
| Tactical Data | item 3000008, the amount held. What has been earned in all is not on the wire |

None of them is a reward track for clear levels: the step record `event_chaos_assault_1` belongs to the Sortie's launch event, which `docs/events.md` covers.

### The Full-Scale Offensive

**`remnants_entity`** -- kept by name, from `event/get_list`: `define_id` (the Offensive, `remnants_boss_penalty_005`), `rank`, `reward_count`. The boards themselves are `remnants_entities`, already read by the Checklist.

**`remnants_boss_penalty/enter_remnants`** answers with the same `rank` and `reward_count` fresher, plus **`rank_percent`** -- the rank as a percentage of the field -- and the board under `entities`.

**The rank moves when the account does nothing.** Two entries six days apart read rank 386 at 0.8 and rank 441 at 0.83, with every best score on the board unchanged: others overtook it. A reader shows the rank with the date it was read. `reward_count` read 9 with nine stars held, three on each of three bosses; whether it counts stars or ranking rewards is untested.

### The Great Rift's divisions

**The account's own standing is in every snapshot already**: `disaster_boss_rank_entities`, from `disaster/get_list` at login and merged row by row from any reply about a half, per season and per half (`define_id` `disaster_s04_rank_01`, `_02`):

| Field | Is |
| ----- | -- |
| `rank`, `rank_id` | the placing, and the SUBDIVISION it falls in -- see the table below |
| `best_score`, `best_score_turn`, `best_score_record` | the best run, the turn it ended on, and the score with its tie-break |
| `week_total_score`, `week_total_score_reward`, `score_week_id` | the week's figure the Checklist reads |
| `last_rank`, `last_rank_id` | 0 and null on the half running; on a finished half a placing a little lower than `rank` in every one on hand. Which of the two the end-of-half reward is paid on is untested |

**`rank_id` names the subdivision**: `disaster_s<season>_rank_best_<half>_<N>`, N counting up from Bronze V to Master I. The account's `disaster_s04_rank_best_2_24` is Diamond II. The shares are the game's own, each the part of the field its subdivision reaches down to:

| Division | I | II | III | IV | V |
| -------- | - | -- | --- | -- | - |
| Master | 30 · 0.1% | 29 · 0.5% | 28 · 1% | 27 · 1.5% | 26 · 2% |
| Diamond | 25 · 5% | 24 · 7% | 23 · 8% | 22 · 9% | 21 · 10% |
| Platinum | 20 · 15% | 19 · 19% | 18 · 22% | 17 · 24% | 16 · 26% |
| Gold | 15 · 34% | 14 · 40% | 13 · 44% | 12 · 48% | 11 · 50% |
| Silver | 10 · 55% | 9 · 60% | 8 · 65% | 7 · 70% | 6 · 75% |
| Bronze | 5 · 80% | 4 · 85% | 3 · 90% | 2 · 95% | 1 · 100% |

The first season named them otherwise, `disaster_s01_h<half>_<n>`, on a scale of its own.

**The ranking screen asks one division at a time**:

| Command | Answers with |
| ------- | ------------ |
| `disaster/enter_disaster_rank` (`season_id`, `define_id`) | the page of the account's own division, and `disaster_boss_rank_entity` |
| `disaster/request_rank_list` (`rank_id`, `page`) | that division's page -- the screen asks for each division's I -- with `refresh_id`, the board's generation |
| `disaster/get_user_savedata` (`target_user_id`) | another player's deck. Never kept |

A page is twenty rows of one subdivision: `rank`, `score`, `damage_score`, `damage_score_team2`, `heal_score`, `shield_score`, `bonus_score`, `clear_time`, `list_level`, `turn_bonus`, `turn`, `rank_id` -- and who, which is not kept. **`score` is a record**: the best score times 10**8, plus `list_level` times 10**7, plus `1793239200 − clear_time` in season 4 -- so the board sorts on best score, then the higher list level, then the earlier clear. That holds on all 172 rows read, the account's own `disaster_rank_info` included; the constant is the season's own.

**Kept as history** under `disaster_boss_rank_tops`: per season, per half, per subdivision seen, a sample per change of its top row -- `rank`, `best_score`, `score_record`, `list_level`, `clear_time`, `turn`, `read_at`, `refresh_id`. Carried from snapshot to snapshot, so the samples are that subdivision's top over the season.

**No percentage and no field size ever arrive** -- nothing like the Sortie's `total_count`. Both follow from the division pages: a division's first rank, less one, over the share above it is the field. On 2026-09-24 Diamond started at 941 below Master's 2%, Platinum at 4704 below 10%, Gold at 12228 below 26%, Silver at 23516 below 50% and Bronze at 35273 below 75%: a field of 47,000 to 47,030 by every one of them. The account's 2474 is then 5.3% down the field, inside Diamond II's band of 5 to 7%.

### The Galactic Disaster

The Great Rift standings (`disaster_boss_rank_entities`) and the seasons (`disaster_entities`) are read by the Checklist. The rest of `disaster/get_list` is not kept:

| Field | Holds |
| ----- | ----- |
| `board_entities` | one row per season: the MEDAL screen. `info.rank_<n>` is each Great Rift half's `best_score` and `total_score`; `sticker_hash` maps every medal earned to the epoch second it was earned; `equip_total`, `spark_total`, `credit_total`, `mon_card_total`, `achievement_count`, `stage_clear_count`, `stage_enter_count`, `monster_kill_count` are season tallies, all 0 on the account's first season |
| `disaster_boss_penalty_entities` | per season, per distortion boss: `highest_clear_level`, `best_score`, and `clear_penalty`, which penalty sets each level was cleared under |
| `step1_clear_record` | the season's best Great Rift first step: `score`, `define_id`, `step1_turn`, `turn_bonus`, `heal_score` |
| `disaster_achievement_entities` | the season's challenge pages, in the claimable-reward row shape, per season. Claimed by `achievement/acquire_disaster_achievement_reward_all`, answering under `achievement_entities` |
| `disaster_collection_entities`, `disaster_chaos_entities`, `story_node_mission_disaster_entities` | what each season's Chaos stages have collected, their options, and the story track's conditions |

## Lifetime counters

### `mission_accumulate`

Kept, as history. Sent with `mission/get_list`, one row per counter: `res_id` `ac_collection_<n>` and a `score` that only climbs. **These are the account's lifetime statistics** -- the collection achievements count off them -- and `ac_collection_003` equals Units' `total_amount` to the unit in every reply that carried both, 36 of them.

**The capture writes what a counter counts onto its row**, as `condition_type`, the first time it sees the counter move, and keeps it: the login sends the rows without it, and the next capture starts from the newest snapshot's. So a snapshot's counters say what they mean as far as any capture on this install has seen them move.

**The wire names what a counter counts only when it moves**: the reply to an action that advanced one carries `mission_condition.condition.accumulate_condition`, with the counter's `condition_type`. So the meanings below are the ones captures have seen move; the rest have not moved on a capture yet.

| Counter | `condition_type` |
| ------- | ---------------- |
| 001, 008, 009, 012, 013 | `COLLECT_CHAR__TYPE_RARITY` |
| 003 | `GET_ITEM__ID` -- Units earned |
| 006 | `GACHA` |
| 014 | `CLEAR_BATTLE__SPOT_AREA` |
| 019 | `VISIT` |
| 022, 044, 045, 050, 053 | `CHAR_LEVEL_UP__TYPE_LEVEL` |
| 024 | `REINFORCE_PIECE__RARITY` -- Memory Fragment upgrades |
| 025 | `ACTIVATE_POTENTIAL_NODE` |
| 030 | `GET_SAVEDATA` |
| 031 | `DISCOMPOSE_SAVEDATA` |
| 032 | `MAKING_PIECE` -- Memory Fragments crafted |
| 033 | `LOGIN` |
| 036 | `GET_EQUIP__RARITY` |
| 037 | `SPARK` |
| 038 | `CARD_DESTINY` |
| 039 | `BUY_PRODUCT_IN_SAFETY` |
| 042 | `USE_STAMINA` |
| 046, 047, 065 | `POLICY__GRADE` |
| 048 | `REINFORCE_PIECE__RARITY_LEVEL` |
| 049 | `CLEAR_UNKNOWN` |
| 054 | `CAFE_DRINK` |
| 056 | `EAT_FOOD__ID` |
| 058 | `GIVE_GIFT__RARITY` |
| 060, 061, 062, 063 | `CLEAR_SIMULATION__ID` |
| 064 | `CLEAR_SIMULATION_PIECE` |
| 067 | `COUNSELING` |
| 069 | `CARD_RESTORATION_ANIMATION` |
| 070, 071, 072, 073 | `ENCOUNTER__RARITY` |
| 075, 077, 079 | `CLEAR_ENCOUNTER__FACTION` |
| 080, 081, 083 | `ATTACK_IN_ENCOUNTER__FACTION` |
| 086 | `DICE_ROLL_RESULT_SUCCESS` |
| 087 | `DICE_ROLL_RESULT_FAILED` |
| 088 | `CHAOS_ASSAULT_CLEAR` |
| 089, 090 | `ASSULT_KILL_MONSTER__GRADE` |
| 091 | `ASSULT_KILL_KEYWORD_MONSTER__GRADE` |

Not yet seen moving: 002, 004, 007, 011, 015, 017, 021, 023, 026, 027, 028, 043, 051, 057, 059, 066, 076, 078, 082, 084, 085. **A counter sharing a type with others splits it by a parameter the row does not carry** -- rarity, level band, faction -- so which of 070 to 073 is which rarity is readable only off the Achievements screen, whose text is client-side. Of the glosses above, 003's is measured; 024's and 032's only translate `PIECE`, which is the wire's word for a Memory Fragment. Everything else is the condition's own name and nothing more.

`lobby/lobby_update` sends **`login_total_count`**, kept, which read the same as counter 033 on 2026-09-24.

### The Achievements screen

`achievements` -- kept, from `mission/get_list` -- is the Achievements screen in the claimable-reward row shape without `issued_time`: ids `battle_*`, `collection_*`, `ingame_*`, `outgame_*`, a `score` and a `complete_time`. Claimed one at a time by `achievement/acquire_achievement_reward`, answering under `achievement_entity`. Rows claimed over rows held is the screen's completion.

### Also in `mission/get_list`

`daily_achieve` is kept; the rest are not.

| Field | Is |
| ----- | -- |
| `daily_achieve` | seven daily tasks, re-issued each day (`issued_time` today). `version` is a lifetime tally of days the task was done: the daily-login task's climbed by one a day, 192 on 2026-05-23 to 315 on 2026-09-24 |
| `chapter_achieve` | `chapter_<nn>_<nn>`, claimable-reward rows |
| `chapter_reward_entities` | per battle chapter, `count` |
| `commander_missions` | a ladder the account claimed in its first days, claimable-reward rows |
| `savedata_mission_entities`, `mission_messenger_entities`, `mission_outgame_entities`, `story_node_missions` | per-combatant `entity_<combatant>_<n>` rows, the messenger's conditions, one-off guide tasks, and the story map's node conditions |
| `event_chaos_exploration_entities` | `exploration_level` per Chaos exploration |
| `zero_orb_achievement_entities` | the Chaos Matrix's own ladder, claimable-reward rows. `complete_time` is sent as a STRING here |

## Collections and clears

| Field | Arrives with | Kept | Holds |
| ----- | ------------ | ---- | ----- |
| `simulation_entities` | `stage/get_list` | no | `clear_count` per Simulation stage (`boss_<n>_<level>`, `ego_<colour>_<level>`, ...) -- how often each has been run |
| `chaos_entities` | `stage/get_list` | no | per Chaos: `exploration_exp`, `exploration_lv_reward` and `highest_embody_level`, none of them measured against a claim |
| `chaos_archive_entities`, `chaos_assault_archive_entities` | `stage/get_list` | no | the relics each Chaos and the Sortie have shown, with a count each, and `collection_reward` |
| `hyperspace_entities` | `hyperspace/get_list` | no | `clear_count` per Basin content. The Basin's stars and rewards are read |
| `zero_orb_archive_entities`, `zero_orb_codex_entities`, `zero_orb_codex_special_entities` | `zero_orb/get_list` | no | the Chaos Matrix's archive (`complete_time` per entry), codex pieces (`lv`, `coordinate`, options) and special codex counts. `zero_orb_entity` itself is read |
| `trauma_code_entities` | `trauma_code/get_list` | no | per combatant's Trauma Code: `unlock_state`, `story_state`, and an `event_achieve_state` of its own |
| `card_archive` | `load/user` | in `characters` | every card id the account has seen |
| `counseling_archive` | `load/user`; `mentalclinic/*` answers with one combatant's | in `characters` | per combatant, each counseling and whether its reward was taken |
| `archive_gift_data`, `archive_supporters` | `load/user` | in `characters` | per combatant the gift items given and rewards received; the supporters recorded |
| `chaos_complete_archive`, `chaos_week_reward_reward_info` | `chaos_report_reward/get_chaos_reward_info` | no | a finished run's collection, and the week's Chaos report rewards as `[res_id, amount]` pairs |

## The town

`characters.town_data` (kept) carries the town's standing -- `happiness`, `population`, `politics`, `tourist` -- and `town_research_level_map`, research id to level. Its `day_changeable_data` is read by the Checklist. `characters.town_calamity` (kept) is the live calamity: `calamity_id`, `remain_day_count`, the projects it struck. **`town_calamity/enter_calamity` answers with the four standings again, and `damaged`**, and they are not the login's: in the one capture holding both, three of the four were lower and politics unchanged. Nothing keeps that reply.

## Event mini-games

What the Checklist needs from an event is in `docs/events.md`. The mini-games' own results, beside it:

| Table | Kept | Holds |
| ----- | ---- | ----- |
| `event_arena_entities` | yes, as `event_*` | per arena event: `exp` and `reward_lv`, the reward level reached |
| `event_arena_tournament_entities`, `event_arena_sub_entities` | yes | per tournament the `round` reached and the six cards slotted; the sub-stages played |
| `event_stock_entity` | yes, folded into `event_stock_entities` by its `res_id`; sent only while the event runs | `money`, `asset_history` (one figure per event day), `highest_grade_id`, `last_lobby_day_index` |
| `holding_entities`, `market_data` | no | the stock event's holdings (`quantity`, `buy_principal`) and every company's price per day |
| `event_operation_entities` | yes | per operation stage: `clear_chaos_difficulty` and the buff options taken, each with its `point` |
| `marble_achievement_entities`, `marble_mission_entities` | yes, by name | the Disaster Marble's reward ladder (claimable-reward rows) and its missions' scores, per season |
| `story_event_entities` | yes, by name | per story event, every episode's `state` (2 once watched) and `complete_time` |

## Combatants between logins

`character/level_up`, `ascend`, `activate_potential_node`, `receive_friendship_reward` and `receive_char_level_reward` each answer with the combatant's row as it now stands -- `exp`, `ascend`, `friendship_exp`, `friendship_reward_index`, `level_reward_index` -- under `char` (the Potential node) or `character` (the rest). The capture reads combatants from the login, so a combatant levelled mid-session reads its login state until the next login. A reader that wanted it current would merge these rows by `res_id` into `characters.characters`, the way missions are merged.

## What is left out

| Commands | Why |
| -------- | --- |
| `battle/*`, `nonbattle/*`, `encounter/*`, `spot_reward/*`, `merchant/*`, `safety_spot/*`, `stage/enter_spot`, `stage/on_enter_stage` | a run's own state -- the hand offered, the map, the monsters -- gone when the run ends. `docs/capture_pipeline.md` says which of their payouts ARE read |
| `chaos_assault/enter_assault`'s `stage_info`, `playing_stage_info`, `zero_system_effs`; `select_boss`'s `player` and `actions` | the same, for a Sortie run |
| `rank_list`, `friend_list`, `business_card` inside a ranking row | other players |
| `dev_msg`, `cheat_user` | debug output the server sends to every client |
| `user_setting`, `lobby_setting_data`, `my_album_entities`, `equipped_skins`, `live_broadcast`, `notice_page`, `tutorial*` | settings and UI |
| `teams`, `team_presets`, `savedata_teams`, `savedata_slot_entities`, `savedata_bookmark_entities` | loadouts rather than stats |
