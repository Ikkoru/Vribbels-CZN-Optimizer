# The wire hunt: what the Checklist still needs, and where it might be

A worklist, not a reference. Every Checklist row that shows no value is here with the fields that could carry it, what the account read at the time, and how confident the match is. A row leaves when it is CONFIRMED and the code reads it; a suspect leaves when a capture rules it out.

`docs/wire_hunt.tsv` is the same thing in a form that sorts and filters, and it is **hand-maintained** -- no script rewrites it, so an edit cannot be lost to a regeneration. This file says how to read it.

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

`shop_list` is 222 rows keyed by product id, each `{count, reset_time, total_count}`. Three things are established:

- **`total_count` counts UP, for the life of the account.** Buying one moved it by exactly one, twice.
- **`reset_time` is written on every purchase**, not on the shop's period boundary: it came back as the server time of the buy in all three purchases.
- **`count` is NOT the stock remaining.** It survived a purchase unchanged twice, and one row read 5 before a purchase and 1 after.

**What `count` IS remains open**, and it is the field the Checklist needs. The reading that fits every row so far is "purchases made in the current period, reset LAZILY on the next interaction" — under it, a row untouched since last month carries last month's tally and the client works out the stock from `reset_time` against the shop's own period. That is a hypothesis with one supporting observation, not a finding. **What would settle it**: capture a shop row's `count` immediately before and after a period rolls over without buying anything.

Product ids seen so far: `town_shop_goods_*` is Nono's Shop, `gacha_duplicate_legend_*` the Memory Archive Traveler exchange, `chaos_*` / `disaster_s0*_*` / `hyperspace_*` / `assault_shop_product_*` / `season_pass_*` the rest.

## What is still missing entirely

**The Great Rift weekly score reaches the wire and the addon does not keep it.** `disaster_boss_rank_entities` is cached, so the score IS in the snapshot; nothing reads it yet. See `game_data/constants.py`.

**Nothing carries a shop's PERIOD.** `shop_res_data` names products and prices; which of them reset weekly and which monthly has not been found, and the Checklist's Monthly column needs it.
