# Capture pipeline

Read before touching `capture/`, the snapshot parser (`optimizer.GearOptimizer._parse_character_data`), or the live-update path in `czn_optimizer_gui.py`.

The chain: mitmdump intercepts the game's WebSocket traffic → the addon template embedded in `capture/manager.py` parses it and maintains `piece_items` + `characters` → `_save_data()` writes `snapshots/memory_fragments_*.json` → the optimizer reads that and builds `character_info` → the tabs render from it.

**One FRAME writes the snapshot at most once, and the frame is the unit rather than the payload.** The client batches its commands whenever it has several to send and the server answers in kind, so a frame carries a LIST of replies -- and loading into the game sends the roster, the inventory and the banner schedule that way. Every branch that changes cached data sets `_save_pending`; the single save runs after the payload loop in `websocket_message`. `_save_data` writes the whole cache whenever it runs, so a second call in one frame adds nothing but a duplicate `Saved:` line.

**`capture/manager.py` is the ONLY file in the repo with a strict ASCII requirement**: the addon is written out as a generated script, and a cp932/cp949 locale cannot encode a smart quote or an em dash into it.

## Character vs partner classification

The snapshot lumps characters AND partner cards into one list with no type field, but the game serializes the two with different schemas, and that is the reliable discriminator. Classifier: `optimizer.GearOptimizer._parse_character_data`.

|                         | Character entry                                                          | Partner entry                                   |
| ----------------------- | ------------------------------------------------------------------------ | ----------------------------------------------- |
| Distinguishing keys     | `potential_node_ids`, `friendship_exp`, `psychosis_*`, `card_animations` | `id` (instance id), `lock`                      |
| Instance id             | none                                                                     | `id`                                            |
| What `partner_id` holds | the equipped partner's INSTANCE id                                       | back-reference to the owning character's RES id |

Precedence:

1. Has `potential_node_ids` or `friendship_exp` → character.
2. Has `id` or `lock` → partner.
3. `res_id` in `CHARACTERS` → character (fallback for an entry with
   neither marker).
4. Else → partner.

**Never test whether `potential_node_ids` is non-EMPTY.** A brand-new character carries `"[]"` until its first node is unlocked; an emptiness test classifies it as a partner, and it then goes missing from every tab until an MF is equipped to it.

**Never split on res_id ranges.** Characters and partners both occupy the 1xxx and 3xxxx ranges in real snapshots.

## The `characters` key on the wire is sometimes a DELTA

The login payload carries every character and partner card. An action response (a partner re-equip, at least) carries the same key holding only the entries the server touched — the partner instance, its new owner, its old owner. `_capture_addon._merge_character_data` therefore replaces its cache only when the incoming list accounts for every entry already cached, and otherwise merges entry by entry, keyed by instance `id` for partners and `res_id` for characters.

**A wholesale replace here is silent, total data loss.** The snapshot on disk keeps its full `piece_items`, so every tab still lists the characters that have gear equipped and only the gearless ones vanish; exclusion checkmarks read as cleared because the res_id lookups go through `character_info`; and the exclude step stops excluding — with no error and no recovery short of re-capturing.

The `user` key needs the same care: it arrives with no roster attached, so it is patched into the cached payload rather than replacing it.

## One frame can carry several replies

The wire shape is `{"cmd": <domain>, "qid": n, "params": {"cmd": <action>, ...}}`, and the client sends a JSON ARRAY of those whenever it has more than one command to send. The server answers in kind: an array of reply objects, each shaped exactly like a solo reply. `websocket_message` unwraps both forms and hands each object to `_handle_server_payload`.

The login burst is the only long stretch of solo commands. Everything after the lobby arrives batched, so a handler reading only the object form sees the login and then apparently nothing — no parsing, no snapshot save, and no debug-log line either, so the capture looks like it went quiet rather than like it dropped anything.

`checks/check_capture_batching.py` drives the template with a frame of each shape.

## The gacha schedule names unreleased units

The reply to `lobby / lobby_update` carries `event_schedules.GACHA`: every banner, past and upcoming, keyed `gacha_pickup_<combatant|supporter>_<res_id>[_<rerun>]`. Those ids are server-side definitions and do not depend on what the account owns, which makes them the only res_ids a unit's owner-scoped absence cannot hide. The rerun suffix follows the res_id, so the FIRST number is the unit.

**The schedule is kept ONCE**, as the GACHA group of `event_schedules`; `_banners()` is what reads it out. A second copy under its own key is 2.8 KB of the snapshot saying the same thing twice, and every reader has to be told which one is current. It arrives with no roster and no inventory attached, so it must survive until a save is possible rather than being written on arrival.

