"""
Capture orchestration manager for CZN game data interception.
Handles proxy lifecycle, hosts file modification, and data capture coordination.
"""

import subprocess
import threading
import socket
import re
import ctypes
import sys
import os
from pathlib import Path
from typing import Optional, Callable

from .constants import PROXY_PORT, GAME_PORT, HOSTS_PATH
from .setup import find_mitmdump


class CaptureError(Exception):
    """Raised when capture operations fail."""
    pass


# Addon template embedded as string constant (works in bundled executables)
ADDON_TEMPLATE = '''"""
mitmproxy Addon for intercepting CZN game WebSocket traffic.
Extracts Memory Fragment inventory and character data from game API responses.
"""

import json
import gzip
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False


class Addon:
    """mitmproxy addon that intercepts WebSocket messages and extracts game data."""

    def __init__(
        self,
        output_dir: Path,
        dict_path: Optional[Path] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        debug_mode: bool = False
    ):
        """
        Initialize the capture addon.

        Args:
            output_dir: Directory to save captured JSON files
            dict_path: Optional path to zstd dictionary file
            log_callback: Optional callback for logging messages (defaults to print)
            debug_mode: If True, log all WebSocket messages to a .jsonl file
        """
        self.output_dir = output_dir
        self.log_callback = log_callback or (lambda msg: print(msg, flush=True))
        self.inventory_data = None
        self.character_data = None
        self.saved_path = None
        self.zstd_dict = None
        self.zstd_dctx = None

        # Debug logging
        self.debug_file = None
        if debug_mode:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_path = self.output_dir / f"websocket_debug_{ts}.jsonl"
            self.debug_file = open(debug_path, "w", encoding="utf-8")
            self.log_callback(f"Debug logging to: {debug_path.name}")

        # Tracks delete (disassemble_piece) requests we're waiting on the
        # server to confirm. Maps qid -> [piece_id, ...]. The delete
        # response carries only item_result (proceeds), not the destroyed
        # piece IDs, so we have to remember intent from the request side
        # and apply the deletion only when the matching server response
        # arrives with res='ok'.
        self.pending_disassembles = {}

        # Tracks bulk-unequip (unequip_piece) requests. The "Unequip All"
        # in-game button sends one unequip_piece message listing all the
        # currently-equipped piece IDs of a single character. The server
        # response has a "pieces" (plural) array with each piece's
        # char_res_id zeroed out. We can't distinguish that from a
        # CREATE response (forge/fuse, same "pieces" key shape) by looking
        # at the response alone -- so we keep a qid-keyed memo of what
        # the client asked for and dispatch on it when the response
        # arrives. Maps qid -> {"item_ids": [...], "char_res_id": int}.
        self.pending_unequips = {}

        # Load zstd dictionary if available
        if dict_path and dict_path.exists() and HAS_ZSTD:
            try:
                with open(dict_path, 'rb') as f:
                    dict_data = f.read()
                self.zstd_dict = zstd.ZstdCompressionDict(dict_data)
                self.zstd_dctx = zstd.ZstdDecompressor(dict_data=self.zstd_dict)
            except Exception as e:
                self.log_callback(f"Warning: Failed to load zstd dictionary: {e}")

    def _detect_region(self) -> Optional[str]:
        """Detect server region from world_id in character data."""
        if not self.character_data:
            return None

        # Check for world_id in user data
        user_data = self.character_data.get("user", {})
        world_id = user_data.get("world_id", "")

        # Map world_id to region
        if "world_live_global" in world_id:
            return "global"
        elif "world_live_asia" in world_id:
            return "asia"

        return None

    def _try_decode_binary(self, raw_bytes):
        """
        Try to decode binary data - may be compressed or plain JSON.
        Returns decoded string or None if unable to decode.
        """
        size = len(raw_bytes)

        # Try plain UTF-8 first
        try:
            return raw_bytes.decode('utf-8')
        except:
            pass

        # Check for Zstandard magic number (0x28 0xB5 0x2F 0xFD)
        ZSTD_MAGIC = bytes([0x28, 0xB5, 0x2F, 0xFD])
        is_zstd = len(raw_bytes) >= 4 and raw_bytes[:4] == ZSTD_MAGIC

        if is_zstd:
            if HAS_ZSTD:
                # Try with dictionary first (required for CZN game data)
                if self.zstd_dctx:
                    try:
                        decompressed = self.zstd_dctx.decompress(raw_bytes)
                        return decompressed.decode('utf-8')
                    except:
                        pass

                # Try without dictionary as fallback
                try:
                    dctx = zstd.ZstdDecompressor()
                    decompressed = dctx.decompress(raw_bytes)
                    return decompressed.decode('utf-8')
                except:
                    pass
            else:
                self.log_callback("ERROR: zstandard module not installed!")

        # Try zstd anyway (in case magic check failed)
        if HAS_ZSTD and not is_zstd:
            # Try with dictionary first
            if self.zstd_dctx:
                try:
                    decompressed = self.zstd_dctx.decompress(raw_bytes)
                    return decompressed.decode('utf-8')
                except:
                    pass
            # Try without dictionary
            try:
                dctx = zstd.ZstdDecompressor()
                decompressed = dctx.decompress(raw_bytes)
                return decompressed.decode('utf-8')
            except:
                pass

        # Try gzip decompression
        try:
            decompressed = gzip.decompress(raw_bytes)
            return decompressed.decode('utf-8')
        except:
            pass

        # Try zlib decompression (with and without header)
        for wbits in [15, -15, 31, 47]:
            try:
                decompressed = zlib.decompress(raw_bytes, wbits)
                return decompressed.decode('utf-8')
            except:
                pass

        return None

    def websocket_message(self, flow):
        """
        Handle WebSocket messages from the game server.
        Extracts piece_items (inventory) and characters data.

        Args:
            flow: mitmproxy flow object containing WebSocket messages
        """
        msg = flow.websocket.messages[-1]
        if msg.from_client:
            # Decode and parse the client request once. The parsed form is
            # needed for two purposes: (1) tracking disassemble_piece intents
            # so we can apply the deletion when the matching server response
            # arrives, which must happen whether or not debug is on; and
            # (2) writing the entry to the debug log when debug is on.
            content = None
            parsed = None
            try:
                if msg.is_text:
                    content = msg.text
                else:
                    content = self._try_decode_binary(msg.content)
                    if content is None:
                        content = "<binary>"
                try:
                    parsed = json.loads(content)
                except (ValueError, TypeError):
                    parsed = None
            except Exception:
                pass

            # Always track disassemble (delete) requests. The game uses a
            # list-of-commands wire shape where one client message can
            # contain multiple commands, so we scan every entry.
            self._track_client_request(parsed)

            # Optional debug log of the raw client message.
            if self.debug_file and content is not None:
                try:
                    entry = {
                        "ts": datetime.now().isoformat(),
                        "direction": "client_to_server",
                        "size": len(content) if isinstance(content, (str, bytes)) else 0,
                        "keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
                        "data": parsed if parsed is not None else content,
                    }
                    self.debug_file.write(json.dumps(entry, ensure_ascii=False) + "\\n")
                    self.debug_file.flush()
                except Exception:
                    pass  # never let debug logging break capture
            return

        try:
            # Handle both text and binary WebSocket frames
            if msg.is_text:
                content = msg.text
            else:
                # Binary frame - try to decode/decompress
                content = self._try_decode_binary(msg.content)
                if content is None:
                    return

            data = json.loads(content)

            # Skip non-object messages (some responses are JSON arrays)
            if not isinstance(data, dict):
                return

            # Debug: log every decoded message before filtering
            if self.debug_file:
                entry = {
                    "ts": datetime.now().isoformat(),
                    "direction": "server_to_client",
                    "keys": list(data.keys()),
                    "size": len(content),
                    "data": data
                }
                self.debug_file.write(json.dumps(entry, ensure_ascii=False) + "\\n")
                self.debug_file.flush()

            if data.get("res") != "ok":
                return

            # Confirm any pending disassemble (delete) request whose qid
            # this response matches. The server reply carries only proceeds
            # in item_result -- no piece info -- so we identify which
            # pieces were destroyed by matching the response qid to the
            # request we tracked earlier.
            qid = data.get("qid")
            if (qid is not None and qid in self.pending_disassembles
                    and self.inventory_data
                    and "piece_items" in self.inventory_data):
                ids = self.pending_disassembles.pop(qid)
                self._apply_piece_disassemble(ids)

            # Pop any pending unequip-piece request matching this qid. The
            # actual state update happens in the "pieces" branch below;
            # we just remember whether this qid was an unequip so we can
            # route to the right handler (unequip vs. create -- they share
            # the "pieces" key shape).
            pending_unequip_info = None
            if qid is not None and qid in self.pending_unequips:
                pending_unequip_info = self.pending_unequips.pop(qid)

            # Live monitoring: apply piece deltas
            #   "piece"  (singular): existing swap / upgrade / equip / unequip flows.
            #   "pieces" (plural):   create flow (forge/fuse/craft a new fragment).
            #                        The response carries the newly-minted piece(s) as
            #                        an array along with the resource cost in
            #                        item_result. We append each piece to the cached
            #                        piece_items so the inventory stays in sync.
            #                        UNEQUIP-ALL also uses this key (returning each
            #                        unequipped piece with char_res_id zeroed); we
            #                        distinguish via pending_unequip_info above.
            if "piece" in data and self.inventory_data and "piece_items" in self.inventory_data:
                self._apply_piece_delta(data)
            elif "pieces" in data and self.inventory_data and "piece_items" in self.inventory_data:
                if pending_unequip_info is not None:
                    self._apply_pieces_unequip(
                        data["pieces"], pending_unequip_info["char_res_id"]
                    )
                else:
                    self._apply_pieces_create(data)

            # Check for 'info' structure (new API format)
            if "info" in data:
                info = data.get("info", {})

                # Check for item data in new format
                if isinstance(info, dict) and "item" in info:
                    item_info = info.get("item", {})

                    # Check for piece (Memory Fragment) data
                    if "piece" in item_info:
                        piece_info = item_info.get("piece", {})
                        # Store this as inventory data (new format)
                        if not self.inventory_data:
                            self.inventory_data = {}
                        self.inventory_data["info_item_piece"] = piece_info
                        self._save_data()

                # Check for character data in new format
                if isinstance(info, dict) and "character" in info:
                    char_info = info.get("character", {})
                    if not self.character_data:
                        self.character_data = {}
                    self.character_data["info_character"] = char_info
                    self._save_data()

            # Capture inventory data (Memory Fragments)
            if "piece_items" in data:
                self.inventory_data = data
                self._save_data()

            # Capture character data
            has_characters = "characters" in data and isinstance(data.get("characters"), list)
            has_user = "user" in data

            if has_characters or has_user:
                self.character_data = data
                self._save_data()

        except Exception as e:
            self.log_callback(f"Error: {e}")

    def _save_data(self):
        """
        Save captured data to JSON file.
        Only saves when inventory data is available.
        Combines inventory and character data into single file.
        """
        if not self.inventory_data:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not self.saved_path:
            self.saved_path = self.output_dir / f"memory_fragments_{ts}.json"

        save_data = {
            "capture_time": datetime.now().isoformat(),
            "inventory": self.inventory_data,
            "characters": self.character_data,
            "detected_region": self._detect_region(),
        }

        with open(self.saved_path, "w") as f:
            json.dump(save_data, f, indent=2)

        count = len(self.inventory_data.get("piece_items", []))
        char_count = len(self.character_data.get("characters", [])) if self.character_data else 0
        self.log_callback(
            f"Saved: {count} Memory Fragments, {char_count} characters -> {self.saved_path.name}"
        )

    def _describe_piece(self, piece_data):
        """Build human-readable piece description like 'Line of Justice Denial (+3)'."""
        res_id = piece_data.get("res_id", 0)
        level = piece_data.get("level", 0)
        res_str = str(res_id)
        if len(res_str) >= 5:
            slot_num = int(res_str[2])
            set_id = int(res_str[4:])
            set_name = SET_NAMES.get(set_id, f"Set{set_id}")
            slot_name = SLOT_NAMES.get(slot_num, f"Slot{slot_num}")
            return f"{set_name} {slot_name} (+{level})"
        return f"Piece {piece_data.get('id', '?')} (+{level})"

    def _apply_piece_delta(self, data):
        """Apply a piece delta update to inventory and log the change."""
        piece_items = self.inventory_data.get("piece_items", [])
        new_piece = data["piece"]
        new_id = new_piece["id"]
        equipped_piece = data.get("equippedPiece")

        # Find old piece for comparison
        old_piece = None
        for i, p in enumerate(piece_items):
            if p["id"] == new_id:
                old_piece = p
                piece_items[i] = new_piece
                break
        else:
            piece_items.append(new_piece)

        # Apply equippedPiece (displaced piece in swap)
        if equipped_piece:
            eq_id = equipped_piece["id"]
            for i, p in enumerate(piece_items):
                if p["id"] == eq_id:
                    piece_items[i] = equipped_piece
                    break
            else:
                piece_items.append(equipped_piece)

        self._save_data()

        # Build log message
        desc = self._describe_piece(new_piece)
        char_id = new_piece.get("char_res_id", 0)
        char_name = CHAR_NAMES.get(char_id, f"Character {char_id}")

        if equipped_piece:
            eq_desc = self._describe_piece(equipped_piece)
            self.log_callback(f"[LIVE] Swapped gear on {char_name}: equipped {desc}, removed {eq_desc}")
        elif old_piece and old_piece.get("level", 0) != new_piece.get("level", 0):
            # Embed [pid={id}] so the main app can compute Highest Pot.
            # from the freshly-reloaded fragment and append it to this
            # line (see _drain_pending_upgrade_lines in czn_optimizer_gui).
            # The main app strips this marker before display so the user
            # doesn\'t see it.
            self.log_callback(f"[LIVE] Upgraded {desc} [pid={new_piece.get('id', 0)}]")
        elif char_id != 0:
            self.log_callback(f"[LIVE] Equipped {desc} to {char_name}")
        else:
            self.log_callback(f"[LIVE] Unequipped {desc}")

    def _apply_pieces_create(self, data):
        """Apply a piece-create response (forge / fuse / craft new fragment).

        The server sends the freshly-minted piece(s) under the 'pieces'
        (plural) key as an array. Each entry has the same shape as a normal
        piece_items entry (id, res_id, char_res_id, level, exp, lock,
        stat_list, ...). We append any entries whose id isn't already in
        piece_items -- defensive in case of message duplication or replay.
        """
        piece_items = self.inventory_data.get("piece_items", [])
        new_pieces = data.get("pieces") or []
        if not isinstance(new_pieces, list):
            return

        existing_ids = {p.get("id") for p in piece_items}
        added = []
        for piece in new_pieces:
            if not isinstance(piece, dict):
                continue
            pid = piece.get("id")
            if pid is None or pid in existing_ids:
                continue
            piece_items.append(piece)
            existing_ids.add(pid)
            added.append(piece)

        if not added:
            return

        self._save_data()

        if len(added) == 1:
            desc = self._describe_piece(added[0])
            self.log_callback(f"[LIVE] Created {desc}")
        else:
            self.log_callback(f"[LIVE] Created {len(added)} pieces")

    def _apply_pieces_unequip(self, pieces_list, char_res_id):
        """Apply a bulk-unequip server response ("Unequip All" in-game).

        The response 'pieces' array contains each affected piece with its
        char_res_id zeroed and equip-related state cleared. The IDs ALREADY
        exist in piece_items -- we replace the matching entries in place
        rather than appending (which is what _apply_pieces_create would
        incorrectly do, since its dedup logic just skips known IDs).

        Args:
            pieces_list: the 'pieces' array from the server response.
            char_res_id: integer res_id of the character whose gear was
                         unequipped (from the original request, coerced
                         from string by _track_client_request). Used for
                         the log message only.
        """
        if not isinstance(pieces_list, list):
            return
        piece_items = self.inventory_data.get("piece_items", [])
        updated_count = 0
        for new_piece in pieces_list:
            if not isinstance(new_piece, dict):
                continue
            pid = new_piece.get("id")
            if pid is None:
                continue
            for i, p in enumerate(piece_items):
                if p.get("id") == pid:
                    piece_items[i] = new_piece
                    updated_count += 1
                    break

        if updated_count == 0:
            return

        self._save_data()

        char_name = CHAR_NAMES.get(char_res_id, f"Character {char_res_id}")
        if updated_count == 1:
            # Defensive: if single-piece unequip also routes through the
            # unequip_piece cmd (we don't have a debug-capture sample of
            # that yet), log per-piece detail to match the single-piece
            # log format produced by _apply_piece_delta's unequip branch.
            desc = self._describe_piece(pieces_list[0])
            self.log_callback(f"[LIVE] Unequipped {desc} from {char_name}")
        else:
            self.log_callback(
                f"[LIVE] Unequipped all {updated_count} pieces from {char_name}"
            )

    def _track_client_request(self, parsed):
        """Scan a parsed client message for command(s) we want to remember
        across the request/response gap. Currently:

            disassemble_piece -- delete flow; the server response carries
                                 no piece info so we have to learn the
                                 destroyed piece IDs from the request.
            unequip_piece     -- bulk-unequip flow ("Unequip All" button);
                                 the server returns a "pieces" array
                                 sharing its key shape with the create
                                 (forge / fuse) flow, so we can't tell
                                 them apart without remembering what the
                                 client asked for.

        The wire shape is a list of command objects:
            [{cmd: 'item', qid: N, params: {cmd: '<inner>', ...}}, ...]
        Multiple commands may be batched in one message (we've seen up
        to two in normal play), so each entry is checked.

        Args:
            parsed: the JSON-parsed client message body, or None / non-list
                    if parsing failed -- handled defensively.
        """
        if not isinstance(parsed, list):
            return
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            params = entry.get("params") or {}
            if not isinstance(params, dict):
                continue
            inner_cmd = params.get("cmd")
            qid = entry.get("qid")
            if qid is None:
                continue

            if inner_cmd == "disassemble_piece":
                ids = params.get("item_db_ids") or []
                if isinstance(ids, list) and ids:
                    # Defensive copy in case the request is reused/mutated
                    # upstream.
                    self.pending_disassembles[qid] = list(ids)

            elif inner_cmd == "unequip_piece":
                ids = params.get("item_db_ids") or []
                if isinstance(ids, list) and ids:
                    # char_res_id arrives as a string ("1009") in the
                    # captured data; coerce to int so the CHAR_NAMES
                    # lookup table (int-keyed) hits.
                    raw_cid = params.get("char_res_id")
                    try:
                        char_res_id = int(raw_cid) if raw_cid is not None else 0
                    except (TypeError, ValueError):
                        char_res_id = 0
                    self.pending_unequips[qid] = {
                        "item_ids": list(ids),
                        "char_res_id": char_res_id,
                    }

    def _apply_piece_disassemble(self, piece_ids):
        """Remove pieces from piece_items by id (called on server confirmation
        of a disassemble_piece request). No-ops cleanly when an id isn't
        currently in piece_items, which can happen if state drifted or the
        same id was somehow processed twice."""
        piece_items = self.inventory_data.get("piece_items", [])
        target = set(piece_ids)
        removed = [p for p in piece_items if p.get("id") in target]
        if not removed:
            return
        # Filter out the deleted pieces in place (rebuild list, then assign).
        self.inventory_data["piece_items"] = [
            p for p in piece_items if p.get("id") not in target
        ]
        self._save_data()

        if len(removed) == 1:
            desc = self._describe_piece(removed[0])
            self.log_callback(f"[LIVE] Deleted {desc}")
        else:
            self.log_callback(f"[LIVE] Deleted {len(removed)} pieces")

    def done(self):
        """Cleanup on shutdown."""
        if self.debug_file:
            self.debug_file.close()
            self.debug_file = None
'''


