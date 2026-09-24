# Events: how to read one, and what the Checklist does with it

Read this before touching the Events block of the Checklist tab, or before adding an event nobody has mapped. `wire_hunt.md` holds the general techniques for pairing wire payloads; this holds what is known about events specifically.

The code is `ui/tabs/checklist_tab.py`: `EVENT_GROUPS` says which schedule groups are listed, `EVENT_CATEGORIES` says what kinds each is (a set — see below), `event_is` asks whether a group is one of them, `EVENT_READERS` says which function reads it, and `_event_finished` is the one thing that can call an event over. `_event_roots` says which mission rows and completion records an event owns. `python docs/events_replay.py` replays every login on record through the readers, which is how a change to any of this is checked against every instalment the account has seen.

**For a new event, start at *Processing a new event*** at the end: it walks the three questions below through every shape seen so far.

## The four questions, in order

Answer them in this order for any event. Each one is cheap and rules out work on the next.

1. **When does it end?** `event_schedules` dates every event, so this always has an answer, and it alone is a useful row. An event nobody has mapped still shows its deadline.
2. **How much is done?** Usually a count of records carrying a claim stamp.
3. **Is it finished?** A separate question from 2, and often easier: the game keeps its own completion flag. See *The one place the game says an event is FINISHED*.
4. **How much is there altogether?** The hard one, and the only one that can make the row lie — see *Floors* below. Where 3 has an answer, this one stops mattering.

## The categories

**An event is usually several of these at once**, so a group's entry in `EVENT_CATEGORIES` is a SET rather than one value. An Overclock event is both Generic and Forced Daily, and the two say different things about it.

| Category | What it is | How to tell | What the row does | Colour when full |
| -------- | ---------- | ----------- | ----------------- | ---------------- |
| **Tallied** | its total is knowable | a stated total, or one derived from something dated | claimed / total | **green** |
| **Generic** | a Tallied event that comes back later largely unchanged | the same event id family has run before, with the same shape | as Tallied | **green** |
| **Forced Daily** | its rewards refresh each day of its run and are lost if not taken that day | its record carries a `reset_time` that rolls daily | counts the DAY, not the event | **orange** |
| **Open-ended** | only a floor is knowable | rows are issued as the event hands them out, so the denominator grows | claimed / rows held **+?** | red; **orange** after 48h unmoved, **green** if the game says finished |
| **Unmapped** | nothing known about its progress | no entry in `EVENT_READERS` | deadline alone | — |

Generic implies Tallied — it is a Tallied event with a second property — and `event_is` applies that so the table need not say it twice.

### The `+?` on an Open-ended row

`16/20` and `16/20+?` are different claims. The first says four left; the second says four left **that the game has handed out so far**, which may be eight. The suffix is `UNKNOWN_MORE`, and it is on every reading whose denominator was counted off the rows in hand.

It comes off in exactly one case — the game itself says the event is finished, below — and that is also the only way such a row goes green.

### A Generic event's own past is on the wire

**A Generic event's own past is on the wire, and that is better than hardcoding it.** Because it has run before, the records of every earlier run are still in the account — and what could not be derived from the live event alone can often be read off the finished ones.

The Overclock cap is the worked example. Nothing states how many doubled runs a day holds, and the game uses two shapes, six a day and two. But `overclock_entities` keeps one row per Overclock event ever played, each carrying its own `count`, so the shapes are simply there to be read: thirteen events, seven sixes and six twos. `_overclock_cap` takes the smallest shape that still fits today's count, which reads a six-shape event's third run as `3/6` where a written-down two would have clamped it to `2/2` and called a day with three runs left finished.

Two guards make that safe:

* **a shape must recur.** One row's `count` can be a day its event ended part-way through, which was never anyone's cap; a real shape shows up across events;
* **the fallback is a floor, not an answer.** `OVERCLOCK_USES` is the smaller of the two shapes, used only where an account has no history at all.

Where a number genuinely resists derivation, a Generic event is still the one place hardcoding does not go stale — the event returns with the same shape, so the number is right next time. The cost is a standing obligation to notice if the game changes it, and the Overclock cap HAS changed before.

### The two Overclock shapes in game

The shape is not arbitrary: it follows the kind of Simulation mission the event doubles, and the two kinds are different contents with different economics.

| Simulation mission | Aether per run | Multiplier | Overclock shape |
| ------------------ | -------------- | ---------- | --------------- |
| Memory Fragment | 60 | none — one run is one run | **2** a day |
| Unit, Battle Memory, Support Data, Manual, Certificate, Growth Stone | 20 × *x* | *x* = 1…6, rewards ×*x* | **6** a day |
| Challenge | — | — | not an Overclock target; the Checklist tracks these as Simulation Challenges under Weekly |

So the six is the multiplier ceiling of the missions it applies to, and the two belongs to the one kind that cannot be multiplied at all. **This makes a one-run experiment decisive**: complete a single Memory Fragment mission with a capture running. Doubled rewards mean the event is the two-shape; doubled rewards on any other type mean the six-shape.

Nothing in the login payload names the targeted mission type, so this is an action test rather than a derivation — the derivation from ended events is what ships. Keep it as the tie-break for the case the derivation cannot settle: a two and a six are indistinguishable while the day's count is still at 1 or 2.

**Measured, and the rule holds.** One Memory Fragment run (`simulation / enter_savedata_stage`, `res_id piece_10_10`, `drop_count 1`, 60 Aether) came back with its rewards under **`return_info.result_reward_drop_overclock`** — the doubled payout — while the live event was a two-shape. A Memory Fragment run IS what this shape doubles.

The same reply settled what the fields mean, which a login payload alone never could:

| | At login | After one run |
| --- | --- | --- |
| `count` | 2 (yesterday's, `reset_time` in yesterday's day) | **1** |
| `total_count` | 10 | **11** |

So `count` is today's tally, zeroed lazily at the daily reset, and `total_count` is the event's lifetime one. A run adds one to both.

**It nearly did not answer, for a reason worth keeping.** The row rides under `return_info`, not at the top level of the reply, so an earlier attempt read nothing and looked exactly like "this event does not double Memory Fragment runs". Two Memory Fragment runs on another day left the snapshot's Overclock row untouched for that reason alone.

### Forced Daily is orange, not green

Claiming everything on offer does not finish a Forced Daily event: tomorrow brings more, and today's are gone whether or not they were taken. A green row means "nothing left to think about", which would be wrong for the rest of the run — so a finished day reads orange.

This is a different orange from the Open-ended one. Nothing here is unproven; the day is genuinely complete and the category alone says so, with no 48-hour settling involved.

**On the LAST day it goes green.** Orange is a promise that the row comes back; on the final day it does not, and taking that day's runs finishes the event outright. `_last_cycle` asks the event's own window whether the day now running is the one that reaches its end. Where there is no window the answer has to be NO — a row that goes green a day early costs the user the last day's rewards, where one that stays orange costs nothing.

### A total written down, and what takes it back

Some events have no knowable total and no floor worth showing either. The launch login event is the one: `event_daily_1` hands out seven rewards in a new account's first week and then sits there for the year its schedule runs, its `received_days` stuck at 7 while `current_days` climbs past fifty. Read as a streak, the row says a reward is waiting that nobody can claim; read as a floor, it says nothing at all.

So the total is written down -- `WRITTEN_TOTALS` in `checklist_tab.py`, keyed by normalised event key -- and the event reads as Tallied against it.