`_report_unknown_units` logs any banner naming a res_id absent from `KNOWN_UNIT_IDS` — the character and partner tables, injected by `_generate_addon_script` the same way `CHAR_NAMES` is. Negative placeholder keys are excluded from that set, so a unit awaiting an id still reports.

`checks/check_capture_banners.py` builds the addon through `_generate_addon_script` rather than from the template alone, so it also catches a global the template reads and the generator stops supplying.

## The pull history is kept in a file of its own

`gacha/history` pages, `gacha/get_rate` replies and the pity records go to `snapshots/gacha_history/captured.json` through `_merge_gacha`, never into the snapshot. **It is the one record here a later capture cannot rebuild**: the game stops listing a pull after about half a year, so the file only ever gains, and every write goes through a checked copy that keeps the previous file as `.bak`.

The app refreshes the Stats & Gacha History tab's pull history on `GACHA_MARKER`, not `SAVE_MARKER`: a history page is no reason to reload the whole snapshot, which a `[LIVE]` line would also cost. The tab's standings sheets are the snapshot's, redrawn on every load. The file's location and name are handed to the generated addon from `gacha_history.py` rather than spelled twice. Everything else -- the wire shapes, the write, the reading -- is in `docs/gacha_history.md`.

## Payloads kept aside and written out later

The excursion board and the Great Rift standings arrive in a frame carrying no roster and no inventory, as the banner schedule does. `_save_data` returns early without `inventory_data`, so each is held on the addon and written by whatever save comes next:

| Attribute        | Wire key                        | Snapshot key                    | What it is                                            |
| ---------------- | ------------------------------- | ------------------------------- | ------------------------------------------------------ |
| `char_visits`    | `char_visits`                   | `char_visits`                   | the excursion board, one row per combatant that has been on one |
| `disaster_ranks` | `disaster_boss_rank_entities`   | `disaster_boss_rank_entities`   | Great Rift standings; the only carrier of the weekly score |

Each is replaced whole rather than merged: the reply IS the board, so a row's absence is a reading. `excursions.py` reads `char_visits`; `checklist_tab.py` reads `disaster_boss_rank_entities` for the Great Rift.

**The standings arrive whole only when the Great Rift's screen lists them** (`disaster/get_list`). Every reply about one rank -- entering it, finishing a run, claiming its weekly reward -- carries that rank's row alone, as `disaster_boss_rank_entity`, singular, and it is merged into its season and slot. Without it a run's new score waits for the next time the list is opened. The row's `week_total_score_reward` reads 0 until the week's reward is claimed and the threshold after, so a 0 there is not a target.

Three more join them, for what the recurring tasks stand at. The Checklist tab reads the Activities claim off `point_entity` and lists `mission_entities`; `season_pass` is captured so a snapshot taken before anything needs it already carries the history:

| Attribute | Wire key | What it is |
| --------- | -------- | ---------- |
| `point_entity` | `point_entity` | when the Activities reward was last claimed — `{"day_id": 1347, "week_id": 147, "day_point": 20, "week_point": 0}`. Written ONLY by the claim (`guide_system` / `point_reward`), so `day_id` is the day it happened on and `day_point` the total it was paid against. See "The day index" in `wire_hunt.md`: neither is live, and a record from an earlier day carries that day's figures |
| `season_pass` | `season_pass_entity` | the Arkhianon Supply's own record: `res_id` (`season_pass_<season>`), `grade`, `exp`, `free_reward_rank`, `pay_reward_rank` |
| `missions` | `mission_entities` | per-mission state, keyed by `res_id` |

**`mission_entities` arrives in TWO shapes under one key**, which is why it is the only one of the three that is MERGED rather than replaced. The login burst sends `content_01_01_01`-style achievement rows carrying only a `score`; a pass claim sends `pass_mission_<season>_NN` rows carrying `pass_id`, `week_id`, `issued_time` and — the useful part — **`complete_time`**. A wholesale replace keeps only whichever arrived last.

**A pass mission's id carries the SEASON**, which increments: the seven `pass_mission_008_NN` rows a claim sent are the Arkhianon Supply's daily and weekly missions, and season 9 renumbers every one of them.

`docs/missions_id_dump.py` writes `docs/missions_id.tsv` from whichever capture last carried them, for annotating by hand. It reads the newest SNAPSHOT that holds missions and falls back to the newest WebSocket debug log, because a session that claimed nothing saves none and the addon's cache does not survive one. Its rows are keyed on the id with the season replaced by `*`, so a hand-typed name survives the season turning over.

