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

## Where each kind of event keeps its progress

One row per kind seen so far. **The group is what decides the reader** — a new event in a known group needs no edit — and `checklist_tab.EVENT_READERS` is the table.

| Group | Where its progress lives | Reading | Exact? |
| ----- | ------------------------ | ------- | ------ |
| `EVENT_SCHEDULE`, `EVENT_NODELIST_PAGE` | `event_mission_entities`, matched by the normalised id | claimed rows / rows held | **floor** |
| `EVENT_DAILY_CHECK` | `attendance_entities`, the first row started after the event | `received_days` / 7 | exact |
| `EVENT_OVERCLOCK` | `overclock_entities[event id]` | doubled runs LEFT today | exact |
| `EVENT_COMBATANT_TRIAL` | `combat_trial_entities`, sized by the banner sharing its window | claims inside the window / 3 per banner | exact |
| the summer event | falls back to its missions | claimed rows / rows held | **floor** |

**A floor is the common case, and it never goes green.** It read three of three on the devil event's first afternoon against a real twenty-one, and twelve of twelve on the summer event with a wave unissued. A checklist that says done when it is not is worse than one that says nothing — so a floor stays red, and turns orange only once it has stopped moving. See "When nothing can prove an event is finished" below.

**The summer event resisted every derivation.** Its define's `reward_count` is the event ITEMS spent and `event_item_count` the items earned, neither of which is a reward count; the rate that converts them (eight items per reward) is not on the wire, nor is the eighty-four the last reward costs, nor any per-reward claimed flag. A rate written into the program read six of six correctly for nine rewards and would have been wrong for the tenth, which is exactly the kind of number that goes stale.

### Totals that are known and still not derivable

Read off the game's own screens, recorded here rather than in the code — **a number typed into the program is wrong the moment its event ends**, and none of these is on the wire.

| Event | Total | How it is built |
| ----- | ----- | --------------- |
| `event_schedule_devil_001` | 21 | three tasks a day, seven days. The ids are `event_devil_<day>_<task>`, and the days present already run 01–07 with a max task of 03 — so `max(day) × max(task)` gives 21 here |
| `event_bartender_01` | 24 | three reward pages of 7, 7 and 10. `max × max` gives 18 and is WRONG: the pages are ragged, and nothing in the ids says so |
| `event_summer_01` | 10 rewards, 84 items | one reward per 8 items fitted. 84 is not 10×8, so the last rewards are not evenly spaced |

The devil case shows the shape of a derivation that would work — a rectangular family's size is `max(first index) × max(second index)` — and the bartender case shows why it cannot be applied blind. **Telling a rectangular family from a ragged one is the open problem.**

### When nothing can prove an event is finished

The Checklist's third colour. A reading whose denominator is only what the game has handed out so far is marked a FLOOR: it draws red like any other unfinished row, and **turns orange once it has stood at its own ceiling for two days**. Orange says "this looks finished and nothing here can prove it".

Two days because an event that is still handing out rewards does so daily, so a tally that has not moved across two of them has either finished or stopped. Reading anything new restarts the clock, and a row BELOW its ceiling never settles however long it sits there — that is work outstanding, not an unanswerable question.

**It needs memory, which is why it lives in `settings/checklist.json`.** When a row last read something new is a fact about the past, and a snapshot holds only the present; `ChecklistManager.first_seen` is the record, and rows that leave the tab are forgotten.

### The lead worth following

The game's Events page has a **Completed Events** tab, so the client decides completion for at least some events. Either it holds the totals in its own data files — the same place the trial slot lists live — or something on the wire says so and has not been found. A capture taken while opening that tab would settle it: if it fires a request, its reply is the answer; if it fires nothing, the totals are client-side and only a stated number can supply them.

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