**Written down so the wire can take it back.** A reward past the number disproves it: `written_total` answers None from then on and the row goes straight back to reading the way its group reads, floor and all. A number typed into the program is only ever a claim about what the wire has not said yet, and this is the shape that lets one be wrong safely. Without the falsifier an eighth claimed day would read `8/7` in green.

The same applies to a mission-tallied event: the write-down holds while the rows in hand have not gone past it.

### Members so far

| Group | Categories | Where its progress lives | Notes |
| ----- | ---------- | ------------------------ | ----- |
| `EVENT_OVERCLOCK` | Generic, Forced Daily | `overclock_entities[event id]` | doubled Simulation runs. `count` is today's tally, `total_count` the event's lifetime one, `reset_time` when the day's was last written. The cap is not stated; `_overclock_cap` reads it off the ended events' own counts |
| `EVENT_DAILY_CHECK` | Tallied | `attendance_entities` | a login streak. The attendance row is the FIRST one started after the event was — the ids do not match |
| `EVENT_COMBATANT_TRIAL` | Tallied, Generic | `combat_trial_entities` | three trials per combatant banner sharing the event's window |
| `EVENT_SCHEDULE` | Open-ended | `event_mission_entities`, plus `event_mission_reward_entities` for the completion flag | the catch-all: story events, seasonal events, `event_bartender_1`. A step-track event (below) reads its completion record instead |
| `EVENT_NODELIST_PAGE` | Open-ended | same two | the missions are named after the combatant, not the list: paired by issue time, see *A Node List shares no word with its missions* |

## Knowing an event: three questions, and what can answer each

A Checklist row about an event is three separate claims, and they have different evidence behind them.

| | The question | How well it can be answered |
| - | ------------ | -------------------------- |
| 1 | How many rewards have been CLAIMED? | **Exactly, always.** `complete_time` on a mission row means its reward was taken; an event with no mission rows keeps its own table (a streak's `received_days`, a trial's slots); a step-track event counts its claims on its completion record, see *Step tracks* |
| 2 | How many does the event HOLD? | The hard one. Seven sources, below |
| 3 | Is it FINISHED? | Definite for a few, derived for some, a judgement for the rest |

### The sources for a total, strongest first

| Source | What it needs | What it gives | How it fails | Where |
| ------ | ------------- | ------------- | ------------ | ----- |
| **The completion flag** | the event's final reward claimed | not a total, but it ends question 3 outright | most events never set one; it exists only where a final reward unlocks after all the others | `_event_finished`, `event_achieve_state` |
| **A rectangular family** | one snapshot, once a batch spans an axis | the whole event, exactly | the family is ragged, and most are | `_grid_total` |
| **Pages issued whole** | one snapshot | an exact count for that page | a page not yet issued at all is invisible | `_page_totals` |
| **A per-unit census** | the event's own table, and one rule per family | an exact count for a page that trickles | the table is not captured, or the rule is wrong | **designed, not built** — below |
| **A finished past instalment** | two instalments of the family agreeing -- their rows, or a step track's steps | the whole event | the family turns out not to repeat itself | `ChecklistManager.event_total`, `_instalment_size` |
| **A write-down** | a person deciding | the whole event | it is wrong until a reward past it proves so | `WRITTEN_TOTALS`, `written_total` |
| **The floor** | nothing | a lower bound, always | it is only ever a lower bound | `_event_progress` |

**They stack, and they cross-check.** `_event_progress` tries them in that order and takes the first that answers. Where two would answer and disagree, the weaker one is wrong: an instalment's history is the PAST and rows in hand are the present, so rows win; a write-down loses to any reward past it. A disagreement is worth noticing rather than smoothing over — it means a rule has broken, and the honest fallback is the floor.

**A final reward is added to whichever of them answers**, once it is known to exist: it is one more reward than the rows, not a total of its own. See *A final reward the wire has not mentioned yet*.

**One instalment is one vote**, however many schedules name it: `event_schedule_arena_2` and `event_arena_2` are the same arena, and `event_total` counts them once (its `same` argument, `_event_key` from the tab).

### A reward has a SOURCE, and sources can be counted

This is the layer that would close most of what is left, and it is not built.

**A page is a kind of source.** The bartender's three pages are one reward per day of the event, a ladder over guestbook entries, and ten cocktails to make. So an event's total is a sum over its pages, and each page is one of three shapes:

| Page shape | Total | Read from |
| ---------- | ----- | --------- |
| a ladder over a counter | its own row count | already exact: ladders arrive whole |
| one reward per unit of content | units x rewards-per-unit | the event's own table, counted |
| a fixed set (ten cocktails) | the size of the set | nothing states it yet |

The census is the middle row: **how many units of content the event has** -- which only a table ISSUED WHOLE could say. **None seen so far is.** `event_bartender_entities` looked like one, a row per day, and is not: it held no rows on the event's first afternoon and gained one as each day's Last Call was made, seven by the time day seven was played (see *The bartender keeps its own per-day record*). A table that grows as the player plays is a floor in the same way the mission rows are. Those tables are captured, every `event_*` one of them, because they arrive in the login burst and nowhere else -- so the next event's can be checked the day it opens: count the table's rows on the first login and again a day later.

What a family would need, then, is not a number but a RULE: `{page prefix: (which table counts its units, rewards per unit)}`. A rule survives what a number cannot — the next instalment running ten days instead of seven recomputes itself, where a written-down 24 would simply be wrong. And it is falsifiable the same way a write-down is: a page that grows past its census-derived total has disproved the rule, and the row goes back to the floor.

**Worked example, `event_bartender_1`.** 7 days x 1 + 7 (ladder, whole) + 10 (cocktails) = 24 mission rewards, plus one final reward that is not a mission row at all — the one that sets the completion flag. 25 in total. The ladder's 7 is derivable on day one; the days and the cocktails were not, on anything the wire sent, and the 7 x 1 was read off the game's own screen.

### Answering question 3

| Answer | When | What the tab shows |
| ------ | ---- | ------------------ |
| **Finished** | the completion flag is set | green |
| **A final reward waiting** | every row claimed, no flag, and the family has paid a final reward before | red (`FINAL_WAITING`), counting the final in the total, and asking `Finished?` for the instalment that turns out not to have one |
| **Finished** | every page whole or resolved, and claimed equals the total, and the event pays nothing outside its mission rows | not claimed yet: nothing states the last condition, which is why this case is still orange |
| **Said so by the user** | the row's `Finished?` box is ticked | green, and sorted down with the rest. The answer is kept against the pair it was given for: either figure moving retires it |
| **Likely finished** | claimed equals the floor and the tally has not moved for two days | orange — see `FLOOR_SETTLES_AFTER` |
| **Unknown** | anything else | red, with `+?` where the denominator is a floor |

**Nothing on the wire closes the gap between the second row and the fourth.** What would is a statement that an event's rewards are all mission rows, which nothing makes and which `event_bartender_1` and `event_summer_01` are both counter-examples to. So the tab asks instead: a row at an unproven ceiling carries a `Finished?` checkbox, and the person who can see the game answers it. That answer is evidence of a different kind from the rest of this page -- it is not checkable, so it is held to the reading it was given for and retired the moment that reading moves.

### What the game's own screens say, and what the program derives

The maintainer read every live event's totals off the game and reported them. This is the only ground truth there is -- nothing on the wire states a total -- so it is what every derivation above is checked against.

