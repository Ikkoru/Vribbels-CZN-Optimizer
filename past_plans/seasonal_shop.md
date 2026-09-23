# The Galactic Disaster's shop on the Checklist — [IMPLEMENTED] 2026-09-23

The season-long shelves are the tab's fifth column, `SEASONAL_COLUMN` in `checklist_tab.py`. One row per offer with the three pages folded together, a heading that counts the season down, a tooltip giving what the season has paid against what a whole one is estimated to, and a row that goes orange when everything on sale has been bought.

Kept for the measurements, for two inferences that are not stated anywhere on the wire, and for the orderings that were tried and rejected.

## What the wire does not say, and what stands in

Three things the Checklist needed and no payload carries. Each is written up where the code that depends on it lives; this is the index.

| Question | Answer, and where it comes from |
| --- | --- |
| How many rewards has a login event? | Nothing states it — not the schedule, not the row, not the claim. Two events run 21.0 days and pay 7 and 15. `ATTENDANCE_FLOOR` floors the ceiling at seven, the shortest any of twenty-four finished at. |
| What does a season pay in total? | Nothing states it: every achievement payload is progress, never a reward. Hand-counted per season in `SEASON_ESTIMATE`; `docs/wire_hunt.md` has the search that settled it. |
| Which of the shop's three pages is open? | Nothing states it, and `shop_res_data` sends all three from the season's first login. Read off the SORTIE rotations inside the season: the first is the preseason, each one after opens a page. |

**The page inference is confirmed by the purchase record**, which stamps `reset_time` on every buy: the first purchase on page two lands at 2026-08-19 13:14 with nine more inside ten minutes, on page three at 2026-09-09 12:26 with ten, against rotations opening 08-19 01:00 and 09-09 01:00. That is somebody shopping the hour a page opened.

**It is wrong for a season whose parts are not one rotation long.** Season 3 ran 28 days and then two of 21, so its pages would be dated a week out. The cost is the colour of a row, which is why the inference was worth making.

## Measurements

| | |
| - | - |
| Season 4 | 61 products, 59 of them season-long, **29 rows** — 27 items, two of them sold at two prices |
| Season buyout | **267,000**, summed per product |
| Why per product | `3100002` and `3100022` are priced 30, 30 and 120 across the pages, so one price times a summed cap is 40,900 short |
| Merge key | the item, `product_count` and the PRICE |
| Tear of God | `LIMIT_WEEK`, so the season-long shelf never held it; no per-shop hiding was needed |
| Season length | The EVENT runs 63 days (s03: 70). `DISASTER_SEASON`'s window reads 84 because it opens 21 days early, through a preseason with no shop and no currency |
| Handover | 21 days from one season's content ending to the next one's shop opening, at every handover the account has seen |
| Pages open | s04: 07-29, 08-19, 09-09 |
| Currency | One item id per season: `3920001` s01, `3920002` s02, `3920006` s03, `3920031` s04 |
| Earned per season | s01 157,660 · s02 168,510 · s04 175,490 and running. s03 unrecoverable — only a mid-season capture survives |
| A Chaos run | Mean 562 over six whole runs, 344 to 810. `_tmp/chaos_runs.py` keeps the record and is where new runs go |

**A run's take is measured through the addon's own cache, not off the wire.** Counting the wire's deltas over-counts about sevenfold: `drop_item` under a `battle/reward_complete` is the reward MENU being offered, `drop_item_info` under the merchant is a price list, and the clear's envelope restates the whole run rather than adding to it. Two bosses and the Core of Discord pay a fixed 420; the rest is which modifiers the run rolled.

## Rejected

**A rate from lifetime earnings**, the way every other shop's tooltip works. The currency is wiped each season, so a lifetime total spans several wipes and last season's says nothing about this one. The play-pattern estimate replaces it, and that is why this one tooltip is bespoke.

**A second estimate at another rate of play.** Every term but the runs is fixed, so two lines moved together and read as a range the numbers could not support.

**Hand-placing Core of the Reverse.** The pages fold together by keeping every row a page shares and putting each row it ADDS just above the row it precedes on its own page — which reproduces the maintainer's own reading of the shop except for that one item. Page 3 lists it first, so putting it below Abyssal Core and Core of Potential contradicts page 3's own order; no rule over the `sort` fields can produce it, and a hand-kept list of exceptions would need reviewing every season.

**Bottom-aligning the shelves inside the `Other` column**, which is where they first went. A season's shop is a season's worth of rows: it clipped six of them at the default window size and thirteen at the minimum. A column of its own fits the lot.

**`spot_type` as the label for where a run's currency came from.** Three `SPOT_TYPE_ELITE` floors in one run paid nothing while a fourth paid 60 — what earns it is a modifier on the monster, which the wire never names. The column in `chaos_runs.tsv` is kept because it is what the wire does say, not because it explains anything.

## Left open

- **Season 5 needs its own `SEASON_ESTIMATE` entry**, hand-counted, or the shop's tooltip shows no estimate. A season the table does not name is silent rather than wrong, so forgetting is safe.
- **No capture covers part 1 of a season**, so nothing can be said about what its runs pay.
- The five columns leave about 11px between them at the default window, and a window under ~1,500 clips the right-hand one. The columns are fixed-width and the grid cannot shrink them, so it clips rather than reflowing; `check_tabs_build` watches that they fit the default size.
