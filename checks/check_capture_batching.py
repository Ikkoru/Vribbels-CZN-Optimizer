"""One WebSocket frame can carry several server replies.

The client batches its commands whenever it has more than one to send --
most of the post-lobby traffic, including the gacha list and the archive
screens -- and the server answers with a JSON array of reply objects
rather than a single one. A handler that accepts only the object form
sees none of it: no parsing, no snapshot save, and nothing in the debug
log either, so the capture looks like it simply went quiet.

Nothing about that is visible from the outside, which is why it is
checked by driving the addon rather than by reading it. The template is
executed here the way mitmdump executes it, and fed a frame of each
shape.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture handles batched frames"


class _Message:
    """One server-to-client text frame."""

    def __init__(self, text):
        self.from_client = False
        self.is_text = True
        self.text = text
        self.content = text.encode("utf-8")


class _Flow:
    def __init__(self, message):
        self.websocket = type("_WS", (), {"messages": [message]})()


def _drive(addon_class, output_dir, payload):
    """Feed one frame to a fresh addon and return what it kept."""
    addon = addon_class(output_dir, log_callback=lambda *_a, **_k: None)
    addon.websocket_message(_Flow(_Message(json.dumps(payload))))
    return addon


def run():
    failures = []
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    namespace = {"__name__": "_addon_under_check"}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    addon_class = namespace["Addon"]

    inventory_reply = {
        "res": "ok", "qid": 8,
        "piece_items": [{"id": 1, "char_res_id": 0}],
    }
    roster_reply = {
        "res": "ok", "qid": 4,
        "characters": [{"res_id": 1003, "friendship_exp": 0}],
        "user": {"day_id": 1},
    }

    # A temp dir, never `snapshots/`: the addon writes a snapshot as soon
    # as it has inventory data.
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)

        solo = _drive(addon_class, output_dir, inventory_reply)
        if solo.inventory_data is None:
            failures.append(
                "A single reply object was ignored. The addon is not "
                "reading server frames at all."
            )

        batched = _drive(addon_class, output_dir, [inventory_reply, roster_reply])
        if batched.inventory_data is None:
            failures.append(
                "The first reply in a batched frame was dropped. Batched "
                "frames carry most post-lobby traffic and would go "
                "unparsed and unlogged."
            )
        roster = (batched.character_data or {}).get("characters") or []
        if not roster:
            failures.append(
                "The second reply in a batched frame was dropped. Only the "
                "first entry of the array is reaching the handler."
            )

    return failures
