# The wire hunt: what the Checklist still needs, and where it might be

A worklist, not a reference. Every Checklist row that shows no value is here with the fields that could carry it, what the account read at the time, and how confident the match is. A row leaves when it is CONFIRMED and the code reads it; a suspect leaves when a capture rules it out.

`docs/wire_hunt.tsv` is what is still OPEN and `docs/wire_hunt_added.tsv` is what the program already reads — a row moves across when the code acts on it. Both are **hand-maintained** -- no script rewrites it, so an edit cannot be lost to a regeneration. This file says how to read it.

Columns: `Row`, `What we need`, `Read on <date>`, `Suspect`, `Confidence`, `Evidence / what would settle it`. The third holds what the account actually showed when the note was taken, which is what a later capture is diffed against.

## How a field gets confirmed

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

Settled — `Vribbels/shop_stock.py` is the canonical write-up and the code that acts on it. In short: `count` is how many were bought in the CURRENT period, `total_count` is the lifetime tally, `reset_time` is when `count` last moved, and `count` is reset **lazily** so a row untouched since the period rolled still carries the previous period's number.

Which prefix is which shop, all established by buying one and reading the product id off the request:

| Prefix | Shop |
| ------ | ---- |
| `town_shop_goods_*` | Nono's Shop |
| `gacha_duplicate_legend_*` | Memory Archive — Traveler |
| `hyperspace_*` | Zeronium Shop — **not** the Basin, which is `hyperspace_entities` |
| `chaos_*` | Blackhorn Trade |
| `card_factor_*` | Exchange Shop — Prism Module |
| `season_pass_*` | Seasonal Shop |

## The day index

The wire counts days from **2022-12-31 18:00 UTC** and stamps the number on anything that happens once a day: `point_entity.day_id`, `attendance_entities`' `start_dayid` and `last_dayid`, a free gacha's `last_issued_day_id`. `Vribbels/weekly_reset.py` holds the epoch and `day_index(now)`.

18:00 UTC is the same hour the week turns on, so `RESET_HOUR` and `DAY_EPOCH` are two measurements of one boundary and correcting either means correcting both. `checks/check_day_index.py` pins them to day numbers the game itself sent.

**A day-stamped record is written lazily, exactly like a shop's `count`.** Nothing rolls it at reset: yesterday's record survives untouched into today and only says which day it belongs to. So the reading is the comparison, not the value — `day_id == day_index(now)` means the thing happened today, and anything lower means today is untouched. The numbers stored *alongside* the stamp belong to that older day too, which is how `point_entity.day_point` can read a full 100 on a day whose real total is 20.

## Pairing two payloads that never name each other

Over and over the wire describes one thing in two places under ids that do not match, and the table joining them is in the client's own data files rather than in any message. Four ways out, cheapest first. **Try them in this order** — each later one costs more and is worth less.

**1. Normalise the ids.** Where the two ids differ only in decoration, strip it and compare. An event's `event_schedule_policy_005` and its missions' `event_policy_5_*` become the same string once the word `schedule` and the zero padding are gone. Costs nothing, needs no history, and keeps working as the numbers increment. `checklist_tab._event_key` does this.

**Use it whenever the two ids share a stem.** It fails silently if a rename breaks the stem, so it belongs with a case that shows on screen rather than one that only feeds a calculation.

**2. Match on the WINDOW.** Where both things are scheduled, two entries covering the same second-exact span are the same period. Every Combatant Trial event's window equals a `gacha_pickup_combatant_*` banner's, which is what says the event runs that banner's combatant — and where two banners share a window they share the trial event, which is then twice the size. `checklist_tab._trial_banners`.

**Use it when the ids share nothing but both are dated.** It is exact when spans match to the second; treat a near-match as no match, since an off-by-an-hour pairing is a guess.

**3. Count inside the window instead of naming.** Where the members cannot be named, count what falls inside the period. It answers "how many" without answering "which". The trap is overlap: two trial events run together for the last week of each, and a claim then falls inside both. What rescues it is that each window names a banner, so a record named for the OTHER event's combatant belongs to that one — and the rest is capped at this event's own size, since an overlap must not read as more than a full one.

