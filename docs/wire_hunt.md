# The wire hunt: what the Checklist still needs, and where it might be

A worklist, not a reference. Every Checklist row that shows no value is here with the fields that could carry it, what the account read at the time, and how confident the match is. A row leaves when it is CONFIRMED and the code reads it; a suspect leaves when a capture rules it out.

`docs/wire_hunt.tsv` is what is still OPEN and `docs/wire_hunt_added.tsv` is what the program already reads — a row moves across when the code acts on it. Both are hand-maintained -- no script rewrites it, so an edit cannot be lost to a regeneration. This file says how to read it.

Columns: `Row`, `What we need`, `Read on <date>`, `Suspect`, `Confidence`, `Evidence / what would settle it`. The third holds what the account actually showed when the note was taken, which is what a later capture is diffed against.

## Confirming a field

Two ways, and only these two count:

1. **A stated value matches**, and the number is distinctive enough that a coincidence is not credible — `week_total_score` reading 1396064 against a Great Rift screen showing 1396064.
2. **An action moves it**, captured before and after — buying two B-Grade Policy Reports moved `town_shop_goods_006.total_count` from 92 to 94.

Everything else is a suspect. A field whose value happens to equal a small number the screen also showed (`1`, `5`, `100`) is a suspect however well it fits.

## The confidence column

| Value | Means |
| ----- | ----- |
| `confirmed` | matched by one of the two routes above, and the evidence is in the Evidence column |
| `strong` | the name and the shape both fit and one value matched, but the value was not distinctive |
| `weak` | the name fits and nothing has been checked |
| `ruled out` | a capture disagreed. Kept, so it is not re-suggested |

## Reading the shop rows

Settled — `Vribbels/shop_stock.py` is the canonical write-up and the code that acts on it. In short: `count` is how many were bought in the CURRENT period, `total_count` is the lifetime tally, `reset_time` is when `count` last moved, and `count` is reset lazily so a row untouched since the period rolled still carries the previous period's number.

Which prefix is which shop, all established by buying one and reading the product id off the request:

| Prefix | Shop |
| ------ | ---- |
| `town_shop_goods_*` | Nono's Shop |
| `gacha_duplicate_legend_*` | Memory Archive — Traveler |
| `hyperspace_*` | Zeronium Shop — **not** the Basin, which is `hyperspace_entities` |
| `chaos_*` | Blackhorn Trade |
| `card_factor_*` | Exchange Shop — Prism Module |
| `season_pass_*` | Season Pass shop — **not** the Seasonal Shop |
| `disaster_s0N_*` | Seasonal Shop — the Galactic Disaster's, and every id is renamed each season |

## The day index, and the week index

The wire counts days from **2022-12-31 18:00 UTC** and stamps the number on anything that happens once a day: `point_entity.day_id`, `attendance_entities`' `start_dayid` and `last_dayid`, a free gacha's `last_issued_day_id`. `Vribbels/weekly_reset.py` holds the epoch and `day_index(now)`.

18:00 UTC is the same hour the week turns on, so `RESET_HOUR` and `DAY_EPOCH` are two measurements of one boundary and correcting either means correcting both. `checks/check_day_index.py` pins them to day numbers the game itself sent.

It does the same thing a week up. Anything that resets weekly carries a `week_id` — the season pass's record, a disaster season's `week_clear_score`, `point_entity`, and the Great Rift standings under their own spelling `score_week_id`. `week_index(now)` is the number to compare it against: weeks are groups of seven day numbers ending on a multiple of seven, so week 193 ran days 1345–1351 and opened Sunday 18:00 UTC. Two routes reach that boundary — `next_reset` from the weekday, `week_index` from the day number — and the check holds them together.

**A period-stamped record is written lazily, exactly like a shop's `count`.** Nothing rolls it at the reset: the old record survives untouched into the new period and only says which period it belongs to. So the reading is the COMPARISON, not the value:

* `day_id == day_index(now)` means the thing happened today, and anything lower means today is untouched. `point_entity.day_point` can read a full 100 on a day whose real total is 20.
* `week_id == week_index(now)` likewise, and this one is worse because the figures are bigger: on the Monday after a reset the pass read a full `10000/10000`, the disaster season a full `8000/8000` and the Great Rift `300000+/300000` — three rows all saying the week's work was done in a week nothing had been done in.

A record with no stamp is read at face value. Nothing about it can say otherwise, and refusing it blanks a row that may be perfectly current.

## A weekly ALLOWANCE is topped up, not zeroed

Loot Certification Cards (`2000027`) and Reason (`2000036`) are spent weekly, and the new week ADDS to what was left rather than replacing it. Neither the allowance nor the date it was granted is stated as such, and the currency document carries no `week_id`:

* `amount` is the balance, and after a reset it is still last week's leftover;
* `last_update` is **not a write stamp, and not a gain stamp either** — an Aether exchange pays one and leaves it alone. What it has tracked, across every capture, is the moment the WEEK's allowance was applied, which is exactly what `last_weekly_reset(now)` has to be compared against;
* `add_max` and `add_charge_value` are 0, so there is no recharge metadata to compute from either.

So once the week has rolled past the record, what the record holds is a leftover and not a stock, and the stock has to be worked out from the game's rule:

| | Grant at the Sunday reset | Cap | Reads |
| --- | --- | --- | --- |
| Loot Certification Card | 4 | 4 | a reset to **4**, the grant being the cap |
| Reason | +3 | 9 | leftover **+3**, stopping at 9 |

`min(leftover + grant, cap)` covers both. **The cap is HARD** — tested in game, no amount of buying takes a holding past it — so the top-up simply stops there. 60 Aether buys one of either, which is the only thing that can move the figure between the reset and the next time the content is opened.

These are the only two numbers on the Checklist that are the game's rule rather than a reading, so what the row shows is an EXPECTATION and is marked `~4`, `~8/9` until a capture replaces it with the real figure. A different mark from the `+?` an event floor carries: that one means *at least this much*, this one means *this, unless something the snapshot cannot see has happened*. Corroboration rather than proof: `total_amount` moved by exactly +4 and +3 across each of the last four week boundaries, and `0 → 4` and `5 → 8` are what the game showed after the reset that prompted this. `total_amount` also takes one-off gains — the cards picked up a stray +1 twice — so it confirms a rate without deriving one.

**An Aether exchange does NOT date the record.** `item / recharge_item` with `recharge_id: recharge_6` spends 60 Aether and pays one Card, and the reply's own `doc` carries a `last_update` from hours earlier — so buying one cannot make the row exact. That is the right way round: `last_update` tracks the WEEK's grant and nothing else, which is exactly what the comparison needs.