| Event, as the game names it | The game says | The program derives | |
| --------------------------- | ------------- | ------------------- | - |
| SE-4 BR33ZE (bartender) | 7 + 7 + 10 rewards, plus Special Reward 1/1 | 24 mission rows and the Special Reward: 25/25, green on the completion flag | agrees |
| Olga's Secret Diary (devil) | 21 | the grid: 7 days x 3 tasks | agrees |
| Beach Cafe Festival (summer) | 20 mission rewards, **plus 10 puzzle and 15 story** | 20 mission rows | agrees on the rows; 25 of its rewards are not rows at all |
| Rei's Gift (`event_daily_16`) | 7, one per login day | claimed against claimed-plus-one | floor, as designed |
| Virtual Tactical Simulation | 3, one per banner combatant | 3 | agrees |
| Basin of Hyperspace | 26 stars | 26/26 | agrees |
| Full-Scale Offensive | 9 stars | 9/9 | agrees |
| Zero System (Chaos Matrix) | 100 rewards | 100/100 | agrees |
| Galactic Disaster, weekly chaos | 8000 | 8000/8000 | agrees |
| Great Rift score | 300000 | 0/300000 | agrees |
| Event Node List (past instalments) | 25 | the grid: 5 x 5, once its last index is issued; 26 with the final reward its completion record says was claimed | agrees on the 25. Whether the game's 25 already counts that reward is open -- see *Still open* |

**Two events pay outside their mission rows**, which is what stops "every row claimed" from meaning "finished": `event_bartender_1`'s Special Reward, and `event_summer_01`'s 10 puzzle rewards and 15 story rewards. Both are counted on their own screens and neither is a mission row. The tab counts the Special Reward once it knows the event has one (*A final reward the wire has not mentioned yet*); the summer's puzzles and stories are in tables nothing reads yet (`event_summer_define_entity`, `story_event_entities`).

