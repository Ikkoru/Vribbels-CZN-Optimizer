# Events: how to read one, and what the Checklist does with it

Read this before touching the Events block of the Checklist tab, or before adding an event nobody has mapped. `wire_hunt.md` holds the general techniques for pairing wire payloads; this holds what is known about events specifically.

The code is `ui/tabs/checklist_tab.py`: `EVENT_GROUPS` says which schedule groups are listed, `EVENT_CATEGORIES` says what kinds each is (a set — see below), `event_is` asks whether a group is one of them, and `EVENT_READERS` says which function reads it.

## The three questions, in order

Answer them in this order for any event. Each one is cheap and rules out work on the next.

1. **When does it end?** `event_schedules` dates every event, so this always has an answer, and it alone is a useful row. An event nobody has mapped still shows its deadline.
2. **How much is done?** Usually a count of records carrying a claim stamp.
3. **How much is there altogether?** The hard one. Get this wrong and the row lies — see *Floors* below.

## The categories

**An event is usually several of these at once**, so a group's entry in `EVENT_CATEGORIES` is a SET rather than one value. An Overclock event is both Generic and Forced Daily, and the two say different things about it.

| Category | What it is | How to tell | What the row does | Colour when full |
| -------- | ---------- | ----------- | ----------------- | ---------------- |
| **Tallied** | its total is knowable | a stated total, or one derived from something dated | claimed / total | **green** |
| **Generic** | a Tallied event that comes back later largely unchanged | the same event id family has run before, with the same shape | as Tallied | **green** |
| **Forced Daily** | its rewards refresh each day of its run and are lost if not taken that day | its record carries a `reset_time` that rolls daily | counts the DAY, not the event | **orange** |
| **Open-ended** | only a floor is knowable | rows are issued as the event hands them out, so the denominator grows | claimed / rows held | red; **orange** after 48h unmoved |
| **Unmapped** | nothing known about its progress | no entry in `EVENT_READERS` | deadline alone | — |

Generic **implies** Tallied — it is a Tallied event with a second property — and `event_is` applies that so the table need not say it twice.

### Why Generic is worth naming

**Anything about a Generic event that resists derivation may be written down.** It is the one kind of hardcoding that does not go stale: the event returns with the same shape, so the number is right next time too. `OVERCLOCK_USES = 2` is the example.

The cost is a standing obligation to notice if the game changes it — older Overclock events ran at six a day rather than two, so it HAS changed before. Say so at the constant.

### Why Forced Daily is orange, not green

Claiming everything on offer does not finish a Forced Daily event: tomorrow brings more, and today's are gone whether or not they were taken. A green row means "nothing left to think about", which would be wrong for the rest of the run — so a finished day reads orange.

This is a different orange from the Open-ended one. Nothing here is unproven; the day is genuinely complete and the category alone says so, with no 48-hour settling involved.

### Members so far

| Group | Categories | Where its progress lives | Notes |
| ----- | ---------- | ------------------------ | ----- |
| `EVENT_OVERCLOCK` | Generic, Forced Daily | `overclock_entities[event id]` | doubled Simulation runs, `count` per day against a cap of 2. Older events of this kind ran at 6, and the cap is not on the wire — see the Generic warning above |
| `EVENT_DAILY_CHECK` | Tallied | `attendance_entities` | a login streak. The attendance row is the FIRST one started after the event was — the ids do not match |
| `EVENT_COMBATANT_TRIAL` | Tallied, Generic | `combat_trial_entities` | three trials per combatant banner sharing the event's window |
| `EVENT_SCHEDULE` | Open-ended | `event_mission_entities` | the catch-all: story events, seasonal events, the bartender |
| `EVENT_NODELIST_PAGE` | Open-ended | `event_mission_entities` | same shape |

## Floors, and the one wrong answer

**A count of the rows the account holds is a FLOOR, not a total.** The game creates a mission row when it issues the mission, so an event still handing them out reads as finished:

* the devil event read `3/3` on its first afternoon against a real 21 — three tasks a day for seven days;
* a summer event read `12/12` with a third wave unissued.

So an Open-ended row **never goes green**, and its reading is marked `FLOOR` in the code to say why. Saying "done" when it is not is the one answer a checklist must never give: it costs the user the reward.

