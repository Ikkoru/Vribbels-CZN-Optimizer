"""
Capture orchestration manager for CZN game data interception.
Handles proxy lifecycle, hosts file modification, and data capture coordination.
"""

import subprocess
import threading
import socket
import ipaddress
import re
import ctypes
import sys
import os
import time
from pathlib import Path
from typing import Optional, Callable

from .constants import PROXY_PORT, GAME_PORT, HOSTS_PATH
from .setup import find_mitmdump


class CaptureError(Exception):
    """Raised when capture operations fail."""
    pass


# Markers delimiting the redirect block this program appends to the
# Windows hosts file. Everything between them belongs to us and is safe
# to rewrite; nothing outside them is ever touched.
HOSTS_BLOCK_START = "# CZN-CAPTURE-START"
HOSTS_BLOCK_END = "# CZN-CAPTURE-END"
_HOSTS_BLOCK_RE = re.compile(
    r"\n*" + re.escape(HOSTS_BLOCK_START)
    + r".*?" + re.escape(HOSTS_BLOCK_END) + r"\n*",
    re.DOTALL,
)


def _strip_capture_block(content: str) -> str:
    """Return hosts-file text with the redirect block removed."""
    return _HOSTS_BLOCK_RE.sub("", content)


def is_loopback_address(ip: str) -> bool:
    """True for any address that points back at this machine.

    A loopback answer to a game-server lookup is never legitimate: it
    means the redirect in the hosts file is what answered the query.
    Unparseable input counts as not-loopback -- the caller's own error
    handling is better placed to deal with a malformed address.
    """
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


# What the addon prints on every save. **Two copies of one literal**:
# the addon is a generated script and cannot import from here, so the
# reader below carries its own. `checks/check_addon_template.py` holds
# them equal -- drift means the app silently stops reloading.
SAVE_MARKER = "[SYNC] saved"

# The same for the Gacha History's file, which refreshes only its own
# tab. Held equal to the addon's by the same check.
GACHA_MARKER = "[SYNC] gacha"

# What opens the timing the addon puts after a line under Debug WS:
# when the request went out, when its reply came in, when the line was
# printed. The reader takes it off before anything else reads the line;
# the Capture Log turns it into the delays between. Held equal to the
# addon's by the same check.
LAG_MARKER = " [@lag "
_LAG_TRAILER = re.compile(re.escape(LAG_MARKER)
                          + r"([0-9.]*),([0-9.]+),([0-9.]+)\]$")


def split_lag(line):
    """(line, stamp): the line without its timing, and the timing.

    `stamp` is None where the line carries none, else epoch seconds for
    `sent` (None where no request is known -- a message the server
    pushed), `got`, `said`, and `read`, the moment this took it off the
    pipe.
    """
    found = _LAG_TRAILER.search(line)
    if found is None:
        return line, None
    return line[:found.start()], {
        "sent": float(found.group(1)) if found.group(1) else None,
        "got": float(found.group(2)), "said": float(found.group(3)),
        "read": time.time()}

# What says this is a working copy rather than a released build, and so
# that the developer tooling may run. The `zRUN*.bat` launchers set it;
# a frozen exe has no way to, which is the point -- a user's capture
# behaves exactly as it did before any of that tooling existed.
#
# **Not a setting.** One in `settings.json` would ship to everyone and
# want explaining, and the thing it guards is of no use to anybody who
# is not reading the wire.
MAINTAINER_ENV = "VRIBBELS_DEV"