**A named login-streak event has one length.** Rei's Gift is seven rewards every time it runs; the 10-, 14- and 21-day rows in `attendance_entities` belong to other events sharing that table, not to longer instalments of one event. What still cannot be done is telling which event a row belongs to before it ends, which is why the row counts claimed against claimed-plus-one — floored at seven, the shortest any of them has finished at. **Nor does the schedule's LENGTH predict it**: `event_daily_15` and `event_daily_holiday_01` both run 21.0 days and paid 7 and 15. Counting from what is claimed alone read `1/1+?` on a new event's first day, which says finished; `Golden Autumn's Invitation` was the one that showed it, at 15 rewards. `checklist_tab.ATTENDANCE_FLOOR`.

**The Galactic Disaster is not one event but a season of them** -- three parts of 21 days, each with a supply store, a medal screen, five pages of challenge missions, a story track, three distortion bosses and a Great Rift half. The Checklist gives it a column of its own, holding the season-long shop and a deadline; the weekly chaos progress and the seasonal score are rows in `Weekly`. The medal screen, the challenge pages and the story track are read by nothing, and each needs its own screen enumerating.

## Floors, and the one wrong answer

**A count of the rows the account holds is a FLOOR, not a total.** The game creates a mission row when it issues the mission, so an event still handing them out reads as finished:

* a summer event read `12/12` with a third wave unissued;
* `event_devil_*` read `3/3` against a real 21 — though that one turned out to be an id collision rather than a floor, and is worth reading about under *Naming* before assuming a short count is this.

So an Open-ended row is marked `FLOOR` in the code and prints `+?` after its total. Saying "done" when it is not is the one answer a checklist must never give: it costs the user the reward. **The only thing that turns such a row green is the game's own completion flag** — see below; nothing the row can count about itself will do it.

After 48 hours at its own ceiling a floor turns **orange** — long enough that an event still handing out rewards daily would have moved it. Reading anything new restarts that clock, and a row below its ceiling never settles, because that is work outstanding rather than an unanswerable question. The record lives in `settings/checklist.json`; when a row last moved is a fact about the past and a snapshot holds only the present.

## The one place the game says an event is FINISHED

**`event_mission_reward_entities`.** One row per event the account has a completion record for, and the row is the answer a floor can never give:

| Field | Is |
| ----- | --- |
| `res_id` | the event's MISSION DEFINE id — `event_bartender_1`, not the schedule's `event_bartender_01` — so it goes through `_event_key` like everything else here. A Node List's can sit one page down, `event_node_30115_achievement` |
| `event_achieve_state` | **1 once the event's final reward has been taken**, 0 otherwise |
| `reward_step`, `version` | on a STEP TRACK, the steps claimed and the claims made after the first; 0 and 0 on a record that holds only a final reward. See below |

That final reward is the one that unlocks only after every other reward in the event is claimed, so the flag is a genuine "all done". `_event_finished` reads it, and a row at its ceiling with the flag set drops the `+?` and goes green. `_event_records` says which records an event owns: those at one of its roots or under it.

**The claim that sets it is `mission / reward_event_limit`**, naming the record by `event_mission_id` -- the same id `complete_nodelist_event_mission_all` calls `event_id`. It answers under the bare key `entity` (*The completion flag's source*, below). **And that claim CREATES the record**: the bartender had none before it and `(0, 0, 1)` after. Nothing before the claim says a final reward is there -- no row, no red dot, nothing in the reply to the claim that took the last ordinary reward, which carried that row and its payout and nothing else.

**Which families pay one**, from every record the captures on hand have carried:

| Family | Instalments with a flagged record | Record id |
| ------ | --------------------------------- | --------- |
| Arena | `event_arena_1`, `event_arena_2` | the event's |
| Node List | all seven on record | `<event>_achievement` on four (`30084`, `1055`, `30113`, `30115`), the event's own on the other three |
| Operation | `event_operation_s2_001` | the event's |
| Rhythm game | `event_rhythm_apex_beat` | the event's |
| Stock | `event_stock_1` | the event's |
| Bartender | `event_bartender_1` | the event's |

Families that have never carried one, over every instalment the logs hold: devil, summer, policy, idol, director, recorder, messenger, codex, the new-year event, and the Galactic Disaster's challenge missions (`event_chaos_mission_*`, four instalments). `event_schedule_devil_001` is confirmed rather than merely unseen: claiming its seventh day's three rewards answered with the mission rows and the items and nothing else.

**The records are purged in batches**, not at a fixed age: the login of 2026-09-03 dropped every record whose event had ended by 29 July -- some had stood since February -- and kept those that ended in August. A family's history is only known if it was written down while its records were there, which is what `ChecklistManager.finals` is for.

Confirmed against every row carrying the field, which is not many, so **treat this as the best reading of a handful of events, not as settled behaviour** -- the next few instalments are as likely to extend these rules as to confirm them. Every event whose mission rows are all complete carries state 1, and the two known-unfinished ones (`event_season_love_4` and `event_chaos_assault_1`) carry 0. An event that has merely ENDED does not get the flag — `event_season_love_4` ended in August and is still 0 — so the flag is about completion and not about the clock.

### A final reward the wire has not mentioned yet

**A family that has paid a final reward is watched for the next one.** `_recall_finals` looks at every event on the schedule, ended ones included, and files each whose record is flagged under its family (`_stem(_event_key(name))`) in `ChecklistManager.finals`; a live event of such a family then counts the final reward in its reading. Every row claimed and the final not taken reads `FINAL_WAITING`: red, with the final in the total -- `24/25+?` -- until the flag arrives and it reads `25/25`.

**One instalment is enough to believe it**, where a total wants two agreeing: being wrong costs a red row asking `Finished?` over a reward that is not there, which the user answers in one click, while missing it costs the reward. That is also why `FINAL_WAITING` asks the question although the row is short of its total by one -- the one is exactly the reward nothing on the wire has confirmed.

**A step track's flag is not a final reward** and is left out of the record: it flags on its own ladder. And the reading assumes a flag means a SEPARATE reward, which the bartender confirms and nothing else has been captured claiming; were it set by the last ordinary claim, the row would read one higher in both figures and go green on that same claim.

### `reward_step` and `version` — read as a tally, not yet measured

Across every row ever captured, **`event_achieve_state` is 1 exactly when `version == reward_step`**:

| Row | `reward_step` | `version` | `state` |
| --- | --- | --- | --- |
| `event_daily_mission_check_1` | 10 | 10 | 1 |
| `event_season_love_2`, `_3`, `_4` | 21, 21, 21 | 12, 11, 7 | 0 |
| `event_half_year_mission_1` | 24 | 8 | 0 |
| `event_anniversary_gacha_1` | 5 | 2 | 0 |
| `event_chaos_assault_1` | 3 | 2 | 0 |
| every final-reward record | 0 | 0 | 1 |

Two readings fit every row: *"`reward_step` is the track's size and `version` is how much of it is claimed"*, or *"`reward_step` is what has been claimed and `version` counts the claims"*. **The code takes the second**, as `STEP_FIELD`, on two pieces of evidence the table alone does not show:

* **The love family moved its ladder.** `event_love_01` held 21 mission rows, thresholds from 100 to 2110 on one score, and the account claimed all 21 of them within six days, in 15 separate claims. `event_love_02`, `_03` and `_04` hold ONE row each -- score 2190, never claimed -- and a record with `reward_step` 21. The same 21 steps, moved from rows to the record.
* **`version` counts the claims after the record is made.** A record is created at `version` 0 by the claim that first touches it, as the bartender's was. Read as a tally, love_02 to _04 took their 21 steps in 13, 12 and 8 claims, where love_01 took 15; and `event_daily_mission_check_1`'s ten steps, one a day, run `version` 0 to 9, with its final reward's claim making the 10 and setting the flag. Read as a size, the three love instalments would each have ended with 9, 10 and 14 steps reached and left unclaimed, at a maxed score, on an account that claimed every one of love_01's.

**What would overturn it, from cheapest:**

1. **Look at the Sortie's clear-level rewards in game.** `event_chaos_assault_1` reads `reward_step 3, version 2` beside `chaos_assault_entity.highest_clear_level` 5. Three rewards on the track with two claimed means `reward_step` is the size; three or more claimed means it is the tally.
2. **Claim ONE step of a live track with a capture running.** `reward_step` moving by one makes it a tally; `version` moving with `reward_step` fixed makes it a size. An AREA reward is not a step -- a capture across a whole Sortie run with two `receive_area_reward` claims moved neither number -- so for the Sortie the claim is a clear-level reward.

Overturned, `_step_progress` would take `version` as the claimed count and `reward_step` as the total, and `_instalment_size` would stay as it is: a finished track's size is `reward_step` under both readings, where it was claimed to the end.

**The reading to rule out first is that `event_chaos_assault_1` has no track at all.** An event row also exists for a permanent content RELEASE — the entry that puts the mode on the event list and is never claimed against — and one of those would sit at fixed numbers forever, which is exactly what it has done since May. A clear-level claim that moves neither number says this row is a release notice, and the question has to be settled on some other track.

### Step tracks

**A step-track event has one mission row and a ladder of rewards on it.** The row accumulates a score and is never itself claimed -- `event_love_04_01` stood at 2190 with `complete_time` 0 long after its event ended -- and the rewards are thresholds on that score, counted on the completion record once the first is claimed. Seen on love (from its second instalment), `event_half_year_mission_1`, `event_anniversary_gacha_1`, `event_daily_mission_check_1` and the Sortie's `event_chaos_assault_1`.

`_step_records` finds them -- a record paired to the event with `reward_step` above 0 -- and `_step_progress` reads the record instead of the row: the steps over themselves with `+?` while nothing else is known, `~7/21` where two finished instalments agree, green on the flag. **Before the first step is claimed there is no record**, and the lone row reads `0/1+?`, which is true: at least one reward, none taken. A finished step track is filed under its steps; filed by its rows, every love instalment held 1.

## Telling a rectangular family from a ragged one

Two mission families can look identical — `event_devil_<day>_<task>` and `event_bartender_1_<page>_<index>` are both a name and two numbers — and mean completely different things. `event_devil_*` is a grid, 3 tasks on each of 7 days, so `max × max` is its total. The bartender's is three pages of different lengths, so `max × max` is nonsense.

**`issued_time` separates them, from one snapshot.** The game creates a mission row when the mission first becomes relevant, so rows stamped with the SAME SECOND were created by one act of the game. What such a batch varies is the shape:

* a batch that varies an EARLIER index and holds the LAST one is the same task repeating per day — a **grid**;
* a batch that varies only the LAST index is one page's ladder — **ragged**.

Run against the whole account, every family answers, and the answers match what the events look like in game:

| Family | A same-second batch | Verdict |
| ------ | ------------------- | ------- |
| `event_devil_<day>_<task>` | 6 rows varying `day`, holding `task` | grid — 7 × 3 = **21** |
| `event_node_<id>_<stage>_<task>` | 4 rows varying `stage`, holding `task` | grid — 4 × 5, plus 5 achievements |
| `event_bartender_1_<page>_<n>` | 12 rows varying `page` AND `n` | ragged |
| `event_summer_mission_01_<wave>_<n>` | 4 rows varying `n` alone | ragged |
| `event_stock_1_<page>_<n>` | 10 rows varying `n` alone | ragged |
| `event_policy_<n>_<m>` | 6 rows varying `m` alone | ragged |

**It answers on the event's first afternoon**, which is the only time the answer is worth anything. `event_devil_*`'s grid batch and all seven of its day numbers were in the snapshot taken hours after it opened, so the 21 was derivable from day one — the `3/3` the row actually showed was the id collision under *Naming*, not a shortage of evidence.

A batch that varies both indices says nothing and is ignored; `event_devil_*` has one of those too. One clean batch is enough.

## A finished instalment's rows are its whole total

**A FINISHED instalment's mission rows are its whole total.** The game issues a row when it issues the mission, so a live event's rows are what has been handed out so far — but an event whose window has closed has handed out everything it ever will, and counting its rows is counting the event.

So every load counts the ended events in `event_schedules` and files the figure under the family the instalment belongs to (`_stem` of the normalised id, so `event_schedule_policy_005` files under `event_policy`). `ChecklistManager` keeps it in `settings/checklist.json`, and the recording is the half that cannot wait: **the game purges old instalments**, and a count nobody wrote down while its rows were there cannot be recovered.

A live event takes its denominator from that record when, and only when:

* **two or more finished instalments of its family agree.** One is a number rather than a pattern — the twenty-four login-streak rows on this account run 7, 10, 14 and 21 days, and only reading them as one family would make that look like an event changing length;
* **the figure is BIGGER than the rows in hand.** Where the live event has issued more than its predecessors held, the wire is saying so against a record that only remembers, and the rows win.

Such a row reads `~1/20` rather than `1/3+?`: the tilde is the tab's mark for a number worked out rather than read. **It does not go green on it** — `event_achieve_state` is still the only thing that ends an event — so the worst an over-large inherited total can do is leave a finished row looking unfinished.

A step-track instalment is filed under the steps on its record, not its one accumulating row (`_instalment_size`). The record starts empty and fills as instalments end; `python docs/events_replay.py` prints what it would hold after every login on hand.

## Totals the wire does not state

Recorded here rather than in the code. **A total typed into the program is wrong the moment its event ends** — unless its event is Generic, which none of these is. These are for working out the pattern, not for shipping.

| Event | Total | How it is built | Derivable? |
| ----- | ----- | --------------- | ---------- |
| `event_schedule_devil_001` | 21 | 3 tasks/day × 7 days; ids are `event_devil_<day>_<task>` | **yes** — a grid, by the test above |
| `event_bartender_01` | 24, plus a final reward | three reward pages of 7, 7, 10, and one more that unlocks after all 24 | **no**: ragged. Pages 2 and 3 show their full 7 and 10, but page 1 is a floor. The final reward is not a mission row — it is what sets the completion flag |
| `event_summer_01` | 10 rewards, 84 items | one reward per 8 items | items spent and earned **yes**, the 10 and the 84 **no** |
| `event_schedule_love_N` | 21 | a step track: 21 thresholds on one accumulating score. The first instalment held them as 21 mission rows instead | **yes, from its history**: finished instalments are filed under their steps, and three have held 21 |
| `event_nodelist_NNN` | 25, and a final reward on the later lists | 4 pages of 5 missions, plus 5 achievements | as a grid once its last index is issued -- it read 8 on its third day -- and from its history otherwise: three finished lists held 25 |

### The bartender keeps its own per-day record

**`event_bartender_entities` is the guestbook: one row per day PLAYED**, and nothing on the Checklist reads it. It rides `event/get_list` at every login:

```json
"bartender_01_day_07_story_1": {
  "user_id": 300001105178, "event_id": "event_bartender_1",
  "bartender_story_id": "bartender_01_day_07_story_1",
  "normal_complete_time": 1789412941, "hidden_complete_time": 1789412661,
  "fail_complete_time": 0, "version": 1}
