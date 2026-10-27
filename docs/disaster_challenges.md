# The Galactic Disaster tab

What is left on the live season's Challenge Mission pages. Weekly Progress is the Checklist's; the tab reads the other four: Mission Records, Chaos Investigation, Battle Report and Annihilation Reward. `Vribbels/disaster_challenges.py` turns a snapshot into the tab's reading and `Vribbels/ui/tabs/disaster_tab.py` draws it; `checks/check_disaster_challenges.py` holds the reader, the capture and the model.

## Where each fact comes from

| Fact | Source |
| ---- | ------ |
| Every achievement: its page, words, target, lock, and the achievements it rewards finishing | the client's `disaster_achievement(sNN)@disaster_achievement`, a table per season (`game_client.disaster_challenges`). `main_category` is the page; `score` and `internal` rows are not one. The two newest seasons are read, and shipped as `from_client.DISASTER_CHALLENGES` |
| A page's title | the client's text, `achievement_category_<page>` |
| When a locked achievement opens | its `schedule_link_condition_schedule_id`, a `condition_schedule` row naming a story chapter (`opt_2`), a Nebula Distortion boss or a Great Rift half (the number ending `opt_2_multiple_link`): that many days into the season's schedule by `disaster_constant_meta`'s `open_story_<n>`, `open_penalty_<n>`, `open_boss_<n>` |
| When each part starts | `unlock_disaster_shop_<n>`, the day the part's Supply round opens (`docs/client_data.md`, *A Galactic Disaster's calendar*) |
| The season, and its day 0 | the live `DISASTER_SEASON` window in `event_schedules` |
| Progress | the wire's `disaster_achievement_entities` (below) |
| A list achievement's items | its `link_disaster_achievement_info_id`: an info row naming a Chaos codex page (`chaos_collection`, its items the rows of the page type's table, `chaos_collection_<type>`, whose ids open with its `chaos_multiple_key`) or a season's own collection (`disaster_collection`, with `disaster_collection_card`). An info row's `link_extra_tag_id` keeps the relics whose own `link_extra_tag_id` carries the tag. An item's name is its `info_desc_2` text, a boss's its monster name |
| What has been found | the codex, `chaos_archive_entities`, and the seasons' collections, `disaster_collection_entities`, with a Chaos run's finds laid over them (below) |

The client lists a later part's achievements before their words: until the patch that opens the part they read `To be updated soon.`, or name a combatant that part brings. They are locked, so the tab counts them rather than writing them out.

## The wire's rows

`disaster/get_list` at login sends `disaster_achievement_entities`, `{season: {res_id: row}}`, the claimable-reward row shape (`docs/events.md`, *One shape for every claimable reward*): `score`, and `complete_time` once its reward is claimed. **A row exists only once an achievement has progress**, so a missing row is an achievement not begun. An achievement for finishing others carries no score: its row is issued when it is claimed, with `score` 0.

After the login, only two things move a row. A claim (`achievement/acquire_disaster_achievement_reward_all`) answers `achievement_entities`, the rows it claimed with their `season_id`. Progress made answers the moving reply's `mission_condition.condition.disaster_achievement`, the season as `group_id`, a row issued by the move among them. Those reports carry `complete_time` 0 whether the row is claimed or not, so one never unclaims a row. The capture folds both in (`Addon._note_challenges`); the snapshot keeps the wire's key.

## Done, waiting, locked

- **Done** is the condition met, claimed or not: a claim, or a score at its target. An achievement for finishing others is done once every one it names is.
- **A reward is waiting** where an achievement is done and not claimed. Unnamed Annihilation Reward rows count here, though not in the page's total.
- **Locked** is an achievement with a gate whose day has not come and no row on the wire. A row means it is open whatever the clock says.
- **The count** is done against every achievement on the page, locked ones and those for finishing others included. Annihilation Reward's unnamed rows (`achievement_type` `default`, its stack and score tiers) are left out of it.
- **The lines**: an open, unfinished named achievement's words, in the game's order. Then the locked ones, summed by when they open, soonest first: `N Part n achievements` for those opening with a part, `N achievements (in 2d)` for one opening inside a part (a Nebula Distortion boss's), `N locked achievements` for one the client does not date.
- **A page with nothing left** is one whose count is full. Its heading moves to the column at the right, in the game's page order.

## The lists

A list achievement's tip names each item still to find, a monster with its kills against the count the codex wants (`max_count`), and says how many open only with a later part. A hidden codex row is left out. The tip names every item not yet found: an achievement asking 90% of a list is met before the list is.

**A Chaos run states everything it has found so far** on nearly every reply inside it, entries the codex already held included: `chaos_complete_archive` (`boss_resid`, `monster_resid`, `relic_resid`, `encounter_resid`, `card_resid`, `fate_resid`) and `disaster_complete_archive` (`disaster_card_resid`), up to three levels down a reply. **Each count is that run's alone**, and the reply closing the run states none. The codex takes a finished run in whole, and sends it at the next login: an item's count there is the last login's plus every run's since, to the codex's own `max_count`. Held to the captures of 2026-10-27, the 17:28 codex plus that session's two runs gave the 20:24 codex item for item, monsters, Unidentified Areas, cards and Equipment.

So the capture keeps the open run's peak counts as `chaos_run_open`, and adds them to `chaos_run_finds`, the finished runs' sums, when the run ends: its close (`stage/clear_stage`), or the next run opening. A whole table arriving drops the finished runs of its kind, the codex the `chaos_` items and a collection the `disaster_` ones; the open run stays, the codex taking a run only at its end. An item's count is the codex's, plus both.

No captured codex or collection, and a tip says so rather than listing every item.
