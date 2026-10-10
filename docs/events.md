# Events: how to read one, and what the Checklist does with it

Read this before touching the Events block of the Checklist tab, or before adding an event nobody has mapped. `wire_hunt.md` holds the general techniques for pairing wire payloads; this holds what is known about events specifically.

The code is `ui/tabs/checklist_tab.py`: `EVENT_GROUPS` says which schedule groups are listed, `EVENT_CATEGORIES` says what kinds each is (a set — see below), `event_is` asks whether a group is one of them, `EVENT_READERS` says which function reads it, and `_event_finished` is the one thing that can call an event over. `_event_roots` says which mission rows and completion records an event owns. `python docs/events_replay.py` replays every login on record through the readers, which is how a change to any of this is checked against every instalment the account has seen.

**The game client states what the wire never does**: every event's name, how many rewards it holds, and whether it pays a final reward (`docs/client_data.md`). The program takes event names from it. Reward totals are worked out from the wire, as this page describes, and that chain is also what has to stand for an event the client does not hold, or when the client cannot be read. Where the client and the wire disagree is listed in `client_data.md`, *What it was held against*.

**For a new event, start at *Processing a new event*** at the end.

## The four questions, in order

Answer them in this order for any event. Each one is cheap and rules out work on the next.

1. **When does it end?** `event_schedules` dates every event, so this always has an answer, and it alone is a useful row. An event nobody has mapped still shows its deadline.
2. **How much is done?** Usually a count of records carrying a claim stamp.
3. **Is it finished?** A separate question from 2, and often easier: the game keeps its own completion flag. See *The one place the game says an event is FINISHED*.
4. **How much is there altogether?** The client states it. Worked out from the wire it is the hard one, and the only one that can make the row lie — see *Floors* below. Where 3 has an answer, this one stops mattering.

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

The Overclock cap is the worked example. Nothing states how many doubled runs a day holds, and the game uses two shapes, six a day and two. But `overclock_entities` keeps one row per Overclock event ever played, each carrying its own `count`, so the shapes are simply there to be read. `_overclock_cap` reads them, which puts a six-shape event's third run at `3/6` where a written-down two would have clamped it to `2/2` and called a day with three runs left finished.

Which shape the live event is comes from its own record where that can say: a lifetime `total_count` above two a day, over the days before today, proves the six before a run is taken today (`_overclock_days_before`). Where it cannot, the event reads as the last one played (`_latest_overclock_shape`), so a day opens on `0/6` or `0/2` rather than always on the smaller.

Two guards make that safe:

* **a shape must recur.** One row's `count` can be a day its event ended part-way through, which was never anyone's cap; a real shape shows up across events;
* **the fallback is a floor, not an answer.** `OVERCLOCK_USES` is the smaller of the two shapes, used only where an account has no history at all.

### The two Overclock shapes in game

The shape follows the kind of Simulation mission the event doubles, and the two kinds are different contents with different economics.

| Simulation mission | Aether per run | Multiplier | Overclock shape |
| ------------------ | -------------- | ---------- | --------------- |
| Memory Fragment | 60 | none — one run is one run | **2** a day |
| Unit, Battle Memory, Support Data, Manual, Certificate, Growth Stone | 20 × *x* | *x* = 1…6, rewards ×*x* | **6** a day |
| Challenge | — | — | not an Overclock target; the Checklist tracks these as Simulation Challenges under Weekly |

So the six is the multiplier ceiling of the missions it applies to, and the two belongs to the one kind that cannot be multiplied at all. **A one-run experiment is decisive**: complete a single Memory Fragment mission with a capture running. Doubled rewards mean the event is the two-shape; doubled rewards on any other type mean the six-shape. Keep it as the tie-break for the case the derivation cannot settle: a two and a six are indistinguishable while the day's count is still at 1 or 2.

The doubled payout comes back under **`return_info.result_reward_drop_overclock`**, and the reply's Overclock row says what the fields mean:

| | At login | After one run |
| --- | --- | --- |
| `count` | 2 (yesterday's, `reset_time` in yesterday's day) | **1** |
| `total_count` | 10 | **11** |

So `count` is today's tally, zeroed lazily at the daily reset, and `total_count` is the event's lifetime one. A run adds what it multiplies by, up to the day's cap: a Memory Fragment run one, and a x5 Growth Stone run five of a six-shape day's six, the next x5 run the one left.

**The row rides under `return_info`, not at the top level of the reply.** A reader of the top level finds nothing, which looks exactly like "this event does not double Memory Fragment runs".

### Forced Daily is orange, not green

Claiming everything on offer does not finish a Forced Daily event: tomorrow brings more, and today's are gone whether or not they were taken. A green row means "nothing left to think about", which would be wrong for the rest of the run — so a finished day reads orange.

This is a different orange from the Open-ended one. Nothing here is unproven; the day is genuinely complete and the category alone says so, with no 48-hour settling involved.