**Use it when 2 pairs the periods but not the members.** Cap it, always: over-counting reads as finished, which is the one wrong answer a checklist must not give.

**4. Learn it from the action.** Where nothing derives, one message usually names both ids at once — a claim, a purchase, an unlock. Remember the pair when it goes past, and carry it forward. `reward_combatant_trial` names the trial event and the slot; `purchase_card_animation` names the combatant and the unlock item.

**Use it last, and keep what it learns.** It only sees what happens while a capture runs, so a table built this way must be seeded from the previous snapshot or it lasts one session — `capture/manager._seed_trial_slots` is the pattern. Prefer it as an OVERRIDE on a derivation rather than as the only source, so a fresh install still reads something.

## Events

**`docs/events.md` is the canonical write-up** — the categories, how to classify one, where each kind keeps its progress, the totals the wire never states, and how to add an event nobody has mapped.

Two things from it are worth repeating here because they are general:

**A count of the rows an account holds is a FLOOR.** The game creates a record when it issues the task, so an event still handing them out reads as finished. That is the one wrong answer a checklist must not give, and it is why such a row never goes green.

**A reading that cannot be proved complete gets a third colour.** Orange, after the floor has stood at its own ceiling for 48 hours — long enough that an event still handing out rewards daily would have moved it. It needs memory, so the record lives in `settings/checklist.json`: when a row last moved is a fact about the past and a snapshot holds only the present.

## What is on the wire and what is not

A recurring confusion worth stating once. Two different things:

* **The state of a record** — claimed, scored, spent — is always on the wire, and reaches any device. `complete_time`, `count`, `received_days`, `reward_level`.
* **The existence of a record** is not. The game issues a mission row when it issues the mission, so a total counted from the rows in hand is a FLOOR: the Basin's live season carried 15 rows of 26, and a summer event read 12 of 12 with a third wave unissued.

So a reading built from rows the account holds says "at least", and only a stated total — `event_summer_define_entity.event_item_count`, a completed season's row count — makes it exact.

**A stamp is rewritten, not appended.** A trial slot's `complete_time` is when its reward was LAST taken, so an earlier cycle's claims cannot be recovered from it. Only the live period can be read.

## Identifying a mission or a shop product

**`mission_condition` is the fast route.** Any reply to an action that progressed a mission carries it, naming every mission touched, grouped by kind (`season_pass_mission`, `daily_achievement`, `achievement`, `accumulate_condition`, `disaster_achievement`) and each with a `condition_type` — `CAFE_DRINK`, `VISIT`, `DAILY_LOGIN`, `CLEAR_INGAME_CONTENTS__ID`. One action names its own missions, so a single deliberate action identifies them without a diff.

For a shop, buy one: the request carries `product_id` and the reply carries `dec_result` (what it cost) and `add_result` (what it gave), so one purchase names the product, its price and its item at once.

## The shop rows are read off the wire

`shop_res_data` carries every product's item, count, per-period cap, period, price and display order, so the Checklist builds its shop rows from the snapshot and nothing is hand-written. `Vribbels/shop_stock.py` is the write-up.

Five `limit_type` values across every shop, and which Checklist column each lands in:

| `limit_type` | Column | Count |
| ------------ | ------ | ----- |
| `LIMIT_WEEK` | Weekly | 26 |
| `LIMIT_MONTH` | Monthly | 64 |
| `LIMIT_ACCOUNT` | Other — a LIFETIME cap that never refreshes; the whole Sortie shop, and the Blackhorn 400 | 261 |
| `NONE` | none — no cap, so nothing counts down and nothing finishes | 130 |
| `LIMIT_BENEFIT` | none yet — 6 products, unexamined | 6 |

**A product whose item no table names shows its res_id**, the same marking the Capture Log uses: a number on screen is an invitation to identify it, where a blank would be a bug nobody can see.

## What `content_*` is

**The Basin of Hyperspace's objectives**, three per stage, arriving with the reply to `hyperspace/get_list` — not story records. `mission_seasson_entities` (the game's own spelling) holds them per Basin season and `season_entities` the stages; the Checklist reads the scored tally as the Basin's progress. `missions_id_dump.py` skips the family for that reason: thirty rows nobody annotates.