The rest join them, all merged rather than replaced for the same reason:

| Attribute | Wire key | What it is |
| --------- | -------- | ---------- |
| `shop_products` | `shop_list`, `shop_entity` | one row per shop product; `shop_list` is all of them at login and `shop_entity` is the one just bought |
| `stage_limits` | `stage_limit_entities` | per-stage run limits. `content_boss` is the Simulation Challenges |
| `month_start` / `month_end` | `month_start`, `month_end` | when the month rolls: 18:00 UTC on the last day of it. `weekly_reset.month_bounds` derives the same pair to the second, which is what a fresh install counts down to |
| `shop_definitions` | `shop_res_data` | every product's item, count, per-period cap, `limit_type`, price and display order. **This is where a shop's MAX comes from** — a `shop_list` row carries only the tally |
| `season_passes` | `season_pass_entities` | every pass the account has played, the live one among them |
| `basin_stages` / `basin_missions` | `season_entities`, `mission_seasson_entities` | the Basin of Hyperspace's stages and its objectives. The scored tally is what the game shows as its progress |
| `event_schedules` | `event_schedules` | every content's WINDOW — when each season, event and rotation opened and when it closes. **The only thing that dates any of them**, which is what the Checklist's countdowns read. See `schedules.py` |
| `disaster_seasons` | `disaster_entities` | one row per Galactic Disaster season, carrying that season's chaos progress and the difficulty cleared |
| `remnants` | `remnants_entities` | the Full-Scale Offensive's stages, each with the stars taken and its best score |
| `zero_orb` | `zero_orb_entity` | the Zero System Chaos Matrix. `reward_level` is how far up its track has been claimed, out of a hundred |
| `overclock` | `overclock_entities`, `result_overclock_entities` | an Overclock event's doubled Simulation runs, counted daily. The second name is the rows one run changed |
| `attendance` | `attendance_entities` | the login-streak events: days shown up against days claimed |
| `season_rewards` | `reward_entities`, `reward_doc` | how many of a season's star rewards have been TAKEN, one row per season and none until the first claim. `reward_doc` is the row a claim changed |
| `combat_trials` | `combat_trial_entities`, `entity` | one row per Combatant Trial slot, whose `complete_time` is when its reward was last claimed. `entity` is the row a claim changed |
| `assault_char_achievements` / `assault_char_titles` | `assault_char_achievement_entities`, `assault_char_title_entities` | the two per-combatant Sortie ladders, keyed by `res_id` (`assault_char_achieve_<char>_<rung>`, `assault_char_title_<char>_<rung>`). Read by `sortie_progress.py` for the Combatants tab's Sortie column |
| `trial_slots` | — | **learned, not received**: which slots a trial event offers, taken from the `reward_combatant_trial` request that claims one. Seeded from the previous snapshot by `_seed_from_previous`, since nothing on the wire restates it |
| `event_defines` | every `event_*_entity` and `event_*_entities` | an event's own record, kept under the key it arrives on. **Every one of them, not a list of the ones in use**: a reader for the next event is written from what captures of the last one kept, and a table nobody kept cannot be read later, since it rides the login burst and nothing else. A singular carrying a `res_id` is one ROW of its collection and is folded into it; `EVENT_FIELDS_HANDLED` keeps out the tables with a reader of their own |
| `login_tables` | `story_event_entities`, `story_event_entity`, the two `marble_*` tables, `remnants_entity`, `chaos_assault_entity` | login tables with no reader yet whose names do not say `event_`, kept whole for the same reason and listed by name beside the sweep. A story episode's claim answers with its one row, keyed by event and story, and it is folded in. `docs/unread_stats.md` says what each holds, and which other tables would be worth adding |
| `lifetime`, `lifetime_types`, `login_total_count` | `mission_accumulate`, `achievements`, `daily_achieve`, `achievement_entity`, the `mission_condition` of any reply, `login_total_count` | the lifetime counters, the Achievements screen and the daily tasks, merged by id and saved as lists. **What a counter counts** arrives only in the `mission_condition` of whatever moved it: written onto the row as `condition_type`, kept through the login that sends the row without it, and seeded from the previous snapshot |
| `rift_tops`, `sortie_rankings` | `result_list` beside a `disaster_boss_rank_entity`; `my_rank` on a ranking's first page | ranking HISTORY: each Great Rift subdivision's top row as one sample per change, and each Sortie season's own standing, field size and top score. Numbers only -- a ranking page is twenty other players, and no name, id, profile or team is kept. Seeded from the previous snapshot, because the game keeps two Sortie seasons and a division top is read once per visit to its screen |

