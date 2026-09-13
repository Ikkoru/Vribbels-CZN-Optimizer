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

## The day index, and the week index

The wire counts days from **2022-12-31 18:00 UTC** and stamps the number on anything that happens once a day: `point_entity.day_id`, `attendance_entities`' `start_dayid` and `last_dayid`, a free gacha's `last_issued_day_id`. `Vribbels/weekly_reset.py` holds the epoch and `day_index(now)`.

18:00 UTC is the same hour the week turns on, so `RESET_HOUR` and `DAY_EPOCH` are two measurements of one boundary and correcting either means correcting both. `checks/check_day_index.py` pins them to day numbers the game itself sent.

**It does the same thing a week up.** Anything that resets weekly carries a `week_id` — the season pass's record, a disaster season's `week_clear_score`, `point_entity`, and the Great Rift standings under their own spelling `score_week_id`. `week_index(now)` is the number to compare it against: weeks are groups of seven day numbers ending on a multiple of seven, so week 193 ran days 1345–1351 and opened Sunday 18:00 UTC. Two routes reach that boundary — `next_reset` from the weekday, `week_index` from the day number — and the check holds them together.

**A period-stamped record is written lazily, exactly like a shop's `count`.** Nothing rolls it at the reset: the old record survives untouched into the new period and only says which period it belongs to. So the reading is the COMPARISON, not the value:

* `day_id == day_index(now)` means the thing happened today, and anything lower means today is untouched. `point_entity.day_point` can read a full 100 on a day whose real total is 20.
* `week_id == week_index(now)` likewise, and this one is worse because the figures are bigger: on the Monday after a reset the pass read a full `10000/10000`, the disaster season a full `8000/8000` and the Great Rift `300000+/300000` — three rows all saying the week's work was done in a week nothing had been done in.

**A record with no stamp is read at face value.** Nothing about it can say otherwise, and refusing it blanks a row that may be perfectly current.

## A weekly ALLOWANCE is topped up, not zeroed

Loot Certification Cards (`2000027`) and Reason (`2000036`) are spent weekly, and the new week ADDS to what was left rather than replacing it. Neither the allowance nor the date it was granted is stated as such, and the currency document carries no `week_id`:

* `amount` is the balance, and after a reset it is still last week's leftover;
* `last_update` is **not a write stamp** — spending the currency does not move it. It does move when the currency is GAINED, which is what the week's top-up is, so it is the right thing to compare against `last_weekly_reset(now)`;
* `add_max` and `add_charge_value` are 0, so there is no recharge metadata to compute from either.

So once the week has rolled past the record, what the record holds is a leftover and not a stock, and the stock has to be worked out from the game's rule:

| | Grant at the Sunday reset | Cap | Reads |
| --- | --- | --- | --- |
| Loot Certification Card | 4 | 4 | a reset to **4**, the grant being the cap |
| Reason | +3 | 9 | leftover **+3**, stopping at 9 |

`min(leftover + grant, cap)` covers both. **The cap is HARD** — tested in game, no amount of buying takes a holding past it — so the top-up simply stops there. 60 Aether buys one of either, which is the only thing that can move the figure between the reset and the next time the content is opened.

**These are the only two numbers on the Checklist that are the game's rule rather than a reading**, so what the row shows is an EXPECTATION and is marked `~4`, `~8/9` until a capture replaces it with the real figure. A different mark from the `+?` an event floor carries: that one means *at least this much*, this one means *this, unless something the snapshot cannot see has happened*. Corroboration rather than proof: `total_amount` moved by exactly +4 and +3 across each of the last four week boundaries, and `0 → 4` and `5 → 8` are what the game showed after the reset that prompted this. `total_amount` also takes one-off gains — the cards picked up a stray +1 twice — so it confirms a rate without deriving one.

**Still open:** whether an Aether exchange moves `last_update`. If it does, one exchange makes the row exact for the rest of the week; if not, the `~` stands until the content is opened. One exchange with a capture running settles it, and it is the only way the expectation can be wrong.

## Pairing two payloads that never name each other

Over and over the wire describes one thing in two places under ids that do not match, and the table joining them is in the client's own data files rather than in any message. Four ways out, cheapest first. **Try them in this order** — each later one costs more and is worth less.