```

Each row carries three outcome stamps. On the account it was read from, all seven days have a `normal` AND a `hidden` time and none has a `fail` — so a day can be finished more than one way, and the record says which ways it was.

**It is a floor, not a denominator.** The table held no rows on the event's first afternoon and gained one with each day's first Last Call -- one after day 1, three after day 3, seven once day 7 was played -- so its length is the days played, the same thing the per-day mission page says, and the event's own length is on neither. Nothing else on the wire states it: `event_info_entity.open_day` is the furthest day the player has opened, not the last one there is.

### The Last Call is what ends a day, and it names the ending

`event_bartender/check_last_call` is the submission: the day's orders plus one `last_call_order`, each an `order_id` and a five-slot `liqueur_count`. The reply says what the player got:

| Field | Is |
| ----- | -- |
| `ending_type` | `NORMAL`, `HIDDEN` — a third for a failure is implied by the record's `fail_complete_time` and has not been seen |
| `story_map_id` | the story that unlocks, `event_bartender_07_nor` against `_hid` |
| `guestbook_id` | the guestbook entry it fills, `bartender_01_guestbook_07` |
| `event_bartender_entity` | that day's row, with the stamp just written |
| `mission_condition` | every mission the submission moved, with its new score |
| `item_result` | `{}` — the Last Call itself pays nothing; the rewards come from claiming the missions |

Both endings of one day were captured minutes apart: `HIDDEN` at 20:04 wrote `hidden_complete_time` and left `normal_complete_time` at 0, and `NORMAL` at 20:09 filled the other and took `version` from 0 to 1. So the two are independent and either can come first.

`check_general_orders` answers the same shape before the last call, with **`can_last_call`** saying whether the day can be ended yet. `set_last_open_day` writes `event_info_entity` (`{"info": {"open_day": 1}}`, under `event_146` rather than `event_bartender_1`) — which day of the event the player has opened up to.

**Nothing here is read yet**, though it IS captured: `event_bartender_entities` rides the login burst into the snapshot with every other `event_*` table. What it states that nothing else does is which endings each played day reached.

### `event_bartender_1`'s pages are one kind of task each

The 7/7/10 is real structure, not decoration: the page number is the middle segment of the mission id, and each page is one KIND of task. `mission_condition` on an action names the kind:

| Page | `condition_type` | Shape | Seen |
| ---- | ---------------- | ----- | ---- |
| `_01_*` | `EVENT_BARTENDER_CLEAR_DAY__ID` | one row per day of the story | 3 of 7 |
| `_02_*` | `EVENT_BARTENDER_GUESTBOOK_CLEAR` | a ladder, all seven sharing one running score | 7 of 7 |
| `_03_*` | `EVENT_BARTENDER_MAKE_COCKTAIL__ID` | a ladder | 10 of 10 |

So the total is 7 + 7 + 10 rather than any product, and the only unknown is page 1, whose rows arrive a day at a time. **Summing each page's own maximum is the right shape of derivation** — it gets 3 + 7 + 10 today — but each page is a floor, so the sum is too.

The guestbook itself is elsewhere: `event_bartender_entities` keys on `bartender_01_day_<NN>_story_1` and each row carries THREE stamps — `normal_complete_time`, `hidden_complete_time`, `fail_complete_time`. The two guestbook entries a day is the normal ending and the hidden one; the third is a failure nobody has triggered. A row appears once its day has been played.

### The summer define entity's two counters

`event_summer_define_entity` has two counters and neither is a reward count:

| Field | Is | Measured |
| ----- | --- | -------- |
| `event_item_count` | event items EARNED, lifetime | 52 → 68 on a claim paying 16 |
| `reward_count` | event items SPENT ON REWARDS, lifetime | 48 → 64 when two rewards were claimed |
| `items[4020001].amount` | what is spendable now | 4 → 0 across four puzzle-piece unlocks |

**A reward costs 8 items**: two of them moved `reward_count` by 16, and the 48 standing before it is the 6 rewards the account had taken. Unlocking a puzzle piece also spends an item but does NOT move `reward_count`, so the three numbers only reconcile as `amount = event_item_count - reward_count - pieces unlocked`.

That gives rewards taken (`reward_count // 8`) and rewards waiting (`amount // 8`) exactly. What is still absent is the DENOMINATOR: the event's 10 rewards and its 84 items are nowhere, and 84 ≠ 10 × 8, so the last rewards are not evenly spaced and no rate would find them anyway.

### What a FINISHED summer event looks like, and what it does not say

Captured in full — the last mission claimed, the last reward taken, the last puzzle piece slotted, the last story watched. Everything the account then held:

| | Reads |
| --- | --- |
| `event_summer_define_entity` | `event_item_count` 88, `reward_count` **84** — the event's whole cost, and it stops there |
| every mission row | 20 of 20 with a `complete_time` |
| `event_summer_set_entities` | three sets, all with a `complete_time` |
| `story_event_entities["event_132"]` | 14 stories, 14 complete |
| the balance of `4020001` | 4 — less than one reward's 8, so nothing is affordable |
| **`event_mission_reward_entities`** | **no summer row at all** |

**So the general completion flag does not cover this event**, and none of the other five is a proof. Each is a floor in the same old way: a fourth mission wave, a fourth set, another story or more items would each make the "complete" reading move again, and nothing on the wire rules that out. The 84 is only recognisable as a total because the maintainer counted it in game.