**The town's daily block carries no date, and `town_visit_reset_time` is what dates it.** The coffee flag and the day's Communication Passes say nothing about which day they belong to, so a snapshot left open past a reset read a drunk coffee as still drunk. That field is the moment the game granted the day — lazily, at the first login after the reset — so a block stamped before the last reset is a finished day's and everything in it has come back. Where it is missing, `capture_time` stands in. This is what makes those rows right with no capture running.

**Two payloads arrive at the TOP LEVEL where the cache holds them nested.** `day_changeable_data` (the coffee flag, the excursion count) belongs under `characters.town_data`, and `new_char_visit` is one row of the `char_visits` board. Ordering a coffee or running an excursion sends each on its own, so without merging them the cache keeps whatever the login said and the Checklist reads a stale flag all session.

**At LOGIN the pass missions arrive somewhere else entirely**, nested as `season_pass_missions[<pass id>][<mission id>]` rather than in the flat `mission_entities` list — which is why a snapshot held the thirty `content_*` rows and none of the twenty-odd pass ones. Both shapes fold into one cache.

**`mission_entity`, singular, is the claim.** A mission's `complete_time` is set when its REWARD IS CLAIMED, not when the task is finished, and the frame that sets it sends that one row rather than the list.

**A Sortie rung is complete only when `complete_time` is set.** `sortie_progress.py` applies that to both ladders.

- Both ladders are sparse — nothing is sent for a rung the game has not offered — so row presence is not completion.
- An ACHIEVEMENT row is issued while its rung is still in progress. Its presence says only that the rung is live.
- A TITLE row happens to arrive only once earned, so there the two readings agree. Do not rely on it; one rule serves both.
- `score` is not a flag. It runs 1–3 on achievement rows and tracks nothing: one combatant's finished rung scores 3 and another's scores 1.
- `acquired_count` is not a flag. It reaches 3 on title rungs that count once each.
- Ladder LENGTHS are constants in `sortie_progress.py`. Unearned rungs send nothing, so the wire cannot state them, and a rung arriving past the end is the one sign the game has lengthened one.

**Every save prints `[SYNC] saved`, and that is what the app reloads on.** The human-readable `Saved:` line is suppressed when it would repeat the previous line word for word — and the login burst saves several times with identical counts, the first as soon as the inventory lands and the later ones carrying the shops, the schedules and the missions. A reload riding on the readable line was therefore skipped for exactly those saves, so the app sat on the first save's snapshot for the whole session. The marker is consumed by the reader and never shown, and it is deliberately not remembered as "the last line" — doing so would sit between two identical reports and stop either reading as a repeat. `checks/check_addon_template.py` holds the reader's copy of the literal equal to the addon's.

**The snapshot's temp-file replace can be refused.** Windows returns `[WinError 5] Access is denied` while another process holds the destination open — the app reading it, an indexer, an antivirus. `_save_data` retries; a save that still cannot land says so and leaves the previous snapshot intact.

**A Communication Pass is in none of them, because it is in nothing.** Spending one debits no id anywhere; the count is derived from `characters.town_data.day_changeable_data.use_town_visit_count`. `Vribbels/game_data/constants.py` holds the evidence.

## The item counts arrive once, and change through seven keys and a sweep

`inventory.items` and `characters.currencies` come down in the login burst and never again. Every later change to either rides on the reply to whatever caused it, in one of two shapes.

**Five keys state what a holding NOW IS** — `add_result` (a gain), `item_result` (a use), `dec_result` (a spend), `calamity_reward` (a town calamity) and `result` (an event mission claim, a story episode). One envelope between them:

```
{"items":    {"<res_id>": {"doc": {..., "res_id": 3120013, "amount": 146, ...}, "diff": 10}},
 "currency": {"<res_id>": {"doc": {..., "res_id": 2000002, "amount": 55, ...},  "diff": -100}}}
```

`doc` is the item's whole record in the shape the cache already holds, and **`doc.amount` is the TOTAL, not the change** — so `_apply_totals` writes it in rather than adding `diff`, and a frame arriving twice cannot double a count. Items are a list keyed by `res_id` and currencies a dict keyed by the same id as a string; an id not yet held is appended.

**`drop_item_result` and `chaos_free_reward_result` are the exception**: a stage's rewards and a Chaos or encounter report screen's, as a LIST with one entry per drop and no record at all —

