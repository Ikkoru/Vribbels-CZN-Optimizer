"""Drinking the daily coffee turns its flag off.

**The reply to `town` / `order_coffee` carries no `day_changeable_data`
at all.** It confirms the order, pays the Aether and lists the missions
it progressed, and says nothing about the coffee being gone. The flag
is only refreshed the next time some OTHER town action happens to send
that block -- in the capture this was written from, the reply to a
`run_visit` fifty-one seconds later. Do nothing else in town and it is
never refreshed, so the Checklist reads `Go drink!` for a coffee that
has been drunk, for the rest of the day.

So the addon remembers the REQUEST by qid and turns the flag off when
the server answers it. That is state established by an action rather
than read off the wire, and nothing about the reply would reveal a
regression -- hence this.

No Tk and no snapshot needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "the coffee is drunk once"

# The reply's own keys, from `websocket_debug_20260907_204525.jsonl`
# frame 67 -- the answer to qid 43, `order_coffee`. Note what is not
# among them.
COFFEE_REPLY_KEYS = ("add_result", "content_locks", "mission_condition",
                     "notice_rollings", "qid", "res")


class _Message:
    def __init__(self, payload, from_client=False):
        self.from_client = from_client
        self.is_text = True
        self.text = json.dumps(payload)
        self.content = self.text.encode()


class _Flow:
    def __init__(self, payload, from_client=False):
        self.websocket = type(
            "W", (), {"messages": [_Message(payload, from_client)]})()


def _coffee(addon):
    town = (addon.character_data or {}).get("town_data") or {}
    return (town.get("day_changeable_data") or {}).get("is_coffee_possible")


def run():
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     ITEM_NAMES={}, KNOWN_UNIT_IDS=set(), REGION_ROUTES={})
    Addon = namespace["Addon"]

    failures = []
    addon = Addon(Path(tempfile.mkdtemp()), log_callback=lambda *a, **k: None)

    # Logging in: the roster, and the town block nested beside it.
    addon.websocket_message(_Flow([{
        "res": "ok",
        "characters": [{"id": 11, "res_id": 101, "level": 60}],
        "user": {"nickname": "probe"},
        "town_data": {"day_changeable_data": {"is_coffee_possible": True}},
    }]))
    if _coffee(addon) is not True:
        failures.append(
            f"after logging in the coffee flag reads {_coffee(addon)!r}, "
            f"not True. The login's own `town_data` is where it starts.")
        return failures

    # Ordering one, exactly as the game sends it.
    addon.websocket_message(_Flow(
        [{"cmd": "town", "qid": 43, "params": {"cmd": "order_coffee",
                                               "takeout_type": 4}}],
        from_client=True))
    if _coffee(addon) is not True:
        failures.append(
            "the coffee flag went false on the REQUEST. Nothing is drunk "
            "until the server answers, and a request that fails would "
            "leave the tab saying the coffee is gone.")

    addon.websocket_message(_Flow(
        {key: "ok" if key == "res" else (43 if key == "qid" else {})
         for key in COFFEE_REPLY_KEYS}))
    if _coffee(addon) is not False:
        failures.append(
            f"after ordering the coffee the flag reads {_coffee(addon)!r}, "
            f"not False. Its reply carries no day_changeable_data "
            f"({', '.join(COFFEE_REPLY_KEYS)}), so nothing else will turn "
            f"it off -- the Checklist keeps saying `Go drink!` all day.")

    # A reply to some OTHER command with the same qid must not count:
    # qids are reused across a session.
    addon.websocket_message(_Flow([{
        "res": "ok",
        "day_changeable_data": {"is_coffee_possible": True},
    }]))
    addon.websocket_message(_Flow({"res": "ok", "qid": 43}))
    if _coffee(addon) is not True:
        failures.append(
            "a reply carrying qid 43 turned the coffee off again after the "
            "order was already answered. The pending qid has to be "
            "consumed, or every later reply reusing that number drinks a "
            "coffee that was never ordered.")
    return failures
