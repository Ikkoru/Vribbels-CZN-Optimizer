"""Which Checklist shop products the user is actually tracking.

Every shop product on the Checklist tab carries a checkbox. A TICKED
one is a thing the user means to buy each period, and its reading is
coloured; an unticked one sinks to the bottom of its shop and greys
out. The tab still lists it -- the shop sells it, and hiding a product
outright would leave the user wondering where it went.

Stored as JSON in `settings/checklist.json` (pure user state, no
bundled default):

    {
        "version": 1,
        "tracked": {
            "town_shop_goods_005": true,
            "town_shop_goods_009": false
        }
    }

Keyed by PRODUCT ID, which is what the wire calls a shop entry and is
stable across the item it sells changing. **An absent id reads as
`DEFAULT_TRACKED`**, so a product the game adds appears already in
whichever state suits most of them rather than needing a first tick.

`DEFAULTS` is the exception to that: a per-product starting state, for
the ones most accounts would answer differently on. It ships in the
code rather than in a file, since a shipped `settings/` file is user
state the sync would then have to reason about.
"""

import json
from pathlib import Path

CHECKLIST_VERSION = 1

# What an id nobody has ticked or unticked reads as.
DEFAULT_TRACKED = True

# Per-product starting states, for products the default is wrong for.
# **Empty until the maintainer has settled their own list** -- a guess
# here is a checkbox every new install has to correct.
DEFAULTS = {}


class ChecklistManager:
    """Loads and persists the Checklist's per-product tracked flags."""

    def __init__(self, base_dir: Path):
        self.settings_dir = Path(base_dir) / "settings"
        self.file = self.settings_dir / "checklist.json"
        self.tracked = {}          # product id (str) -> bool

    def load(self):
        """Read the flags. An unreadable file behaves like a fresh one.

        A missing or corrupt file is not an error the user can act on,
        and refusing to build the tab over it would cost them the whole
        Checklist for a bad byte.
        """
        self.tracked = {}
        if not self.file.exists():
            return
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        raw = data.get("tracked") if isinstance(data, dict) else None
        if isinstance(raw, dict):
            self.tracked = {str(k): bool(v) for k, v in raw.items()}

    def is_tracked(self, product_id) -> bool:
        """Whether a product is ticked. Absent ids take the default."""
        product_id = str(product_id)
        if product_id in self.tracked:
            return self.tracked[product_id]
        return DEFAULTS.get(product_id, DEFAULT_TRACKED)

    def set_tracked(self, product_id, value: bool):
        """Tick or untick one product, and persist it."""
        product_id = str(product_id)
        if self.tracked.get(product_id) == bool(value):
            return
        self.tracked[product_id] = bool(value)
        self._write()

    def _write(self):
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        data = {"version": CHECKLIST_VERSION, "tracked": self.tracked}
        tmp = self.file.with_suffix(self.file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)