# Addon template embedded as string constant (works in bundled executables)
ADDON_TEMPLATE = '''"""
mitmproxy Addon for intercepting CZN game WebSocket traffic.
Extracts Memory Fragment inventory and character data from game API responses.
"""

import json
import gzip
import os
import time
import zlib
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

# How many times a snapshot's temp-file replace is retried, and how long
# to wait between tries. Windows refuses the rename while any other
# process holds the destination open, which the app itself does every
# time it reads the snapshot -- a transient state, not a failure.
SAVE_REPLACE_TRIES = 5
SAVE_REPLACE_WAIT = 0.2

# Printed on EVERY save, whether or not the human-readable `Saved:`
# line is. The app watches for it to reload, and the two must not share
# one line: the readable one is suppressed when it would repeat, and a
# reload riding on it was skipped for exactly the login-burst saves
# that carry the shops. The reader consumes this and does not show it.
SAVE_MARKER = "[SYNC] saved"

# Printed after every write of the Gacha History's file, and consumed
# the same way. The app refreshes that one tab on it: a history page is
# no reason to reload the whole snapshot, which a `[LIVE]` line costs.
GACHA_MARKER = "[SYNC] gacha"

# Put after every line printed while a reply is handled, in debug mode
# only: when its request went out, when the reply came in and when the
# line was printed, in epoch seconds. The app takes it off and shows the
# delays between -- so a line that arrives late says whether the game
# or the program held it.
LAG_MARKER = " [@lag "

# How much of a payload the wire catalogue keeps as an example, and how
# many entries it will hold. The sample says what SHAPE a field is, not
# what is in it -- a reader who wants the whole thing turns debug
# logging on and captures one.
#
# The cap guards against a key built out of something unbounded rather
# than against an expected size: one account's vocabulary is a few
# hundred pairs.
# Event tables with a reader of their own, kept out of the general
# `event_*` sweep: the completion record is merged by id and written
# as a LIST, where the sweep would keep the wire's dict beside it.
EVENT_FIELDS_HANDLED = frozenset({
    "event_mission_reward_entities", "event_mission_reward_entity",
    "result_event_mission_reward_entities",
})

CATALOGUE_SAMPLE = 200
CATALOGUE_MAX = 4000


class Addon:
    """mitmproxy addon that intercepts WebSocket messages and extracts game data."""

    def __init__(
        self,
        output_dir: Path,
        dict_path: Optional[Path] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        debug_mode: bool = False,
        catalogue_path: Optional[Path] = None
    ):
        """
        Initialize the capture addon.

        Args:
            output_dir: Directory to save captured JSON files
            dict_path: Optional path to zstd dictionary file
            log_callback: Optional callback for logging messages (defaults to print)
            debug_mode: If True, log all WebSocket messages to a
                .jsonl.gz file
            catalogue_path: Where to keep the wire catalogue. None
                leaves it unwritten, which is what a check that only
                wants the parsing wants.
        """
        self.output_dir = output_dir

        # **What the wire has ever sent, and which request sent it.**
        # A field nobody reads is invisible: `entity` and
        # `issued_limit_entities` both reached the addon while nothing
        # looked at them, and no amount of reading the code would have
        # said so. This is the record that would --
        # `command|key` to a count, when it was first and last
        # seen, its type and a short sample.
        #
        # Kept whether or not debug logging is on, because it is
        # kilobytes and its whole value is being there when a question
        # is asked about a session nobody thought to record. MERGED
        # with what is already on disk, so it accumulates.
        # **This session's sightings only.** Seeding it from the file
        # would have every write add the whole history to itself
        # again -- one reply seen once read back as three.
        self.catalogue_path = catalogue_path
        self.catalogue = {}
        self.catalogue_dirty = False
        # qid -> the command that asked, so a reply's keys can be
        # attributed. Cleared with everything else on a new `helo`:
        # qids restart at 1 there.
        self.qid_commands = {}

        # The server's own word for when this account last logged in.
        # A RELAUNCH moves it and a reconnect does not, which is what
        # the snapshot rotation turns on -- see `_check_for_relaunch`.
        self.login_stamp = None

        # What the last SAVE line reported: the counts and the file.
        # A save that would say the same thing again says nothing.
        self._last_save = None

        # Every line goes through a wrapper that remembers the last one,
        # so the save report can tell whether it would be repeating
        # itself. See `_save_data`.
        sink = log_callback or (lambda msg: print(msg, flush=True))
        self._last_line = None

        # Under debug mode every line printed while a reply is handled
        # carries `LAG_MARKER` and three times. `_reply_times` is the
        # (request sent, reply received) of the reply being handled,
        # None between replies; `qid_sent` is when each request went
        # out, by qid.
        self.debug_mode = bool(debug_mode)
        self._reply_times = None
        self.qid_sent = {}

        def remember(msg, *args, **kwargs):
            # **The save marker is not a line for this purpose.** It
            # goes out on every save, so remembering it would put it
            # between two identical reports and stop either from
            # reading as a repeat.
            if msg != SAVE_MARKER:
                self._last_line = msg
            if self.debug_mode and self._reply_times is not None:
                sent, got = self._reply_times
                msg = "%s%s%s,%.3f,%.3f]" % (
                    msg, LAG_MARKER, "" if sent is None else "%.3f" % sent,
                    got, time.time())
            sink(msg, *args, **kwargs)

        self.log_callback = remember
        self.inventory_data = None
        self.character_data = None

        # The gacha schedule, keyed by banner id. Every pickup banner
        # names its unit in its own id -- gacha_pickup_supporter_30116 --
        # which is the only res_id in the whole payload that does not
        # depend on owning the unit, so a release's id is readable here
        # from the day its banner opens.

        # One row per combatant that has been on an excursion, from a
        # frame that carries nothing else the snapshot wants. Kept on
        # its own like the banners and written out with the next save:
        # a frame with no inventory in it never saves by itself.
        self.char_visits = None

        # The Great Rift standings, season -> rank slot -> record. The
        # weekly score is in there and in nothing else the game sends.
        self.disaster_ranks = None
        # The Sortie ladders, keyed by res_id. See where they are read
        # for why they are merged rather than replaced.
        self.assault_char_achievements = {}
        self.assault_char_titles = {}

        # One row per Galactic Disaster season, carrying that season's
        # weekly chaos score.
        self.disaster_seasons = None

        # What the recurring tasks stand at: the day's and week's
        # activity points, the season pass's own record, and every
        # mission row seen this session keyed by its res_id. MERGED
        # rather than replaced -- the login burst and a pass claim each
        # send a DIFFERENT set under one key, so a wholesale replace
        # loses whichever arrived first.
        self.point_entity = None
        self.remnants = None
        self.zero_orb = None
        self.attendance = {}
        self.season_rewards = None
        # {event id: row} -- the only place the game says an event is
        # FINISHED rather than how far along it is. See the branch
        # below and `docs/events.md`.
        self.event_rewards = {}
        # {field: record} -- an event's own progress, by the key
        # it arrives under. See the event branch below.
        self.event_defines = {}
        # {trial event id: [slot ids]}, learned from claims and
        # kept forever -- see `reward_combatant_trial`.
        self.trial_slots = {}
        self.combat_trials = None
        self.overclock = None
        self.season_pass = None
        self.missions = {}

        # Every shop product seen this session, keyed by product id.
        # MERGED for the same reason the missions are: the login burst
        # sends the whole `shop_list` and a purchase sends ONE product
        # back under `shop_entity`, so a replace would drop the rest.
        self.shop_products = {}

        # When the current MONTH began and ends, epoch seconds. Sent
        # once at login and nowhere else.
        self.month_start = None
        self.month_end = None

        # Per-stage run limits, keyed by stage id.
        self.stage_limits = {}
        self.issued_limits = {}

        # Every pass the account has played, and the shops' own product
        # DEFINITIONS -- what each sells, its cap, its period, its
        # price and the shop's display order. Sent once at login, and
        # the only thing that says what a product's per-period maximum
        # is: a `shop_list` row carries the tally and nothing else.
        self.season_passes = None
        self.shop_definitions = None

        # The Basin of Hyperspace: its stages, and the objectives whose
        # tally is what the game shows as its progress.
        self.basin_stages = None
        self.basin_missions = None

        # Every content's window: when each season, event and rotation
        # opened and when it closes. The only thing that dates them.
        self.event_schedules = None

        self.saved_path = None

        # Set by anything that changes the cached data, cleared by
        # the one save at the end of the frame. **A frame is the
        # unit, not a payload**: the client batches its commands and
        # the server answers in kind, so a login reply arrives as
        # several payloads -- the roster, the inventory, the banner
        # schedule -- and saving per payload writes the same file
        # three times and announces it three times.
        self._save_pending = False

        # What the last `Received` line said, {res_id: amount}. A run
        # whose clear only restates a payout the line before it already
        # reported has nothing to add -- see `_report_run_total`.
        self._last_receipt = None

        # The qids whose drops have already been applied. A drop
        # list carries deltas rather than totals, so applying one
        # twice doubles it; a short ring is enough, a retransmit
        # arriving right after the frame it repeats.
        self._applied_drops = deque(maxlen=64)

        # Account identity of this capture session, from the first
        # `user` record seen. A second, different one means a second
        # game is running: two accounts' data would be merged into one
        # snapshot, and nothing downstream could tell them apart --
        # piece_items carry no account id, so once the two are mixed
        # the snapshot is silently wrong. Capture stops instead.
        self.session_account = None
        self.mixed_accounts = False

        # Which region the game actually connected to, learned from
        # the TLS SNI of the first connection. Both regions are
        # redirected, so this is OBSERVED rather than chosen.
        self.detected_region = None
        # Every region seen this session. More than one means two
        # games running on different servers.
        self.seen_regions = set()

        self.zstd_dict = None
        self.zstd_dctx = None

        # Debug logging.
        #
        # **Compressed, because the content is almost all repetition.**
        # A bare login is 1.8MB of which 99.3% is byte-for-byte what
        # the last login said. The format is unchanged -- still one
        # JSON object per line -- so a reader only has to open it
        # through `gzip` instead of `open`.
        #
        # **One gzip MEMBER per line**, concatenated, rather than one
        # stream over the whole file. A stream is readable only once
        # its end marker is written, so a capture that is KILLED --
        # which is how an always-on one ends -- would leave a file
        # `gzip.open` refuses outright, sync-flushed or not. A member
        # per line is complete after every single write, and measured
        # against the whole-file stream it costs almost nothing: 12.7x
        # against 13.2 on a login, 10.7 against 12.6 with play in it.
        self.debug_file = None
        if debug_mode:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_path = self.output_dir / f"websocket_debug_{ts}.jsonl.gz"
            self.debug_file = open(debug_path, "wb")
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

        # Tracks the daily coffee (town/order_coffee). **Its own reply
        # carries no day_changeable_data**, so nothing in it says the
        # coffee is gone -- the flag is only refreshed the next time
        # some other town action happens to send that block, which can
        # be a session later or never. Ordering one is what makes it
        # false, so the request is remembered by qid and applied when
        # the server answers res='ok'. A set of qids; the request
        # carries nothing else worth keeping.
        self.pending_coffees = set()

        # What each gacha request asked for, by qid: ("history", banner,
        # cursor) or ("get_rate", banner, None). **Neither reply says**
        # -- a rates reply does not name its banner, and a history page
        # does not say whether it is the first. See `_merge_gacha`.
        self.gacha_requests = {}
        # Set once the Gacha History's file has refused to be read, so
        # the complaint is made once rather than on every page.
        self._gacha_refused = False

        # Load zstd dictionary if available
        if dict_path and dict_path.exists() and HAS_ZSTD:
            try:
                with open(dict_path, 'rb') as f:
                    dict_data = f.read()
                self.zstd_dict = zstd.ZstdCompressionDict(dict_data)
                self.zstd_dctx = zstd.ZstdDecompressor(dict_data=self.zstd_dict)
            except Exception as e:
                self.log_callback(f"Warning: Failed to load zstd dictionary: {e}")

        self._seed_trial_slots()

    def _seed_trial_slots(self):
        """Carry the trial pairing over from the newest snapshot.

        **The only state here that cannot be rebuilt from the wire.**
        Everything else this addon caches arrives again at the next
        login; which trial slots an event offers is named ONLY by the
        request that claims one, so a session with no claim in it would
        write an empty table over what an earlier one worked out --
        and the pairing would last exactly as long as the capture that
        saw it.

        Read once, at startup, and failures are silent: a missing or
        unreadable snapshot means starting empty, which is where this
        began anyway.
        """
        try:
            saved = sorted(self.output_dir.glob("memory_fragments_*.json"))
            if not saved:
                return
            with open(saved[-1], "r", encoding="utf-8") as f:
                previous = json.load(f)
            known = previous.get("combatant_trial_slots")
            if isinstance(known, dict):
                for event, slots in known.items():
                    if isinstance(slots, list):
                        self.trial_slots[str(event)] = [str(s) for s in slots]
        except Exception:
            pass

    def _detect_region(self):
        """The region this session's connections actually went to.

        Observed in `server_connect` from the client's SNI, because both
        regions are redirected and the game picks. NOT read from the
        payload: `world_id` is something the CLIENT sends in its auth
        request, and the server's `user` record does not carry it -- a
        reader of that field finds it absent every time and answers
        None.
        """
        return self.detected_region

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
        # When the proxy took the message off the wire, which is the
        # reference the lag stamp measures from.
        at = getattr(msg, "timestamp", None) or time.time()
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
            self._note_sent(parsed, at)

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
                    self._write_debug(entry)
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

            # One frame carries either a single reply object or a LIST
            # of them: the client batches its commands whenever it has
            # several to send, and the server answers in kind. Both forms
            # reach the same handler, one reply at a time.
            if isinstance(data, dict):
                payloads = [data]
            elif isinstance(data, list):
                payloads = [item for item in data if isinstance(item, dict)]
            else:
                return

            for payload in payloads:
                self._reply_times = (self.qid_sent.pop(payload.get("qid"),
                                                       None), at)
                self._handle_server_payload(payload, len(content))

            if self._save_pending:
                self._save_pending = False
                self._save_data()

        except Exception as e:
            self.log_callback(f"Error: {e}")
        finally:
            self._reply_times = None

    def _note_sent(self, parsed, at):
        """When each request in a client message went out, by qid, for
        the lag stamp. Debug mode only: nothing else reads it."""
        if not self.debug_mode or not isinstance(parsed, list):
            return
        for entry in parsed:
            if isinstance(entry, dict) and entry.get("qid") is not None:
                if len(self.qid_sent) > CATALOGUE_MAX:
                    self.qid_sent.clear()
                self.qid_sent[entry["qid"]] = at

    def server_connect(self, data):
        """Point this connection at its own region's server.

        Both game hostnames are redirected to loopback, so a connection
        can be for either region -- but mitmproxy's reverse mode has a
        single upstream, fixed at launch. The client's SNI still carries
        the hostname it believes it is talking to, and that is what
        picks the address.

        Leaving the address alone falls back to the launch upstream,
        which is the behaviour from before both regions were redirected.
        """
        sni = getattr(data.client, "sni", None)
        if not sni:
            return
        route = REGION_ROUTES.get(sni)
        if route is None:
            return
        region, ip, port = route
        try:
            data.server.address = (ip, port)
        except Exception as e:
            self.log_callback("[!] Could not route " + str(sni) + ": " + str(e))
            return
        self._note_region(region)

    def _note_region(self, region):
        """Record which server region this session is talking to."""
        if region in self.seen_regions:
            return
        self.seen_regions.add(region)
        if self.detected_region is None:
            self.detected_region = region
            self.log_callback("[REGION] " + str(region))
        else:
            self.log_callback(
                "[X] A game on a second server region connected ("
                + str(region) + "). Two games are running at once; "
                "close the extra one and capture again."
            )

    def _account_of(self, data):
        """Account id in this payload, or None if it carries no user."""
        user = data.get("user")
        if not isinstance(user, dict):
            return None
        return user.get("id") or user.get("auth_id")

    def _account_is_consistent(self, data):
        """False once a SECOND account has been seen this session.

        Two games running at once -- two accounts, or the same region
        twice -- both reach this proxy, and their payloads are
        indistinguishable after the fact: only the `user` record names
        an account, and piece_items do not. Merging them produces one
        snapshot holding one account's fragments against another's
        roster, with nothing to detect it downstream. So the first
        account wins and the rest of the session is dropped.
        """
        if self.mixed_accounts:
            return False
        account = self._account_of(data)
        if account is None:
            return True
        if self.session_account is None:
            self.session_account = account
            return True
        if account == self.session_account:
            return True
        self.mixed_accounts = True
        self.log_callback(
            "[X] A second game account started sending data. Capture "
            "has stopped to avoid mixing two accounts into one "
            "snapshot. Close the extra game, then capture again."
        )
        return False

    def _handle_server_payload(self, data, frame_size):
        """Act on one reply object from the server.

        A frame yields one of these when the server answers a single
        command and several when it answers a batch, so nothing here
        knows how the reply arrived. frame_size describes the whole
        frame and is recorded in the debug log.
        """
        # Debug: log every decoded message before filtering
        if self.debug_file:
            entry = {
                "ts": datetime.now().isoformat(),
                "direction": "server_to_client",
                "keys": list(data.keys()),
                "size": frame_size,
                "data": data
            }
            self._write_debug(entry)

        self._note_keys(data)

        if data.get("res") != "ok":
            return

        # Dropped AFTER the debug log, so a mixed session is still
        # visible in the debug file, and BEFORE anything that mutates
        # cached state.
        if not self._account_is_consistent(data):
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

        # The daily coffee was drunk. See `pending_coffees`: the reply
        # confirms it and says nothing else about it, so the cached
        # flag is turned off here rather than read off the wire.
        if qid is not None and qid in self.pending_coffees:
            self.pending_coffees.discard(qid)
            if self._set_day_field("is_coffee_possible", False):
                self._save_pending = True

        # A trial claim answers with the ONE slot row it changed, under
        # the bare key `entity`. Folded into the board rather than
        # replacing it -- everything else about the trials is untouched.
        entity = data.get("entity")
        if (isinstance(entity, dict)
                and entity.get("event_combatant_trial_slot_id")):
            if not isinstance(self.combat_trials, list):
                self.combat_trials = []
            slot = entity["event_combatant_trial_slot_id"]
            for index, row in enumerate(self.combat_trials):
                if (isinstance(row, dict)
                        and row.get("event_combatant_trial_slot_id") == slot):
                    self.combat_trials[index] = entity
                    break
            else:
                self.combat_trials.append(entity)
            self._save_pending = True

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

        # A fragment that arrives as a REWARD is shaped differently and
        # is never at the top level -- see `_reward_pieces`. Without
        # this, everything a Chaos week reward or a Simulation run pays
        # is missing from the inventory until the next login.
        if self.inventory_data and "piece_items" in self.inventory_data:
            gained = self._reward_pieces(data)
            if gained:
                self._apply_pieces_create({"pieces": gained})

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
                    self._save_pending = True

            # Check for character data in new format
            if isinstance(info, dict) and "character" in info:
                char_info = info.get("character", {})
                if not self.character_data:
                    self.character_data = {}
                self.character_data["info_character"] = char_info
                self._save_pending = True

        # Capture inventory data (Memory Fragments)
        if "piece_items" in data:
            self.inventory_data = data
            self._save_pending = True

        # Capture character data.
        #
        # Two very different messages arrive under the same key. The
        # login payload carries the FULL roster -- every character and
        # every partner card -- alongside the user record. Action
        # responses (re-equipping a partner, for one) reply with the
        # same `characters` key but only the entries the server
        # touched: the partner instance, its new owner and its old
        # owner. Overwriting the cache with one of those deltas
        # destroys the roster, which silently empties character_info
        # and everything derived from it -- the Combatants tab, the
        # exclude checklist, the res_id lookups the exclude step
        # needs -- with no error anywhere.
        #
        # So a characters list replaces the cache only when it
        # accounts for everything already in it; otherwise it is
        # merged and nothing is dropped.
        has_characters = "characters" in data and isinstance(data.get("characters"), list)
        has_user = "user" in data

        if has_user:
            self._check_for_relaunch(data["user"])

        if has_characters:
            self._merge_character_data(data)
            self._save_pending = True
        elif has_user:
            # A user-record update with no roster attached: patch the
            # cached payload rather than replacing it, or the roster
            # goes the same way as above.
            if self.character_data:
                self.character_data["user"] = data["user"]
            else:
                self.character_data = data
            self._save_pending = True

        # The lobby reply carries the schedule of every gacha banner,
        # past and upcoming. It arrives batched, alongside no roster and
        # no inventory, so it is kept on its own and written out with
        # whatever the next save carries.
        schedules = data.get("event_schedules")
        if isinstance(schedules, dict):
            # **Kept WHOLE, not just the banners.** Every content the
            # Checklist counts days on has its window in here -- the
            # Sortie season, the Basin, the pass, the seasonal event,
            # the Chaos Matrix -- and no other payload dates any of
            # them. See `schedules.py`.
            self.event_schedules = schedules
            self._save_pending = True
            if isinstance(schedules.get("GACHA"), dict):
                self._report_unknown_units()

        # The excursion board's reply: one row per combatant that has
        # been taken on one, carrying which of the visits it has
        # experienced. It arrives in its own frame with a reset record
        # and nothing else, so it is kept aside like the banners.
        #
        # Replaced whole rather than merged: the reply is the board,
        # every row of it, and a combatant with no row has been on no
        # excursion -- which is a reading, not a gap to preserve.
        if isinstance(data.get("char_visits"), list):
            self.char_visits = data["char_visits"]
            self._save_pending = True

        # What the server says your holdings now are. FIVE keys carry
        # the same envelope -- a gain, a spend, a use, a town calamity
        # and an event mission claim all report the item's whole record
        # -- so one handler takes them rather than five that would
        # drift apart.
        #
        # **Nothing else on the wire updates an item count.** The
        # inventory arrives once, at login, and every later change is
        # one of these, so a key missing from this list is a payout
        # that lands nowhere: no save, no log line, and the Materials
        # tab serving whatever was true when the game started.
        #
        # `result` is the most OVERLOADED key on the wire -- a string,
        # a bool, a stage's step record -- so it counts only where it
        # carries a rewards payload or nests one. See `_nested_reward`.
        # **`item` is guarded the same way** for its name rather than
        # its history: it has only ever arrived as an envelope, on a
        # login event's claim, and a key that generic is one the game
        # can reuse for anything.
        for key in ("add_result", "item_result", "dec_result",
                    "calamity_reward", "result", "item"):
            payload = data.get(key)
            if not isinstance(payload, dict):
                continue
            if key in ("result", "item") and not ("currency" in payload
                                                  or "items" in payload):
                # **A story episode nests its rewards one deeper**, as
                # `result.story_reward_result.reward`, and the `result`
                # around them carries no `currency` or `items` of its
                # own -- so the guard above is exactly what dropped
                # them. Everything a story paid landed nowhere and the
                # Capture Log reported no receipt.
                payload = self._nested_reward(payload)
                if payload is None:
                    continue
            self._apply_totals(payload, spent=key == "dec_result")

        # **A run's own clear reward is nested**, under the stage
        # reply's `return_info` and never at the top level:
        # `result_reward_drop_item` is what finishing the run paid, and
        # `chaos_assault_result.refund_item_result` hands a Sortie's
        # entry deposit back. Both are ordinary totals envelopes.
        #
        # Swept by SHAPE rather than by name, because the names are
        # per-content and there is no reason to think the next kind of
        # run will reuse them. **Safe to over-collect**: an envelope
        # states what a holding now is, so taking one twice writes the
        # same number. The drop LISTS beside them in the same payload
        # -- `confirm_drop_item` -- would double, which is why only
        # envelopes are swept. See `_nested_rewards`.
        stated = set()
        for nested in self._nested_rewards(data.get("return_info")):
            stated |= self._apply_totals(nested)

        # And the run's own tally -- REPORTED, never applied, and only
        # where the envelopes above have not already named the same
        # items.
        #
        # A Simulation or Chaos run's `result_reward_drop_item` states
        # the whole run as holdings, so reporting the list beside it
        # prints one payout twice under two different words. A Sortie's
        # is `{}` and only its deposit refund carries anything, so the
        # list is the only statement of what that run paid -- which is
        # why this exists. The test is WHICH items were named, not
        # whether any envelope spoke: the refund speaks and says
        # nothing about the payout.
        self._report_run_total(
            (data.get("return_info") or {}).get("confirm_drop_item")
            if isinstance(data.get("return_info"), dict) else None,
            stated)

        # A stage's rewards, which are the exception: a LIST of drops
        # with no record and no total, so they are added rather than
        # written in. See `_apply_drops`.
        #
        # **`chaos_free_reward_result` is the same list under another
        # name** -- what a Chaos run or an encounter pays out at its
        # report screen. Read only under the first name, a whole report
        # screen's reward went unreported: the items still reached the
        # snapshot, because the client asks for the inventory again
        # afterwards, so the only sign was the log staying quiet.
        #
        # **`drop_item` is NOT a third name for it.** It is the run's
        # accumulated tally, re-sent after every battle and never the
        # payout -- see `docs/capture_pipeline.md` and the check that
        # pins it.
        for key in ("drop_item_result", "chaos_free_reward_result"):
            drops = data.get(key)
            if isinstance(drops, list) and drops:
                # The qid is what stops a re-applied frame doubling a
                # count, so each key gets its own -- a reply carrying
                # both would otherwise apply only whichever came first.
                self._apply_drops(drops, None if qid is None
                                  else "%s/%s" % (qid, key))

        # What the recurring tasks stand at. Three keys, kept aside like
        # the board above because each arrives in a frame carrying no
        # roster and no inventory.
        #
        # `point_entity` is the DAILY and WEEKLY activity totals, and
        # arrives with the reply to a Daily "Claim All".
        # `season_pass_entity` is the Arkhianon Supply's own rank and
        # exp, and `mission_entities` the per-mission state -- which
        # comes in TWO shapes: the login burst sends the `content_*`
        # achievements and a pass claim sends `pass_mission_*` rows
        # carrying `complete_time`. Both are kept; the shape is told
        # apart by the keys on a row, not by which frame it came in.
        if isinstance(data.get("point_entity"), dict):
            self.point_entity = data["point_entity"]
            self._save_pending = True
        if isinstance(data.get("season_pass_entity"), dict):
            self.season_pass = data["season_pass_entity"]
            self._save_pending = True
        # At login it is a LIST of every pass the account has played,
        # the live one among them. Kept whole: which is live is a
        # reading, and the caller makes it.
        if isinstance(data.get("season_pass_entities"), list):
            self.season_passes = data["season_pass_entities"]
            self._save_pending = True
        if isinstance(data.get("mission_entities"), list):
            self._merge_missions(data["mission_entities"])
            self._save_pending = True
        # An EVENT's missions arrive under their own key and in the
        # same shape, so they join the same cache -- the ids do not
        # collide, every one of them starting `event_`. This is what
        # says an event has been finished and its rewards taken, which
        # nothing in `event_schedules` does.
        if isinstance(data.get("event_mission_entities"), list):
            self._merge_missions(data["event_mission_entities"])
            self._save_pending = True
        # The Full-Scale Offensive's stages, one row each with the
        # stars taken and the best score. Replaced whole: the reply IS
        # the board, and a stage's absence from it is a reading.
        if isinstance(data.get("remnants_entities"), dict):
            self.remnants = data["remnants_entities"]
            self._save_pending = True
        # The Chaos Matrix's own record, and the Overclock event's
        # daily counter. **The counter arrives under TWO names**: the
        # login sends `overclock_entities` and a Simulation run sends
        # the rows it changed as `result_overclock_entities`, so the
        # second is merged rather than replacing the board.
        # The trial slots themselves: each says when its reward
        # was last claimed. A claim reply sends the ONE row it
        # changed as `entity`, so that is merged rather than
        # replacing the board.
        if isinstance(data.get("combat_trial_entities"), list):
            self.combat_trials = data["combat_trial_entities"]
            self._save_pending = True
        # How many of a season's star rewards have been CLAIMED, one
        # row per season. Absent until the first claim, so no row is a
        # season nobody has taken anything from. A claim answers with
        # the single row it changed, under `reward_doc`.
        if isinstance(data.get("reward_entities"), list):
            self.season_rewards = data["reward_entities"]
            self._save_pending = True
        doc = data.get("reward_doc")
        if isinstance(doc, dict) and doc.get("res_id") is not None:
            if not isinstance(self.season_rewards, list):
                self.season_rewards = []
            for index, row in enumerate(self.season_rewards):
                if isinstance(row, dict) and row.get("res_id") == doc["res_id"]:
                    self.season_rewards[index] = doc
                    break
            else:
                self.season_rewards.append(doc)
            self._save_pending = True
        # An event's own progress record, whatever shape it takes.
        # Each kind of event has its own field and they share nothing
        # but the naming, so they are kept by the field they arrive
        # under and the Checklist reads whichever it knows -- a set of
        # puzzles here, a stated total there.
        #
        # **Every `event_*` table, not a list of the ones in use.**
        # These are what say how BIG an event is -- `event_bartender_1`'s is
        # one row per day of it -- and the total a Checklist row needs
        # is a count over them. A table nobody reads yet costs a few
        # kilobytes; a table nobody KEPT cannot be read later, because
        # it only ever arrives at login. Eight of them on this account
        # come to 16KB against a 2.2MB snapshot, and the bulky
        # story-node payloads in the same reply do not carry the
        # prefix. See `docs/events.md`.
        for key, value in data.items():
            if not isinstance(value, dict) or not value or not key.startswith(
                    "event_"):
                continue
            # **The tables with a reader of their own stay out.** Each
            # is merged its own way and written into the snapshot under
            # its own name; sweeping one up here would put a second
            # copy in the same file, under the same key, and the later
            # of the two wins.
            if key in EVENT_FIELDS_HANDLED:
                continue
            # **The SINGULAR of a collection is the one row that
            # changed**, and it arrives under its own key rather than
            # inside the plural. Finishing a summer puzzle answers with
            # `event_summer_set_entity`, so without this the set's
            # `complete_time` stays 0 until the next login -- the
            # snapshot shows an unfinished puzzle beside the reward it
            # just paid for. **And it must not be kept as a table of
            # its own**: a second copy under a second name is one more
            # thing for a reader to pick the wrong one of.
            # A singular carrying a `res_id` is ONE ROW; a singular
            # without one is a record of its own, like an event's
            # define. That test rather than "have I seen the plural" --
            # a capture started mid-session sees the row before it ever
            # sees the collection, and would then keep the second copy.
            if key.endswith("_entity") and value.get("res_id") is not None:
                held = self.event_defines.setdefault(
                    key[:-len("_entity")] + "_entities", {})
                if isinstance(held, dict):
                    held[str(value["res_id"])] = value
                    self._save_pending = True
                continue
            if key.endswith("_entity") or key.endswith("_entities"):
                self.event_defines[key] = value
                self._save_pending = True
        # The login-streak events: days shown up, days claimed.
        #
        # **Merged by event, never replaced.** The login burst sends
        # the whole list, but a reward claim has only ever been seen
        # from the login side -- so whatever shape a claim reply turns
        # out to use, a partial list must update its own rows rather
        # than throw the rest away. Both the plural and the singular
        # spelling are taken, which is how every other entity here
        # arrives.
        for key in ("attendance_entities", "result_attendance_entities",
                    "attendance_entity"):
            rows = data.get(key)
            if isinstance(rows, dict) and rows.get("event_id") is not None:
                rows = [rows]
            elif isinstance(rows, dict):
                rows = list(rows.values())
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("event_id") is None:
                    continue
                # **`completed` survives the replacement.** It is the
                # only thing that says a streak is OVER rather than
                # claimed for today -- the two look identical in the
                # record, `current_days` equal to `received_days` in
                # both -- and it arrives on the claim reply alone. The
                # login that follows sends a row without it, and
                # letting that row win would lose the answer for good.
                was = self.attendance.get(str(row["event_id"]))
                if isinstance(was, dict) and was.get("completed"):
                    row = dict(row)
                    row["completed"] = was["completed"]
                self.attendance[str(row["event_id"])] = row
                self._save_pending = True
        # Whether an event is FINISHED, which is the one thing a count
        # of claimed missions cannot say -- the account holds only the
        # rows the game has issued so far, so a full tally is a floor.
        # `event_achieve_state` is 1 once the event's own completion
        # reward has been taken. Merged by event: the login sends every
        # row, and a claim is expected to send one.
        #
        # **The claim that sets it answers under the bare key
        # `entity`**, which is the same key a trial claim uses for a
        # different row -- so the flag itself is what says which this
        # is. Reading only the three spelled-out keys dropped the one
        # reply that ever carries a completion, and the event went on
        # reading as unfinished with the wire having said otherwise.
        for key in ("event_mission_reward_entities",
                    "result_event_mission_reward_entities",
                    "event_mission_reward_entity", "entity"):
            rows = data.get(key)
            if isinstance(rows, dict) and rows.get("res_id") is not None:
                rows = [rows]
            elif isinstance(rows, dict):
                rows = list(rows.values())
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("res_id") is None:
                    continue
                if key == "entity" and "event_achieve_state" not in row:
                    continue
                self.event_rewards[str(row["res_id"])] = row
                self._save_pending = True
        if isinstance(data.get("zero_orb_entity"), dict):
            self.zero_orb = data["zero_orb_entity"]
            self._save_pending = True
        if isinstance(data.get("overclock_entities"), dict):
            self.overclock = dict(data["overclock_entities"])
            self._save_pending = True
        # **A doubled run's own row arrives nested**, under the stage
        # reply's `return_info` rather than at the top level -- which is
        # why the Overclock row sat at its login value all session while
        # `return_info.result_reward_drop_overclock` paid out beside it.
        # Both places are read; nothing else in the reply is.
        for carrier in (data, data.get("return_info")):
            if not isinstance(carrier, dict):
                continue
            if not isinstance(carrier.get("result_overclock_entities"), list):
                continue
            if not isinstance(self.overclock, dict):
                self.overclock = {}
            for row in carrier["result_overclock_entities"]:
                if isinstance(row, dict) and row.get("res_id"):
                    self.overclock[str(row["res_id"])] = row
            self._save_pending = True
        # A Daily Check-in claim answers with NO record at all -- the
        # event, the streak before, the streak after and whether that
        # finished it. So the cached row is patched from those rather
        # than replaced by one, and the next login sends the real thing.
        #
        # **`completed` is kept, and it is the only thing that can say
        # a streak has ENDED.** Streak lengths vary by event -- one
        # account's history holds runs of 7, 10, 14 and 21 days -- and
        # a finished streak's record is identical to one claimed for
        # today, `current_days` equal to `received_days` in both.
        streak = data.get("received_days_after")
        event_id = data.get("event_id")
        if event_id is not None and isinstance(streak, int) and not isinstance(
                streak, bool):
            row = self.attendance.get(str(event_id))
            if not isinstance(row, dict):
                row = {"event_id": event_id}
                self.attendance[str(event_id)] = row
            row["received_days"] = streak
            if data.get("completed") is True:
                row["completed"] = True
            self._save_pending = True
        # **At LOGIN the pass missions arrive somewhere else entirely**,
        # nested as `season_pass_missions[<pass id>][<mission id>]`
        # rather than in the flat `mission_entities` list -- which is
        # why a snapshot held the 30 `content_*` achievements and none
        # of the twenty-odd pass rows.
        pass_missions = data.get("season_pass_missions")
        if isinstance(pass_missions, dict):
            for group in pass_missions.values():
                if isinstance(group, dict):
                    self._merge_missions(
                        [row for row in group.values()
                         if isinstance(row, dict)])
            self._save_pending = True

        # And ONE row, singular, when a mission's reward is claimed --
        # which is the frame that sets its `complete_time`. Without
        # this the cache keeps the row as it was before the claim, so
        # a mission claimed during the session still reads unclaimed.
        if isinstance(data.get("mission_entity"), dict):
            self._merge_missions([data["mission_entity"]])
            self._save_pending = True

        # And a LIST of them, under the bare key `entities`, when an
        # event's rewards are claimed -- `complete_event_mission_all`
        # and its nodelist twin both answer this way. Without it a
        # reward claimed during the session still reads unclaimed, and
        # a row the claim ISSUED is missing from the denominator too.
        #
        # **`entities` is not always missions.** The Full-Scale
        # Offensive's board arrives under the same key as a dict keyed
        # by `list_id`, so the guard is a LIST of rows carrying both
        # `res_id` and `complete_time` -- the shape every claim reply
        # ever captured has, and one the board does not have.
        rows = data.get("entities")
        if isinstance(rows, list):
            claimed = [row for row in rows
                       if isinstance(row, dict) and row.get("res_id")
                       is not None and "complete_time" in row]
            if claimed:
                self._merge_missions(claimed)
                self._save_pending = True

        # What limits a stage to N runs a period: `content_boss` is the
        # Simulation Challenges. Same shape as a shop row and the same
        # lazy reset -- `count` is the runs TAKEN this period and
        # `reset_time` is when it last moved.
        if isinstance(data.get("stage_limit_entities"), dict):
            for res_id, row in data["stage_limit_entities"].items():
                if isinstance(row, dict):
                    self.stage_limits[str(res_id)] = row
            self._save_pending = True

        # The same shape, for what the ACCOUNT has bought rather than
        # what a stage allows: `subscription_1` is the monthly pass,
        # and its `expire_time` is the one thing on the wire that says
        # how long the daily gift keeps coming. `vi1` is the day its
        # reward was last taken, in the same day numbering everything
        # else here uses.
        if isinstance(data.get("issued_limit_entities"), dict):
            for res_id, row in data["issued_limit_entities"].items():
                if isinstance(row, dict):
                    self.issued_limits[str(res_id)] = row
            self._save_pending = True

        # **The claim answers in a LIST, under a name of its own.**
        # `lobby/monthly_subscription_reward` pays the daily gift and
        # sends the row straight back as `issued_entities` -- the same
        # record, with `count` and `vi1` already moved. Read only at
        # login, the row says what the login said until the next one.
        issued = data.get("issued_entities")
        for row in issued if isinstance(issued, list) else ():
            if isinstance(row, dict) and row.get("res_id") is not None:
                self.issued_limits[str(row["res_id"])] = row
                self._save_pending = True

        # **The town's own daily block arrives on its own**, at the top
        # level of a reply -- ordering a coffee, running an excursion,
        # or asking `check_day_changeable_data` -- where the cache
        # holds it nested under `characters`. Nothing merged it, so the
        # coffee flag and the excursion count stayed at whatever the
        # login said for the whole session.
        day_data = data.get("day_changeable_data")
        if isinstance(day_data, dict) and isinstance(self.character_data,
                                                     dict):
            town = self.character_data.setdefault("town_data", {})
            if isinstance(town, dict):
                town["day_changeable_data"] = day_data
                self._save_pending = True

        # And so does one excursion board row, after a visit. The board
        # is a LIST keyed by res_id, so the row replaces its own rather
        # than the whole board.
        visit = data.get("new_char_visit")
        if isinstance(visit, dict) and visit.get("res_id") is not None:
            if not isinstance(self.char_visits, list):
                self.char_visits = []
            for index, row in enumerate(self.char_visits):
                if isinstance(row, dict) and row.get("res_id") == visit["res_id"]:
                    self.char_visits[index] = visit
                    break
            else:
                self.char_visits.append(visit)
            self._save_pending = True

        # The month the shops' monthly products reset on. Sent once, at
        # login, and the only thing that says when a monthly period
        # began -- a shop row's own `count` is stale until the first
        # purchase of the period, so the boundary is what tells one
        # from the other.
        # The Basin of Hyperspace, whose progress is its OBJECTIVES:
        # `mission_seasson_entities` (the game's own spelling) holds
        # them per Basin season, and `season_entities` the stages. Both
        # arrive with the reply to `hyperspace/get_list` and nowhere
        # else, so they are kept aside like the boards above.
        if isinstance(data.get("mission_seasson_entities"), dict):
            self.basin_missions = data["mission_seasson_entities"]
            self._save_pending = True
        if isinstance(data.get("season_entities"), dict):
            self.basin_stages = data["season_entities"]
            self._save_pending = True

        if isinstance(data.get("shop_res_data"), dict):
            self.shop_definitions = data["shop_res_data"]
            self._save_pending = True

        if isinstance(data.get("month_start"), int):
            self.month_start = data["month_start"]
            self._save_pending = True
        if isinstance(data.get("month_end"), int):
            self.month_end = data["month_end"]
            self._save_pending = True

        # The shops' own per-product rows: what has been bought this
        # period, when it was last bought, and the lifetime total. TWO
        # SHAPES again -- `shop_list` is every product at login and
        # `shop_entity` is the one just bought -- so both fold into one
        # cache rather than replacing it.
        shop_list = data.get("shop_list")
        if isinstance(shop_list, dict):
            for product_id, row in shop_list.items():
                if isinstance(row, dict):
                    self.shop_products[str(product_id)] = row
            self._save_pending = True
        shop_entity = data.get("shop_entity")
        if isinstance(shop_entity, dict) and shop_entity.get("res_id"):
            self.shop_products[str(shop_entity["res_id"])] = shop_entity
            self._save_pending = True

        # The Great Rift standings, keyed by season and then by rank
        # slot. This is where the weekly score lives -- nothing else
        # carries it -- and the frame it arrives in holds a dozen other
        # disaster records the snapshot does not want, so it is picked
        # out by name and kept aside like the two above.
        if isinstance(data.get("disaster_boss_rank_entities"), dict):
            self.disaster_ranks = data["disaster_boss_rank_entities"]
            self._save_pending = True
        # **And one rank's row, on every reply about that rank** --
        # entering it, finishing a run, claiming its weekly reward --
        # as `disaster_boss_rank_entity`, singular. The whole standings
        # come only when the Great Rift's screen lists them, so without
        # this a run's new score waits for the next time it is opened.
        row = data.get("disaster_boss_rank_entity")
        if isinstance(row, dict) and row.get("season_id") \
                and row.get("define_id"):
            ranks = dict(self.disaster_ranks) \
                if isinstance(self.disaster_ranks, dict) else {}
            season = ranks.get(row["season_id"])
            season = dict(season) if isinstance(season, dict) else {}
            season[row["define_id"]] = row
            ranks[row["season_id"]] = season
            self.disaster_ranks = ranks
            self._save_pending = True
        # **The two Sortie ladders, per combatant.** Both arrive whole
        # on the login burst and again as they are earned, and both are
        # SPARSE: nothing is sent for a rung the game has not offered
        # yet, so no snapshot can say how LONG a ladder is. A row being
        # present is not the rung being done either -- an achievement
        # row is issued while it is still in progress. `complete_time`
        # is what finishes one; `sortie_progress.py` does the reading.
        #
        # Merged rather than replaced: the run-end reply carries only
        # the rungs that run earned, where the login carries every one
        # the account has.
        for key, held in (("assault_char_achievement_entities",
                           self.assault_char_achievements),
                          ("assault_char_title_entities",
                           self.assault_char_titles)):
            rows = data.get(key)
            rows = (rows if isinstance(rows, list)
                    else list(rows.values()) if isinstance(rows, dict)
                    else None)
            if not rows:
                continue
            for row in rows:
                if isinstance(row, dict) and row.get("res_id"):
                    held[str(row["res_id"])] = row
            self._save_pending = True

        # And the season's own row, which carries the WEEKLY CHAOS
        # score. A different record from the standings above, arriving
        # in the same frame.
        if isinstance(data.get("disaster_entities"), list):
            self.disaster_seasons = data["disaster_entities"]
            self._save_pending = True

        # The Gacha History: pages of the game's Rescue records, a
        # banner's rates, the pity counters. Its own file, not the
        # snapshot -- see `_merge_gacha` -- and a failure there must
        # never cost the rest of the capture.
        asked = self.gacha_requests.pop(qid, None) if qid is not None \\
            else None
        try:
            self._merge_gacha(asked, data)
        except Exception as e:
            self.log_callback("[X] Gacha History: " + str(e))

    # ------------------------------------------------ the gacha history

    def _merge_gacha(self, asked, data):
        """Fold one reply's history page, rates or pity counters into
        the Gacha History's file.

        **The one record here a later capture cannot rebuild.** The game
        lists about half a year of pulls and drops the rest, so the file
        lives in `gacha_history/`, where neither the snapshot rotation
        nor the archive reaches, and a reply only ever ADDS to it: a
        record the game has stopped listing stays, which is the point.
        `gacha_history.py` does the reading.

        Records are kept exactly as the wire sent them, keyed by the `id`
        the game gives each one.
        """
        records = data.get("gacha_history_list")
        records = records if isinstance(records, list) else None
        rates = None
        if (asked and asked[0] == "get_rate"
                and isinstance(data.get("rates"), dict)):
            rates = {key: data.get(key)
                     for key in ("rates", "total_rate_info", "pools")}
        pities = []
        for key in ("gacha_pity_entity_list", "gacha_pities"):
            if isinstance(data.get(key), list):
                pities.extend(row for row in data[key]
                              if isinstance(row, dict))
        if isinstance(data.get("gacha_pity_entity"), dict):
            pities.append(data["gacha_pity_entity"])
        if records is None and rates is None and not pities:
            return

        store = self._read_gacha_store()
        if store is None:
            return
        held = {}
        for row in store["records"]:
            if isinstance(row, dict) and row.get("id") not in (None, ""):
                held[str(row["id"])] = row
        before = list(held.values())
        added = 0
        for row in records or ():
            if not isinstance(row, dict) or row.get("id") in (None, ""):
                continue
            if str(row["id"]) not in held:
                held[str(row["id"])] = row
                added += self._gacha_pulls_in(row)
        changed = bool(added)
        when = datetime.now().isoformat(timespec="seconds")

        # The FIRST page -- no cursor -- is the newest pulls, so reading
        # it is what brings a banner up to date. The rest only reach
        # further back.
        if records is not None and asked and asked[0] == "history" \\
                and not asked[2]:
            store["read"][asked[1]] = when
            changed = True
        if rates is not None:
            was = store["rates"].get(asked[1])
            if not isinstance(was, dict) or any(
                    was.get(key) != value for key, value in rates.items()):
                store["rates"][asked[1]] = dict(rates, seen=when)
                changed = True
        for row in pities:
            name = row.get("res_id")
            was = store["pity"].get(name)
            if not name or was == row:
                continue
            # `version` is the record's write counter, so an older copy
            # arriving late cannot overwrite a newer one.
            if isinstance(was, dict) and self._gacha_int(
                    row.get("version")) < self._gacha_int(was.get("version")):
                continue
            store["pity"][name] = row
            changed = True
        if not changed:
            return

        # Newest first, the order the game lists them in.
        store["records"] = sorted(
            held.values(), reverse=True,
            key=lambda r: (self._gacha_int(r.get("createAt")),
                           self._gacha_int(r.get("id"))))
        if not self._write_gacha_store(store, before):
            return
        if added:
            total = sum(self._gacha_pulls_in(r) for r in store["records"])
            self.log_callback(
                "[GACHA] Rescue records: +%d pulls, %d kept" % (added, total))
        self.log_callback(GACHA_MARKER)

    @staticmethod
    def _gacha_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _gacha_pulls_in(record):
        """How many pulls one record is. `reward` is JSON TEXT on the
        wire -- `"[1009,30117]"` -- not a list."""
        reward = record.get("reward")
        if isinstance(reward, str):
            try:
                reward = json.loads(reward)
            except ValueError:
                return 0
        return len(reward) if isinstance(reward, list) else 0

    def _gacha_path(self):
        return self.output_dir / GACHA_FOLDER / GACHA_FILE

    def _read_gacha_store(self):
        """The Gacha History's file, or a fresh one where there is none.

        **Falls back to the backup** where the file is missing or will
        not parse: a write renames the file to its backup before the new
        copy takes its place, so a capture killed between the two leaves
        only the backup. Starting fresh there would put a one-page
        history over the whole of it at the next write.

        None where something is there and cannot be read at all --
        writing then would do the same.
        """
        path = self._gacha_path()
        problems = []
        for candidate in (path, path.with_name(path.name + ".bak")):
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                problems.append(candidate.name + ": " + str(e))
                continue
            if not isinstance(data, dict):
                problems.append(candidate.name + ": not a history file")
                continue
            for key, empty in (("records", list), ("rates", dict),
                               ("pity", dict), ("read", dict)):
                if not isinstance(data.get(key), empty):
                    data[key] = empty()
            return data
        if problems:
            if not self._gacha_refused:
                self._gacha_refused = True
                self.log_callback(
                    "[X] Gacha History could not be read ("
                    + "; ".join(problems) + "). Nothing new is kept "
                    "until it can be.")
            return None
        return {"kind": GACHA_KIND, "version": 1, "records": [],
                "rates": {}, "pity": {}, "read": {}}

    def _write_gacha_store(self, store, before):
        """Write the Gacha History through a checked copy.

        The copy is written and read back, and must equal what was meant
        and still hold every record `before` held, unchanged. Only then
        does the file become `<name>.bak` -- which replaces the older
        backup, and is how the older one goes -- and the copy take its
        place. A failure before that leaves the file exactly as it was.

        The same procedure as `gacha_history.write_verified`, which the
        app uses for its imports; a generated addon cannot import it.
        `checks/check_gacha_history.py` drives both.
        """
        path = self._gacha_path()
        tmp = path.with_name(path.name + ".tmp")
        bak = path.with_name(path.name + ".bak")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            with open(tmp, "r", encoding="utf-8") as f:
                back = json.load(f)
        except (OSError, ValueError) as e:
            self._gacha_discard(tmp)
            self.log_callback(
                "[X] Gacha History: the copy could not be written: " + str(e))
            return False
        problems = [] if back == store else ["it does not read back as "
                                             "what was written"]
        kept = {}
        if isinstance(back, dict) and isinstance(back.get("records"), list):
            kept = {str(r.get("id")): r for r in back["records"]
                    if isinstance(r, dict)}
        lost = [row for row in before if kept.get(str(row.get("id"))) != row]
        if lost:
            problems.append("%d records went missing or changed" % len(lost))
        if problems:
            self._gacha_discard(tmp)
            self.log_callback(
                "[X] Gacha History: the new copy failed its check ("
                + "; ".join(problems) + "), so " + path.name
                + " is unchanged.")
            return False
        try:
            if path.exists():
                self._gacha_replace(path, bak)
            self._gacha_replace(tmp, path)
        except OSError as e:
            # The file went to its backup and the copy could not follow:
            # put it back rather than leave the history on the backup.
            if not path.exists() and bak.exists():
                try:
                    self._gacha_replace(bak, path)
                except OSError:
                    pass
            self._gacha_discard(tmp)
            self.log_callback(
                "[X] Gacha History: " + path.name + " could not be "
                "replaced: " + str(e))
            return False
        return True

    @staticmethod
    def _gacha_replace(src, dst):
        for attempt in range(SAVE_REPLACE_TRIES):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if attempt == SAVE_REPLACE_TRIES - 1:
                    raise
                time.sleep(SAVE_REPLACE_WAIT)

    @staticmethod
    def _gacha_discard(path):
        try:
            path.unlink()
        except OSError:
            pass

    @staticmethod
    def _nested_reward(payload):
        """A rewards payload buried inside a `result`, or None.

        A story episode answers with
        `result.story_reward_result.reward.{currency, items}`, and the
        `result` around it carries only `is_clear`, the node's id and a
        title level -- so the shape test that keeps `result` honest is
        exactly what threw a story's rewards away.

        **Two levels, and no names.** `story_reward_result` is what a
        STORY happens to call its envelope and nothing says the next
        kind of content will agree, so the sweep looks for the shape
        instead. It stops at two because `result` is the most
        overloaded key on the wire and a deeper walk would eventually
        find something that only resembles a reward.
        """
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            if "currency" in value or "items" in value:
                return value
            for deeper in value.values():
                if isinstance(deeper, dict) and ("currency" in deeper
                                                 or "items" in deeper):
                    return deeper
        return None

    @staticmethod
    def _nested_rewards(payload, depth=3):
        """Every totals envelope inside `payload`, however it is named.

        `_nested_reward` answers the same question for a `result` and
        stops at the FIRST match; a stage's `return_info` carries
        several, so this collects them all.

        The test is the shape: a dict holding `items` or `currency`
        whose rows carry a `doc`. Bounded, because a deep enough walk
        of a stage reply eventually finds something that only
        resembles a reward -- and the walk stops descending as soon as
        it has an envelope, so a `doc` inside one cannot be taken for
        another.
        """
        found = []

        def envelope(value):
            for group in ("items", "currency"):
                rows = value.get(group)
                if isinstance(rows, dict) and any(
                        isinstance(row, dict) and isinstance(row.get("doc"),
                                                             dict)
                        for row in rows.values()):
                    return True
            return False

        def walk(value, left):
            if not isinstance(value, dict) or left <= 0:
                return
            if envelope(value):
                found.append(value)
                return
            for deeper in value.values():
                walk(deeper, left - 1)

        walk(payload, depth)
        return found

    def _apply_totals(self, result, spent=False):
        """Apply a record that states what a holding NOW IS.

        Shape: {"items": {res_id: entry}, "currency": {res_id: entry}},
        each entry carrying `doc` -- the item's whole record, in the
        same shape the cache already holds -- and `diff`, how much of it
        moved. `add_result`, `item_result` and `dec_result` all use it;
        `spent` only picks the word for the log.

        **`doc.amount` is the total, not the change.** It is written in
        rather than added to, so a frame seen twice cannot double a
        count and a frame missed cannot leave one short.

        Items live in a LIST keyed by res_id and currencies in a DICT
        keyed by the same id as a string; both are replaced whole,
        because the record that arrives is the record the snapshot
        wants. An id not yet held is appended: a first pickup has no
        entry to update.

        **The receipt is what the CACHE moved, not what the payload
        says it did.** One payout can arrive in two replies -- a
        Simulation run's lands under `drop_item_result` and again
        under the `savedata_result` its clear reports -- and the
        second writes the same total the first did. Reading `diff` off
        the payload printed that twice, identical figures and all,
        for one reward. Where there is no cached entry to measure
        against the payload's own `diff` is all there is, and a first
        pickup takes it.

        **What it RETURNS is the ids it REPORTED**, which is what the
        caller suppresses a run's total on. An envelope that only
        restated what another already applied reported nothing, so it
        suppresses nothing -- and a Chaos run, whose clear restates
        the whole run rather than paying again, gets its `Total
        rewards` line back.
        """
        moved = []
        items = result.get("items")
        if isinstance(items, dict) and self.inventory_data is not None:
            held = self.inventory_data.setdefault("items", [])
            if isinstance(held, list):
                for entry in items.values():
                    doc = entry.get("doc") if isinstance(entry, dict) else None
                    if not isinstance(doc, dict) or "res_id" not in doc:
                        continue
                    was = next((row.get("amount") for row in held
                                if isinstance(row, dict)
                                and row.get("res_id") == doc["res_id"]), None)
                    self._replace_item(held, doc)
                    shift = self._shift(was, doc, entry)
                    if shift:
                        moved.append((doc["res_id"], shift))
                    self._save_pending = True

        currencies = result.get("currency")
        if isinstance(currencies, dict) and self.character_data is not None:
            held = self.character_data.setdefault("currencies", {})
            if isinstance(held, dict):
                for entry in currencies.values():
                    doc = entry.get("doc") if isinstance(entry, dict) else None
                    if not isinstance(doc, dict) or "res_id" not in doc:
                        continue
                    was = (held.get(str(doc["res_id"])) or {}).get("amount")
                    held[str(doc["res_id"])] = doc
                    shift = self._shift(was, doc, entry)
                    if shift:
                        moved.append((doc["res_id"], shift))
                    self._save_pending = True

        if moved:
            verb = self._verb(moved, spent)
            self.log_callback("[LIVE] %s %s"
                              % (verb, self._describe_amounts(moved)))
            if verb == "Received":
                self._note_receipt(moved)
        return {res_id for res_id, _diff in moved}

    def _note_receipt(self, moved):
        """Remember what a `Received` line said. See `_last_receipt`."""
        receipt = {}
        for res_id, amount in moved:
            receipt[res_id] = receipt.get(res_id, 0) + amount
        self._last_receipt = receipt

    @staticmethod
    def _shift(was, doc, entry):
        """What to report for one holding, or None to report nothing.

        **The figure is the payload's `diff` and the DECISION is the
        cache's.** Whether the total the envelope writes differs from
        the one already held is the only thing that separates a payout
        from the same payout restated -- but the difference itself is
        not the payout: a holding drifts between sightings, Aether
        regenerating a point every six minutes, and subtracting two
        totals reports the drift along with the reward.

        A holding never seen has no total to compare and is taken on
        the payload's word, which is what a first pickup is.
        """
        now = doc.get("amount")
        if not isinstance(was, (int, float)) or not isinstance(now,
                                                               (int, float)):
            return entry.get("diff")
        return entry.get("diff") if now != was else None

    @staticmethod
    def _verb(moved, spent):
        """`Received` or `Spent`, off the SIGNS rather than the key.

        The key a payload arrives under is a poor guide to which way it
        went: the Sortie's entry fee is charged through `item_result`
        and came out as `Received Aether -10`. Where every figure moved
        the same way, that is the answer; a payload with movement in
        both directions falls back to the key, which is the best thing
        left to say about it.
        """
        ways = {diff > 0 for _res_id, diff in moved
                if isinstance(diff, (int, float)) and diff}
        if ways == {True}:
            return "Received"
        if ways == {False}:
            return "Spent"
        return "Spent" if spent else "Received"

    def _replace_item(self, held, doc):
        """Put `doc` in the cached item list, by res_id."""
        for index, row in enumerate(held):
            if isinstance(row, dict) and row.get("res_id") == doc["res_id"]:
                held[index] = doc
                break
        else:
            held.append(doc)

    def _apply_drops(self, drops, qid):
        """Apply a stage's rewards, which arrive as DELTAS.

        Every other envelope states what a holding now is. This one
        does not: it is the drop list the results screen shows, one
        entry per drop with the amount that drop gave, so a x6 run
        sends six entries for the same item and the total is their sum.
        There is no record and no `amount` to write in, which leaves
        adding as the only option.

        **Adding is what makes a repeat dangerous**, so the qid is
        remembered and a frame already applied is skipped. That is the
        same guard the disassemble path uses, for the same reason.

        An id the currencies already hold is a currency -- Units arrive
        this way -- and everything else is an item.
        """
        if qid is not None:
            if qid in self._applied_drops:
                return
            self._applied_drops.append(qid)

        totals = {}
        for row in drops:
            if not isinstance(row, dict):
                continue
            res_id, amount = row.get("id"), row.get("amount")
            if res_id is None or not isinstance(amount, int):
                continue
            totals[res_id] = totals.get(res_id, 0) + amount
        if not totals:
            return

        currencies = (self.character_data or {}).get("currencies")
        currencies = currencies if isinstance(currencies, dict) else {}
        held = None
        if self.inventory_data is not None:
            held = self.inventory_data.setdefault("items", [])
            if not isinstance(held, list):
                held = None

        applied = []
        for res_id, amount in totals.items():
            key = str(res_id)
            if key in currencies and isinstance(currencies[key], dict):
                record = dict(currencies[key])
                record["amount"] = record.get("amount", 0) + amount
                currencies[key] = record
            elif held is not None:
                for index, row in enumerate(held):
                    if isinstance(row, dict) and row.get("res_id") == res_id:
                        record = dict(row)
                        record["amount"] = record.get("amount", 0) + amount
                        held[index] = record
                        break
                else:
                    held.append({"res_id": res_id, "amount": amount})
            else:
                continue
            applied.append((res_id, amount))
            self._save_pending = True

        if applied:
            self.log_callback("[LIVE] Received %s"
                              % self._describe_amounts(applied))
            self._note_receipt(applied)

    def _report_run_total(self, drops, already_named=()):
        """Say what a whole run paid, without changing a single count.

        **NOT dead code, and nothing here may start applying it.** Every
        item in this list has already been written in by an envelope;
        adding it would double the run. The value is that it is the one
        statement of the run as a WHOLE -- the envelopes come split
        across the frames that paid them -- so it goes to the log as a
        reading and stops there.
        """
        if not isinstance(drops, list):
            return
        totals = {}
        for row in drops:
            if not isinstance(row, dict):
                continue
            res_id, amount = row.get("id"), row.get("amount")
            if res_id is not None and isinstance(amount, int):
                totals[res_id] = totals.get(res_id, 0) + amount
        # Nothing to add where every item was already named by an
        # envelope in the same reply: that line IS this one.
        #
        # Nor where the last `Received` line said exactly this. A
        # Simulation's payout arrives twice -- its drops pay it, and
        # its clear restates the same totals -- and the restatement
        # moves nothing, so it names nothing above; the receipt a line
        # earlier is what already said it. A Chaos run pays at its
        # spots in pieces, so no one receipt matches its total, and
        # the total stays: it is the one line saying what the whole
        # run paid.
        if (totals and not set(totals) <= set(already_named or ())
                and totals != self._last_receipt):
            self.log_callback("[LIVE] Total rewards: %s"
                              % self._describe_amounts(totals.items()))

    @staticmethod
    def _describe_amounts(moved):
        """`(res_id, diff)` pairs as words, named where this build can."""
        words = []
        for res_id, diff in moved:
            name = ITEM_NAMES.get(res_id, str(res_id))
            words.append("%s %+d" % (name, diff) if diff else name)
        return ", ".join(words)

    def _merge_missions(self, rows):
        """Fold mission rows into the cache, keyed by res_id.

        Two different sets arrive under one key -- the login burst's
        `content_*` achievements and a pass claim's `pass_mission_*`
        rows -- so replacing would keep only whichever came last.
        """
        for row in rows:
            if isinstance(row, dict) and row.get("res_id") is not None:
                self.missions[str(row["res_id"])] = row

    def _banners(self):
        """The gacha schedule, read from the ONE copy of it.

        `event_schedules["GACHA"]` is where the banners live, and the
        snapshot carries them nowhere else: a second key holding the
        same 2.8 KB byte for byte is one more thing for a reader to
        pick the wrong one of.
        """
        group = (self.event_schedules or {}).get("GACHA")
        return group if isinstance(group, dict) else {}

    def _report_unknown_units(self):
        """Log any banner naming a res_id this build has no entry for.

        A newly released unit reaches the game_data tables by hand, and
        until it does it renders as its bare res_id. The banner is the
        earliest warning available -- it names the unit weeks before the
        maintainer can own one.
        """
        seen = []
        for banner_id in sorted(self._banners()):
            # gacha_pickup_<kind>_<res_id>[_<rerun>] -- the res_id is the
            # FIRST number, and a rerun suffix follows it.
            parts = banner_id.split("_")
            if len(parts) < 4 or parts[0] != "gacha" or parts[1] != "pickup":
                continue
            numbers = [p for p in parts[3:] if p.isdigit()]
            if numbers and int(numbers[0]) not in KNOWN_UNIT_IDS:
                seen.append((banner_id, int(numbers[0])))
        for banner_id, res_id in seen:
            self.log_callback(
                f"[LIVE] Banner {banner_id} names res_id {res_id}, "
                f"which is not in game_data"
            )

    @staticmethod
    def _entry_identity(entry):
        """Identity of one entry in a characters-list payload.

        Partner cards carry an instance `id`; characters never do, so
        their res_id identifies them. The two schemas therefore can't
        collide, and two copies of the same partner card stay distinct.
        """
        if not isinstance(entry, dict):
            return None
        if "id" in entry:
            return ("id", entry["id"])
        return ("res", entry.get("res_id"))

    def _merge_character_data(self, data):
        """Fold an incoming characters payload into the cached one.

        A payload that accounts for every entry already cached is
        authoritative and replaces the cache outright. Anything narrower
        is a delta: its entries overwrite the matching cached ones (or
        get appended) and the rest of the cached payload -- the user
        record included -- is left alone.
        """
        incoming = data.get("characters") or []
        cached = (self.character_data or {}).get("characters")
        if not isinstance(cached, list) or not cached:
            self.character_data = data
            return

        incoming_ids = {self._entry_identity(e) for e in incoming}
        cached_ids = {self._entry_identity(e) for e in cached}
        if cached_ids <= incoming_ids:
            self.character_data = data
            return

        merged = list(cached)
        index = {}
        for i, entry in enumerate(merged):
            index.setdefault(self._entry_identity(entry), i)
        for entry in incoming:
            key = self._entry_identity(entry)
            if key in index:
                merged[index[key]] = entry
            else:
                index[key] = len(merged)
                merged.append(entry)

        self.character_data["characters"] = merged

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
            "char_visits": self.char_visits,
            "disaster_boss_rank_entities": self.disaster_ranks,
            "assault_char_achievement_entities":
                self.assault_char_achievements or None,
            "assault_char_title_entities": self.assault_char_titles or None,
            "disaster_entities": self.disaster_seasons,
            # What the recurring tasks stand at. The Checklist tab
            # reads `point_entity` and `mission_entities`; the rest are
            # written so a capture taken before anything needs them
            # already carries the history.
            "point_entity": self.point_entity,
            "remnants_entities": self.remnants or None,
            "zero_orb_entity": self.zero_orb,
            "overclock_entities": self.overclock or None,
            # Kept as LISTS, the shape the wire uses and every
            # snapshot already on disk carries. They are merged by id
            # while the capture runs and flattened here.
            "attendance_entities": list(self.attendance.values()) or None,
            "event_mission_reward_entities":
                list(self.event_rewards.values()) or None,
            "reward_entities": self.season_rewards or None,
            **self.event_defines,
            "combat_trial_entities": self.combat_trials or None,
            "combatant_trial_slots": self.trial_slots or None,
            "season_pass_entity": self.season_pass,
            "mission_entities": self.missions or None,
            "shop_list": self.shop_products or None,
            "month_start": self.month_start,
            "month_end": self.month_end,
            "stage_limit_entities": self.stage_limits or None,
            "issued_limit_entities": self.issued_limits or None,
            "season_pass_entities": self.season_passes,
            "shop_res_data": self.shop_definitions,
            "season_entities": self.basin_stages,
            "mission_seasson_entities": self.basin_missions,
            "event_schedules": self.event_schedules,
            "detected_region": self._detect_region(),
        }

        # Temp file then replace, the way every settings manager writes.
        # A capture rewrites ONE path for the whole session, and the app
        # reads that same path -- `Load Latest`, and the checks that
        # take the newest snapshot. Written in place, a read landing
        # mid-write gets a truncated file and a JSON error naming a line
        # number, which reads as corrupt data rather than as a race.
        tmp = self.saved_path.with_suffix(self.saved_path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2)
        except OSError as e:
            # **A capture that cannot write says so.** Left to the
            # frame handler's own catch this came out as a bare
            # `Error:` with no mention of a snapshot, in a log whose
            # every other line is about the game.
            self.log_callback(
                f"[X] Could not write {self.saved_path.name}: {e}. The "
                f"capture is still running; nothing has been lost that "
                f"the next save will not write again.")
            return

        # **The replace can be REFUSED on Windows** with
        # `[WinError 5] Access is denied` while another process holds
        # the destination open -- the app reading it, an indexer, an
        # antivirus scanning what was just written. It is transient, so
        # it is retried rather than reported: a save that gives up
        # leaves the previous snapshot on disk and a `.tmp` beside it,
        # and the capture carries on as if nothing was lost.
        for attempt in range(SAVE_REPLACE_TRIES):
            try:
                tmp.replace(self.saved_path)
                break
            except PermissionError:
                if attempt == SAVE_REPLACE_TRIES - 1:
                    self.log_callback(
                        f"Could not replace {self.saved_path.name}: it is "
                        f"open in another program. The capture is still "
                        f"running; the next save will try again.")
                    return
                time.sleep(SAVE_REPLACE_WAIT)

        count = len(self.inventory_data.get("piece_items", []))
        char_count = len(self.character_data.get("characters", [])) if self.character_data else 0
        report = (
            f"Saved: {count} Memory Fragments, {char_count} characters -> {self.saved_path.name}"
        )

        # **Every save says so on this line, suppressed or not.** The
        # app reloads when it sees a save go past, and the login burst
        # saves several times with IDENTICAL counts -- the first as
        # soon as the inventory lands, the later ones carrying the
        # shops, the schedules and the missions. Suppressing the
        # human-readable line for those suppressed the RELOAD with it,
        # so the app sat on the first save's snapshot for the rest of
        # the session and every shop row read empty until a restart.
        self.log_callback(SAVE_MARKER)
        # **Written beside the snapshot, not only at shutdown.** A
        # capture left running for weeks would otherwise hold every
        # sighting in memory until the process ended, and lose the
        # lot if it ended badly.
        self._write_catalogue()

        # **Printed only when it would say something new**, which for
        # this line means a different file or different counts. A save
        # that changed neither is the program working, and the program
        # working is not news; a save that FAILS says so above.
        #
        # **Comparing against the LAST LINE is not enough**, which is
        # the tempting simplification: a `[LIVE]` line lands after
        # every upgrade, delete and reward, so there is almost always
        # something in between and the same figures go back up.
        if (count, char_count, self.saved_path.name) != self._last_save:
            self._last_save = (count, char_count, self.saved_path.name)
            self.log_callback(report)

    def _describe_piece(self, piece_data):
        """Build human-readable piece description like 'Line of Justice Denial +3'."""
        res_id = piece_data.get("res_id", 0)
        level = piece_data.get("level", 0)
        res_str = str(res_id)
        if len(res_str) >= 5:
            slot_num = int(res_str[2])
            set_id = int(res_str[4:])
            set_name = SET_NAMES.get(set_id, f"Set{set_id}")
            slot_name = SLOT_NAMES.get(slot_num, f"Slot{slot_num}")
            return f"{set_name} {slot_name} +{level}"
        return f"Piece {piece_data.get('id', '?')} +{level}"

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

        self._save_pending = True

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

    @staticmethod
    def _reward_pieces(data):
        """Fragments a REWARD paid, as a list of piece documents.

        **A reward's fragments look nothing like a forge's.** Forging
        answers with a top-level `pieces` LIST of documents; a reward
        answers with a `pieces` DICT keyed by the fragment's own id,
        each value a `{diff, doc}` pair, and never at the top level.
        Three carriers have been seen, all of them a level down:

            item_result.pieces                         a Chaos week reward
            return_info.result_reward_drop_item        a Simulation run
            return_info.result_reward_drop_overclock   a doubled one

        so the whole of `return_info` is swept rather than those two
        names, which are only the ones a capture has happened to show.

        **`auto_disassemble_piece` must not be read.** Those
        fragments were broken down for materials on the way in and
        never reach the inventory -- the game pays their dust under
        `gained_items` instead. They are excluded three times over
        and by accident rather than by design: their `pieces` is a
        LIST, its rows have no `doc`, and what is inside has no
        `id`. Any ONE of those going away leaves them out, so a
        rewrite here should re-establish the exclusion on purpose
        rather than assume it survives.
        """
        carriers = [data.get("item_result")]
        nested = data.get("return_info")
        if isinstance(nested, dict):
            carriers.extend(nested.values())
        found = []
        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            rows = carrier.get("pieces")
            if not isinstance(rows, dict):
                continue
            for row in rows.values():
                doc = row.get("doc") if isinstance(row, dict) else None
                if isinstance(doc, dict):
                    found.append(doc)
        return found

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

        self._save_pending = True

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

        self._save_pending = True

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

    def _write_debug(self, entry):
        """One frame into the debug log, as its own gzip member.

        See the note where the file is opened: a member per line is
        what keeps the file readable after every write, and the flush
        is what puts it on disk.
        """
        line = json.dumps(entry, ensure_ascii=False) + "\\n"
        self.debug_file.write(gzip.compress(line.encode("utf-8")))
        self.debug_file.flush()

    # ------------------------------------------------- the wire catalogue

    def _read_catalogue(self):
        """What is already on disk, or an empty catalogue."""
        if self.catalogue_path is None or not self.catalogue_path.exists():
            return {}
        try:
            held = json.loads(self.catalogue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        rows = held.get("keys") if isinstance(held, dict) else None
        return rows if isinstance(rows, dict) else {}

    def _note_command(self, entry):
        """Remember which command a qid belongs to.

        `cmd` names the family and `params.cmd` the call inside it, so
        the pair is what a reader would grep for -- `mission` alone
        answers a dozen different things.
        """
        qid = entry.get("qid")
        if qid is None:
            return
        params = entry.get("params")
        inner = params.get("cmd") if isinstance(params, dict) else None
        name = str(entry.get("cmd"))
        if inner:
            name += "/" + str(inner)
        if len(self.qid_commands) > CATALOGUE_MAX:
            self.qid_commands.clear()
        self.qid_commands[qid] = name

    def _note_keys(self, data):
        """Record every top-level key of one reply against its command.

        The reply carries the qid it answers, which is how a key is
        tied back to what asked for it. A reply with no qid, or one
        whose request was never seen -- the game had already been
        running when the capture started -- is filed under `?`.
        """
        if self.catalogue_path is None:
            return
        asked = self.qid_commands.get(data.get("qid"), "?")
        when = datetime.now().isoformat(timespec="seconds")
        for key, value in data.items():
            if key in ("res", "qid", "service_server_time", "reset_resp"):
                continue                 # on every reply; nothing to learn
            name = asked + "|" + str(key)
            row = self.catalogue.get(name)
            if row is None:
                if len(self.catalogue) >= CATALOGUE_MAX:
                    continue
                try:
                    sample = json.dumps(value, ensure_ascii=False)
                except (TypeError, ValueError):
                    sample = repr(value)
                row = {"count": 0, "first": when,
                       "type": type(value).__name__,
                       "sample": sample[:CATALOGUE_SAMPLE]}
                self.catalogue[name] = row
            row["count"] += 1
            row["last"] = when
            self.catalogue_dirty = True

    def _write_catalogue(self):
        """Persist the catalogue, merged with whatever else wrote it.

        Re-read before writing because two captures can run over one
        file. Counts add, the first sighting is the earlier of the two
        and the last the later -- so nothing is lost by whichever
        finishes second.
        """
        if self.catalogue_path is None or not self.catalogue_dirty:
            return
        merged = self._read_catalogue()
        for name, row in self.catalogue.items():
            was = merged.get(name)
            if not isinstance(was, dict):
                merged[name] = dict(row)
                continue
            merged[name] = {
                "count": (was.get("count") or 0) + row["count"],
                "first": min(str(was.get("first") or row["first"]),
                             row["first"]),
                "last": max(str(was.get("last") or row["last"]),
                            row["last"]),
                "type": row["type"],
                "sample": was.get("sample") or row["sample"],
            }
        try:
            self.catalogue_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.catalogue_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"keys": merged}, indent=1, ensure_ascii=False),
                encoding="utf-8")
            tmp.replace(self.catalogue_path)
        except OSError:
            return                       # never let this break a capture
        # What was just folded in must not be folded in twice.
        self.catalogue = {}
        self.catalogue_dirty = False

    def _check_for_relaunch(self, user):
        """Start a snapshot of its own when the game has been RELAUNCHED.

        **A capture is not one sitting.** `saved_path` is chosen on
        the first save and rewritten on every one after, so without a
        rotation a month of capture leaves exactly one snapshot: the
        newest state, with no history behind it. That history is what
        every derived reading here is built from -- a currency's rate,
        a streak's length, an event's total.

        **The marker is `last_login_tm`, and the ones that look easier
        are wrong.** This game reconnects often, and a reconnect:

        * closes and reopens the websocket, so `websocket_end` fires;
        * redoes the handshake, so `helo` arrives again;
        * keeps its `session` token for a while and then rotates it
          anyway -- one launch was seen using seven.

        Rotating on any of those turned a single evening with a few
        dropped connections into three snapshots. What a reconnect
        does NOT do is log in again: across those three the server's
        `last_login_tm`, `activated_tm` and the account payload's own
        `server_time` were identical to the second, and the previous
        real launch's differed. So the server's own word for "this
        account logged in" is the one thing that means a new game.

        Dropping the path is the whole rotation: the next save picks a
        new timestamped name, and the file the last game filled is
        left as it was. Nothing is created until there is something to
        put in it.

        The CACHE is deliberately kept. A snapshot is meant to be the
        whole account, and the login burst rewrites all of it anyway.
        """
        if not isinstance(user, dict):
            return
        stamp = user.get("last_login_tm")
        if stamp is None or stamp == self.login_stamp:
            return
        was, self.login_stamp = self.login_stamp, stamp
        if was is None or self.saved_path is None:
            return                       # the capture's first login
        self.log_callback("Game relaunched -- starting a new snapshot")
        self.saved_path = None

    def websocket_end(self, flow):
        """The game's connection closed.

        **Which is not the same as the game closing.** A dropped
        connection looks identical, and this game drops them often --
        so nothing here rotates a snapshot or says anything to the
        log. See `_check_for_relaunch` for what does.

        What it is good for is the requests still waiting on a reply:
        that connection is gone and they will not be answered on it.
        """
        self._forget_pending()

    def _forget_pending(self):
        """Drop every request still waiting on a reply.

        Called when a new game connects. Each of these maps a qid to
        what the client asked for, and a qid means nothing across
        connections -- see the note in `_track_client_request`.
        """
        self.qid_sent.clear()
        if not (self.pending_disassembles or self.pending_unequips
                or self.pending_coffees or self.gacha_requests):
            return
        self.pending_disassembles.clear()
        self.pending_unequips.clear()
        self.pending_coffees.clear()
        self.gacha_requests.clear()

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

            # **A new game has started, and its qids begin again at
            # one.** `helo` is the first command of every connection,
            # so anything still waiting here was asked by the game that
            # just went away and will never be answered -- and leaving
            # it would let an unrelated reply of the new game's qid 1
            # claim it. The costly one is a disassemble: its intent is
            # a list of fragments to delete, and a stale one applied to
            # the wrong reply takes real fragments out of the snapshot.
            #
            # Harmless while a capture covered one launch, which is
            # every capture taken so far. Not harmless once a capture
            # is left running for days.
            if entry.get("cmd") == "helo":
                self._forget_pending()
                self.qid_commands.clear()
                continue

            self._note_command(entry)

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

            elif inner_cmd == "order_coffee":
                self.pending_coffees.add(qid)

            elif entry.get("cmd") == "gacha" and inner_cmd in (
                    "history", "get_rate"):
                banner = params.get("id" if inner_cmd == "history"
                                    else "gacha_id")
                if banner:
                    self.gacha_requests[qid] = (
                        inner_cmd, str(banner), params.get("last_db_id"))

            elif inner_cmd == "reward_combatant_trial":
                # **The only place the two ids appear together.** A
                # trial slot's own row says when its reward was last
                # claimed and nothing about which event offered it, and
                # the login says nothing either -- so the pairing is
                # learned here, from the request that claims one, and
                # kept. Once a slot is paired, later cycles are read
                # off its `complete_time` against the event's window.
                event = params.get("event_combatant_trial_id")
                slot = params.get("event_combatant_trial_slot_id")
                if event and slot:
                    slots = self.trial_slots.setdefault(str(event), [])
                    if str(slot) not in slots:
                        slots.append(str(slot))
                        self._save_pending = True

    def _set_day_field(self, field, value):
        """Write one field of the cached town daily block.

        For state an ACTION establishes and no reply states -- see
        `pending_coffees`. Returns whether anything was written: there
        is nothing to save when the block has not arrived yet, which is
        the case for a capture started before the game logged in.
        """
        if not isinstance(self.character_data, dict):
            return False
        town = self.character_data.get("town_data")
        if not isinstance(town, dict):
            return False
        day = town.get("day_changeable_data")
        if not isinstance(day, dict):
            return False
        day[field] = value
        return True

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
        self._save_pending = True

        if len(removed) == 1:
            desc = self._describe_piece(removed[0])
            self.log_callback(f"[LIVE] Deleted {desc}")
        else:
            self.log_callback(f"[LIVE] Deleted {len(removed)} pieces")

    def done(self):
        """Cleanup on shutdown."""
        self._write_catalogue()
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
        # Called with a region_id, or "conflict" when two servers
        # answer in one session. Set by the Capture tab.
        self.region_callback = None
        # Called when the addon has written the Gacha History's file.
        # Set by the main window; runs on the proxy-reader thread.
        self.gacha_update_callback = None

        self.capturing = False
        self.proxy_process = None
        # Wall clock at the moment the proxy was launched. A snapshot
        # older than this belongs to an EARLIER session, which is the
        # difference between "this run captured nothing" and "this run
        # captured what you see". None while not capturing.
        self._session_started_at = None
        self.game_server_ips = {}
        # host -> region_id, filled by resolve_game_server. The addon
        # routes each connection by the hostname the client asked for,
        # so this is what tells it which region that hostname is.
        self.host_regions = {}
        self.original_hosts_content = None
        # Last region OBSERVED, for the readout to open on. Nothing
        # about a capture depends on it: both regions are redirected
        # and the addon routes per connection.
        self.current_region = None
        # Mirrors the debug_mode flag of the current capture session
        # (set by start_capture). The output reader uses it to decide
        # whether WebSocket ping/pong keepalive lines reach the log.
        self._debug_mode = False

        # Upgrade log lines from the addon arrive tagged with [pid=N] so
        # the main app can find the upgraded fragment and append its new
        # Highest Pot. range. We hold those lines here instead of forwarding
        # them straight to log_callback; the main app drains the queue
        # after the post-upgrade reload finishes and emits the augmented
        # version. Thread-safe by design (proxy reader thread puts; main
        # thread gets). Each item is (line, stamp) -- see `split_lag`.
        import queue as _queue  # avoid polluting module namespace
        self.pending_upgrade_lines = _queue.Queue()

    def is_capturing(self) -> bool:
        """Check if currently capturing."""
        return self.capturing

    def get_latest_capture(self) -> Optional[Path]:
        """Most recent snapshot on disk, from ANY session, or None."""
        files = list(self.output_folder.glob("memory_fragments_*.json"))
        return max(files, key=lambda f: f.stat().st_mtime) if files else None

    def get_session_capture(self) -> Optional[Path]:
        """The snapshot THIS capture session wrote, or None.

        `get_latest_capture` answers a different question, and using it
        to report a result is how a capture that recorded nothing came
        to announce the previous run's file as its own -- with a success
        line and no hint that the proxy had seen no traffic. That is the
        shape a wrong Server Region takes: the hosts redirect points at
        a hostname the game never contacts, so nothing reaches the proxy.

        One second of slack because some filesystems keep mtime only to
        the second, so a snapshot written in the same second the proxy
        started can carry a timestamp just below the watermark.
        """
        if self._session_started_at is None:
            return None
        latest = self.get_latest_capture()
        if latest is None:
            return None
        return latest if (latest.stat().st_mtime
                          >= self._session_started_at - 1) else None

    def _read_detected_region(self, capture_file: Path) -> Optional[str]:
        """Read detected_region from capture file."""
        import json
        try:
            with open(capture_file, "r", encoding="utf-8") as f:
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
        """Deprecated: the region is observed, not chosen.

        Every region is redirected during a capture and the addon routes
        each connection to its own server, so there is nothing here to
        select. Kept as a no-op because losing it would break any caller
        not updated in the same edit; `detected_region` on the snapshot
        is the answer now.
        """
        return

    def resolve_game_server(self):
        """Resolve EVERY region's hostnames to IP addresses.

        Both regions are redirected during a capture, so both have to be
        resolved before the redirect is written -- once the hosts block
        is in place, the answer for either is 127.0.0.1.

        Fills `game_server_ips` (host -> ip) and `host_regions`
        (host -> region_id), which together are what the addon routes on.
        """
        from .constants import SERVERS
        self.game_server_ips = {}
        self.host_regions = {}
        for region_id, server_config in SERVERS.items():
            for host in server_config.hosts:
                try:
                    ip = socket.gethostbyname(host)
                except socket.gaierror:
                    continue
                self.game_server_ips[host] = ip
                self.host_regions[host] = region_id

    def resolved_to_loopback(self) -> bool:
        """True if any resolved game-server address points at this machine.

        Which can only mean the redirect in the hosts file answered the
        lookup. Taking such an address at face value would give mitmdump
        itself as its own upstream, and every request the game made would
        be forwarded back into the proxy in an endless loop.
        """
        return any(is_loopback_address(ip)
                   for ip in self.game_server_ips.values())

    def modify_hosts_file(self) -> str:
        """
        Modify Windows hosts file to redirect game traffic to local proxy.

        Returns:
            The hosts file content without the redirect block

        Raises:
            CaptureError: If hosts file modification fails
        """
        try:
            # The hosts file belongs to the system and carries other
            # people's entries. It is read whole, edited and written back,
            # so an encoding guess that differs between the read and the
            # write corrupts lines this program never touched. UTF-8 with
            # surrogateescape round-trips any byte it cannot decode
            # unchanged, which is the only safe option on a file whose
            # encoding is not ours to know.
            with open(HOSTS_PATH, "r", encoding="utf-8",
                      errors="surrogateescape") as f:
                content = f.read()

            # Strip any block an earlier run left behind before appending
            # this one. Accepting a file that already carries the redirect
            # leaves its contents unverified, and leaves the redirect
            # itself free to answer the game-server lookup that decides
            # the proxy's upstream (see remove_hosts_redirect).
            content = _strip_capture_block(content)

            # Redirect EVERY region, not just a selected one: which
            # server the game talks to is the game's choice, and
            # redirecting only one meant a game on the other never
            # passed through the proxy at all -- a silent no-capture.
            # The addon sends each connection on to its own region.
            from .constants import SERVERS
            entries = ["\n" + HOSTS_BLOCK_START]
            for server_config in SERVERS.values():
                for host in server_config.hosts:
                    entries.append(f"127.0.0.1 {host}")
            entries.append(HOSTS_BLOCK_END + "\n")

            new_content = content + "\n".join(entries)

            with open(HOSTS_PATH, "w", encoding="utf-8",
                      errors="surrogateescape") as f:
                f.write(new_content)

            self._flush_dns()

            return content

        except Exception as e:
            raise CaptureError(f"Failed to modify hosts file: {e}")

    def _flush_dns(self):
        """Drop the OS resolver cache so a hosts-file edit takes effect.

        Failure is reported rather than swallowed: a cache still holding
        the pre-edit answer is one of the ways a lookup can keep
        resolving to the wrong address after the file itself is correct.

        Carries a timeout, a closed stdin and CREATE_NO_WINDOW like every
        other external call in this program -- without the last one a
        console window flashes over the UI.
        """
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            )
        try:
            result = subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=10,
                stdin=subprocess.DEVNULL,
                **kwargs
            )
        except (OSError, subprocess.SubprocessError) as e:
            self.log_callback(f"Could not flush the DNS cache: {e}", "warning")
            return
        if result.returncode != 0:
            self.log_callback(
                f"Could not flush the DNS cache (exit {result.returncode})",
                "warning",
            )

    def remove_hosts_redirect(self) -> bool:
        """Take the game-server redirect out of the hosts file.

        Returns True if a redirect block was there and has been removed,
        False if the file was already clean. Only the marked block is
        touched; the rest of the file is preserved as-is.

        Worth calling before any lookup that has to reach the real
        server, not just when winding a capture down: a block left behind
        by a run that ended without removing it (a crash, or the process
        being killed) makes every game-server lookup answer with this
        machine, and the game itself unable to connect at all.

        Raises:
            CaptureError: If the file can't be read, or carries a block
                that can't be removed (no administrator rights, for
                instance). Callers that only want best-effort cleanup
                should use restore_hosts_file instead.
        """
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8",
                      errors="surrogateescape") as f:
                content = f.read()
        except OSError as e:
            raise CaptureError(f"Could not read the hosts file: {e}")

        if HOSTS_BLOCK_START not in content:
            return False

        try:
            with open(HOSTS_PATH, "w", encoding="utf-8",
                      errors="surrogateescape") as f:
                f.write(_strip_capture_block(content))
        except OSError as e:
            raise CaptureError(
                "A capture redirect left in the hosts file could not be "
                f"removed: {e}\n\nEditing it needs Administrator rights."
            )

        self._flush_dns()
        return True

    def restore_hosts_file(self):
        """
        Restore Windows hosts file to original state.
        Removes CZN-CAPTURE entries added by modify_hosts_file().
        """
        try:
            self.remove_hosts_redirect()
        except CaptureError as e:
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

            # **Beside the settings, not among the captures.** The
            # catalogue is a record built up over months, and the
            # snapshots folder is the one a user empties.
            #
            # **And only where the app was started by a zRUN bat**,
            # which is the maintainer's way in and not a released
            # build's. `None` here switches the whole thing off inside
            # the addon -- nothing recorded and nothing written -- so a
            # user's capture is untouched by any of it. See
            # MAINTAINER_ENV.
            catalogue_path = None
            if os.environ.get(MAINTAINER_ENV):
                catalogue_path = (self.output_folder.parent / "settings"
                                  / "wire_catalogue.json").absolute()

            # Find dictionary path
            dict_path = self._find_dictionary_path()
            dict_path_str = f'Path(r"{dict_path}")' if dict_path else "None"
            catalogue_str = (f'Path(r"{catalogue_path}")'
                             if catalogue_path else "None")

            if not dict_path:
                self.log_callback("Warning: zstd dictionary not found", "warning")

            # Build lookup dicts for live monitoring log messages
            from game_data import CHARACTERS, SETS
            from game_data.constants import EQUIPMENT_SLOTS
            from game_data.partners import PARTNERS

            # Every item this build can name, for the log line a reward
            # writes. Partial by nature -- the tables name what has been
            # identified -- and an id neither carries logs as itself.
            #
            # The stones' name is BUILT from their row rather than
            # listed: the table holds the Element and the tier and the
            # game spells the pair this way round. The promotion and
            from game_data.constants import item_names as build_item_names
            # Every id this build can name, shaped rows spelled out --
            # `game_data.constants.item_names` owns that, and the
            # Checklist's shop rows read the same map. A log line
            # saying `Traces of Memory +40` is the whole point of it.
            item_names = build_item_names()

            char_names = {rid: c["name"] for rid, c in CHARACTERS.items() if c is not None}
            set_names = {sid: s["name"] for sid, s in SETS.items()}
            slot_names = {k: v.split(" ", 1)[1] if " " in v else v for k, v in EQUIPMENT_SLOTS.items()}

            # Every res_id this build can name. Units awaiting an id sit
            # under a negative placeholder key, which no banner can match.
            known_unit_ids = {rid for rid in list(CHARACTERS) + list(PARTNERS) if rid > 0}

            # hostname -> (region_id, real_ip, port). The addon reads
            # the client's SNI and sends that connection to the right
            # server, which is what lets BOTH regions be redirected at
            # once. Empty if resolution failed, in which case the addon
            # leaves mitmproxy's launch upstream alone.
            region_routes = {
                host: (self.host_regions.get(host), ip, GAME_PORT)
                for host, ip in self.game_server_ips.items()
            }

            # Where the Gacha History's file lives and what it calls
            # itself. `gacha_history.py` owns all three and reads what
            # the addon writes, so they are handed over rather than
            # spelled a second time.
            import gacha_history

            # Generate standalone script using embedded template
            addon_code = f'''{ADDON_TEMPLATE}

