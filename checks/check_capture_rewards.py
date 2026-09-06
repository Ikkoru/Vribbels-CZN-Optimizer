"""What the game gives you has to reach the cached counts.

The inventory arrives ONCE, in the login burst. Every later change to an
item or a currency rides on the reply to whatever caused it, and there
are TWO shapes of that:

  * `add_result`, `item_result` and `dec_result` state what a holding
    NOW IS -- `doc` is the item's whole record and `doc.amount` the
    total, not the change. Written in rather than added to, so a frame
    seen twice cannot double a count.
  * `drop_item_result` is a stage's rewards, and states only what each
    drop GAVE: a list with one entry per drop, no record and no total,
    so a x6 run sends six entries for one item. Adding is the only
    option, which is why the qid is remembered -- a repeat would
    double it.

A capture that reads neither keeps serving the counts the account had
when the game was started: the Materials tab reads a stale number, no
snapshot is written, and no line reaches the Capture Log, so nothing
anywhere says the figures stopped moving.

Driven through `_generate_addon_script` rather than the template alone:
the log line names items through a table the generator injects, and a
global the addon reads but the generator stops supplying raises only
when a reward actually arrives.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture applies rewards"

# The shape a real reward carries, read off a debug capture: one item
# and one currency, each with its whole record under `doc`.
ITEM_ID = 3300013
CURRENCY_ID = 2000001


class _Message:
    def __init__(self, text):
        self.from_client = False
        self.is_text = True
        self.text = text
        self.content = text.encode("utf-8")


class _Flow:
    def __init__(self, message):
        self.websocket = type("_WS", (), {"messages": [message]})()


def _build_addon(output_dir, log):
    """The real generated addon, built the way a capture builds it."""
    from capture.manager import CaptureManager

    manager = CaptureManager(output_dir, log_callback=lambda *_a, **_k: None)
    script = manager._generate_addon_script()
    namespace = {"__name__": "_generated_addon_under_check"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    addon = namespace["addons"][0]
    addon.log_callback = lambda *args, **kwargs: log.append(args[0] if args else "")
    return addon


def _reward(item_total, currency_total):
    return {
        "res": "ok", "qid": 42,
        "add_result": {
            "items": {str(ITEM_ID): {
                "doc": {"res_id": ITEM_ID, "amount": item_total, "version": 1},
                "diff": 1}},
            "currency": {str(CURRENCY_ID): {
                "doc": {"res_id": CURRENCY_ID, "amount": currency_total,
                        "version": 2},
                "diff": 50000}},
        },
    }


def run():
    failures = []
    add_source_to_path()

    login = {
        "res": "ok", "qid": 8,
        "piece_items": [{"id": 1, "char_res_id": 0}],
        "items": [{"res_id": ITEM_ID, "amount": 49, "version": 0}],
    }
    roster = {
        "res": "ok", "qid": 4,
        "characters": [{"res_id": 1003, "friendship_exp": 0}],
        "currencies": {str(CURRENCY_ID): {"res_id": CURRENCY_ID,
                                          "amount": 660439}},
    }

    log = []
    # A temp dir, never `snapshots/`: the addon writes one as soon as it
    # has inventory data.
    with tempfile.TemporaryDirectory() as tmp:
        addon = _build_addon(Path(tmp), log)
        addon.websocket_message(_Flow(_Message(json.dumps([login, roster]))))
        log.clear()
        addon._save_pending = False

        addon.websocket_message(
            _Flow(_Message(json.dumps(_reward(50, 710439)))))

        held = {row.get("res_id"): row.get("amount")
                for row in addon.inventory_data.get("items", [])
                if isinstance(row, dict)}
        if held.get(ITEM_ID) != 50:
            failures.append(
                f"after a reward of one, the cached item read "
                f"{held.get(ITEM_ID)} rather than the 50 the server "
                f"reported. Nothing else on the wire carries an item "
                f"count, so whatever is cached here is what every tab "
                f"shows until the game is restarted.")

        currencies = addon.character_data.get("currencies", {})
        if currencies.get(str(CURRENCY_ID), {}).get("amount") != 710439:
            failures.append(
                f"the cached currency read "
                f"{currencies.get(str(CURRENCY_ID), {}).get('amount')} "
                f"rather than 710439. Currencies are kept apart from the "
                f"item list -- see `MaterialsTab.refresh_materials` -- so "
                f"they need applying on their own.")

        if not addon._save_pending and not list(Path(tmp).glob("*.json")):
            failures.append(
                "a reward left no save pending. The counts moved in "
                "memory and nothing wrote them out, so the tabs keep "
                "reading the snapshot from before the reward.")

        if not any("Received" in line for line in log):
            failures.append(
                f"a reward wrote nothing to the Capture Log; it logged "
                f"{log}. A change with no line is indistinguishable from "
                f"a capture that has gone quiet, which is exactly how "
                f"this was noticed missing.")

        # The same frame again. `doc.amount` is a total, so nothing moves.
        addon.websocket_message(
            _Flow(_Message(json.dumps(_reward(50, 710439)))))
        held = {row.get("res_id"): row.get("amount")
                for row in addon.inventory_data.get("items", [])
                if isinstance(row, dict)}
        if held.get(ITEM_ID) != 50:
            failures.append(
                f"a repeated reward frame took the item to "
                f"{held.get(ITEM_ID)}. `doc.amount` is the total the item "
                f"now stands at -- adding `diff` to what is cached is "
                f"right until a frame arrives twice, and then it is "
                f"wrong for good.")

        # An id held by nobody yet has no row to update.
        addon.websocket_message(_Flow(_Message(json.dumps({
            "res": "ok", "qid": 43,
            "add_result": {"items": {"999999": {
                "doc": {"res_id": 999999, "amount": 3}, "diff": 3}}},
        }))))
        held = {row.get("res_id"): row.get("amount")
                for row in addon.inventory_data.get("items", [])
                if isinstance(row, dict)}
        if held.get(999999) != 3:
            failures.append(
                "an item picked up for the first time was dropped: it has "
                "no row in the cached list to replace, so it has to be "
                "appended rather than skipped.")

        # A SPEND, which is the same envelope under another key.
        addon.websocket_message(_Flow(_Message(json.dumps({
            "res": "ok", "qid": 44,
            "dec_result": {"currency": {str(CURRENCY_ID): {
                "doc": {"res_id": CURRENCY_ID, "amount": 610439},
                "diff": -100000}}},
        }))))
        currencies = addon.character_data.get("currencies", {})
        if currencies.get(str(CURRENCY_ID), {}).get("amount") != 610439:
            failures.append(
                f"a spend left the currency at "
                f"{currencies.get(str(CURRENCY_ID), {}).get('amount')} "
                f"rather than 610439. `dec_result` carries the same "
                f"envelope as a gain and has to be applied the same way, "
                f"or every count drifts upward across a session.")

        # And a STAGE's rewards, which are deltas rather than totals:
        # one entry per drop, the same item appearing once per run.
        log.clear()
        addon.websocket_message(_Flow(_Message(json.dumps({
            "res": "ok", "qid": 45,
            "drop_item_result": [
                {"id": ITEM_ID, "amount": 2, "cur_drop_count": 1},
                {"id": ITEM_ID, "amount": 3, "cur_drop_count": 2},
                {"id": CURRENCY_ID, "amount": 7000, "cur_drop_count": 1},
            ],
        }))))
        held = {row.get("res_id"): row.get("amount")
                for row in addon.inventory_data.get("items", [])
                if isinstance(row, dict)}
        currencies = addon.character_data.get("currencies", {})
        if held.get(ITEM_ID) != 55:
            failures.append(
                f"a stage's drops left the item at {held.get(ITEM_ID)} "
                f"rather than 55 -- 50 held plus the 2 and 3 of two "
                f"drops. A drop list states what each drop GAVE and "
                f"never a total, so the entries have to be summed onto "
                f"what is cached.")
        if currencies.get(str(CURRENCY_ID), {}).get("amount") != 617439:
            failures.append(
                f"a drop of currency left "
                f"{currencies.get(str(CURRENCY_ID), {}).get('amount')} "
                f"rather than 617439. Units drop from stages like any "
                f"item but are held among the CURRENCIES, so a drop has "
                f"to look there before it looks at the item list.")
        if not any("Received" in line for line in log):
            failures.append(
                f"a stage's drops wrote nothing to the Capture Log; it "
                f"logged {log}.")

        # The same drop frame again -- a retransmit. Deltas double where
        # totals cannot, so the qid is what has to stop it.
        addon.websocket_message(_Flow(_Message(json.dumps({
            "res": "ok", "qid": 45,
            "drop_item_result": [
                {"id": ITEM_ID, "amount": 2, "cur_drop_count": 1},
                {"id": ITEM_ID, "amount": 3, "cur_drop_count": 2},
                {"id": CURRENCY_ID, "amount": 7000, "cur_drop_count": 1},
            ],
        }))))
        held = {row.get("res_id"): row.get("amount")
                for row in addon.inventory_data.get("items", [])
                if isinstance(row, dict)}
        if held.get(ITEM_ID) != 55:
            failures.append(
                f"a repeated drop frame took the item to "
                f"{held.get(ITEM_ID)}. Nothing in a drop list says what "
                f"the holding now is, so a second application cannot be "
                f"corrected by the next frame -- the qid guard is the "
                f"only thing between a retransmit and a doubled count.")

    return failures
