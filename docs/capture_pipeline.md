# Capture pipeline

Read before touching `capture/`, the snapshot parser
(`optimizer.GearOptimizer._parse_character_data`), or the live-update
path in `czn_optimizer_gui.py`.

The chain: mitmdump intercepts the game's WebSocket traffic → the addon
template embedded in `capture/manager.py` parses it and maintains
`piece_items` + `characters` → `_save_data()` writes
`snapshots/memory_fragments_*.json` → the optimizer reads that and
builds `character_info` → the tabs render from it.

**One payload writes the snapshot at most once.** A login reply carries
the roster, the inventory and the banner schedule together, and
`_handle_server_payload` reads each with its own branch -- so a branch
sets a flag and the save happens once at the end of the handler. It
writes the whole cache whenever it runs, so a second call in one payload
adds nothing but a duplicate `Saved:` line.

**`capture/manager.py` is the ONLY file in the repo with a strict ASCII
requirement**: the addon is written out as a generated script, and a
cp932/cp949 locale cannot encode a smart quote or an em dash into it.

## Character vs partner classification

The snapshot lumps characters AND partner cards into one list with no
type field, but the game serializes the two with different schemas, and
that is the reliable discriminator. Classifier:
`optimizer.GearOptimizer._parse_character_data`.

|                         | Character entry                                                          | Partner entry                                   |
| ----------------------- | ------------------------------------------------------------------------ | ----------------------------------------------- |
| Distinguishing keys     | `potential_node_ids`, `friendship_exp`, `psychosis_*`, `card_animations` | `id` (instance id), `lock`                      |
| Instance id             | none                                                                     | `id`                                            |
| What `partner_id` holds | the equipped partner's INSTANCE id                                       | back-reference to the owning character's RES id |

Precedence:

1. Has `potential_node_ids` or `friendship_exp` → character.
2. Has `id` or `lock` → partner.
3. `res_id` in `CHARACTERS` → character (fallback for an entry with
   neither marker).
4. Else → partner.

**Never test whether `potential_node_ids` is non-EMPTY.** A brand-new
character carries `"[]"` until its first node is unlocked; an emptiness
test classifies it as a partner, and it then goes missing from every tab
until an MF is equipped to it.

**Never split on res_id ranges.** Characters and partners both occupy
the 1xxx and 3xxxx ranges in real snapshots.

## The `characters` key on the wire is sometimes a DELTA

The login payload carries every character and partner card. An action
response (a partner re-equip, at least) carries the same key holding
only the entries the server touched — the partner instance, its new
owner, its old owner. `_capture_addon._merge_character_data` therefore
replaces its cache only when the incoming list accounts for every entry
already cached, and otherwise merges entry by entry, keyed by instance
`id` for partners and `res_id` for characters.

**A wholesale replace here is silent, total data loss.** The snapshot on
disk keeps its full `piece_items`, so every tab still lists the
characters that have gear equipped and only the gearless ones vanish;
exclusion checkmarks read as cleared because the res_id lookups go
through `character_info`; and the exclude step stops excluding — with no
error and no recovery short of re-capturing.

The `user` key needs the same care: it arrives with no roster attached,
so it is patched into the cached payload rather than replacing it.

## One frame can carry several replies

The wire shape is
`{"cmd": <domain>, "qid": n, "params": {"cmd": <action>, ...}}`, and the
client sends a JSON ARRAY of those whenever it has more than one command
to send. The server answers in kind: an array of reply objects, each
shaped exactly like a solo reply. `websocket_message` unwraps both forms
and hands each object to `_handle_server_payload`.

The login burst is the only long stretch of solo commands. Everything
after the lobby arrives batched, so a handler reading only the object
form sees the login and then apparently nothing — no parsing, no
snapshot save, and no debug-log line either, so the capture looks like
it went quiet rather than like it dropped anything.

`checks/check_capture_batching.py` drives the template with a frame of
each shape.

## The gacha schedule names unreleased units

