"""
Capture system constants for CZN data interception.
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class ServerConfig:
    """Configuration for a game server region."""
    region_id: str           # Internal ID: "global" or "asia"
    display_name: str        # User-facing name: "Global" or "Asia"
    hosts: List[str]         # Game server hostnames
    # The client sends this in its auth request; the server never
    # echoes it, so nothing in a capture can be matched against it.
    # Kept as documentation of what the region IS, not as a lever --
    # the region is detected from the connection's SNI instead.
    world_id: str


# Server configurations
SERVERS = {
    "global": ServerConfig(
        region_id="global",
        display_name="Global",
        hosts=["live-g-czn-gamemjc2n1x.game.playstove.com"],
        world_id="world_live_global"
    ),
    "asia": ServerConfig(
        region_id="asia",
        display_name="Asia",
        hosts=["live-czn-gamelksj2nmf.game.playstove.com"],
        world_id="world_live_asia"
    )
}

# Network configuration
# GAME_HOSTS deprecated - removed, use SERVERS dict instead
GAME_PORT = 13701
PROXY_PORT = 13701

# File system paths
# When running from PyInstaller bundle, use exe directory
# When running from source, use script directory
if getattr(sys, 'frozen', False):
    # Running from bundled exe - use exe directory
    BASE_DIR = Path(sys.executable).parent
else:
    # Running from source - use script directory
    BASE_DIR = Path(__file__).parent.parent

OUTPUT_DIR = BASE_DIR / "snapshots"
HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
