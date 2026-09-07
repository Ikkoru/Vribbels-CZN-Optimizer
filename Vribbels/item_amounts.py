"""How much of each item a snapshot says is held, by res_id.

**Two sources under one reading.** `inventory.items` is a list, each
entry carrying its own `amount`; the generic materials are CURRENCIES
and live in `characters.currencies`, a dict keyed by the res_id as a
STRING. A reader taking only the first reports 0 for a currency however
many are held, with nothing to say it went wrong.

Period items are in neither, because they carry no amount at all --
their copies are listed, each with its own expiry. `period_items.py`
reads those.

No Tk and no managers: this takes the snapshot dict and returns data.
"""


def held(raw_data):
    """{res_id: amount} across both sources, ints throughout.

    A malformed entry is skipped rather than raising: this feeds
    panels, and an id reading 0 is what "none held" looks like anyway.
    """
    out = {}
    inventory = (raw_data or {}).get("inventory") or {}
    for item in inventory.get("items") or []:
        if not isinstance(item, dict):
            continue
        res_id = item.get("res_id")
        if isinstance(res_id, int):
            out[res_id] = item.get("amount", 0)
    currencies = ((raw_data or {}).get("characters") or {}).get(
        "currencies") or {}
    for key, record in currencies.items():
        try:
            out[int(key)] = record.get("amount", 0)
        except (AttributeError, TypeError, ValueError):
            continue
    return out
