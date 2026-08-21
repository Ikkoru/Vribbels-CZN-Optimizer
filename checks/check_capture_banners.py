"""A pickup banner names its unit's res_id in the banner's own id.

`gacha_pickup_supporter_30116` is the only place a res_id appears
without owning the unit, so the banner schedule is what tells the
maintainer a release's id -- weeks before a copy can be obtained. The
addon keeps it under the snapshot's `gacha_banners` key and logs any
res_id the tables have no entry for.

Both halves fail quietly. An unwritten key looks like a snapshot that
simply has no banners in it, and a notice that never fires looks like a
patch with nothing new in it.

The addon is generated here exactly as `start_capture` generates it, so
this also covers the globals the template reads but the generator
supplies -- `KNOWN_UNIT_IDS` among them, which is a NameError at capture
time if the generator ever stops emitting it.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture records gacha banners"

UNKNOWN_RES_ID = 999999


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
    addon.log_callback = log.append
    return addon


def run():
    failures = []
    add_source_to_path()
    from game_data.characters import CHARACTERS

    known = min(rid for rid in CHARACTERS if rid > 0)

    lobby_reply = {
        "res": "ok", "qid": 15,
        "event_schedules": {
            "GACHA": {
                # A rerun suffix follows the res_id and must not be read
                # as one.
                f"gacha_pickup_combatant_{known}_2": {
                    "schedule_id": "x", "start_time": 1, "end_time": 2,
                },
                f"gacha_pickup_supporter_{UNKNOWN_RES_ID}": {
                    "schedule_id": "y", "start_time": 1, "end_time": 2,
                },
                "gacha_general": {"schedule_id": "z", "start_time": 1, "end_time": 2},
            }
        },
    }
    inventory_reply = {"res": "ok", "qid": 8, "piece_items": []}

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        log = []
        addon = _build_addon(output_dir, log)

        addon.websocket_message(_Flow(_Message(json.dumps(lobby_reply))))

        if not addon.gacha_banners:
            failures.append(
                "The lobby reply's gacha schedule was not kept. New "
                "release ids would only be visible in a debug log."
            )

        notices = [line for line in log if "not in game_data" in line]
        if not any(str(UNKNOWN_RES_ID) in line for line in notices):
            failures.append(
                f"No notice for res_id {UNKNOWN_RES_ID}, which no table "
                f"has an entry for. A new release would land silently."
            )
        if any(f"_{known}_2" in line for line in notices):
            failures.append(
                f"Banner for known res_id {known} was reported as "
                f"unknown. The rerun suffix is being read as a res_id."
            )

        # The schedule arrives before the inventory does, so it has to
        # survive until a save is possible.
        addon.websocket_message(_Flow(_Message(json.dumps(inventory_reply))))
        written = list(output_dir.glob("memory_fragments_*.json"))
        if not written:
            failures.append("No snapshot was written for the inventory reply.")
        else:
            snapshot = json.loads(written[0].read_text(encoding="utf-8"))
            if not snapshot.get("gacha_banners"):
                failures.append(
                    "The snapshot has no `gacha_banners`. A schedule that "
                    "arrives before the inventory is being dropped."
                )

    return failures