The reply to `lobby / lobby_update` carries `event_schedules.GACHA`:
every banner, past and upcoming, keyed
`gacha_pickup_<combatant|supporter>_<res_id>[_<rerun>]`. Those ids are
server-side definitions and do not depend on what the account owns,
which makes them the only res_ids a unit's owner-scoped absence cannot
hide. The rerun suffix follows the res_id, so the FIRST number is the
unit.

The addon keeps the schedule on `self.gacha_banners` and `_save_data`
writes it to the snapshot's `gacha_banners` key. It arrives with no
roster and no inventory attached, so it must survive until a save is
possible rather than being written on arrival.

`_report_unknown_units` logs any banner naming a res_id absent from
`KNOWN_UNIT_IDS` — the character and partner tables, injected by
`_generate_addon_script` the same way `CHAR_NAMES` is. Negative
placeholder keys are excluded from that set, so a unit awaiting an id
still reports.

`checks/check_capture_banners.py` builds the addon through
`_generate_addon_script` rather than from the template alone, so it also
catches a global the template reads and the generator stops supplying.

## The proxy's upstream must never be a loopback address

mitmdump runs in reverse-proxy mode with the game server's IP as its
upstream and its own listen port as the destination port, so a loopback
upstream makes the proxy its own upstream: every request is forwarded
back into it, one new client connection per hop, until the log is
thousands of lines of `GET https://127.0.0.1:13701/api/` and nothing has
reached either the game or the snapshot.

A redirect block left in the hosts file by a run that ended without
removing it produces exactly that, because `socket.gethostbyname` then
answers 127.0.0.1. `start_capture` clears the block and re-resolves
whenever `resolved_to_loopback()` is true, and refuses to start if it
still is. The Capture tab's prerequisite probe clears a leftover block
at launch, skipping that while a capture is running (when the redirect
is load-bearing). `modify_hosts_file` rewrites an existing block rather
than accepting it. Only the text between `HOSTS_BLOCK_START` and
`HOSTS_BLOCK_END` is ever touched.

## Logging from the proxy reader thread

`capture_log_msg` is safe to call from any thread: an off-thread call
marshals itself onto the UI thread and drops the line if Tk is not
accepting work (see the `root.after()` rule in `ui_runtime.md`). Keep it
that way when adding log callers.

`CaptureManager`'s `live_update_callback` has the same cross-thread
shape and is safe only because capture cannot start before mainloop is
running.

## Upgraded-line augmentation

`[LIVE] Upgraded` lines carry an internal `[pid=N]` marker so the app
can find the upgraded fragment after the post-upgrade reload and append
what it scores under each preset; the marker is stripped before the user
sees it. A fragment with upgrades left reports a range under the label
`Highest Potential`, and one with none reports a single value under
`Highest GS` -- the same distinction the Memory Fragments tab's two
columns make. Lines are queued (`pending_upgrade_lines`) because the
fragment has
to be re-read from the new snapshot first, and
`_drain_pending_upgrade_lines` emits them after the reload. The fragment
object is retained so a later Upgrade Log Settings toggle can re-render
the line in place against a different preset selection.

Which presets reach the line is decided in `_upgrade_potentials_suffix`.
Beyond the Log Presets checklist, four mismatch filters (Capture tab, on
by default, stored in `settings.json`) drop presets whose combatants
cannot use the fragment's MAIN stat:

- **Element** — an element DMG% main that is not the combatant's
  element. Combatants whose element cannot be resolved are never
  filtered, matching the optimizer's off-element Slot V candidacy
  filter.
- **ATK/DEF** — read off the combatant's ATK/DEF Split: 0-33 rejects a
  DEF% main, 67-100 rejects an ATK% main, the band between accepts both.
  Keyed on the main stat rather than the slot, so it covers ATK% in
  slots IV, V and VI as well as DEF% in slot VI.
- **DPS HP% / DPS Ego** — a combatant whose Shielding & Healing weight
  is 45 or less counts as a damage dealer and rejects an HP% main (slots
  IV, V, VI) or an Ego main (slot VI). Two separate filters.

**A preset survives if ANY of its selected combatants accepts the
fragment** — the line lists presets, not combatants, and one preset can
be assigned to combatants of different elements, scaling or roles.