On the LAST day it goes green. Orange is a promise that the row comes back; on the final day it does not, and taking that day's runs finishes the event outright. `_last_cycle` asks the event's own window whether the day now running is the one that reaches its end. Where there is no window the answer has to be NO — a row that goes green a day early costs the user the last day's rewards, where one that stays orange costs nothing.

### A total written down, and what takes it back

Some events have no total the wire states and no floor worth showing either. The launch login event is the one: `event_daily_1` hands out seven rewards in a new account's first week and then sits there for the year its schedule runs, its `received_days` stuck at 7 while `current_days` climbs past fifty. Read as a streak, the row says a reward is waiting that nobody can claim; read as a floor, it says nothing at all. The client's check-in table gives it seven days.

So the total is written down -- `WRITTEN_TOTALS` in `checklist_tab.py`, keyed by normalised event key -- and the event reads as Tallied against it.

Written down so the wire can take it back. A reward past the number disproves it: `written_total` answers None from then on and the row goes straight back to reading the way its group reads, floor and all. A number typed into the program is only ever a claim about what the wire has not said yet, and this is the shape that lets one be wrong safely. Without the falsifier an eighth claimed day would read `8/7` in green.

The same applies to a mission-tallied event: the write-down holds while the rows in hand have not gone past it.

### Members so far

| Group | Categories | Where its progress lives | Notes |
| ----- | ---------- | ------------------------ | ----- |
| `EVENT_OVERCLOCK` | Generic, Forced Daily | `overclock_entities[event id]` | doubled Simulation runs. `count` is today's tally, `total_count` the event's lifetime one, `reset_time` when the day's was last written. The cap is not stated; `_overclock_cap` reads the shapes off the ended events' own counts, and the live event's own days or the last event pick one |
| `EVENT_DAILY_CHECK` | Tallied | `attendance_entities` | a login streak. The attendance row is the FIRST one started after the event was — the ids do not match |
| `EVENT_COMBATANT_TRIAL` | Tallied, Generic | `combat_trial_entities` | three trials per combatant banner sharing the event's window |
| `EVENT_SCHEDULE` | Open-ended | `event_mission_entities`, plus `event_mission_reward_entities` for the completion flag | the catch-all: story events, seasonal events, `event_bartender_1`. A step-track event (below) reads its completion record instead |
| `EVENT_NODELIST_PAGE` | Open-ended | same two | the missions are named after the combatant, not the list: paired by issue time, see *A Node List shares no word with its missions* |
| `LOBBY_COUNTDOWN` | unmapped | `issued_limit_entities["1st_countdown"]`: `usable_time` and `expire_time` are the schedule's window, `vs1` the days reached and `vs2` the days claimed (offsets from 0, as a JSON list), `vi1` and `vi2` the day ids of the last of each | a login event under a group of its own, the Nightmare Carnival's countdown check-in (`countdown_attendance_1st`). Each day's reward claims itself at login, `lobby_countdown_reward`, whose `popup_infos` name the day (`countdown_attendance_1st_01`) and its items. With nothing to do, the row shows only its deadline |

**The Galactic Disaster is not one event but a season of them** -- three parts of 21 days, each with a supply store, a medal screen, five pages of challenge missions, a story track, three distortion bosses and a Great Rift half. The Checklist gives it a column of its own, holding the season-long shop and a deadline; the weekly chaos progress and the seasonal score are rows in `Weekly`. Between one season's content and the next, the shop is shut and the two rows read `Not open` (`checklist_tab.disaster_off_season`). That stretch is the three weeks the new season's window spends in preseason, under the ended season's `DISASTER_SEASON_END` tail window. The medal screen, the challenge pages and the story track are read by nothing.

## Knowing an event: three questions, and what can answer each

A Checklist row about an event is three separate claims, and they have different evidence behind them.

| | The question | How well it can be answered |
| - | ------------ | -------------------------- |
| 1 | How many rewards have been CLAIMED? | **Exactly, always.** `complete_time` on a mission row means its reward was taken; an event with no mission rows keeps its own table (a streak's `received_days`, a trial's slots); a step-track event counts its claims on its completion record, see *Step tracks* |
| 2 | How many does the event HOLD? | The client states it; off the wire, the sources below |
| 3 | Is it FINISHED? | Definite for a few, derived for some, a judgement for the rest |

### The sources for a total, strongest first

