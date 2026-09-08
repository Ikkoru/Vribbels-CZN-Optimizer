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

The addon keeps the schedule on `self.gacha_banners` and `_save_data` writes it to the snapshot's `gacha_banners` key. It arrives with no roster and no inventory attached, so it must survive until a save is possible rather than being written on arrival.

`_report_unknown_units` logs any banner naming a res_id absent from `KNOWN_UNIT_IDS` — the character and partner tables, injected by `_generate_addon_script` the same way `CHAR_NAMES` is. Negative placeholder keys are excluded from that set, so a unit awaiting an id still reports.

`checks/check_capture_banners.py` builds the addon through `_generate_addon_script` rather than from the template alone, so it also catches a global the template reads and the generator stops supplying.

## Three payloads are kept aside and written out later

The banner schedule is one of three that arrive in a frame carrying no roster and no inventory. `_save_data` returns early without `inventory_data`, so each is held on the addon and written by whatever save comes next:

| Attribute        | Wire key                        | Snapshot key                    | What it is                                            |
| ---------------- | ------------------------------- | ------------------------------- | ------------------------------------------------------ |
| `gacha_banners`  | `event_schedules.GACHA`         | `gacha_banners`                 | every banner, past and upcoming                       |
| `char_visits`    | `char_visits`                   | `char_visits`                   | the excursion board, one row per combatant that has been on one |
| `disaster_ranks` | `disaster_boss_rank_entities`   | `disaster_boss_rank_entities`   | Great Rift standings; the only carrier of the weekly score |

Each is replaced whole rather than merged: the reply IS the board, so a row's absence is a reading. `excursions.py` reads the second, nothing reads the third yet.

Three more join them, for what the recurring tasks stand at. The Checklist tab reads `day_point` off the first and lists the third; the pass record is captured so a snapshot taken before anything needs it already carries the history:

| Attribute | Wire key | What it is |
| --------- | -------- | ---------- |
| `point_entity` | `point_entity` | the day's and week's ACTIVITY totals — `{"day_id": 1345, "week_id": 147, "day_point": 100, "week_point": 0}`, arriving with the reply to a Daily "Claim All" |
| `season_pass` | `season_pass_entity` | the Arkhianon Supply's own record: `res_id` (`season_pass_<season>`), `grade`, `exp`, `free_reward_rank`, `pay_reward_rank` |
| `missions` | `mission_entities` | per-mission state, keyed by `res_id` |

**`mission_entities` arrives in TWO shapes under one key**, which is why it is the only one of the three that is MERGED rather than replaced. The login burst sends `content_01_01_01`-style achievement rows carrying only a `score`; a pass claim sends `pass_mission_<season>_NN` rows carrying `pass_id`, `week_id`, `issued_time` and — the useful part — **`complete_time`**. A wholesale replace keeps only whichever arrived last.

**A pass mission's id carries the SEASON**, which increments: the seven `pass_mission_008_NN` rows a claim sent are the Arkhianon Supply's daily and weekly missions, and season 9 renumbers every one of them.

`docs/missions_id_dump.py` writes `docs/missions_id.tsv` from whichever capture last carried them, for annotating by hand. It reads the newest SNAPSHOT that holds missions and falls back to the newest WebSocket debug log, because a session that claimed nothing saves none and the addon's cache does not survive one. Its rows are keyed on the id with the season replaced by `*`, so a hand-typed name survives the season turning over.

Six more join them, all merged rather than replaced for the same reason:

| Attribute | Wire key | What it is |
| --------- | -------- | ---------- |
| `shop_products` | `shop_list`, `shop_entity` | one row per shop product; `shop_list` is all of them at login and `shop_entity` is the one just bought |
| `stage_limits` | `stage_limit_entities` | per-stage run limits. `content_boss` is the Simulation Challenges |
| `month_start` / `month_end` | `month_start`, `month_end` | when the month rolls, which is 18:00 UTC on the LAST day and cannot be computed |
| `shop_definitions` | `shop_res_data` | every product's item, count, per-period cap, `limit_type`, price and display order. **This is where a shop's MAX comes from** — a `shop_list` row carries only the tally |
| `season_passes` | `season_pass_entities` | every pass the account has played, the live one among them |
| `basin_stages` / `basin_missions` | `season_entities`, `mission_seasson_entities` | the Basin of Hyperspace's stages and its objectives. The scored tally is what the game shows as its progress |
| `event_schedules` | `event_schedules` | every content's WINDOW — when each season, event and rotation opened and when it closes. **The only thing that dates any of them**, which is what the Checklist's countdowns read. See `schedules.py` |

**Two payloads arrive at the TOP LEVEL where the cache holds them nested.** `day_changeable_data` (the coffee flag, the excursion count) belongs under `characters.town_data`, and `new_char_visit` is one row of the `char_visits` board. Ordering a coffee or running an excursion sends each on its own, so without merging them the cache keeps whatever the login said and the Checklist reads a stale flag all session.

**At LOGIN the pass missions arrive somewhere else entirely**, nested as `season_pass_missions[<pass id>][<mission id>]` rather than in the flat `mission_entities` list — which is why a snapshot held the thirty `content_*` rows and none of the twenty-odd pass ones. Both shapes fold into one cache.

**`mission_entity`, singular, is the claim.** A mission's `complete_time` is set when its REWARD IS CLAIMED, not when the task is finished, and the frame that sets it sends that one row rather than the list.

