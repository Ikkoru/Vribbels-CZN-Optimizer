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
| **Not kept** | only in the debug logs | add the key to that tuple -- a login table is kept whole by one string -- and pin it in `check_capture_event_state` |

Each entry below says which. **A key that is not kept has no history**: the first snapshot to carry it is the first reading there will ever be, so a reader that wants a trend should start keeping before it starts reading.

**Other players are never kept.** `chaos_assault/get_ranking` sends twenty strangers per page with their names and profile cards, and `load/user` carries a `friend_list`. A reader takes the account's own row and the counts beside it.

## Standings

### The Sortie

**`chaos_assault_entity`** -- kept by name. Rides `event/get_list`, `chaos_assault/enter_assault`, and the run end's `chaos_assault_result`.

| Field | Is |
| ----- | -- |
| `schedule_id` | the Sortie season, `assault_1_s7` |
| `highest_clear_level` | the highest clear level ever reached |
| `schedule_highest_clear_level` | the same within this season; 0 before its first clear |
| `total_clear_count` | lifetime clears, one per finished run |

**`chaos_assault/get_ranking`** -- not kept, and sent only while the ranking screen is open, one page per request (`tab` `ongoing`, `page` 1 to `page_max`).

| Field | Is |
| ----- | -- |
| `my_rank` | the account's own row: `rank`, `score`, `record_timestamp`, the four `char_res_ids` and `assault_char_titles` of the run that set it |
| `chaos_assault_rank_entity` | the same standing as a record: `rank`, `best_score`, `best_score_record`, `best_record_timestamp`, `best_clear_time_sec`, `last_rank` |
| `total_count` | how many accounts are ranked this season -- the denominator a percentile needs |
| `max_rank`, `page_max` | how far the listed board goes: 100 places in pages of 20 |
| `reset_time` | when the season's board closes, epoch seconds |
| `rank_list` | the page of OTHER players. Never kept |

`best_score_record` is the score with seven more digits after it -- `430339747707` against a score of `43033` -- which reads as the score followed by a tie-break. Nothing has been measured about the tail.

**`chaos_assault/get_records`** -- not kept; sent when the records screen opens. One row per attempt this season, **the best one first with `is_best: true`, then every attempt newest first -- the best one again among them**. A reader that counts attempts skips the flagged row.

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

**The account's Sortie ladders** -- `assault_achievement_entities` (not kept) is the account-wide Sortie Data ladder, ids `assault_achievement_NNN`, sent with `mission/get_list` and answered row by row by the `..._reward_all` claim. It is the claimable-reward row shape (`docs/events.md`, *One shape for every claimable reward*). Whether an unfinished rung is issued is untested -- every row on hand is stamped -- so a reader takes `complete_time`, not row presence. The two per-combatant ladders ARE read, by `sortie_progress.py`. `assault_tactical_skill_node_entities` is the Tactical Authority tree, one row per node, ids `a_skill_s<season>_<tier>_a<branch>_<step>`; `chaos_assault/check_season_reset` sends it whole and `assault_tactical_skill_level_up` one node back.

### The Full-Scale Offensive

**`remnants_entity`** -- kept by name, from `event/get_list`: `define_id` (the Offensive, `remnants_boss_penalty_005`), `rank`, `reward_count`. The boards themselves are `remnants_entities`, already read by the Checklist.

**`remnants_boss_penalty/enter_remnants`** answers with the same `rank` and `reward_count` fresher, plus **`rank_percent`** -- the rank as a percentage of the field -- and the board under `entities`.

**The rank moves when the account does nothing.** Two entries six days apart read rank 386 at 0.8 and rank 441 at 0.83, with every best score on the board unchanged: others overtook it. A reader shows the rank with the date it was read. `reward_count` read 9 with nine stars held, three on each of three bosses; whether it counts stars or ranking rewards is untested.

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

Not kept. Sent with `mission/get_list`, one row per counter: `res_id` `ac_collection_<n>` and a `score` that only climbs. **These are the account's lifetime statistics** -- the collection achievements count off them -- and `ac_collection_003` equals Units' `total_amount` to the unit in every reply that carried both, 36 of them.

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

`lobby/lobby_update` sends **`login_total_count`**, not kept, which read the same as counter 033 on 2026-09-24.

### The Achievements screen

`achievements` -- not kept, from `mission/get_list` -- is the Achievements screen in the claimable-reward row shape without `issued_time`: ids `battle_*`, `collection_*`, `ingame_*`, `outgame_*`, a `score` and a `complete_time`. Claimed one at a time by `achievement/acquire_achievement_reward`, answering under `achievement_entity`. Rows claimed over rows held is the screen's completion.

### Also in `mission/get_list`, none kept

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