```
[{"id": 3120012, "amount": 2, "cur_drop_count": 1}, {"id": 3120012, "amount": 3, "cur_drop_count": 2}, ...]
```

so a x6 run sends six entries for the same item and the total is their sum. Nothing states what the holding becomes, which leaves `_apply_drops` adding — and **adding is what makes a repeat dangerous**, so the frame's `qid` is remembered and one already applied is skipped. An id the currencies already hold is a currency (Units drop this way); everything else is an item.

`result` is the most OVERLOADED key on the wire — a string, a bool, a stage's step record — so it counts only where it carries a rewards payload or nests one, two levels down under an envelope of its own.

Without these branches nothing on the wire moves an item count: the Materials tab reads what the account had at login, no save is triggered, and no line reaches the Capture Log — a capture that has gone stale looks exactly like one where nothing has happened. `checks/check_capture_rewards.py` drives all seven keys.

**A key missing from the list is close to invisible.** The client asks for the inventory again after a run, so the counts still end up right; the only symptom is the Capture Log staying quiet about something the player watched arrive. `calamity_reward` and `chaos_free_reward_result` were both found by the wire catalogue rather than by reading anything.

**Three keys are payout-shaped and must NOT be applied.** `battle/reward_complete` answers with `drop_item`, a list in exactly the drop shape — and it is the RUN's running tally rather than the battle's payout: the same entries come back after every battle and grow as spots are picked up, while the counts they name stay put. One capture sent `[Units 2000, Traces of Memory 2]` four times in fifty seconds with the Units balance unchanged throughout, then carried those entries plus the spot pickups for the rest of the run. `world/get_stage_info|drop_item` and `merchant/*|drop_item_info` carry the same accumulated list. Applied, a five-battle run pays five times over. `checks/check_capture_rewards.py` holds the line.

**A run's own clear reward is NESTED, and nothing at the top level carries it.** `stage/clear_stage` answers with `return_info`, and inside it:

| Where | Pays |
| ----- | ---- |
| `return_info.result_reward_drop_item` | what finishing the run gave — items and currency together |
| `return_info.chaos_assault_result.refund_item_result` | a Sortie's entry deposit back (Aether +10) |
| `return_info.confirm_drop_item` | nothing — but it is REPORTED. The run's accumulated pickups, every one of them already paid by an envelope, so applying it doubles the run. It is also the only statement of a run as a WHOLE, where the envelopes arrive split across the frames that paid them, so `_report_run_total` writes it to the log as `Total rewards:` and changes no count. Its own line, because a Sortie's deposit refund lands in the same frame and one line holding both reads as a single receipt. Not written where it would repeat a line: every item already named by an envelope in the same reply, or exactly what the last `Received` line said -- a Simulation's drops pay the whole run before its clear restates it |

So `_nested_rewards` sweeps `return_info` by SHAPE rather than by name — the names are per-content and there is no reason the next kind of run will reuse them — and takes every totals envelope it finds, bounded and stopping as soon as it has one. **Over-collecting is safe here**: an envelope states what a holding now is, so taking one twice writes the same number. The drop LISTS in the same payload would double, which is why only envelopes are swept.

This is what a Sortie pays at its report screen, and reading only the reply's own keys is why every Sortie finished in silence. The entry itself is `chaos_assault/enter_assault` (Aether −10) and each area's reward is `chaos_assault/receive_area_reward`, which charges a Reason under `dec_result` and pays under `item_result` — both already read.

**The log's word is picked from the SIGNS, not from the key.** A Sortie's entry fee is CHARGED through `item_result`, so reading the key announces it as a receipt: `Received Aether -10`. Where every figure in a payload moved the same way that is the answer; a payload with movement both ways falls back to the key.

### A Sortie's fields nothing reads

The Sortie's standing, rankings, attempt records, score breakdowns and ladders are in `docs/unread_stats.md`, *The Sortie*, with every other stat the wire sends and nothing shows. The two per-combatant ladders are the exception — those ARE read, by `sortie_progress.py`.

**`spot_reward/assault_card_reward` is not a holding and must never be treated as one.** It is the roguelite draft a run offers between spots — `cards` is the hand offered, `result_card` the one taken, with `index` and `slot_index` saying where. Those cards exist for that run and are gone when it ends, so nothing in them survives to be counted, shown, or compared against a later capture.

## The proxy's upstream must never be a loopback address

mitmdump runs in reverse-proxy mode with the game server's IP as its upstream and its own listen port as the destination port, so a loopback upstream makes the proxy its own upstream: every request is forwarded back into it, one new client connection per hop, until the log is thousands of lines of `GET https://127.0.0.1:13701/api/` and nothing has reached either the game or the snapshot.

