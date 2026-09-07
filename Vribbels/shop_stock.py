"""What each shop sells, and what is left to buy of it.

Two payloads, and both are needed:

* **`shop_res_data`** is the shop's own DEFINITIONS, one per product:
  what item it gives (`product_link_item_id`) and how many
  (`product_count`), the per-period cap (`limit_count`), which period
  (`limit_type`), the price (`price_link_item_id`, `price_count`), and
  the shop's display order (`sort`). Sent once at login.
* **`shop_list`** is what the ACCOUNT has done with them, one row per
  product: `{count, reset_time, total_count}`.

All three of a row's fields are settled, by a capture that bought the
same product twice in separate purchases and read the shop's own figure
either side:

* **`count` is how many were bought in the CURRENT PERIOD**, so what is
  left is `limit_count - count`. Two purchases of `town_shop_goods_014`
  took it 0 -> 1 -> 2 while the shop read 20/20 -> 19/20 -> 18/20.
* **`total_count` counts UP for the life of the account**, +1 per unit.
* **`reset_time` is written on every PURCHASE**, not on the period
  boundary. It is the last time `count` moved.

**`count` is reset LAZILY, and that is the trap.** A row nobody has
bought from since the period rolled over still carries the previous
period's tally: `town_shop_goods_014` read 20 hours after the weekly
reset had refilled it, and only the next purchase took it to 1. So a
`count` whose `reset_time` predates the current period means NOTHING
BOUGHT, not a shop bought out -- and reading it straight draws a full
shop as empty.

`period_start` is what tells the two apart. The weekly boundary comes
from `weekly_reset`; the monthly one is on the wire as `month_start`,
because the month rolls at 18:00 UTC on the LAST day and cannot be
derived from a date.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

import weekly_reset

DEFINITIONS_FIELD = "shop_res_data"
STOCK_FIELD = "shop_list"
MONTH_START_FIELD = "month_start"

# The wire's shop category -> what the game calls it. **A shop absent
# here gets no rows**, which is what keeps the tab to the shops the
# maintainer tracks rather than every product table the login sends.
SHOPS = {
    "shop_town": "Nono's Shop",
    "shop_gacha_dup": "$hop - Memory Archive - Traveler",
    "shop_hyperspace": "$hop - Zeronium Shop",
    "shop_chaos": "$hop - Blackhorn Trade",
    "shop_exchange_product": "$hop - Exchange Shop - Prism Module",
    "shop_disaster": "Seasonal Shop",
    "shop_assault": "Sortie - Chaos Analysis Lab",
}

# The wire's `limit_type` -> which Checklist column the product belongs
# in. **`NONE` is absent on purpose**: a product with no cap has nothing
# to count down and nothing to finish, so it is not a checklist row.
#
# `LIMIT_ACCOUNT` is a LIFETIME cap that never refreshes -- the Sortie
# shop is all of it, and the Blackhorn 400 -- so it sits under Other
# rather than under a period.
PERIOD_BY_LIMIT = {
    "LIMIT_WEEK": "weekly",
    "LIMIT_MONTH": "monthly",
    "LIMIT_ACCOUNT": "account",
}

# How long each period runs, for a `count` old enough to be last
# period's. `account` never rolls, so its tally is always current.
NEVER_ROLLS = ("account",)


def definitions(raw_data):
    """{category: {product id: definition}} from a snapshot."""
    out = (raw_data or {}).get(DEFINITIONS_FIELD)
    return out if isinstance(out, dict) else {}


def stock(raw_data):
    """{product id: the account's row} from a snapshot."""
    out = (raw_data or {}).get(STOCK_FIELD)
    return out if isinstance(out, dict) else {}


def products(category, period, raw_data):
    """[(product id, definition)] in one shop and one period, in order.

    Sorted by the shop's own `sort`, which is the order the game lists
    them in. A product with no cap is left out: `PERIOD_BY_LIMIT` has
    no entry for `NONE`.
    """
    rows = []
    for product_id, define in definitions(raw_data).get(category, {}).items():
        if not isinstance(define, dict):
            continue
        limit = define.get("limit_count")
        if PERIOD_BY_LIMIT.get(define.get("limit_type")) != period:
            continue
        if not isinstance(limit, int) or limit <= 0:
            continue
        rows.append((product_id, define))
    return sorted(rows, key=lambda pair: (pair[1].get("sort", 0), pair[0]))


def period_start(period, raw_data, now):
    """When the current period began, epoch seconds, or None.

    A period that never rolls has no boundary, so 0 serves -- every
    tally is current. The monthly boundary is the wire's own
    `month_start`; without it there is no honest answer.
    """
    if period in NEVER_ROLLS:
        return 0
    if period == "weekly":
        # The reset BEFORE now: `next_reset` looks forward.
        return weekly_reset.next_reset(now) - 7 * 24 * 3600
    start = (raw_data or {}).get(MONTH_START_FIELD)
    return start if isinstance(start, int) else None


def remaining(product_id, define, raw_data, now):
    """(left to buy, cap), or (None, cap) where it cannot say.

    None is a reading, not a failure. Three ways to get one: the
    snapshot never carried the product's row, the row's `count` is not
    a number, or the boundary its period is measured from is unknown.

    A `count` last touched BEFORE the period began is not stale data to
    reject -- it is last period's tally, which says the shelf is full.
    """
    limit = define.get("limit_count")
    if not isinstance(limit, int) or limit <= 0:
        return None, None
    row = stock(raw_data).get(product_id)
    if not isinstance(row, dict):
        return None, limit
    count = row.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        return None, limit
    started = period_start(
        PERIOD_BY_LIMIT.get(define.get("limit_type")), raw_data, now)
    if started is None:
        return None, limit
    touched = row.get("reset_time")
    if _is_time(touched) and touched < started:
        return limit, limit
    return max(0, limit - count), limit


def _is_time(value):
    """True for something comparable against an epoch second.

    A float counts; `bool` does not, being an int that would compare as
    0 or 1 against a timestamp and mark every row stale.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)