**1. Normalise the ids.** Where the two ids differ only in decoration, strip it and compare. An event's `event_schedule_policy_005` and its missions' `event_policy_5_*` become the same string once the word `schedule` and the zero padding are gone. Costs nothing, needs no history, and keeps working as the numbers increment. `checklist_tab._event_key` does this.

**Its failure mode is a PARTIAL match, which looks like a small answer rather than a wrong one.** The devil event's missions leave its index out entirely and number the DAY in that position, so the normalised key matched day one and dropped six more days — a 21-reward event reading `3/3` with nothing to see. Where a family can be counted independently, count it and compare; `docs/events.md` has the recovery.

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

**A count of the rows an account holds is a FLOOR.** The game creates a record when it issues the task, so an event still handing them out reads as finished. That is the one wrong answer a checklist must not give, and it is why such a row never goes green — and why it prints `+?` after its total, so the reading says which kind of number it is.

**A completion FLAG beats a total.** `event_mission_reward_entities.event_achieve_state` answers "is anything left" without answering "how much was there", which turns out to be the question a checklist actually asks. Look for one of these before trying to derive a denominator.

**A reading that cannot be proved complete gets a third colour.** Orange, after the floor has stood at its own ceiling for 48 hours — long enough that an event still handing out rewards daily would have moved it. It needs memory, so the record lives in `settings/checklist.json`: when a row last moved is a fact about the past and a snapshot holds only the present.

## What is on the wire and what is not

A recurring confusion worth stating once. Two different things:

* **The state of a record** — claimed, scored, spent — is always on the wire, and reaches any device. `complete_time`, `count`, `received_days`, `reward_level`.
* **WHEN it reaches the wire is a third thing.** Some records have only ever been seen in the login burst, so an action taken while a capture runs changes nothing the capture saves — the reading is not wrong, it is an hour old, and on screen those look identical. `docs/events.md` lists the login-only event fields; the general rule is to merge a payload by id rather than assign it, so a partial list cannot wipe the rest.
* **WHERE in the reply is a fourth.** A stage reply nests its whole outcome under **`return_info`**, so a handler reading only the top level sees nothing: `result_overclock_entities` rode there for a whole session while `result_reward_drop_overclock` paid out beside it. When a record does not update from an action that obviously changed it, search the reply for the key before concluding the wire is silent.
* **And a claim may answer with no record at all.** A Daily Check-in claim sends `event_id`, `received_days_before`, `received_days_after` and `completed` — numbers, not an entity. Nothing to merge; the cached row has to be patched from them.
* **The existence of a record** is not. The game issues a mission row when it issues the mission, so a total counted from the rows in hand is a FLOOR: the Basin's live season carried 15 rows of 26, and a summer event read 12 of 12 with a third wave unissued.

So a reading built from rows the account holds says "at least", and only a stated total — a completed season's row count — makes it exact.

**But WHEN a row was created is itself information.** `issued_time` is the second the game decided the row was relevant, so rows sharing one are one act of the game, and what such a batch varies says how the family is laid out: vary an early index and hold the last, and the same task is repeating per day, which makes the family a grid with a computable total. `docs/events.md` has the test and the six families it has been run against.

**A stamp is rewritten, not appended.** A trial slot's `complete_time` is when its reward was LAST taken, so an earlier cycle's claims cannot be recovered from it. Only the live period can be read.

## Identifying a mission or a shop product

**`mission_condition` is the fast route.** Any reply to an action that progressed a mission carries it, naming every mission touched, grouped by kind (`season_pass_mission`, `daily_achievement`, `achievement`, `accumulate_condition`, `disaster_achievement`, `event_mission`) and each with a `condition_type` — `CAFE_DRINK`, `VISIT`, `DAILY_LOGIN`, `CLEAR_INGAME_CONTENTS__ID`, `EVENT_BARTENDER_MAKE_COCKTAIL__ID`. One action names its own missions, so a single deliberate action identifies them without a diff.

**A row leaves the list when it completes**, so repeating the action and watching who drops out reads a ladder's thresholds off a payload that states none of them.

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