A redirect block left in the hosts file by a run that ended without removing it produces exactly that, because `socket.gethostbyname` then answers 127.0.0.1. `start_capture` clears the block and re-resolves whenever `resolved_to_loopback()` is true, and refuses to start if it still is. The Capture tab's prerequisite probe clears a leftover block at launch, skipping that while a capture is running (when the redirect is load-bearing). `modify_hosts_file` rewrites an existing block rather than accepting it. Only the text between `HOSTS_BLOCK_START` and `HOSTS_BLOCK_END` is ever touched.

## Logging from the proxy reader thread

**Nothing on the reader thread calls into Tk.** tkinter hands a Tk call from another thread to the UI thread and WAITS for it -- `root.after` included -- so a reader that scheduled its lines sat behind every snapshot reload, reading nothing off the proxy's pipe until the UI thread was free, and the proxy stops at its next print once that pipe fills. So `capture_log_msg`, `set_capture_status` and `set_detected_region` put an off-thread call in the Capture tab's inbox, and `live_update_callback` and the gacha callback only set flags. `OptimizerGUI._poll_capture`, every `CAPTURE_POLL_MS` on the UI thread, writes the lines out, then runs the reload if one was asked for, then writes the lines that arrived during it. Keep it that way when adding log callers; `check_tabs_build` holds a hand-off to returning while the UI thread is held.

**Only the save marker asks for a reload.** A `[LIVE]` line is printed while its reply is handled, before the save it leads to, so a reload it asked for would read the old file; and each extra ask is a whole reload on the UI thread. The flag coalesces the rest: saves that land during a reload get one more after it.

### Timing a line, under Debug WS

**A line that reaches the Capture Log late was held by the game or by the program**, and Debug WS says which. The addon puts `LAG_MARKER` and three times after every line it prints while handling a reply: when that reply's request went out (by qid, from the proxy's own message timestamp), when the reply came in, and when the line was printed. `split_lag` takes it off in the reader, first thing, so every later test of the line sees the text the addon wrote; the reader adds when it read the line, and `capture_log_msg` shows the four gaps after it in dim text -- `server`, `capture`, `pipe`, `UI`, in milliseconds. `UI` is taken on the UI thread, so the wait in the inbox is inside it, and an `Upgraded` line's includes the reload it waits for (below).

**What none of them can see is the game holding an action before it sends the request.** A late line whose four numbers are small was held there, and nothing here can shorten that. A message the server pushes unasked has no request, so it shows no `server`.

The marker exists twice, the addon's and the reader's, and `checks/check_capture_lag.py` holds them equal and drives the real addon with and without debug mode.

## A capture left running, and what a debug log costs

Both measured off the captures on disk rather than estimated.

**Two things grow with the capture, and neither bounds itself.** `saved_path` is chosen once per addon instance and rewritten on every save, so without a rotation a month of capture is one `memory_fragments_*.json` — the newest state, with no history behind it. The debug log has no ceiling at all and is flushed on every frame. What each is answered with is below.

### A debug log's size, per session

| | one login | a session with play |
| - | ---------- | -------------------- |
| total | 1.81 MB over 58 frames | 4.33 MB over 263 frames |
| `piece_items` | 490 KB (27%) | 1465 KB (33%) |
| `savedata` | 213 KB (12%) | 639 KB (14%) |
| `shop_res_data` | 278 KB (15%) | 278 KB (6%) |
| `snapshot` (battle) | — | 562 KB (13%) |

A capture averages 2.7 MB uncompressed, so a month of daily play is on the order of 80 MB — multiply rather than trusting a total, since the folder is never pruned and only grows.

### Compressing and rotating the debug log

**The log is gzipped, one MEMBER per line.** `websocket_debug_*.jsonl.gz`, still one JSON object per line — a reader opens it with `gzip.open(path, "rt", encoding="utf-8")` and changes nothing else.

A member per line rather than one stream over the file, because **a stream is readable only once its end marker is written** and an always-on capture ends by being killed. A sync-flush does not help: Python's `gzip` refuses the file outright with `EOFError`. Per line, the file is complete after every single write, and the ratio barely moves:

| | whole-file stream | member per line |
| - | ------------------ | ---------------- |
| one login | 13.2x | 12.7x |
| session with play | 12.6x | 10.7x |