The same capture confirmed the grant itself. `total_amount` went 192 → 196 across the reset (+4, the Card's whole allowance) and the balance the row had predicted as `~4` read a real 4 on the next capture.

## Pairing two payloads that never name each other

Over and over the wire describes one thing in two places under ids that do not match, and the table joining them is in the client's own data files rather than in any message. Four ways out, cheapest first. **Try them in this order** — each later one costs more and is worth less.

**1. Normalise the ids.** Where the two ids differ only in decoration, strip it and compare. An event's `event_schedule_policy_005` and its missions' `event_policy_5_*` become the same string once the word `schedule` and the zero padding are gone. Costs nothing, needs no history, and keeps working as the numbers increment. `checklist_tab._event_key` does this.

**Its failure mode is a PARTIAL match, which looks like a small answer rather than a wrong one.** `event_devil_*` leaves its index out entirely and number the DAY in that position, so the normalised key matched day one and dropped six more days — a 21-reward event reading `3/3` with nothing to see. Where a family can be counted independently, count it and compare; `docs/events.md` has the recovery.

Use it whenever the two ids share a stem. It fails silently if a rename breaks the stem, so it belongs with a case that shows on screen rather than one that only feeds a calculation.

**2. Match on the WINDOW.** Where both things are scheduled, two entries covering the same second-exact span are the same period. Every Combatant Trial event's window equals a `gacha_pickup_combatant_*` banner's, which is what says the event runs that banner's combatant — and where two banners share a window they share the trial event, which is then twice the size. `checklist_tab._trial_banners`.

Use it when the ids share nothing but both are dated. It is exact when spans match to the second; treat a near-match as no match, since an off-by-an-hour pairing is a guess.

**3. Count inside the window instead of naming.** Where the members cannot be named, count what falls inside the period. It answers "how many" without answering "which". The trap is overlap: two trial events run together for the last week of each, and a claim then falls inside both. What rescues it is that each window names a banner, so a record named for the OTHER event's combatant belongs to that one — and the rest is capped at this event's own size, since an overlap must not read as more than a full one.

Use it when 2 pairs the periods but not the members. Cap it, always: over-counting reads as finished, which is the one wrong answer a checklist must not give.

**4. Learn it from the action.** Where nothing derives, one message usually names both ids at once — a claim, a purchase, an unlock. Remember the pair when it goes past, and carry it forward. `reward_combatant_trial` names the trial event and the slot; `purchase_card_animation` names the combatant and the unlock item.

Use it last, and keep what it learns. It only sees what happens while a capture runs, so a table built this way must be seeded from the previous snapshot or it lasts one session — `capture/manager._seed_from_previous` is the pattern. Prefer it as an OVERRIDE on a derivation rather than as the only source, so a fresh install still reads something.

## Events

`docs/events.md` is the canonical write-up — the categories, how to classify one, where each kind keeps its progress, the totals the wire never states, and how to process a new event.

Two things from it are worth repeating here because they are general:

**A count of the rows an account holds is a FLOOR.** The game creates a record when it issues the task, so an event still handing them out reads as finished. That is the one wrong answer a checklist must not give, and it is why such a row prints `+?` after its total — so the reading says which kind of number it is — and goes green only on a completion flag from the game rather than on anything it can count.

**A completion FLAG beats a total.** `event_mission_reward_entities.event_achieve_state` answers "is anything left" without answering "how much was there", which turns out to be the question a checklist actually asks. Look for one of these before trying to derive a denominator.

A reading that cannot be proved complete gets a third colour. Orange, after the floor has stood at its own ceiling for 48 hours — long enough that an event still handing out rewards daily would have moved it. It needs memory, so the record lives in `settings/checklist.json`: when a row last moved is a fact about the past and a snapshot holds only the present.

## What is on the wire and what is not

A recurring confusion worth stating once. Two different things:

* **The state of a record** — claimed, scored, spent — is always on the wire, and reaches any device. `complete_time`, `count`, `received_days`, `reward_level`.
* **WHEN it reaches the wire is a third thing.** Some records have only ever been seen in the login burst, so an action taken while a capture runs changes nothing the capture saves — the reading is not wrong, it is an hour old, and on screen those look identical. `docs/events.md` lists the login-only event fields; the general rule is to merge a payload by id rather than assign it, so a partial list cannot wipe the rest.
* **A STORY episode buries its rewards two levels down**, at `result.story_reward_result.reward.{currency, items}` — and the `result` around them carries only `is_clear`, the node's id and a title level, so the shape test that keeps that overloaded key honest is what dropped them. `capture/manager._nested_reward` sweeps two levels for the shape rather than for the name, because `story_reward_result` is what a STORY calls its envelope and nothing says the next content will agree.

  **It hid behind a self-correcting symptom.** The client asks for the whole item list moments after a story, so the counts came right on their own and only the Capture Log's receipt was missing. When a log line is absent but the numbers look right, suspect a reward path rather than assuming the capture is fine.
* **A REWARD's Memory Fragments are shaped nothing like a forged one's.** Forging answers with a top-level `pieces` LIST of documents; a reward answers with a `pieces` DICT keyed by the fragment's id, each value a `{diff, doc}` pair, and always a level down — under `item_result` (a Chaos week reward) or inside `return_info` (a Simulation run, doubled or not). Beside it sits `auto_disassemble_piece`, whose `pieces` are fragments broken down on the way in: they never reach the inventory and must not be added. `capture/manager._reward_pieces`.
* **WHERE in the reply is a fourth.** A stage reply nests its whole outcome under **`return_info`**, so a handler reading only the top level sees nothing: `result_overclock_entities` rode there for a whole session while `result_reward_drop_overclock` paid out beside it. When a record does not update from an action that obviously changed it, search the reply for the key before concluding the wire is silent.
* **And a claim may answer with no record at all.** A Daily Check-in claim sends `event_id`, `received_days_before`, `received_days_after` and `completed` — numbers, not an entity. Nothing to merge; the cached row has to be patched from them.
* **The existence of a record** is not. The game issues a mission row when it issues the mission, so a total counted from the rows in hand is a FLOOR: the Basin's live season carried 15 rows of 26, and a summer event read 12 of 12 with a third wave unissued.

So a reading built from rows the account holds says "at least", and only a stated total — a completed season's row count — makes it exact.

But WHEN a row was created is itself information. `issued_time` is the second the game decided the row was relevant, so rows sharing one are one act of the game, and what such a batch varies says how the family is laid out: vary an early index and hold the last, and the same task is repeating per day, which makes the family a grid with a computable total. `docs/events.md` has the test and the six families it has been run against.

**A stamp is rewritten, not appended.** A trial slot's `complete_time` is when its reward was LAST taken, so an earlier cycle's claims cannot be recovered from it. Only the live period can be read.

A Galactic Disaster season's schedule window is three weeks longer than the event. `DISASTER_SEASON` opens 21 days before the content does, and through that preseason neither the shop nor the season's currency exists — so a season reading 84 days on the wire runs 63 (s04) or 70 (s03, whose first part ran four rotations instead of three). Both check out against the stated dates: s03 opened 2026.04.29 against a window from 2026.04.08, s04 on 2026.07.29 against 2026.07.08. The window's END is the event's end, so a countdown off it is right and only a LENGTH taken from it is not.

And nothing says which of a seasonal shop's PAGES is open. No `event_schedules` group names a shop page, and `shop_res_data` sends all three from the season's first login, so a page yet to open is indistinguishable from one on sale. What dates them is the SORTIE rotation: the rotations starting inside a Galactic Disaster season are its preseason and then one per page. The purchase record is what confirms it — `shop_list` stamps `reset_time` on every buy, and this account's first purchase on page two lands at 2026-08-19 13:14 with nine more inside ten minutes, on page three at 2026-09-09 12:26 with ten, against rotations opening 08-19 01:00 and 09-09 01:00. **A season whose parts are not one rotation long is misdated** — season three ran 28 days and then two of 21 — and what that costs is the colour of a row.

No achievement states its REWARD. The shop sends definitions — `shop_res_data`, one per product, naming the item it gives and the price — and nothing else does. Every achievement payload the login burst carries (`achievements`, `disaster_achievement_entities`, `assault_achievement_entities`, `zero_orb_achievement_entities`, `mission_accumulate`, `chapter_achieve`) is the account's own progress: an id, a score, a claim time. Searched every debug capture for the live season's currency and it appears in exactly two places — a payout already made (`drop_item`, `drop_item_info`, `confirm_drop_item`, `result_reward_drop_item`) and the shop's prices. So "how much does this content pay in total" cannot be read off the wire, and anything that needs it counts by hand: `checklist_tab.SEASON_ESTIMATE` is the one place that does.

## Identifying a mission or a shop product

`mission_condition` is the fast route. Any reply to an action that progressed a mission carries it, naming every mission touched, grouped by kind (`season_pass_mission`, `daily_achievement`, `achievement`, `accumulate_condition`, `disaster_achievement`, `event_mission`) and each with a `condition_type` — `CAFE_DRINK`, `VISIT`, `DAILY_LOGIN`, `CLEAR_INGAME_CONTENTS__ID`, `EVENT_BARTENDER_MAKE_COCKTAIL__ID`. One action names its own missions, so a single deliberate action identifies them without a diff.

**A row leaves the list when it completes**, so repeating the action and watching who drops out reads a ladder's thresholds off a payload that states none of them.

For a shop, buy one: the request carries `product_id` and the reply carries `dec_result` (what it cost) and `add_result` (what it gave), so one purchase names the product, its price and its item at once.

## The shop rows are read off the wire

`shop_res_data` carries every product's item, count, per-period cap, period, price and display order, so the Checklist builds its shop rows from the snapshot and nothing is hand-written. `Vribbels/shop_stock.py` is the write-up.

Five `limit_type` values across every shop, and which Checklist column each lands in:

| `limit_type` | Column | Count |
| ------------ | ------ | ----- |
| `LIMIT_WEEK` | Weekly | 26 |
| `LIMIT_MONTH` | Monthly | 64 |
| `LIMIT_ACCOUNT` | Other — the wire calls it a LIFETIME cap; it refreshes with a SEASON, and which season is the shop's own. The Sortie shop's is the Sortie season, the Galactic Disaster shop's is its own — four times longer | 261 |
| `NONE` | none — no cap, so nothing counts down and nothing finishes | 130 |
| `LIMIT_BENEFIT` | none yet — 6 products, unexamined | 6 |

A product whose item no table names shows its res_id, the same marking the Capture Log uses: a number on screen is an invitation to identify it, where a blank would be a bug nobody can see.

One shop, one currency. Every product on a screen the Checklist lists carries the same `price_link_item_id` — checked across every screen it lists — which is what lets a shop's heading total its bill against a single holding: `<held>/<what the ticked products still cost>`. The screens that DO mix them are the ones bought with real money or Crystals, and none of those is on the tab. Two cases read as "no total" rather than as an error: the seasonal supplies are free and carry no price item at all, and the seasonal shop keeps every season it has ever run, each in its own currency, so the live-season filter is what leaves one standing.

## A currency's lifetime total, and the account's age

A currency in `characters.currencies` keeps three figures, and the third is the one worth having:

| Field | Is |
| ----- | -- |
| `amount` | what is held now |
| `total_amount` | lifetime GAINED |
| `total_use_amount` | lifetime spent |

The three reconcile exactly — Policy Point read 36043 gained against 36020 spent with 23 in hand — and `total_amount` is monotonic: checked across 101 snapshots and five currencies, not one backward step. So the rate a currency is earned at is one subtraction between two readings of it, with nothing to model about what was spent in between. `Vribbels/checklist_manager.py` is what keeps those readings.

**Two of the seven shop currencies are not currencies.** Black Mass (3920007) and the Enrapturing Crystal (3920031) are ordinary `inventory.items` entries with an `amount` and no lifetime anything. **The shops account for them instead:** what is held, plus `shop_list[*].total_count` times each product's price, summed over every product priced in that currency.

That reconstruction was checked against the wire's own answer for the five currencies that state one — `held + bought` against `total_amount`, at every snapshot carrying both shop payloads:

| Currency | Readings | Exact | Off |
| -------- | -------- | ----- | --- |
| Policy Point | 36 | 36 | — |
| Moment of the Radiant Traveler | 36 | 36 | — |
| Zeronium | 36 | 36 | — |
| Prism Film | 36 | 36 | — |
| Crystal of Discord | 36 | 33 | 3, by up to +300 |

The three misses are all in the same direction — the derived figure HIGH — which is a capture that caught `shop_list` updated and `currencies` not yet. Black Mass derives monotonically across all 36 readings and exactly one shop prices in it, which is the Sortie shop itself.

The method needs both shop payloads. `shop_list` absent is not "nothing bought": it is the payload not having arrived, and reading the holding alone would put a total in the record that every later reading has to climb back over.

It does NOT generalise past shop-only currencies: Crystals read 228721 spent against 248000 of shop purchases, and Moment of the Radiant Hero 2175 against 675 — both are spent and earned outside the shop tables.

`characters.user` dates the account and counts its days:

| Field | Is |
| ----- | -- |
| `createAt` | account creation, epoch seconds |
| `day_id` | today, in the same day numbering `weekly_reset.day_index` produces — the two agreed exactly |
| `login_total_count` | distinct days logged in, NOT sessions |
| `login_continuous_count`, `highest_login_continuous_count` | the current and best streaks |

**`login_total_count` counts days, not logins.** It read 325 against an account age of 325.1 days, and moved +126 over 127 days across the snapshot history while several of those days carried three or four captures each. So it is an ACTIVE-DAY count: equal to the elapsed days for an account that logs in daily, and below it for one that skips.

Together those make a lifetime rate available from a single capture — `total_amount` over the days since `createAt` — which is what lets a shop heading's hover answer on the first capture rather than after a year of them.

## The monthly pass, and what it would take to show it

The Daily Coronomicon Gift is the monthly subscription's daily reward. Everything needed to show it is in **`issued_limit_entities`**, which rides the login burst beside `stage_limit_entities` and is saved into the snapshot. One row, `subscription_1`:

```json
{"res_id": "subscription_1", "issued_limit_type": 1,
 "reset_time": 1761688235, "usable_time": 1761688235,
 "expire_time": 1797962400, "count": 14, "total_count": 14,
 "vi1": 1353, "vi2": 321, "vi3": 0, "version": 625}
```

| Field | Is | How that was settled |
| ----- | -- | -------------------- |
| `reset_time`, `usable_time` | when the pass was FIRST bought | both 2025-10-28 21:50 UTC, three days into an account made 2025-10-24 |
| `expire_time` | when it runs out | 2026-12-22 18:00 UTC, on the same 18:00 boundary every daily reset uses |
| `count`, `total_count` | months bought | `expire_time - reset_time` is 419.8 days, which is **13.99 x 30** against a `count` of 14. A month of pass is 30 days |
| `vi1` | the day its gift was last CLAIMED | 1353, which was that day's `user.day_id`, and it moved on the claim |
| `vi2` | gifts claimed over the pass's life | 321 against 322 days between `reset_time` and today, so one missed day |
| `vi3` | unknown | 0 on this row |

Claiming it is `lobby / monthly_subscription_reward`, which answers with an `item_result` — 90 Crystals (2000004) on the capture — and with the row above under a name of its own: `issued_entities`, a LIST where the login sends a dict keyed by res_id. The capture folds both into the same table, so a claim moves `vi1` and `count` as it happens rather than at the next login.

So a row could read **claimed today** (`vi1` against `weekly_reset.day_index(now)`, the same lazy-stamp comparison every other daily row makes) and **days left** (`expire_time` against now — 98.9 on the capture). Nothing further needs capturing.

**Do not generalise the field meanings past `subscription_1`.** The other row in the same collection, `season_subscription_ticket_1`, carries `issued_limit_type: 4` against this one's `1`, and its span is 27.4 days for a `count` of 1 — a different product with its own arithmetic.

## `content_*`

The Basin of Hyperspace's objectives, three per stage, arriving with the reply to `hyperspace/get_list` — not story records. `mission_seasson_entities` (the game's own spelling) holds them per Basin season and `season_entities` the stages; the Checklist reads the scored tally as the Basin's progress. `missions_id_dump.py` skips the family for that reason: thirty rows nobody annotates.