| Source | What it needs | What it gives | How it fails | Where |
| ------ | ------------- | ------------- | ------------ | ----- |
| **The completion flag** | the event's final reward claimed | not a total, but it ends question 3 outright | it exists only where a final reward unlocks after all the others | `_event_finished`, `event_achieve_state` |
| **A rectangular family** | one snapshot, once a batch spans an axis | the whole event, exactly | the family is ragged, and most are | `_grid_total` |
| **Pages issued whole** | one snapshot | an exact count for that page | a page not yet issued at all is invisible; a page of one row counts only where other pages' rows share its second | `_page_totals` |
| **A finished past instalment** | two instalments of the family agreeing -- their rows, or a step track's steps | the whole event | the family turns out not to repeat itself | `ChecklistManager.event_total`, `_instalment_size` |
| **A write-down** | a person deciding | the whole event | it is wrong until a reward past it proves so | `WRITTEN_TOTALS`, `written_total` |
| **The floor** | nothing | a lower bound, always | it is only ever a lower bound | `_event_progress` |

They stack, and they cross-check. `_event_progress` tries them in that order and takes the first that answers. Where two would answer and disagree, the weaker one is wrong: an instalment's history is the PAST and rows in hand are the present, so rows win; a write-down loses to any reward past it. A disagreement is worth noticing rather than smoothing over — it means a rule has broken, and the honest fallback is the floor.

**A final reward is added to whichever of them answers**, once it is known to exist: it is one more reward than the rows, not a total of its own. See *A final reward the wire has not mentioned yet*.

**One instalment is one vote**, however many schedules name it: `event_schedule_arena_2` and `event_arena_2` are the same arena, and `event_total` counts them once (its `same` argument, `_event_key` from the tab).

### Answering question 3

| Answer | When | What the tab shows |
| ------ | ---- | ------------------ |
| **Finished** | the completion flag is set | green |
| **A final reward waiting** | every row claimed, no flag, and the family has paid a final reward before | red (`FINAL_WAITING`), counting the final in the total, and asking `Finished?` for the instalment that turns out not to have one |
| **Said so by the user** | the row's `Finished?` box is ticked | green, and sorted down with the rest. The answer is kept against the pair it was given for: either figure moving retires it |
| **Likely finished** | claimed equals the floor and the tally has not moved for two days | orange — see `FLOOR_SETTLES_AFTER` |
| **Unknown** | anything else | red, with `+?` where the denominator is a floor |

**Nothing on the wire says an event's rewards are all mission rows**, and some are not: `event_bartender_1` pays a Special Reward outside its 24 rows, and `event_summer_01` 10 puzzle and 15 story rewards outside its 20, in tables nothing reads (`event_summer_define_entity`, `story_event_entities`). So "every row claimed" never means "finished" on its own, and the tab asks instead: a row at an unproven ceiling carries a `Finished?` checkbox, and the person who can see the game answers it. That answer is not checkable, so it is held to the reading it was given for and retired the moment that reading moves.

**A login streak has one length per event**, which the client's check-in table states and the wire never does. Off the wire, the row counts claimed against claimed-plus-one, floored at `checklist_tab.ATTENDANCE_FLOOR`, the shortest a streak has run: counting from what is claimed alone read `1/1+?` on a new streak's first day, which says finished. The schedule's length does not predict it -- two 21-day schedules paid 7 and 15. The last claim carries `completed`, which the capture keeps on the streak's row and the tab reads as finished.

## Floors, and the one wrong answer

**A count of the rows the account holds is a FLOOR, not a total.** The game creates a mission row when it issues the mission, so an event still handing them out reads as finished: a summer event read `12/12` with a third wave unissued. (`event_devil_*` read `3/3` against a real 21, but that was an id collision rather than a floor -- see *Naming* before assuming a short count is this.)

So an Open-ended row is marked `FLOOR` in the code and prints `+?` after its total. Saying "done" when it is not is the one answer a checklist must never give: it costs the user the reward. **The only thing that turns such a row green is the game's own completion flag** — see below; nothing the row can count about itself will do it.

After 48 hours at its own ceiling a floor turns **orange** — long enough that an event still handing out rewards daily would have moved it. Reading anything new restarts that clock, and a row below its ceiling never settles, because that is work outstanding rather than an unanswerable question. The record lives in `settings/checklist.json`; when a row last moved is a fact about the past and a snapshot holds only the present.

## The one place the game says an event is FINISHED

`event_mission_reward_entities`. One row per event the account has a completion record for, and the row is the answer a floor can never give:

| Field | Is |
| ----- | --- |
| `res_id` | the event's MISSION DEFINE id — `event_bartender_1`, not the schedule's `event_bartender_01` — so it goes through `_event_key` like everything else here. A Node List's can sit one page down, `event_node_30115_achievement` |
| `event_achieve_state` | **1 once the event's final reward has been taken**, 0 otherwise |
| `reward_step`, `version` | on a STEP TRACK, the steps claimed and the claims made after the first; 0 and 0 on a record that holds only a final reward. See below |

That final reward is the one that unlocks only after every other reward in the event is claimed, so the flag is a genuine "all done". `_event_finished` reads it, and a row at its ceiling with the flag set drops the `+?` and goes green. `_event_records` says which records an event owns: those at one of its roots or under it. An event that has merely ENDED does not get the flag, so the flag is about completion and not about the clock.