**Dedup was measured and not taken.** Two logins three minutes apart were byte-for-byte identical in **1802.7 KB of 1815.9**. Only 13.2 KB differed, and half of that was the auth cookie:

  | Payload | Changed |
  | ------- | ------- |
  | `cheetah_cookie` | 6.9 KB |
  | `currencies` | 5.6 KB |
  | `user` | 0.5 KB |
  | `session`, `server_time`, `seqnum` | under 0.1 KB |

So the login burst — the bulk of every capture — is almost pure repetition between launches. Storing it content-addressed would beat gzip handily, at the cost of the one property that makes these files useful: that a two-line script can read them.

### Telling a relaunch from a reconnect

Four signals look like a new game and three of them are traps. **This game drops its connection often**, and a reconnect closes and reopens the websocket, redoes the handshake and re-sends the lobby — so `websocket_end` fires, `helo` arrives with its `qid: 1` and its device block, `lobby_update` comes back with `from_title: true`, and a fresh `session` token is issued. An evening with a few dropped connections is indistinguishable from an evening of relaunches by any of them.

**`characters.user.last_login_tm` is the marker**, because a reconnect resumes and only a login logs in. Three snapshots written across one evening of dropped connections carried it identical to the second — as they did `activated_tm` and the account payload's own `server_time` — where the launch before them differed.

| Signal | On a relaunch | On a reconnect |
| ------ | ------------- | --------------- |
| `websocket_end` | fires | **fires** |
| `helo` | sent | **sent** |
| `session` | new | **new, and again mid-session** |
| `user.last_login_tm` | moves | stays |

**So a capture rotates its snapshot on `last_login_tm` and nothing else.** The next save picks a new timestamped name and the file the last game filled is left as it was. Nothing is created until there is something to put in it, so a launch that sends nothing costs no file. The addon's CACHE is deliberately kept across the rotation: a snapshot is meant to be the whole account, and the login burst rewrites all of it anyway.

`websocket_end` still earns its keep — it drops the requests still waiting on a reply, which that connection will not answer — but it says nothing to the log and rotates nothing.

### The wire catalogue

Kept in `settings/wire_catalogue.json` — beside the settings rather than among the captures, since the snapshots folder is the one that gets emptied — and whether or not debug logging is on.

**Only on a working copy.** The `zRUN*.bat` launchers set `VRIBBELS_DEV`; a frozen exe has no way to, and without it the catalogue is off entirely: nothing recorded and nothing written, so a released build's capture is untouched by any of it. It is a switch rather than a setting because a setting would ship to everyone and want explaining, and what it guards is of no use to anybody who is not reading the wire.

**The marker has to survive the elevation.** Capture needs Administrator, so the program relaunches itself through `ShellExecuteW`'s "runas" -- which starts the new process with a FRESH environment. The elevated copy is the one that captures, and it never saw the variable, so every session that accepted the UAC prompt ran with the catalogue off. `DEV_FLAG` rides the relaunch on the command line and `_adopt_dev_flag` reads it back, **only where the program is running from source**: a frozen build ignores the flag whoever types it, so the switch is still closed by construction rather than by trust.

One entry per `command|key` seen, with a count, first and last sighting, the type and a 200-character sample:

```json
"mission/reward_event_limit|entity": {
  "count": 1, "first": "2026-09-14T22:13:07", "last": "2026-09-14T22:13:07",
  "type": "dict", "sample": "{\"res_id\": \"event_bartender_1\", ..."}
```

The command comes from the qid the reply answers, which the addon has seen go past on the request. A reply with no qid, or one whose request predates the capture, is filed under `?`.

**It is the record that makes an unread field visible.** `entity` and `issued_limit_entities` were both found this way: no amount of reading the addon would have said so — a field nobody reads leaves no trace in the code. `docs/wire_catalogue.py` prints the catalogue against the keys the addon actually asks for, deriving the second half from the source so the two cannot drift.

**The captures taken before it exists are foldable in**: `docs/wire_catalogue_backfill.py` replays a debug log through the real addon with only the clock replaced, so each sighting is filed under the frame's own timestamp. It reports by default and writes on `--write`, and it reads the uncompressed captures only — compression and the catalogue arrived together, so a `.jsonl.gz` has been catalogued already and folding it in would count one sighting twice.

It MERGES with what is on disk: counts add, the first sighting is the earlier. It must not also start from the file — that would fold the whole history into itself on every write, and one sighting would read as three.

**Qids restart at 1 with each `helo`**, which is why `_forget_pending` exists: the pending-intent maps are keyed by qid, and an intent left unanswered by a game that went away would otherwise be claimed by an unrelated reply from the next one.

### Saving reports itself only when it changes