After 48 hours at its own ceiling a floor turns **orange** — long enough that an event still handing out rewards daily would have moved it. Reading anything new restarts that clock, and a row below its ceiling never settles, because that is work outstanding rather than an unanswerable question. The record lives in `settings/checklist.json`; when a row last moved is a fact about the past and a snapshot holds only the present.

## Totals the wire does not state

Recorded here rather than in the code. **A total typed into the program is wrong the moment its event ends** — unless its event is Generic, which none of these is. These are for working out the pattern, not for shipping.

| Event | Total | How it is built | Derivable? |
| ----- | ----- | --------------- | ---------- |
| `event_schedule_devil_001` | 21 | 3 tasks/day × 7 days; ids are `event_devil_<day>_<task>` | `max(day) × max(task)` gives 21 — but see below |
| `event_bartender_01` | 24 | three reward pages of 7, 7, 10 | **no**: `max × max` gives 18. The pages are ragged and nothing in the ids says so |
| `event_summer_01` | 10 rewards, 84 items | one reward per 8 items fitted into puzzles | **no**: neither the rate nor the 84 nor any per-reward flag is on the wire, and 84 ≠ 10×8, so the last rewards are not evenly spaced |

**The open problem is telling a rectangular family from a ragged one.** The devil case shows the derivation that would work; the bartender case shows why it cannot be applied blind.

## Naming, and how to find an event's records

An event's schedule id and its records' ids differ, but only in decoration. `checklist_tab._event_key` strips the words `schedule` and `mission` and the zero padding, after which they match:

```
event_schedule_policy_005  ->  event_policy_5_*
event_summer_01            ->  event_summer_mission_01_*
event_schedule_love_4      ->  event_love_04_*
event_stock_01             ->  event_stock_1_01_*
event_schedule_devil_001   ->  event_devil_01_*
```

Matching is on a segment boundary, so `event_daily_1` cannot swallow `event_daily_12`'s rows.

**Attendance and trial events do not follow this** — their records are numbered in a different space entirely, and `wire_hunt.md` says how each is paired.

## Where an event's data arrives

* **`event/get_list`** is the master payload, sent when the events screen opens. It carries every event entity at once: `event_bartender_entities`, `event_summer_define_entity`, `event_summer_set_entities`, `remnants_entities`, `marble_*`, `story_event_*`, `event_arena_*`. **It carries no trial entity**, which is why the trial slot lists have to be learned.
* **`event_mission_entities`** arrives with the login's `mission` reply and holds every event mission the account has been issued.
* **A claim** answers with the rows it changed, under `entities` — and pays under **`result`**, which is the fourth key the wire uses for a rewards payload and the one that was missed. Watch for it when a claim seems to pay nothing.

Claim commands seen so far, all naming the event and the records together:

| Command | Names |
| ------- | ----- |
| `mission / complete_event_mission_all` | `event_id` (or `event_mission_define_id`) and `mission_ids` |
| `mission / complete_nodelist_event_mission_all` | `event_id` and `mission_ids` |
| `event_combatant_trial / reward_combatant_trial` | the trial event AND the slot — the only place the two meet |
| `hyperspace / get_star_reward` | the Basin season, answering with `reward_doc` |

## Adding an event nobody has mapped

1. Watch it for a capture: open the event, claim one reward, note the time. `wire_hunt.md` has the diffing recipe.
2. Find where its progress lives — a `*_entities` collection, or mission rows under the normalised id.
3. Decide its categories — there may be more than one. **If in doubt it is Open-ended**, which is the safe answer: it shows a floor and never claims completion.
4. Add the group to `EVENT_CATEGORIES` and `EVENT_READERS`. A new event in a group that already has both needs no edit at all — that is the point of keying on the group.

## Still open

* **The Completed Events tab.** The game has one, so the client decides completion for at least some events — and it must decide BEFORE the tab is opened, to know what to sort in there. So a capture of opening it would most likely show no request at all, and the totals are client-side, in the same place the trial slot lists live. Worth one capture to confirm, but do not expect it to pay.
* **`event_bartender_entities` stays `{}`** even after claiming, so the bartender's pages are invisible. Claiming on a page never touched might populate it.
* **Event display names.** Every row shows an id, because the wire never sends a name — the client has them in a localisation table.