**Every save prints `[SYNC] saved`, and that is what the app reloads on.** The human-readable `Saved:` line is suppressed when it would repeat the previous line word for word — and the login burst saves several times with identical counts, the first as soon as the inventory lands and the later ones carrying the shops, the schedules and the missions. A reload riding on the readable line was therefore skipped for exactly those saves, so the app sat on the first save's snapshot for the whole session. The marker is consumed by the reader and never shown, and it is deliberately not remembered as "the last line" — doing so would sit between two identical reports and stop either reading as a repeat. `checks/check_addon_template.py` holds the reader's copy of the literal equal to the addon's.

**The snapshot's temp-file replace can be refused.** Windows returns `[WinError 5] Access is denied` while another process holds the destination open — the app reading it, an indexer, an antivirus. `_save_data` retries; a save that still cannot land says so and leaves the previous snapshot intact.

**A Communication Pass is in none of them, because it is in nothing.** Spending one debits no id anywhere; the count is derived from `characters.town_data.day_changeable_data.use_town_visit_count`. `Vribbels/game_data/constants.py` holds the evidence.

## The item counts arrive once, and change through four keys

`inventory.items` and `characters.currencies` come down in the login burst and never again. Every later change to either rides on the reply to whatever caused it, in one of two shapes.

**Three keys state what a holding NOW IS** — `add_result` (a gain), `item_result` (a use), `dec_result` (a spend). One envelope between them:

```
{"items":    {"<res_id>": {"doc": {..., "res_id": 3120013, "amount": 146, ...}, "diff": 10}},
 "currency": {"<res_id>": {"doc": {..., "res_id": 2000002, "amount": 55, ...},  "diff": -100}}}
```

`doc` is the item's whole record in the shape the cache already holds, and **`doc.amount` is the TOTAL, not the change** — so `_apply_totals` writes it in rather than adding `diff`, and a frame arriving twice cannot double a count. Items are a list keyed by `res_id` and currencies a dict keyed by the same id as a string; an id not yet held is appended.

**`drop_item_result` is the exception**: a stage's rewards, as a LIST with one entry per drop and no record at all —

```
[{"id": 3120012, "amount": 2, "cur_drop_count": 1}, {"id": 3120012, "amount": 3, "cur_drop_count": 2}, ...]
```

so a x6 run sends six entries for the same item and the total is their sum. Nothing states what the holding becomes, which leaves `_apply_drops` adding — and **adding is what makes a repeat dangerous**, so the frame's `qid` is remembered and one already applied is skipped. An id the currencies already hold is a currency (Units drop this way); everything else is an item.

Without these branches nothing on the wire moves an item count: the Materials tab reads what the account had at login, no save is triggered, and no line reaches the Capture Log — a capture that has gone stale looks exactly like one where nothing has happened. `checks/check_capture_rewards.py` drives all four keys.

## The proxy's upstream must never be a loopback address

mitmdump runs in reverse-proxy mode with the game server's IP as its upstream and its own listen port as the destination port, so a loopback upstream makes the proxy its own upstream: every request is forwarded back into it, one new client connection per hop, until the log is thousands of lines of `GET https://127.0.0.1:13701/api/` and nothing has reached either the game or the snapshot.

A redirect block left in the hosts file by a run that ended without removing it produces exactly that, because `socket.gethostbyname` then answers 127.0.0.1. `start_capture` clears the block and re-resolves whenever `resolved_to_loopback()` is true, and refuses to start if it still is. The Capture tab's prerequisite probe clears a leftover block at launch, skipping that while a capture is running (when the redirect is load-bearing). `modify_hosts_file` rewrites an existing block rather than accepting it. Only the text between `HOSTS_BLOCK_START` and `HOSTS_BLOCK_END` is ever touched.

## Logging from the proxy reader thread

`capture_log_msg` is safe to call from any thread: an off-thread call marshals itself onto the UI thread and drops the line if Tk is not accepting work (see the `root.after()` rule in `ui_runtime.md`). Keep it that way when adding log callers.

`CaptureManager`'s `live_update_callback` has the same cross-thread shape and is safe only because capture cannot start before mainloop is running.

## Upgraded-line augmentation

`[LIVE] Upgraded` lines carry an internal `[pid=N]` marker so the app can find the upgraded fragment after the post-upgrade reload and append what it scores under each preset; the marker is stripped before the user sees it. A fragment with upgrades left reports a range under the label `Highest Potential`, and one with none reports a single value under `Highest GS` -- the same distinction the Memory Fragments tab's two columns make. Lines are queued (`pending_upgrade_lines`) because the fragment has to be re-read from the new snapshot first, and `_drain_pending_upgrade_lines` emits them after the reload. The fragment object is retained so a later Upgrade Log Settings toggle can re-render the line in place against a different preset selection.

Which presets reach the line is decided in `_upgrade_potentials_suffix`. Beyond the Log Presets checklist, four mismatch filters (Capture tab, on by default, stored in `settings.json`) drop presets whose combatants cannot use the fragment's MAIN stat:

- **Element** — an element DMG% main that is not the combatant's element. Combatants whose element cannot be resolved are never filtered, matching the optimizer's off-element Slot V candidacy filter.
- **ATK/DEF** — read off the combatant's ATK/DEF Split: 0-33 rejects a DEF% main, 67-100 rejects an ATK% main, the band between accepts both. Keyed on the main stat rather than the slot, so it covers ATK% in slots IV, V and VI as well as DEF% in slot VI.
- **DPS HP% / DPS Ego** — a combatant whose Shielding & Healing weight is 45 or less counts as a damage dealer and rejects an HP% main (slots IV, V, VI) or an Ego main (slot VI). Two separate filters.

**A preset survives if ANY of its selected combatants accepts the fragment** — the line lists presets, not combatants, and one preset can be assigned to combatants of different elements, scaling or roles.