OUTPUT_DIR = Path(r"{self.output_folder.absolute()}")
CATALOGUE_PATH = {catalogue_str}
DICT_PATH = {dict_path_str}
CHAR_NAMES = {char_names}
ITEM_NAMES = {item_names}
SET_NAMES = {set_names}
SLOT_NAMES = {slot_names}
KNOWN_UNIT_IDS = {known_unit_ids}
REGION_ROUTES = {region_routes}
GACHA_FOLDER = {gacha_history.FOLDER!r}
GACHA_FILE = {gacha_history.CAPTURED!r}
GACHA_KIND = {gacha_history.STORE_KIND!r}

addons = [Addon(OUTPUT_DIR, dict_path=DICT_PATH, debug_mode={debug_mode},
                catalogue_path=CATALOGUE_PATH)]
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

    @staticmethod
    def _region_from_line(line):
        """The region a proxy line reports, or None if it reports none.

        "conflict" means a second server region answered in one
        session -- two games running at once.
        """
        if "[REGION]" in line:
            return line.split("[REGION]", 1)[1].strip() or None
        if "second server region" in line:
            return "conflict"
        return None

    def _log_line(self, line, tag, stamp):
        """Forward one of the addon's lines, with its Debug WS timing
        where it carries one. Passed only then, so a log callback that
        takes no timing keeps working."""
        if stamp is None:
            self.log_callback(line, tag)
        else:
            self.log_callback(line, tag, stamp=stamp)

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

        # WebSocket ping/pong keepalive frames: pure connection-liveness
        # noise for a user, but a useful heartbeat when debugging capture
        # problems (pings stopping often precedes a dead capture) -- so
        # they're only suppressed outside debug mode.
        if not self._debug_mode:
            skip_patterns = skip_patterns + [
                "Received WebSocket ping",
                "Received WebSocket pong",
            ]

        try:
            for line in self.proxy_process.stdout:
                line = line.strip()
                if not line:
                    continue
                # Off before anything reads the line: every test below,
                # and what the log shows, is the line as the addon wrote
                # it. Only Debug WS lines carry one.
                line, stamp = split_lag(line)

                # The addon reports which server region a connection
                # actually went to; both hostnames are redirected, so
                # this is the only place the answer exists.
                #
                # Handled BEFORE the skip filter, and it returns
                # rather than falling through, because that filter
                # drops any line containing "connect" -- which the
                # two-regions warning does, in the word "connected".
                # Left below the filter it vanished entirely: no
                # readout, no log line, nothing to show why.
                region = self._region_from_line(line)
                if region is not None:
                    if self.region_callback:
                        self.region_callback(region)
                    if region == "conflict":
                        self.log_callback(f"[proxy] {line}", "error")
                    continue

                # Skip verbose mitmproxy messages
                if any(pattern.lower() in line.lower() for pattern in skip_patterns):
                    continue

                # **The addon says this on every save, suppressed line
                # or not.** Consumed rather than shown: it exists so a
                # reload cannot ride on a human-readable line that is
                # skipped whenever it would repeat itself.
                if SAVE_MARKER in line:
                    if self.status_callback:
                        self.status_callback("[OK] Data Captured!")
                    if self.live_update_callback:
                        self.live_update_callback()
                    continue
                if GACHA_MARKER in line:
                    if self.gacha_update_callback:
                        self.gacha_update_callback()
                    continue
                if "[GACHA]" in line:
                    self._log_line(line, "info", stamp)
                    continue

                # Route live updates with info tag, everything else with default tag
                #
                # **Neither a `[LIVE]` line nor the `Saved:` line asks
                # for a reload; only the save marker above does.** A
                # `[LIVE]` line is printed while the reply is handled,
                # BEFORE the save it leads to, so a reload it asked for
                # would read the file as it was -- and an `Upgraded`
                # line drained after that would score the fragment as
                # it stood before the upgrade. Each extra ask is also a
                # whole reload on the UI thread, four to a forge, with
                # every line behind them waiting.
                if "[LIVE]" in line:
                    # Defer [LIVE] Upgraded lines: they carry a [pid=N]
                    # marker that lets the main app fill in Highest Pot.
                    # after the post-upgrade reload completes. All other
                    # [LIVE] events (Equipped / Unequipped / Swapped /
                    # Created / Deleted) log immediately as before.
                    if "[LIVE] Upgraded" in line and "[pid=" in line:
                        self.pending_upgrade_lines.put((line, stamp))
                    else:
                        self._log_line(line, "info", stamp)
                else:
                    self._log_line(line, None, stamp)

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
        self._debug_mode = bool(debug_mode)

        # Resolve game servers for current region
        # (Always re-resolve to ensure we use the correct region's servers)
        self.resolve_game_server()

        # A loopback answer means a redirect is already in the hosts file,
        # left by a run that ended without removing it. Handing that
        # address to mitmdump as its upstream would point the proxy at
        # itself, and every request the game made would loop back into it
        # forever. Clear the block and ask the OS again.
        if self.resolved_to_loopback():
            self.log_callback(
                "The game server resolves to this machine: a capture "
                "redirect is still in the hosts file. Removing it.",
                "warning",
            )
            self.remove_hosts_redirect()
            self.resolve_game_server()

        if not self.game_server_ips:
            raise CaptureError("Could not resolve game servers.")

        if self.resolved_to_loopback():
            raise CaptureError(
                "The game server still resolves to this machine.\n\n"
                "Something is redirecting it locally. Check "
                f"{HOSTS_PATH} for an entry pointing "
                "the game server at 127.0.0.1 and remove it."
            )

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
                "Run 'pip install mitmproxy' in a terminal, or check the "
                "Setup & Settings tab."
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

        # Set BEFORE the first payload can arrive, so any snapshot the
        # addon writes this session is newer than it.
        self._session_started_at = time.time()
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

        # Only a snapshot THIS session wrote counts as a result. See
        # get_session_capture: reporting the newest file on disk made a
        # capture that recorded nothing announce the previous run's
        # file, which is how a wrong Server Region looked like success.
        captured = self.get_session_capture()
        if captured:
            detected = self._read_detected_region(captured)
            self.log_callback(f"Capture stopped. File: {captured.name}",
                              "success")
            self._session_started_at = None
            return (captured, detected)

        self._session_started_at = None
        self.log_callback(
            "Capture stopped, but nothing was captured: no game traffic "
            "reached the proxy.",
            "warning")
        return None