**A save reports itself only when it would say something new** — a different file, or different counts. The suppression is keyed on those figures and not on the last line logged: any `[LIVE]` line in between, and there is one after every upgrade, delete and reward, would otherwise put the same numbers back on screen, and an evening of capture reads as that one sentence repeated.

What is left is the file being written, the numbers moving, and — loudly — a save that FAILS. The write is wrapped for that: unwrapped, an `OSError` surfaces through the frame handler's own catch as a bare `Error:` with no mention of a snapshot, in a log whose every other line is about the game.

`SAVE_MARKER` is unaffected and still goes out on every save. The app reloads on it, and the two must not share a line — see `_save_data`.

### Folding old captures into an archive

`capture/archive.py` moves superseded captures into `archived_captures.tar.xz`, beside the loose ones. `docs/snapshots_archive.py` is the same code with a report attached, for a run by hand; `--list` says what the archive holds.

**One archive, rebuilt, never appended to.** Consecutive snapshots are near-identical and that only pays inside ONE compression stream: measured over 114 real captures, a solid rebuild came to 242 KB where compressing each file alone came to 7.0 MB. Rebuild cost is proportional to the whole archive, which is what the water marks are for — a rebuild per file would pay the whole cost every time and lose the ratio as well.

**"Old" is positional, not temporal.** A file is a candidate when it is the Nth back from the newest of its own kind, so what the program reads is never in reach however long ago it was written. `KINDS` carries both marks per kind, and is the only place they are written down — snapshots and logs compact at different counts, since a log is the bigger file and nothing shipped reads an old one.

**A loose file is deleted only after its archived copy has been read back and its SHA-256 matched**, in that same pass, and `_delete` refuses anything that is not directly in the folder, not named like a capture, or not verified — `_capture_addon.py` sits in that directory. A verification mismatch is never retried: either the archive is wrong or the file changed underneath, and both want a human, so the run stops with the old archive untouched. A file that will not open, or will not delete, is left loose for the next compaction instead of failing the run.

**Logs go in decompressed.** xz cannot shrink a `.gz`, and ungzipping on the way in recovers about 85% of a log's archived size. `gzip.open` streams straight into the tar, so nothing is written to a temporary file, and the member keeps the `.jsonl` name.

## Upgraded-line augmentation

`[LIVE] Upgraded` lines carry an internal `[pid=N]` marker so the app can find the upgraded fragment after the post-upgrade reload and append what it scores under each preset; the marker is stripped before the user sees it. A fragment with upgrades left reports a range under the label `Highest Potential`, and one with none reports a single value under `Highest GS` -- the same distinction the Memory Fragments tab's two columns make. Lines are queued (`pending_upgrade_lines`) because the fragment has to be re-read from the new snapshot first, and `_drain_pending_upgrade_lines` emits them after the reload. The fragment object is retained so a later Upgrade Log Settings toggle can re-render the line in place against a different preset selection.

Which presets reach the line is decided in `_upgrade_potentials_suffix`. Beyond the Log Presets checklist, four mismatch filters (Capture tab, on by default, stored in `settings.json`) drop presets whose combatants cannot use the fragment's MAIN stat:

- **Element** — an element DMG% main that is not the combatant's element. Combatants whose element cannot be resolved are never filtered, matching the optimizer's off-element Slot V candidacy filter.
- **ATK/DEF** — read off the combatant's ATK/DEF Split: 0-33 rejects a DEF% main, 67-100 rejects an ATK% main, the band between accepts both. Keyed on the main stat rather than the slot, so it covers ATK% in slots IV, V and VI as well as DEF% in slot VI.
- **DPS HP% / DPS Ego** — a combatant whose Shielding & Healing weight is 45 or less counts as a damage dealer and rejects an HP% main (slots IV, V, VI) or an Ego main (slot VI). Two separate filters.

**A preset survives if ANY of its selected combatants accepts the fragment** — the line lists presets, not combatants, and one preset can be assigned to combatants of different elements, scaling or roles.

**A ceiling in the Mythic colour beats what the preset's combatant wears.** From `MYTHIC_FROM_LEVEL` on, `_beats_equipped` scores the fragment the combatant has in the same slot under the same preset, as the Memory Fragments tab would, and marks the preset where the new fragment's ceiling prints higher than that one's -- its Potential, where it has no upgrades left. Only for a preset assigned to exactly one combatant, and never for an empty slot: a combatant with nothing on is not in use. The capture tab's `_mark_beaten` finds the number by the preset's name ENDING its entry, so `Nine` does not take the ceiling of `Nine (Line of Justice)`.