class CaptureManager:
    """
    Manages the complete capture workflow:
    - Proxy server lifecycle
    - Hosts file modification/restoration
    - Game server resolution
    - Data capture coordination
    """

    def __init__(
        self,
        output_folder: Path,
        log_callback: Callable[[str, Optional[str]], None],
        status_callback: Optional[Callable[[str], None]] = None,
        live_update_callback: Optional[Callable[[], None]] = None
    ):
        """
        Initialize the capture manager.

        Args:
            output_folder: Directory to save captured JSON files
            log_callback: Function(message, tag) for logging (tag can be None, "success", "error", "warning", "info")
            status_callback: Optional function(status) for status updates
            live_update_callback: Optional function() called when data changes (for auto-reload)
        """
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self.log_callback = log_callback
        self.status_callback = status_callback
        self.live_update_callback = live_update_callback

        self.capturing = False
        self.proxy_process = None
        self.game_server_ips = {}
        self.original_hosts_content = None
        self.current_region = "global"  # Default region

        # Upgrade log lines from the addon arrive tagged with [pid=N] so
        # the main app can find the upgraded fragment and append its new
        # Highest Pot. range. We hold those lines here instead of forwarding
        # them straight to log_callback; the main app drains the queue
        # after the post-upgrade reload finishes and emits the augmented
        # version. Thread-safe by design (proxy reader thread puts; main
        # thread gets).
        import queue as _queue  # avoid polluting module namespace
        self.pending_upgrade_lines = _queue.Queue()

    def is_capturing(self) -> bool:
        """Check if currently capturing."""
        return self.capturing

    def get_latest_capture(self) -> Optional[Path]:
        """
        Get path to most recent capture file.

        Returns:
            Path to latest capture file, or None if no snapshots exist
        """
        files = list(self.output_folder.glob("memory_fragments_*.json"))
        return max(files, key=lambda f: f.stat().st_mtime) if files else None

    def _read_detected_region(self, capture_file: Path) -> Optional[str]:
        """Read detected_region from capture file."""
        import json
        try:
            with open(capture_file, 'r') as f:
                data = json.load(f)
            return data.get("detected_region")
        except Exception:
            return None

    def open_snapshots_folder(self):
        """Open snapshots folder in file explorer."""
        self.output_folder.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.output_folder)
        else:
            subprocess.run(["xdg-open", str(self.output_folder)])

    def set_region(self, region_id: str):
        """Set the active server region for capture."""
        from .constants import SERVERS
        if region_id not in SERVERS:
            raise ValueError(f"Unknown region: {region_id}")
        self.current_region = region_id

    def resolve_game_server(self):
        """
        Resolve game server hostnames to IP addresses for current region.
        Stores results in self.game_server_ips.
        """
        from .constants import SERVERS
        server_config = SERVERS[self.current_region]
        self.game_server_ips = {}
        for host in server_config.hosts:
            try:
                ip = socket.gethostbyname(host)
                self.game_server_ips[host] = ip
            except socket.gaierror:
                pass

    def modify_hosts_file(self) -> str:
        """
        Modify Windows hosts file to redirect game traffic to local proxy.

        Returns:
            Original hosts file content (for restoration)

        Raises:
            CaptureError: If hosts file modification fails
        """
        try:
            with open(HOSTS_PATH, "r") as f:
                content = f.read()

            # Don't modify if already modified
            if "# CZN-CAPTURE-START" in content:
                return content

            # Add redirect entries
            from .constants import SERVERS
            server_config = SERVERS[self.current_region]
            entries = ["\n# CZN-CAPTURE-START"]
            for host in server_config.hosts:
                entries.append(f"127.0.0.1 {host}")
            entries.append("# CZN-CAPTURE-END\n")

            new_content = content + "\n".join(entries)

            with open(HOSTS_PATH, "w") as f:
                f.write(new_content)

            # Flush DNS cache
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)

            return content

        except Exception as e:
            raise CaptureError(f"Failed to modify hosts file: {e}")

    def restore_hosts_file(self):
        """
        Restore Windows hosts file to original state.
        Removes CZN-CAPTURE entries added by modify_hosts_file().
        """
        try:
            with open(HOSTS_PATH, "r") as f:
                content = f.read()

            # Remove our capture entries
            pattern = r'\n*# CZN-CAPTURE-START.*?# CZN-CAPTURE-END\n*'
            content = re.sub(pattern, '', content, flags=re.DOTALL)

            with open(HOSTS_PATH, "w") as f:
                f.write(content)

            # Flush DNS cache
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)

        except Exception as e:
            self.log_callback(f"Failed to restore hosts: {e}", "error")

    def _find_dictionary_path(self) -> Optional[Path]:
        """
        Find the zstd dictionary file.
        Searches in order: output_folder, Vribbels folder, bundled location.
        If found in bundled location, copies to output_folder for addon script access.

        Returns:
            Path to dictionary file if found, None otherwise
        """
        import shutil
        dict_name = "zstd_dictionary.bin"

        # Check output folder first (always accessible by addon script)
        dict_path = self.output_folder / dict_name
        if dict_path.exists():
            return dict_path

        # Check Vribbels folder (development mode)
        vribbels_folder = Path(__file__).parent.parent
        source_path = vribbels_folder / dict_name
        if source_path.exists():
            return source_path

        # Check if running from PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            bundled_path = Path(sys._MEIPASS) / dict_name
            if bundled_path.exists():
                # Copy to output folder so addon script can access it
                # (addon runs as separate process without _MEIPASS access)
                try:
                    dest_path = self.output_folder / dict_name
                    shutil.copy2(bundled_path, dest_path)
                    return dest_path
                except Exception:
                    # Return bundled path as fallback
                    return bundled_path

        return None

    def _generate_addon_script(self, debug_mode: bool = False) -> Path:
        """
        Generate temporary addon script with configured output directory.

        Args:
            debug_mode: If True, enable WebSocket debug logging in addon

        Returns:
            Path to generated addon script

        Raises:
            CaptureError: If script generation fails
        """
        try:
            addon_script = self.output_folder / "_capture_addon.py"

            # Find dictionary path
            dict_path = self._find_dictionary_path()
            dict_path_str = f'Path(r"{dict_path}")' if dict_path else "None"

            if not dict_path:
                self.log_callback("Warning: zstd dictionary not found", "warning")

            # Build lookup dicts for live monitoring log messages
            from game_data import CHARACTERS, SETS
            from game_data.constants import EQUIPMENT_SLOTS

            char_names = {rid: c["name"] for rid, c in CHARACTERS.items() if c is not None}
            set_names = {sid: s["name"] for sid, s in SETS.items()}
            slot_names = {k: v.split(" ", 1)[1] if " " in v else v for k, v in EQUIPMENT_SLOTS.items()}

            # Generate standalone script using embedded template
            addon_code = f'''{ADDON_TEMPLATE}

OUTPUT_DIR = Path(r"{self.output_folder.absolute()}")
DICT_PATH = {dict_path_str}
CHAR_NAMES = {char_names}
SET_NAMES = {set_names}
SLOT_NAMES = {slot_names}

addons = [Addon(OUTPUT_DIR, dict_path=DICT_PATH, debug_mode={debug_mode})]
'''

            # Always write the addon as UTF-8. On Windows the default
            # locale-derived encoding may be cp932 / cp949 / cp1252 etc.,
            # and any non-ASCII char in the template (em-dash, smart quote,
            # arrow, etc.) would otherwise crash with an UnicodeEncodeError.
            with open(addon_script, "w", encoding="utf-8") as f:
                f.write(addon_code)

            return addon_script

        except Exception as e:
            raise CaptureError(f"Failed to generate addon script: {e}")

    def _read_proxy_output(self):
        """
        Read proxy process output and forward to log callback.
        Runs in background thread.
        """
        if not self.proxy_process:
            return

        # Patterns to filter out (verbose mitmproxy messages)
        skip_patterns = [
            "Loading script",
            "client connect",
            "client disconnect",
            "server connect",
            "server disconnect",
            "HTTP/2 connection",
            "CONNECT",
            "WebSocket text message",
            "WebSocket binary message",
            "<<",
            ">>",
        ]

        try:
            for line in self.proxy_process.stdout:
                line = line.strip()
                if not line:
                    continue

                # Skip verbose mitmproxy messages
                if any(pattern.lower() in line.lower() for pattern in skip_patterns):
                    continue

                # Route live updates with info tag, everything else with default tag
                if "[LIVE]" in line:
                    # Defer [LIVE] Upgraded lines: they carry a [pid=N]
                    # marker that lets the main app fill in Highest Pot.
                    # after the post-upgrade reload completes. All other
                    # [LIVE] events (Equipped / Unequipped / Swapped /
                    # Created / Deleted) log immediately as before.
                    if "[LIVE] Upgraded" in line and "[pid=" in line:
                        self.pending_upgrade_lines.put(line)
                    else:
                        self.log_callback(f"[proxy] {line}", "info")
                    if self.live_update_callback:
                        self.live_update_callback()
                else:
                    self.log_callback(f"[proxy] {line}", None)

                # Auto-reload on any save (initial capture + deltas)
                if "Saved:" in line and "Memory Fragments" in line:
                    if self.status_callback:
                        self.status_callback("[OK] Data Captured!")
                    if self.live_update_callback:
                        self.live_update_callback()

            # Check exit code when process ends
            if self.proxy_process:
                exit_code = self.proxy_process.poll()
                if exit_code is not None and exit_code != 0:
                    self.log_callback(f"[proxy] Process exited with code {exit_code}", "error")
        except Exception as e:
            self.log_callback(f"[proxy] Output reader error: {e}", "error")

    def start_capture(self, debug_mode: bool = False):
        """
        Start the capture process:
        1. Check admin privileges
        2. Resolve game servers
        3. Modify hosts file
        4. Generate addon script
        5. Start mitmproxy
        6. Start background thread for output reading

        Args:
            debug_mode: If True, log all WebSocket messages to a debug file

        Raises:
            CaptureError: If capture cannot be started
        """
        # Check admin privileges
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if not is_admin:
                raise CaptureError(
                    "Administrator privileges required.\n\n"
                    "Please restart as Administrator."
                )
        except AttributeError:
            # Not on Windows, skip admin check
            pass

        self.log_callback("Starting capture...", None)

        # Resolve game servers for current region
        # (Always re-resolve to ensure we use the correct region's servers)
        self.resolve_game_server()

        if not self.game_server_ips:
            raise CaptureError("Could not resolve game servers.")

        # Get first resolved IP for upstream connection
        # (Using IP avoids circular DNS lookup through modified hosts file)
        real_ip = list(self.game_server_ips.values())[0]

        # Modify hosts file
        try:
            self.modify_hosts_file()
            self.log_callback("Hosts file modified", "success")
        except CaptureError as e:
            raise CaptureError(f"Failed to modify hosts file: {e}")

        # Generate addon script
        try:
            addon_script = self._generate_addon_script(debug_mode=debug_mode)
        except CaptureError as e:
            self.restore_hosts_file()
            raise

        # Find mitmdump executable
        mitmdump_path = find_mitmdump()
        if not mitmdump_path:
            self.restore_hosts_file()
            raise CaptureError(
                "mitmdump not found.\n\n"
                "Please ensure mitmproxy is installed and accessible.\n"
                "Run 'pip install mitmproxy' in a terminal, or check the Setup tab."
            )

        # Build mitmdump command
        # Note: -q (quiet) removed to allow seeing errors and addon output
        cmd = [
            mitmdump_path,
            "--mode", f"reverse:https://{real_ip}:{GAME_PORT}/",
            "--listen-port", str(PROXY_PORT),
            "--ssl-insecure",
            "--set", "upstream_cert=false",
            "--set", "keep_host_header=true",
            "--set", "connection_strategy=lazy",
            "-s", str(addon_script),
        ]

        # Start proxy process
        try:
            # Hide console window on Windows
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                # CREATE_NO_WINDOW flag to prevent console window
                creationflags = subprocess.CREATE_NO_WINDOW

            self.proxy_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            threading.Thread(target=self._read_proxy_output, daemon=True).start()
        except Exception as e:
            self.log_callback(f"[X] Failed to start proxy: {e}", "error")
            self.restore_hosts_file()
            raise CaptureError(f"Failed to start proxy: {e}")

        self.capturing = True

        if self.status_callback:
            self.status_callback("Capturing...")

        self.log_callback("Capture started! Launch the game and load into the main menu.", "success")

    def stop_capture(self) -> Optional[tuple[Path, Optional[str]]]:
        """
        Stop the capture process:
        1. Terminate proxy process
        2. Restore hosts file
        3. Return path to captured file

        Returns:
            Path to captured file if any, None otherwise
        """
        if not self.capturing:
            return None

        # Stop proxy
        if self.proxy_process:
            self.proxy_process.terminate()
            try:
                self.proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proxy_process.kill()
            self.proxy_process = None

        # Restore hosts file
        self.restore_hosts_file()

        self.capturing = False

        if self.status_callback:
            self.status_callback("[O] Stopped")

        # Get latest capture file
        latest = self.get_latest_capture()
        if latest:
            detected = self._read_detected_region(latest)
            self.log_callback(f"Capture stopped. File: {latest.name}", "success")
            return (latest, detected)

        self.log_callback("Capture stopped. No data captured.", None)
        return None
