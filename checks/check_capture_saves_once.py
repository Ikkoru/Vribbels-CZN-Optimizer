"""One server payload writes the snapshot once, and says so once.

The login reply carries the whole roster, the whole inventory and the
gacha schedule in a single message. `_handle_server_payload` reads each
of those with its own branch, and each branch used to write the file
itself -- so loading into the game wrote the same snapshot three times
and printed three `Saved:` lines in the Capture Log.

Nothing about that is visible from the code: every branch is correct on
its own, and the duplication only exists for a payload that trips more
than one. It is also awkward to see by hand, because it needs the proxy,
the game and a fresh login. So the payload is synthesised here instead.

The file content is identical either way -- `_save_data` writes the
whole cache whenever it runs -- which is exactly why nothing else would
ever have caught it.
"""

import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture saves once per payload"


def run():
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    # The addon is a program inside a string literal -- mitmdump writes
    # it out and runs it -- so there is no class to import. Executing the
    # template is what `check_addon_template` already proves is safe: it
    # imports nothing beyond the standard library.
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    Addon = namespace["Addon"]

    failures = []
    work = Path(tempfile.mkdtemp())
    lines = []
    mgr = Addon(work, log_callback=lambda msg, *a, **k: lines.append(msg))

    # A login reply, cut down to the keys that each used to save: the
    # inventory, the roster with its user record, and the banner
    # schedule. Anything the manager needs beyond these it defaults.
    payload = {
        # The handler drops anything the server did not answer "ok" to,
        # before it reads a single key.
        "res": "ok",
        "piece_items": [
            {"id": 1, "res_id": 1010001, "level": 0, "char_res_id": 0},
        ],
        "characters": [
            {"id": 11, "res_id": 101, "level": 60},
        ],
        "user": {"nickname": "probe"},
        "event_schedules": {"GACHA": {}},
    }

    mgr._handle_server_payload(payload, frame_size=len(str(payload)))

    saves = [l for l in lines if str(l).startswith("Saved:")]
    if len(saves) != 1:
        failures.append(
            f"one payload produced {len(saves)} `Saved:` lines, not 1. A "
            f"login reply carries the inventory, the roster and the banner "
            f"schedule at once; each branch that reads one must set a flag "
            f"rather than write the file, with a single save at the end of "
            f"`_handle_server_payload`. Lines: {saves}"
        )

    written = list(work.glob("memory_fragments_*.json"))
    if len(written) != 1:
        failures.append(
            f"one payload wrote {len(written)} snapshot files, not 1: "
            f"{[p.name for p in written]}"
        )

    return failures