The one thing that IS exact is a different question: **`amount // 8` is how many rewards are waiting**, and it needs no total at all. `0` there means nothing to collect right now — which is what a checklist is actually for — while "the event is over" stays unanswerable.

Finishing the last puzzle also pays a one-off item (`4010003` here), which would serve as a per-event completion marker. That is a hardcode per event and worth it only if a general answer never turns up.

## Naming, and how to find an event's records

An event's schedule id and its records' ids differ, but only in decoration. `checklist_tab._event_key` strips the words `schedule`, `mission` and `season` (`EVENT_NOISE_WORDS`) and the zero padding, after which they match:

```
event_schedule_policy_005  ->  event_policy_5_*
event_summer_01            ->  event_summer_mission_01_*
event_schedule_love_4      ->  event_love_04_*        and  event_season_love_4
event_stock_01             ->  event_stock_1_01_*     and  event_stock_1
event_bartender_01         ->  event_bartender_1_*    and  event_bartender_1
```

The right-hand column of the last three is the completion record's id, which lives in the same namespace as the mission rows — so one normaliser serves both.

Matching is on a segment boundary, so `event_daily_1` cannot swallow `event_daily_12`'s rows.

### The event's index is not always in its missions' ids

**`event_schedule_devil_001` is the exception.** Its schedule is `event_schedule_devil_001` and its missions are `event_devil_<day>_<task>` — that `01` is DAY one, not the event. So the normalised key `event_devil_1` matched day one's three rows and silently dropped days two to seven, and a 21-reward event read `3/3` with nothing about it looking wrong. Every other family repeats the index, which is why it took an account with six days claimed to notice.

`_event_rows` handles it by trying the STEM — the key without its own index — and taking the extra rows unless another event's key claims them. Three guards, all load-bearing and all pinned:

* **the full key must match something first.** A stem alone is wildly greedy: `event_2` stems to the bare word `event` and would take every event mission on the account, and `event_schedule_chaos_mission_5` stems to `event_chaos` and would take the Sortie's. Neither has a single row under its own key, which is what rules them out.
* **another schedule's key wins.** `event_schedule_policy_004` is still in `event_schedules` long after it ended, so `event_policy_4_*` belongs to it and not to `_005`, which shares the stem.
* **a row issued before every row of the event's own is an earlier instalment's.** An instalment's schedule can go while its rows stay: `event_arena_1_*` outlived its schedule, and the stem took all 23 into arena_2's count, filing one instalment of 17 rewards as 40. Policy's older instalments went the same way, 18 for 6. A later day of the same event is issued with or after the first -- the devil's grid arrives as one batch on day one -- so `_first_issued` of the event's own rows is the line.

**When adding an event, check this by counting.** The rows the account holds under the family stem, against what the row reports. They agreeing is the whole test, and it is one line -- and `docs/events_replay.py` runs it over every instalment on record.

### A Node List shares no word with its missions

**`event_nodelist_007` owns `event_node_30115_*`**: the schedule is numbered by list and the missions by the combatant it features, and nothing on the wire links the two numbers. The define tables that look like the link (`story_event_node_list_entities`, `mission_event_node_list_story_node_entities`) cover only the oldest lists and stop there.

What does link them is time. **An instalment's rows are first issued inside its own list's window**, so `EVENT_ROW_FAMILIES` maps the schedule family to the mission family and `_event_roots` gives a list the instalment whose FIRST row its window saw. Later rows of the same instalment are issued days in and prove nothing -- `event_node_30113`'s last rows arrived eight days after its first -- so the first is what places it, and a list with no window takes nothing at all rather than every instalment ever issued. Over the three lists the logs cover, each takes exactly one instalment and no instalment goes to two.

A list's rows are its missions (four pages of five, `event_node_<id>_<page>_<n>`) and its achievement page (`event_node_<id>_achievement_<n>`), 25 in all. Its completion record sits on the achievement page on four of the seven lists and on the list itself on the other three, with no pattern in the dates; `_event_records` takes a record at or UNDER the list's instalment, so both count.

**Attendance and trial events do not follow this** — their records are numbered in a different space entirely, and `wire_hunt.md` says how each is paired.

## The payloads an event's data arrives in

* **`event/get_list`** is the master payload, sent when the events screen opens. It carries every event entity at once: `event_bartender_entities`, `event_summer_define_entity`, `event_summer_set_entities`, `remnants_entities`, `marble_*`, `story_event_*`, `event_arena_*`. **It carries no trial entity**, which is why the trial slot lists have to be learned. The capture keeps every `event_*` table in it, plus `story_event_entities` and the two `marble_*` tables by name, since nothing about theirs marks them.
* **`event_mission_entities`** arrives with the login's `mission` reply and holds every event mission the account has been issued.
* **`event_mission_reward_entities`** arrives in the same `mission` reply and carries the completion flag above.
* **A claim** answers with the rows it changed, under `entities` — and pays under **`result`**, which is the fourth key the wire uses for a rewards payload and the one that was missed. Watch for it when a claim seems to pay nothing.
* **`mission_condition`** rides on the reply to any action that moved a mission, and is the single most informative payload an event has. Its `condition.event_mission` list names every event mission that one act touched, each with its `condition_type`, its `issued_time` and its NEW score — so one deliberate action says what a family's rows are FOR. A row drops out of the list once it is complete, which is how a ladder's thresholds become readable without any of them being stated.

Claim commands seen so far, all naming the event and the records together:

| Command | Names |
| ------- | ----- |
| `mission / complete_event_mission_all` | `event_id` (or `event_mission_define_id`) and `mission_ids` |
| `mission / complete_nodelist_event_mission_all` | `event_id` and `mission_ids` |
| `event_summer / complete_event_mission_all` | `event_mission_define_id` — the wave, not the event |
| `event_summer / get_summer_reward_all` | the event; claims every affordable reward at once |
| `event_combatant_trial / reward_combatant_trial` | the trial event AND the slot — the only place the two meet |
| `hyperspace / get_star_reward` | the Basin season, answering with `reward_doc` |
| `mission / reward_event_limit` | `event_mission_id`, the completion record's id: the FINAL reward, answering under the bare `entity` |

**The command says whether an event is paged.** A flat mission list claims with `complete_event_mission_all`; one with reward pages uses `complete_nodelist_event_mission_all`. The bartender uses the nodelist command although it is scheduled under `EVENT_SCHEDULE` and not `EVENT_NODELIST_PAGE`, so the schedule group is not what decides it. Only a captured claim shows this, which makes it a confirmation rather than a classifier — `issued_time` gets there first and needs no capture.

### One shape for every claimable reward

**Every claimable reward on this wire is the same row**, whatever the content -- an event's missions, the Sortie's ladders, the Galactic Disaster's achievements, the Chaos Matrix's, the account's own:

| Field | Is |
| ----- | -- |
| `res_id` | the reward; its prefix names the family and its trailing numbers the page and index |
| `score` | progress towards it. A ladder's rows share one running score |
| `issued_time` | when the game handed it out -- on event, Sortie and Galactic Disaster rows; absent from the account-wide achievement tables |
| `complete_time` | when its reward was CLAIMED, and 0 until then |
| `version` | how many times the row has been written since it was issued |

Tables carrying it: `event_mission_entities`, the season pass's missions, `assault_achievement_entities` and `assault_char_achievement_entities`, `disaster_achievement_entities`, `achievements`, `chapter_achieve`, `savedata_mission_entities`, `zero_orb_achievement_entities` and `marble_achievement_entities`. `story_event_entities` and `event_summer_set_entities` stamp `complete_time` the same way on rows of another shape.