The claim that sets it is `mission / reward_event_limit`, naming the record by `event_mission_id` -- the same id `complete_nodelist_event_mission_all` calls `event_id`. It answers under the bare key `entity` (*The completion flag's source*, below). **And that claim CREATES the record**: the bartender had none before it and `(0, 0, 1)` after. Nothing before the claim says a final reward is there -- no row, no red dot, nothing in the reply to the claim that took the last ordinary reward.

Which events pay one is in the client (`event_mission_define`'s `special_reward_*`). The seven-day story events pay none, so **a seven-day story event's completion is known only by count**: all 21 rows claimed against its 7 x 3 grid.

**The records are purged in batches**, not at a fixed age: one login dropped every record whose event had ended more than a month before, some standing since February. A family's history is only known if it was written down while its records were there, which is what `ChecklistManager.finals` is for.

### A final reward the wire has not mentioned yet

**A family that has paid a final reward is watched for the next one.** `_recall_finals` looks at every event on the schedule, ended ones included, and files each whose record is flagged under its family (`_stem(_event_key(name))`) in `ChecklistManager.finals`; a live event of such a family then counts the final reward in its reading. Every row claimed and the final not taken reads `FINAL_WAITING`: red, with the final in the total -- `24/25+?` -- until the flag arrives and it reads `25/25`.

**One instalment is enough to believe it**, where a total wants two agreeing: being wrong costs a red row asking `Finished?` over a reward that is not there, which the user answers in one click, while missing it costs the reward. That is also why `FINAL_WAITING` asks the question although the row is short of its total by one -- the one is exactly the reward nothing on the wire has confirmed.

**A step track's flag is not a final reward** and is left out of the record: it flags on its own ladder. And the reading assumes a flag means a SEPARATE reward, which the bartender confirms; were it set by the last ordinary claim, the row would read one higher in both figures and go green on that same claim.

### `reward_step` and `version` — read as a tally, not yet measured

Across every row captured, **`event_achieve_state` is 1 exactly when `version == reward_step`**:

| Row | `reward_step` | `version` | `state` |
| --- | --- | --- | --- |
| `event_daily_mission_check_1` | 10 | 10 | 1 |
| `event_season_love_2`, `_3`, `_4` | 21, 21, 21 | 12, 11, 7 | 0 |
| `event_half_year_mission_1` | 24 | 8 | 0 |
| `event_anniversary_gacha_1` | 5 | 2 | 0 |
| `event_chaos_assault_1` | 3 | 2 | 0 |
| every final-reward record | 0 | 0 | 1 |

Two readings fit every row: *"`reward_step` is the track's size and `version` is how much of it is claimed"*, or *"`reward_step` is what has been claimed and `version` counts the claims"*. **The code takes the second**, as `STEP_FIELD`:

* **The love family moved its ladder.** `event_love_01` held 21 mission rows, thresholds from 100 to 2110 on one score, and the account claimed all 21 of them within six days, in 15 separate claims. `event_love_02`, `_03` and `_04` hold ONE row each -- score 2190, never claimed -- and a record with `reward_step` 21. The same 21 steps, moved from rows to the record.
* **`version` counts the claims after the record is made.** A record is created at `version` 0 by the claim that first touches it, as the bartender's was. Read as a tally, love_02 to _04 took their 21 steps in 13, 12 and 8 claims, where love_01 took 15; and `event_daily_mission_check_1`'s ten steps, one a day, run `version` 0 to 9, with its final reward's claim making the 10 and setting the flag. Read as a size, the three love instalments would each have ended with steps reached and left unclaimed, at a maxed score, on an account that claimed every one of love_01's.

**Every `reward_step` above equals the size the client gives the track** (`event_mission_reward`). Under the code's reading that is every track claimed in full; under the other it is true by definition, so the client does not settle it. A LIVE step track does: if `reward_step` equals the client's size while steps are still unclaimed, it is a size. The next love instalment, `event_love_05`, is already in the client.

Overturned, `_step_progress` would take `version` as the claimed count and `reward_step` as the total, and `_instalment_size` would stay as it is: a finished track's size is `reward_step` under both readings, where it was claimed to the end.

### Step tracks

**A step-track event has one mission row and a ladder of rewards on it.** The row accumulates a score and is never itself claimed -- `event_love_04_01` stood at 2190 with `complete_time` 0 long after its event ended -- and the rewards are thresholds on that score, counted on the completion record once the first is claimed. Seen on love (from its second instalment), `event_half_year_mission_1`, `event_anniversary_gacha_1`, `event_daily_mission_check_1` and the Sortie's launch event, `event_chaos_assault_1`.

`_step_records` finds them -- a record paired to the event with `reward_step` above 0 -- and `_step_progress` reads the record instead of the row: the steps over themselves with `+?` while nothing else is known, `~7/21` where two finished instalments agree, green on the flag. **Before the first step is claimed there is no record**, and the lone row reads `0/1+?`, which is true: at least one reward, none taken. A finished step track is filed under its steps; filed by its rows, every love instalment held 1.

## Telling a rectangular family from a ragged one

Two mission families can look identical — `event_devil_<day>_<task>` and `event_bartender_1_<page>_<index>` are both a name and two numbers — and mean completely different things. `event_devil_*` is a grid, 3 tasks on each of 7 days, so `max × max` is its total. The bartender's is three pages of different lengths, so `max × max` is nonsense.

`issued_time` separates them, from one snapshot. The game creates a mission row when the mission first becomes relevant, so rows stamped with the SAME SECOND were created by one act of the game. What such a batch varies is the shape:

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

It answers on the event's first afternoon, which is the only time the answer is worth anything. A batch that varies both indices says nothing and is ignored; one clean batch is enough.

**A grid under-reads a Node List until its last index is issued**: `event_nodelist_007`'s came to 8 on its third day, where it held 25, because the batch that made it a grid spanned its pages but only two of its five indices. A grid is this instalment speaking, so it outranks the family's past and the smaller number wins.

### A page is one kind of task

A mission id's middle segment is its page, and each page is one KIND of task. `event_bartender_1`'s, from the `condition_type` an action's `mission_condition` names:

| Page | `condition_type` | Shape | Rows |
| ---- | ---------------- | ----- | ---- |
| `_01_*` | `EVENT_BARTENDER_CLEAR_DAY__ID` | one row per day of the story, issued as each day is played | 7 |
| `_02_*` | `EVENT_BARTENDER_GUESTBOOK_CLEAR` | a ladder, all seven sharing one running score | 7 |
| `_03_*` | `EVENT_BARTENDER_MAKE_COCKTAIL__ID` | a ladder | 10 |

So the total is a sum over pages rather than any product. `_page_totals` counts a page whose rows share one `issued_time` as whole, since one act issued it; a page whose rows trickle in, like the per-day one, is a floor, and so is the sum.

## A finished instalment's rows are its whole total

**A FINISHED instalment's mission rows are its whole total.** The game issues a row when it issues the mission, so a live event's rows are what has been handed out so far — but an event whose window has closed has handed out everything it ever will, and counting its rows is counting the event.

So every load counts the ended events in `event_schedules` and files the figure under the family the instalment belongs to (`_stem` of the normalised id, so `event_schedule_policy_005` files under `event_policy`). `ChecklistManager` keeps it in `settings/checklist.json`, and the recording is the half that cannot wait: **the game purges old instalments**, and a count nobody wrote down while its rows were there cannot be recovered from the wire.

A live event takes its denominator from that record when, and only when:

* **two or more finished instalments of its family agree.** One is a number rather than a pattern — login streaks of 7, 10, 14 and 21 days share one table, and only reading them as one family would make that look like an event changing length;
* **the figure is BIGGER than the rows in hand.** Where the live event has issued more than its predecessors held, the wire is saying so against a record that only remembers, and the rows win.

Such a row reads `~1/20` rather than `1/3+?`: the tilde is the tab's mark for a number worked out rather than read. **It does not go green on it** — `event_achieve_state` is still the only thing that ends an event — so the worst an over-large inherited total can do is leave a finished row looking unfinished.

A step-track instalment is filed under the steps on its record, not its one accumulating row (`_instalment_size`). The record starts empty and fills as instalments end; `python docs/events_replay.py` prints what it would hold after every login on hand.

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

**`event_schedule_devil_001` is the exception.** Its schedule is `event_schedule_devil_001` and its missions are `event_devil_<day>_<task>` — that `01` is DAY one, not the event. So the normalised key `event_devil_1` matched day one's three rows and silently dropped days two to seven, and a 21-reward event read `3/3` with nothing about it looking wrong.

`_event_rows` handles it by trying the STEM — the key without its own index — and taking the extra rows unless another event's key claims them. Three guards, all load-bearing and all pinned:

* **the full key must match something first.** A stem alone is wildly greedy: `event_2` stems to the bare word `event` and would take every event mission on the account, and `event_schedule_chaos_mission_5` stems to `event_chaos` and would take the Sortie's. Neither has a single row under its own key, which is what rules them out.
* **another schedule's key wins.** `event_schedule_policy_004` is still in `event_schedules` long after it ended, so `event_policy_4_*` belongs to it and not to `_005`, which shares the stem.
* **a row issued before every row of the event's own is an earlier instalment's.** An instalment's schedule can go while its rows stay: `event_arena_1_*` outlived its schedule, and the stem took all 23 into arena_2's count, filing one instalment of 17 rewards as 40. A later day of the same event is issued with or after the first -- the devil's grid arrives as one batch on day one -- so `_first_issued` of the event's own rows is the line.

**When adding an event, check this by counting.** The rows the account holds under the family stem, against what the row reports, and against the client's count. They agreeing is the whole test -- and `docs/events_replay.py` runs it over every instalment on record.

### A Node List shares no word with its missions

`event_nodelist_007` owns `event_node_30115_*`: the schedule is numbered by list and the missions by the combatant it features, and nothing on the wire links the two numbers. The client does (`event_nodelist_define`); the program does not read it for this.

What links them on the wire is time. **An instalment's rows are first issued inside its own list's window**, so `EVENT_ROW_FAMILIES` maps the schedule family to the mission family and `_event_roots` gives a list the instalment whose FIRST row its window saw. Later rows of the same instalment are issued days in and prove nothing -- `event_node_30113`'s last rows arrived eight days after its first -- so the first is what places it, and a list with no window takes nothing at all rather than every instalment ever issued.

A list with an achievement page has its missions (four pages of five, `event_node_<id>_<page>_<n>`) and the page (`event_node_<id>_achievement_<n>`), 25 in all: a reward per node, one per stage cleared, each stage's issued as its last node opens. Its completion record, `Clear All Missions`, sits on the achievement page on some lists and on the list itself on others; `_event_records` takes a record at or UNDER the list's instalment, so both count. The story-map lists are shaped otherwise, and how their final reward counts is the one place the client and this page disagree (`client_data.md`).

**Attendance and trial events do not follow this** — their records are numbered in a different space entirely, and `wire_hunt.md` says how each is paired.

## The payloads an event's data arrives in

* **`event/get_list`** is the master payload, sent when the events screen opens. It carries every event entity at once: `event_bartender_entities`, `event_summer_define_entity`, `event_summer_set_entities`, `remnants_entities`, `marble_*`, `story_event_*`, `event_arena_*`. **It carries no trial entity**, which is why the trial slot lists have to be learned. The capture keeps every `event_*` table in it, plus `story_event_entities` and the two `marble_*` tables by name, since nothing about theirs marks them: a table that arrives only at login and was not kept cannot be read later.
* **`event_mission_entities`** arrives with the login's `mission` reply and holds every event mission the account has been issued.
* **`event_mission_reward_entities`** arrives in the same `mission` reply and carries the completion flag above.
* **A claim** answers with the rows it changed, under `entities` — and pays under **`result`**, one of the reward keys (`capture_pipeline.md`, *The item counts arrive once, and change through the reward keys and a sweep*). Watch for it when a claim seems to pay nothing.
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

The command says whether an event is paged. A flat mission list claims with `complete_event_mission_all`; one with reward pages uses `complete_nodelist_event_mission_all`. The bartender uses the nodelist command although it is scheduled under `EVENT_SCHEDULE` and not `EVENT_NODELIST_PAGE`, so the schedule group is not what decides it.

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

The claims share a shape too: a `complete_*_all` or `*_reward_all` command naming the rows (`mission_ids`, `achievement_ids`), answered with the rows it changed -- under the table's own name, the bare `entities`, or a singular `*_entity` -- and paid under `item_result` or `result`.

So a new event's rewards are recognisable before anything else is known about it: a table of rows with `res_id` and `complete_time` is claimable rewards, claimed where the stamp is set.

## Fields only ever seen in the login burst

**This is the hazard that looks like a Checklist bug.** Some event records have never been observed outside the login payload. A capture that stays open all evening still shows what the account looked like at login, so a claim made during it changes nothing on the tab until the next login — and the row is not wrong, it is *old*, which is indistinguishable on screen.

| Field | Seen in | What a mid-session claim sends |
| ----- | ------- | ----------------------------- |
| `attendance_entities` | `load` and `mission` replies at login | **no record at all** — see below |
| `overclock_entities` | the `unlock` reply at login | `result_overclock_entities`, nested under the stage reply's **`return_info`** |
| `event_mission_reward_entities` | the `mission` reply at login | the final reward's claim sends its one row under the bare `entity`; an ordinary reward claim sends nothing |
| `event_mission_entities` | login | its own rows, under the BARE key `entities` — not under its own name. A task that MOVES, its row issued or its score raised, is in the moving reply's `mission_condition.event_mission` and nowhere else until the next login; merged, never over a claim's `complete_time` |
| `event_summer_set_entities` | the `event/get_list` payload | the one row that changed, under the SINGULAR `event_summer_set_entity` |

### A Daily Check-in claim's reply

`attendance / reward` with an `event_id`, and the reply names no entity:

```
{"completed": false, "event_id": "event_143",
 "received_days_before": 5, "received_days_after": 6,
 "reward_list": [{"count": 1, "res_id": 2000023}], "item": {...}}
```

So there is nothing to merge: the cached row is patched from `received_days_after`, and the next login sends the real record.

And the reward rides in `item`, a top-level totals envelope like any other — not in `reward_list`, which states the same payout as a delta beside it. A key that generic is guarded by its shape rather than trusted by its name; `capture/manager` takes it with `result`. Without that, a login event's reward reaches neither the Capture Log nor the item counts.

**`completed` is the game's own word on the wire that the streak has ENDED.** Captured on the claim that finished `event_143`: `received_days_before: 6, received_days_after: 7, completed: true`. The addon keeps it on the row AND across the login that follows — the row that login sends is identical to a streak merely claimed for today, so letting it win would lose the answer for good.

### A streak's record

What the record states exactly:

| Field | Is |
| ----- | -- |
| `current_days` | days shown up for |
| `received_days` | days claimed |
| `last_dayid` | the last day the streak ADVANCED — **the LOGIN, not the claim.** The record read `2/1/1348` and then `2/2/1348` across a claim |

So the row reads claimed against claimed-plus-one, red where `current_days` is ahead and orange where it is level. **One claim advances the streak by exactly one** — `received_days_before` to `received_days_after` — and the record has never been caught more than one apart. Once a streak is over, `current_days`, `received_days` and the span between `start_dayid` and `last_dayid` are all its length; before that, only the client's check-in table says how long it runs.

**`event_daily_1`, the launch login event, is the exception**: its schedule runs a year, and its `received_days` sits at 7 while `current_days` climbs, so off the wire it looks like a streak permanently one day behind. Nothing in the record tells the two apart, and it is never claimed: the client knows from its check-in table that the seven days are all there is, and the program has it as a write-down (*A total written down*).

### The completion flag's source

`mission / reward_event_limit` with an `event_mission_id` — the claim of the final reward that unlocks only once every other has been taken. Captured on `event_bartender_1`:

```
{"item_result": {"items": {"9700001": ..., "9700002": ...}},
 "entity": {"res_id": "event_bartender_1", "event_achieve_state": 1}}
```

Under the bare key `entity`, which is also what a Combatant Trial claim answers under with a different row — so the addon takes it only when `event_achieve_state` is on it. Read as only the three spelled-out keys, the one reply that ever carries a completion is dropped, and a finished event goes on reading `24/24+?` with the wire having said outright that it is finished.

### A completion is kept by the server; a streak's is not

Captured by logging in after finishing both, and the two answers differ:

* **`event_mission_reward_entities` comes back with it.** The login sent the new row, `event_bartender_1` with `event_achieve_state: 1`, `reward_step: 0`, `version: 0`. So a completion is the server's own record and arrives at every login — an event once finished stays finished across restarts, with nothing client-side needed.
* **`attendance_entities` does not.** The finished streak came back as `current_days: 7, received_days: 7` with no `completed` anywhere. That flag exists only in the reply to the claim that ends the streak.

So the addon's copy of `completed` carries the answer through the session that saw the claim, and the program keeps its own across sessions: `ChecklistManager.remember_streak` files the event id in `settings/checklist.json` and `_recall_streaks` writes the flag back onto the login's row. Without that record a finished streak reads orange from the next start until its event ends — the honest answer for a row that cannot be told from one merely claimed today, and not the true one.

### The defences

Both in `capture/manager.py`, and both are the general rule rather than anything about these two fields:

* **merge by id, never replace.** A one-row payload updates its own row and leaves the rest alone. A wholesale assignment looks right on every capture ever taken and wipes the list the first time a partial one arrives.
* **look under `return_info` as well as at the top level.** A stage reply nests its whole outcome there. Reading only the top level is indistinguishable from the wire being silent, which is exactly how the Overclock row was misread.
* **accept all four spellings** — `x_entities` (list), `result_x_entities` (list), `x_entity` (one record) and, for a completion, the bare `entity`. The singular is the ROW THAT CHANGED and belongs folded into the collection, not kept beside it: a second copy under a near-identical name is one more thing for a reader to pick the wrong one of. **`entity` is shared with the Combatant Trial claim**, which puts a different row under it, so the presence of `event_achieve_state` is what says which is which. `checks/check_capture_event_state.py` holds all four plus the shapes above.

### Reading a capture for whether anything mid-session landed

Scan the saved snapshot for records stamped AFTER the session's own login — `attendance_entities[].last_time` is that login, since the streak is touched by logging in.

**The point is to separate a dead capture from a field the reader misses**, and they look the same from the tab. A capture is demonstrably live when `inventory.service_server_time` and a currency balance's `last_update` move during the session; a streak and an Overclock row still carrying their login values beside them are a claim that sends no record and a row nested one level down. **When a row will not move, capture the ONE action that should move it and read the reply whole**, rather than diffing snapshots.

## Processing a new event

Every event row needs the same three answers -- rewards claimed, rewards held, and whether a final reward is still owed. The work for a new event is finding which shapes it is, from as few captures as possible.

1. **Look it up in the client first.** `python docs/client_tables.py --text "<words of its name>"` finds its `event@title` id, and `--table event@event` its row: its kind, its schedule, and the tables its rewards are counted in (`docs/client_data.md`, *Where each fact is*). That gives the total and whether a final reward follows, which every step below is checked against.
2. **Log in once, with a capture running.** The login burst carries the schedule, `event/get_list` and `mission/get_list`, and the capture keeps every table in them the readers could want.
3. **Open the event, do ONE thing that moves a mission, and claim ONE reward.** Note the time. The action's `mission_condition` names the family's rows and what each is for; the claim shows its command and where it pays. `wire_hunt.md` has the diffing recipe.
4. **Pair it.** `python docs/events_replay.py <a word of its id>` shows what the row reads at every login; `[]` means no rows were paired. Missions named after something the schedule does not carry go in `EVENT_ROW_FAMILIES`, the way a Node List's combatant does; missions under a fixed name unlike the schedule go in `EVENT_MISSIONS`.
5. **Recognise its shape:**

   | Shape | How to tell | Claimed | Held, off the wire | Final reward |
   | ----- | ----------- | ------- | ------------------ | ------------ |
   | Mission ladder | rows with `res_id` and `complete_time` under the event's key | rows with a `complete_time` | a grid, pages issued whole, the family's history, else a floor | the completion record, once claimed |
   | Step track | ONE row whose `score` climbs and never gets a `complete_time`; a record with `reward_step` above 0 after the first claim | `reward_step`, read as a tally | the family's history | the same record's flag |
   | A table of its own | a new `event_*` table in `event/get_list`, or a named one like `story_event_entities` | whatever its rows stamp -- one claim shows which field moves | its row count, only if it did not move between two logins a day apart | -- |

   Streaks, trials and Overclock events have shapes of their own, each under its own heading above.
6. **Watch for a final reward** where the client says there is one: claim it with a capture running, and `mission / reward_event_limit` answering under `entity` confirms it. The family is remembered from then on, and its next instalment reads the final as waiting until it is claimed.
7. **Decide its categories and its reader** -- there may be more than one category. **If in doubt it is Open-ended**, the safe answer: a floor with `+?` that never claims completion. Add the group to `EVENT_CATEGORIES` and `EVENT_READERS`; a new event in a group that already has both needs no edit, which is the point of keying on the group.
8. **Check what it reads against *Fields only ever seen in the login burst*.** A record that arrives only at login needs its claim shape captured before the row can be trusted to move mid-session.
9. **Replay it** with `docs/events_replay.py`: the reading should move at the logins where the game did, and end at the client's total.

## Still open

* **`reward_step` vs `version`.** Read as a tally on the evidence under *`reward_step` and `version`*, which also says how the next live step track settles it against the client's size.
* **Rhythm games, the Disaster Marble, Trauma Codes and the collab coupon read nothing.** Their schedules share no word with their records (`ds_s3_event_rhythm_game` owns `event_rhythm_*`; `marble_s01` keeps its ladder in `marble_achievement_entities`), and each is one instalment on record, too few to pair by rule.

Settled, and kept so they are not re-suggested:

* **Event display names** are the game client's, since the wire never sends one: `docs/client_data.md`. The game's update notes (`page.onstove.com/chaoszeronightmare/en/list/142421`) name every event with its schedule, and usually its reward table.
* **A streak's length, and the launch login event's**, are in the client's check-in table. Off the wire, nothing tells the launch event from a streak one day behind: it is never claimed, a day left unclaimed looks the same in the record, and `reddot_info` names no event.
* **The Completed Events tab is entirely client-side.** Opening the event list screen after finishing several events sent NOT ONE request. Whatever the client sorts in there, it decides from the records the login already gave it.
* **`event_bartender_entities`** is the GUESTBOOK, not the reward pages, and it fills in as the days are played. One row per day, three completion stamps each.
* **`event_info_entity`** is `{"open_day": 1}` under a different `event_id`: the furthest day opened. Nothing in it is a total.
* **A third id space.** The mission commands name an event by a bare number — `event_142` is `event_devil_*`, `event_143` the login streak, `event_146` is `event_bartender_1` — alongside the schedule's `event_schedule_devil_001` and the reward record's `event_bartender_1`. It is `event@event`'s own id in the client. Every reader pairs on the normalised key instead.
* **The message that unlocks when an event's rewards are all claimed** is most likely client-side and not on the wire at all. It is an EVENT screen's own message rather than anything in `messenger_entities`, which is the separate Combatant messenger. Nothing needs it: `event_achieve_state` names the event outright and arrives on the claim.
* **`mission_event_node_list_story_node_entities`** and **`story_event_node_list_entities`** look like define lists, long and whole for an event long finished, but they are the account's own records, complete only because the event was completed. They say nothing about a live one.