**The claims share a shape too**: a `complete_*_all` or `*_reward_all` command naming the rows (`mission_ids`, `achievement_ids`), answered with the rows it changed -- under the table's own name, the bare `entities`, or a singular `*_entity` -- and paid under `item_result` or `result`.

**So a new event's rewards are recognisable before anything else is known about it**: a table of rows with `res_id` and `complete_time` is claimable rewards, claimed where the stamp is set. What is NOT shared is where the total comes from, which is the rest of this page.

## Fields only ever seen in the login burst

**This is the hazard that looks like a Checklist bug.** Some event records have never been observed outside the login payload. A capture that stays open all evening still shows what the account looked like at login, so a claim made during it changes nothing on the tab until the next login — and the row is not wrong, it is *old*, which is indistinguishable on screen.

| Field | Seen in | What a mid-session claim sends |
| ----- | ------- | ----------------------------- |
| `attendance_entities` | `load` and `mission` replies at login | **no record at all** — see below |
| `overclock_entities` | the `unlock` reply at login | `result_overclock_entities`, nested under the stage reply's **`return_info`** |
| `event_mission_reward_entities` | the `mission` reply at login | the final reward's claim sends its one row under the bare `entity`; an ordinary reward claim sends nothing |
| `event_mission_entities` | login | its own rows, under the BARE key `entities` — not under its own name |
| `event_summer_set_entities` | the `event/get_list` payload | the one row that changed, under the SINGULAR `event_summer_set_entity` |

### A Daily Check-in claim's reply

`attendance / reward` with an `event_id`, and the reply names no entity:

```
{"completed": false, "event_id": "event_143",
 "received_days_before": 5, "received_days_after": 6,
 "reward_list": [{"count": 1, "res_id": 2000023}], "item": {...}}
```

So there is nothing to merge: the cached row is patched from `received_days_after`, and the next login sends the real record.

**And the reward rides in `item`**, a top-level totals envelope like any other — not in `reward_list`, which states the same payout as a delta beside it. A key that generic is guarded by its shape rather than trusted by its name; `capture/manager` takes it with `result`. Until it did, a login event's reward reached neither the Capture Log nor the item counts.

**`completed` is the game's own word that the streak has ENDED**, and it is the only one there is. Captured on the claim that finished `event_143` (`websocket_debug_20260914_195103.jsonl`, qid 39): `received_days_before: 6, received_days_after: 7, completed: true`. The addon keeps it on the row AND across the login that follows — the row that login sends is identical to a streak merely claimed for today, so letting it win would lose the answer for good.

### A streak has no stated length

The claim that proved `completed` also disproved the constant it was meant to confirm. One account's twenty-four streaks:

| Days | Streaks |
| ---- | ------- |
| 7 | 19 |
| 10 | 1 |
| 14 | 2 |
| 21 | 2 |

**The length is per event and the wire never states it.** In twenty-three of the twenty-four, `current_days`, `received_days` and the span between `start_dayid` and `last_dayid` are all the same number once the streak is over — so the length is readable afterwards and never in advance.

What the record does state exactly:

| Field | Is |
| ----- | -- |
| `current_days` | days shown up for |
| `received_days` | days claimed |
| `last_dayid` | the last day the streak ADVANCED — **the LOGIN, not the claim.** The record read `2/1/1348` and then `2/2/1348` across a claim |

So the row reads claimed against claimed-plus-one, red where `current_days` is ahead and orange where it is level. **One claim advances the streak by exactly one** — `received_days_before` to `received_days_after` — and the record has never been caught more than one apart.

**`event_1`, the year-long login event, is the exception and reads wrong.** `event_daily_1`'s schedule runs 365 days, and its streak row's `received_days` has sat at 7 across every capture while `current_days` climbed to 56 — so it looks like a streak permanently one day behind.

Three things have been ruled out as ways to tell it apart:

* **It is never claimed.** Every `attendance / reward` command in all thirty-four debug captures names `event_143`, the live streak. Not once `event_1`. So the CLIENT knows there is nothing there, and knows it from a reward table the server never sends.
* **A day left unclaimed does not separate them.** That state is already in the record: on 2026-09-09 at 20:52 the live streak read `current_days 2, received_days 1` with the reward genuinely waiting, and `event_1` read `51/7` beside it. Both look "behind" in exactly the same way.
* **`reddot_info` does not carry it.** The login burst's red-dot payload is two lists of item ids — new savedata and new fragments — and mentions no event, mission or streak.

What `current_days: 56` counts is still unknown: the account is 326 days old with 325 login days, so it is neither. Until that is explained, nothing here should be built on it.

### The completion flag's source

`mission / reward_event_limit` with an `event_mission_id` — the claim of the final reward that unlocks only once every other has been taken. Captured on `event_bartender_1` (`websocket_debug_20260914_195103.jsonl`, qid 100):

```
{"item_result": {"items": {"9700001": ..., "9700002": ...}},
 "entity": {"res_id": "event_bartender_1", "event_achieve_state": 1}}
```

**Under the bare key `entity`**, which is also what a Combatant Trial claim answers under with a different row — so the addon takes it only when `event_achieve_state` is on it. Read as only the three spelled-out keys, the one reply that ever carries a completion was dropped, and `event_bartender_1` went on reading `24/24+?` with the wire having said outright that it was finished.

### A completion is kept by the server; a streak's is not

Captured by logging in after finishing both (`websocket_debug_20260914_205131.jsonl`), and the two answers differ:

* **`event_mission_reward_entities` comes back with it.** The login sent six rows where it had sent five, the new one being `event_bartender_1` with `event_achieve_state: 1`, `reward_step: 0`, `version: 0`. So a completion is the server's own record and arrives at every login — an event once finished stays finished across restarts, with nothing client-side needed.
* **`attendance_entities` does not.** The finished streak came back as `current_days: 7, received_days: 7, version: 13` with no `completed` anywhere. That flag exists only in the reply to the claim that ends the streak.

So the addon's copy of `completed` carries the answer through the session that saw the claim, and the program keeps its own across sessions: `ChecklistManager.remember_streak` files the event id in `settings/checklist.json` and `_recall_streaks` writes the flag back onto the login's row. Without that record a finished streak reads orange from the next start until its event ends — the honest answer for a row that cannot be told from one merely claimed today, and not the true one.

**A finished streak's `version` is `2 x received_days - 1`** — 13 at seven days, 19 at ten, 27 at fourteen, 41 at twenty-one — and stops moving when the streak ends, where the year-long event's climbs on. It re-encodes what `current_days` already says and adds nothing, and three of the account's oldest rows carry `version: 0` regardless. Not a signal.

### The defences

Both in `capture/manager.py`, and both are the general rule rather than anything about these two fields:

* **merge by id, never replace.** A one-row payload updates its own row and leaves the rest alone. A wholesale assignment looks right on every capture ever taken and wipes the list the first time a partial one arrives.
* **look under `return_info` as well as at the top level.** A stage reply nests its whole outcome there. Reading only the top level is indistinguishable from the wire being silent, which is exactly how the Overclock row was misread.
* **accept all four spellings** — `x_entities` (list), `result_x_entities` (list), `x_entity` (one record) and, for a completion, the bare `entity`. The singular is the ROW THAT CHANGED and belongs folded into the collection, not kept beside it: a second copy under a near-identical name is one more thing for a reader to pick the wrong one of. **`entity` is shared with the Combatant Trial claim**, which puts a different row under it, so the presence of `event_achieve_state` is what says which is which. `checks/check_capture_event_state.py` holds all four plus the shapes above.

### Reading a capture for whether anything mid-session landed

Scan the saved snapshot for records stamped AFTER the session's own login — `attendance_entities[].last_time` is that login, since the streak is touched by logging in.

**The point is to separate a dead capture from a field the reader misses**, and they look the same from the tab. On the capture that prompted this, the capture was demonstrably live: `inventory.service_server_time` and the Aether balance's `last_update` both moved several minutes into the session, which is two Memory Fragment runs being paid for. In the same file the streak and the Overclock row still carried their login values.

So the capture worked. What it could not do was see a claim that sends no record and a row nested one level down — and the next capture, taken with the same actions deliberately isolated, showed both immediately. **When a row will not move, capture the ONE action that should move it and read the reply whole**, rather than diffing snapshots.

## Processing a new event

Every event row needs the same three answers -- rewards claimed, rewards held, and whether a final reward is still owed -- and each shape seen so far has a known source for each. The work for a new event is finding which shapes it is, from as few captures as possible.

**On its first day, with a capture running:**

1. **Log in once.** The login burst carries the schedule, `event/get_list` and `mission/get_list`, and the capture keeps every table in them the readers could want.
2. **Open the event, do ONE thing that moves a mission, and claim ONE reward.** Note the time. The action's `mission_condition` names the family's rows and what each is for; the claim shows its command and where it pays. `wire_hunt.md` has the diffing recipe.
3. **Log in again a day later.** A table whose row count has not moved was issued whole, and that is the only way to know it.

**Then, from what was captured:**

4. **Pair it.** `python docs/events_replay.py <a word of its id>` shows what the row reads at every login; `[]` means no rows were paired. Missions named after something the schedule does not carry go in `EVENT_ROW_FAMILIES`, the way a Node List's combatant does; missions under a fixed name unlike the schedule go in `EVENT_MISSIONS`.
5. **Recognise its shape:**

   | Shape | How to tell | Claimed | Held | Final reward |
   | ----- | ----------- | ------- | ---- | ------------ |
   | Mission ladder | rows with `res_id` and `complete_time` under the event's key | rows with a `complete_time` | a grid, pages issued whole, the family's history, else a floor | the completion record, once claimed |
   | Step track | ONE row whose `score` climbs and never gets a `complete_time`; a record with `reward_step` above 0 after the first claim | `reward_step`, read as a tally | the family's history | the same record's flag |
   | A table of its own | a new `event_*` table in `event/get_list`, or a named one like `story_event_entities` | whatever its rows stamp -- one claim shows which field moves | its row count, only if it did not move between the two logins | -- |

   Streaks, trials and Overclock events have shapes of their own, each under its own heading above.
6. **Watch for a final reward.** Once everything is claimed, look in game for a reward that unlocks after all the others, the way the bartender's Special Reward did, and claim it with a capture running: `mission / reward_event_limit` answering under `entity` confirms it. The family is remembered from then on, and its next instalment reads the final as waiting until it is claimed.
7. **Decide its categories and its reader** -- there may be more than one category. **If in doubt it is Open-ended**, the safe answer: a floor with `+?` that never claims completion. Add the group to `EVENT_CATEGORIES` and `EVENT_READERS`; a new event in a group that already has both needs no edit, which is the point of keying on the group.
8. **Check what it reads against *Fields only ever seen in the login burst*.** A record that arrives only at login needs its claim shape captured before the row can be trusted to move mid-session.
9. **Replay it** with `docs/events_replay.py`: the reading should move at the logins where the game did.

## Still open

* **A ragged family's page lengths.** The bartender's three pages are 7, 7 and 10, and two of the three can be read in full from the rows the account holds — but only because those pages were played. Page 1 hands out a row a day and will read short all week. Nothing distinguishes "this page is finished" from "this page is still being issued", which is the same wall every Open-ended reading hits. The completion flag answers the only question that really matters — *is there anything left* — without answering this one.
* **`reward_step` vs `version`.** Read as a tally on the evidence under *`reward_step` and `version`*, which also lists the two ways to settle it, cheapest first. Nothing has moved either number on a live track yet: an ordinary event reward claim does not touch `event_mission_reward_entities`, and the bartender's final reward CREATED its row rather than moving one. `event_chaos_assault_1` -- `chaos_assault` is the code's inherited word for Sortie -- is the readiest track, at `reward_step 3, version 2` since May beside a clear level of 5.
* **Whether every flagged family pays a SEPARATE final reward.** Only the bartender's was captured being claimed, and there the game's screen shows it apart from the 24. The Node Lists flag on their achievement page; were that flag set by claiming the last achievement rather than by a reward of its own, a list reads one higher than the game's 25, in both figures. The next Node List settles it: count its rewards on screen once the last is claimed, or capture that claim.
* **A grid under-reads a Node List until its last index is issued.** `event_nodelist_007`'s grid came to 8 on its third day, where it held 25: the batch that makes it a grid spanned its pages but only two of its five indices. The family's history knows 25, but a grid is this instalment speaking and outranks the past, so the smaller number wins. Which should win when a grid and a history disagree is open.
* **Rhythm games, the Disaster Marble, Trauma Codes and the collab coupon read nothing.** Their schedules share no word with their records (`ds_s3_event_rhythm_game` owns `event_rhythm_*`; `marble_s01` keeps its ladder in `marble_achievement_entities`), and each is one instalment on record, too few to pair by rule.
* **Telling the launch login event from a streak one day behind.** Three ways have been ruled out and none is left — see *A streak has no stated length*, which also says what a next attempt would have to explain first.
* **Event display names.** Every row shows an id, because the wire never sends a name — the client has them in a localisation table.

Settled, and kept so they are not re-suggested:

* **The Completed Events tab is entirely client-side.** Captured: opening the event list screen after finishing several events sent NOT ONE request. The two login captures taken minutes apart, one of them with the screen opened, carry the same thirty-eight commands — the only difference is a `req_very_cheetah_cookie` keepalive. Whatever the client sorts in there, it decides from the records the login already gave it.

* **`event_bartender_entities`** is the GUESTBOOK, not the reward pages, and it fills in as the days are played. One row per day, three completion stamps each.
* **`event_info_entity`** is still `{"open_day": 1}` under a different `event_id`. Nothing in it is a total.
* **A third id space.** The mission commands name an event by a bare number — `event_142` is `event_devil_*`, `event_143` the login streak, `event_146` is `event_bartender_1` — alongside the schedule's `event_schedule_devil_001` and the reward record's `event_bartender_1`. Nothing needs the numeric one: every reader pairs on the normalised key.
* **`event_devil_*`'s last claim produces no completion flag.** Claiming the seventh day's three rewards answered with the mission rows and the items and nothing else — no `event_achieve_state`, because the event has no final reward to unlock one. It stays a floor, correctly.
* **The message that unlocks when an event's rewards are all claimed** is most likely client-side and not on the wire at all. It is an EVENT screen's own message rather than anything in `messenger_entities`, which is the separate Combatant messenger. Nothing needs it: `event_achieve_state` names the event outright and arrives on the claim.
* **`mission_event_node_list_story_node_entities`** and **`story_event_node_list_entities`** look like define lists — 81 and 43 rows for an event long finished — but they are the account's own records, complete only because the event was completed. They say nothing about a live one.
