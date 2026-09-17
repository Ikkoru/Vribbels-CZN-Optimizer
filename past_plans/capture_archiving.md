# Archiving old captures — [IMPLEMENTED] 2026-09-17

All five phases landed. The first run against the real folder took 146 captures — 281.6 MB — to 1.3 MB in 4.8s at Balanced, and every one of the 152 captures in the backup was afterwards found either in the archive or still loose, with matching content and nothing missing.

Kept for the measurements, and for the options that were rejected: the manifest that turned out to duplicate the tar header, the per-file appending that costs 29x, and the dated archive name that would have brought it back.


`Vribbels/snapshots/` only grows. Nothing in `capture/` deletes anything, so a long-running install accumulates one `memory_fragments_*.json` per game relaunch (~1.7 MB each) and, for anyone who ticks Debug WS, one `websocket_debug_*.jsonl.gz` per session. With always-on capture the snapshots are the growth; the logs are the maintainer's.

This folds the old ones into a single solid archive, in a background thread at launch, deleting a loose file only after its archived copy has been read back and matched byte for byte.

## What decides the design

Measured on 114 real snapshots (194 MB), packed as one solid `.tar.xz`:

| | bytes | of raw | pack | read one member back |
| --- | --- | --- | --- | --- |
| preset 0 | 8,442,392 | 4.343% | 2.1s | 1.00s |
| **preset 3** | **242,480** | **0.125%** | **1.1s** | 0.33s |
| preset 6 | 230,124 | 0.118% | 15.9s | 0.32s |
| preset 9 | 233,300 | 0.120% | 16.1s | 0.35s |
| preset 9 \| EXTREME | 177,052 | 0.091% | 36.7s | 0.34s |
| one member at a time, preset 6 | 7,011,556 | 3.607% | 18.1s | — |

**Appending costs 29x.** Consecutive snapshots are nearly identical, and that only pays inside ONE compression stream. So the archive is REBUILT, never appended to.

**Rebuild cost is proportional to the whole archive**, not to what is being added, so three rebuilds to add nine files cost three times one rebuild to add nine. Hence a high-water mark.

**Presets 0, 6 and 9 are dominated.** Preset 0 is bigger AND slower than 3; 6 and 9 cost 14x the time of 3 for 5% less. Only 3 and 9|EXTREME sit on the frontier, which is why the setting has two working stops.

## Constraints

- **The loose files are irreplaceable.** A file is deleted only after the archive that has just replaced the old one has been re-opened, its member read back, and its SHA-256 matched against the file about to be removed — in that same pass. "Verified" means verified by this run, not present in some earlier archive; the files being archived now are exactly the ones that were not in it before.
- **The deleter takes a whitelist, not a path.** It refuses anything that is not (a) directly inside the snapshots directory, (b) matching `memory_fragments_*.json` or `websocket_debug_*.jsonl` / `.jsonl.gz`, and (c) matched by SHA-256 against its member moments earlier. `_capture_addon.py` and `__pycache__/` live in that same directory and must never be reachable.
- **`_MEIPASS` is read-only** in frozen builds: the archive lives beside the snapshots under `_user_data_dir()`.
- **Four globs read the folder** and none may see the archive: `memory_fragments_*.json`, `websocket_debug_*.jsonl`, `websocket_debug_*.jsonl.gz`, `snapshots/*.json`. A `.tar.xz` name matches none.
- **Readers need more than the newest file.** `czn_optimizer_gui.auto_load` and four checks want the newest snapshot; `docs/missions_id_dump.py` walks BACKWARDS through snapshots until it finds one carrying missions, and through logs the same way.
- **Compaction must not touch the capture path.** `_save_data()` runs inside live WebSocket handling.

## Shape

**One archive, one stable name, rebuilt in place.** `archived_captures.tar.xz`, beside the loose files. No date in the name: a dated name means a new archive per compaction, which is the per-file case and its 29x penalty.

**No manifest.** A tar header already carries each member's name and size, and `tarfile.getmembers()` reads them without touching the payload, so the settings panel's count and content size come free. The xz stream carries its own CRC64 per block, so integrity is covered. SHA-256 is computed at verify time from both sides and compared — storing it would only duplicate what the comparison already has.

**Logs go in decompressed.** xz cannot shrink a `.gz`: the maintainer's two logs cost 2,238,825 bytes stored as-is against 414,555 decompressed, so about 85% of a log's archived size is recovered by ungzipping on the way in. `gzip.open()` streams straight into `tarfile.addfile()`, so no temp file is involved. The member is named `.jsonl`; that it came from a `.gz` is readable from the name, and nothing downstream acts on it differently.

**Two water marks, per type, and the two types do not want the same numbers.** Compact when the loose count of a type reaches HIGH, leaving the newest LOW of that type loose. "Old" here is positional, not temporal: the Nth file back from the newest, never a file the program is about to read.

| | HIGH | LOW | why LOW is that |
| --- | --- | --- | --- |
| `memory_fragments_*.json` | 16 | 3 | NOT the walker: measured over 116 captures, every one written since the addon learned to keep `mission_entities` carries it, so the walk needs one. LOW covers what else wants a loose file — the app loads the newest, a diff needs two, one spare. |
| `websocket_debug_*.jsonl.gz` | 13 | 3 | The maintainer's numbers alone. Nothing shipped reads a debug log — `capture/manager.py` writes one and no other file under `Vribbels/` opens one — and the two readers that do live in `docs/`, which the build does not package. An end user with Debug WS off has none of these files, so these marks never fire for them. |

**A snapshot cannot be empty or truncated.** `_save_data` returns early unless `inventory_data` has arrived, and it writes a `.tmp` and `replace()`s it, retrying the Windows `PermissionError` that a held destination raises. A crash mid-write leaves a `memory_fragments_*.json.tmp`, which matches none of the readers' globs, not a half-written `.json`.

**It CAN be semi-empty** — inventory present, `mission_entities` absent — but not any more. The field arrives in the LOGIN payload and a snapshot file is only started on a relaunch, which means a login, so every capture since the addon learned to keep it has carried it: 52 of 52, with the 64 that lack it all older than 2026-09-07. A miss costs nothing either way, since `missions_id.tsv` merges rather than replaces and a run that finds nothing leaves the file alone.

**Nothing walks PAST a corrupt file.** Both dump scripts call `json.loads` with no guard, so a file damaged some other way (disk, an external edit) ends the run with a traceback rather than being skipped — and a larger LOW would not help, since the walk dies at the first bad file it touches whichever way it is set. The fix is a guard in the walkers, not a bigger window; see Phase 4. The app itself is already covered: `czn_optimizer_gui.load_data` wraps the parse in a `try`.

### The compaction sequence

1. Sweep a stale `.tmp` from an interrupted run, then stop unless HIGH is reached for at least one type.
2. Build `archived_captures.tar.xz.tmp` from the existing archive's members plus the loose files older than the newest LOW.
3. Read every member of the `.tmp` back; compare each against the loose file it came from by size and SHA-256.
4. Only on a clean verify, atomically replace the archive with the `.tmp`.
5. Re-open the replaced archive and delete each loose file, one at a time, each only after its own member has matched again.
6. Report what happened to the Capture Log.

A crash at any point leaves either the old archive plus all loose files, or the new archive plus all loose files — never neither. A loose file that is already inside the archive is harmless duplication; the next compaction deletes it once it matches.

### What a failure does

Not one rule — the failures are different in kind, and only the last two are worth interrupting anyone over.

- **A locked or unreadable file** (antivirus, the indexer, another process) — Windows' usual. Retry three times with a short backoff. If it still will not open, leave it loose and carry on: the archive is correct without it, and the next compaction picks it up. **No alert.**
- **A single loose file that will not delete** — the archive is already good, so this is not a reason to abandon anything. Leave it; the next compaction finds it already inside and deletes it then. **No alert.**
- **A SHA-256 mismatch, or a member missing from the rebuilt archive** — stop. Never retry, never delete. A retry cannot fix a mismatch: either the archive is wrong or the file changed underneath, and both want a human. Keep the old archive, delete the `.tmp`. **Alert.**
- **Out of disk, or any other `OSError` while writing** — abort, delete the `.tmp`, keep everything. **Alert.**

### Deleting

**A verified loose file is deleted outright.** The archive is the safety copy and it was matched byte for byte a moment earlier; sending it to the Recycle Bin would guard a failure that verification has already eliminated, while filling a user's bin with hundreds of files they will not recognise.

**The archive itself, deleted by the button, goes to the Recycle Bin** — that is the one irreversible action with no copy behind it. `SHFileOperationW` with `FOF_ALLOWUNDO` through `ctypes` does it without a dependency, and falls back to a plain delete where there is no bin (a network or removable drive). No `send2trash` dependency: the build already has one fragile third-party step and does not need another.

## Telling the user something went wrong

Only the two abort-class failures above raise it. The rest are self-healing and must stay silent, or the alert becomes wallpaper.

- **The `Capture` tab** takes a dark red background — dark enough that the word `Capture` stays legible on it — and blinks slowly until the tab is pressed.
- **The `Capture Log` panel's title** takes the same red and blinks, stopping when the user leaves the Capture tab or after 7 seconds, whichever comes first.

**The log title is the easy half.** It is a `ttk.LabelFrame`, and giving that one widget its own style name (`Alert.TLabelframe.Label`) colours its label alone.

**The tab is not.** ttk applies `TNotebook.Tab` to every tab of a notebook, so there is no per-tab background or foreground, and tab state is limited to `normal` / `disabled` / `hidden`, so no custom style state can be mapped either. What IS per-tab is `text`, `image`, `compound` and `underline`.

**A generated dot image beside the label.** `notebook.tab(i, image=dot, compound=tk.LEFT)` is per-tab, and the dot needs no asset: a `tk.PhotoImage(width=px(8), height=px(8))` with `put(alert_red, to=(0, 0, w, h))` is a solid square built at runtime, sized through `px()` like everything else. Blinking alternates it with an empty image of the same size, so the label does not shift. The tab keeps its plain, legible text and the colour lands beside it.

The image must be held on an attribute for as long as the tab shows it — a `PhotoImage` with no Python reference is garbage-collected and the tab goes blank. It is also the one `px()` case that is not a geometry call, so `check_ui_scales.py` will want to see it double.

The blink itself is a `root.after` loop, cancelled on `<<NotebookTabChanged>>`, on the 7-second timer, and on window close. The alert state is worth building as a small reusable thing rather than as archiving's own: nothing else in the app currently has a way to say "something failed while you were not looking".

## Settings

`Setup & Settings` tab, `Settings` panel, a second column to the right of the existing settings. Top to bottom:

```
Compression: [ Balanced v ]
Archives old captures. Applies on the next launch.

Archive size: 8.6 MB        Snapshot folder: 7.4 MB

                            [ Delete Archive ]
```

- **Dropdown**: `Off`, `Balanced` (preset 3, the default), `Strongest` (preset 9|EXTREME). `Off` belongs in the same control rather than a separate toggle — it is the same question.
- **`Off` stops archiving; it does not extract.** Someone choosing Off wants less machinery, not 286 MB back in their folder. `Delete Archive` is the explicit way out.
- **A setting change marks the archive due**, and the next launch rebuilds at the new preset whether or not HIGH is reached — which is what the caption promises. It does not fire on the click: a 37-second pass because someone opened a dropdown is not what the control looks like it does.
- **`Snapshot folder` excludes the archive**, so the two figures add up to the folder rather than overlapping. `Archive size` is the file on disk; its tooltip gives the content size inside, which is the figure that decides whether deleting is worth it.
- Both are recomputed when the tab is selected, not on a timer.
- **`Delete Archive`** aligns with the bottom of the panel. Its confirmation names the loss: "Delete N archived captures (286 MB of history, 8.6 MB on disk)? This cannot be undone." with `Delete` and `Cancel` — the affirmative names the action rather than saying `Yes`.
- The new column needs spacing-registry entries like any other; see `.claude/rules/ui.md`.

## Phases

### Phase 1 — the archiver, headless — DONE

Run against the real folder: 146 captures, 281.6 MB, archived and deleted in 4.8s at Balanced, leaving 1.3 MB — 0.47% — and 3 of each kind loose. Every member was hashed back against its loose file, and every one of the 152 captures in `snapshots.rar` was then found either in the archive or still on disk, with matching content and nothing missing.


`capture/archive.py`: build, verify, replace, delete, plus `read_member(name)` for tooling. No UI, no threading, no wiring. Driven by a maintainer-only script with `--dry-run` that archives without deleting.

Acceptance:

- a round trip over synthetic files in a temp dir returns every byte;
- a log goes in decompressed and its content comes back identical to what `gzip.open` yields from the original;
- with verification forced to fail, NOTHING is deleted and the old archive survives;
- the deleter refuses a path outside the snapshots directory, a path that matches neither name pattern, and a path whose SHA-256 was not matched in this pass — including `_capture_addon.py`, which sits in that directory;
- an interrupted build leaves no `.tmp` behind after the next run's sweep, and the old archive intact.

### Phase 2 — run it at launch — DONE

A daemon thread started after `_reveal_window` has settled. Failures log to the Capture Log and never raise into the UI. No guard against a running capture: a capture only writes NEW files, the archiver only touches files older than the newest LOW, and at Balanced the whole pass is about a second.

Acceptance: launching with HIGH+ loose files leaves LOW loose and the rest archived, with the app usable throughout; launching with fewer than HIGH sweeps any stale `.tmp` and does nothing else.

### Phase 3 — the settings column — DONE

The controls above, the sizes, the delete button and its confirmation. The setting persists through `SettingsManager`; `Off` means the Phase 2 thread never starts.

Acceptance: `checks/check_settings_roundtrip.py` covers the new key; `checks/check_tabs_build.py` sees the new widgets; the spacing audit has targets for the new column.

### Phase 4 — teach the tooling about the archive — DONE

`docs/items_id_dump.py` and `docs/missions_id_dump.py` fall back to `read_member` when the loose files run out, so a deep walk still reaches archived captures. The same edit gives both walkers a guard: a file that will not parse is skipped with a line saying which one, rather than ending the run — which is the resilience a larger LOW was reaching for and cannot provide. `docs/wire_catalogue_backfill.py` learns that a restored log named `.jsonl` may be a decompressed `.jsonl.gz`, so its "uncompressed means it predates the catalogue" rule does not misfire on one.

### Phase 5 — the alert — DONE

The red blink, once one of the three approaches above is chosen. Last because the archiver is correct without it: a failure that alerts nobody still changes nothing on disk.

Acceptance: an injected abort-class failure lights the tab and the title; an injected retry-class failure lights neither; the blink stops on press, on leaving the tab, and at 7 seconds; no `after` callback survives window close; the dot survives a garbage collection pass, and doubles at 200%.

## Decisions taken

- **No guard against a running capture.** A capture only writes new files and the archiver only reads old ones, so the two cannot collide. CPU contention is about a second at Balanced.
- **No "currently loaded file" guard.** `load_file` exists on the GUI and is passed into the context, but no tab calls it, so there is no way to open an older snapshot from the UI and the hot window already covers what is loaded. (That callback is unused wiring; worth a look some time, not here.)
- **No manifest member.** Proposed for name, size, SHA-256, a gz-decompressed flag and an archive date; every field turned out to be either already in the tar header, recomputable at the moment it is needed, or read by nothing. A field nobody reads is a stale output waiting to happen.
- **No grace period on first compaction.** HIGH is already one: thirteen files pass before anything is archived, and an end user would never notice a grace period as a distinct phase.
- **No extract-back path.** Anyone wanting the files out can open the `.tar.xz` with WinRAR or 7-Zip. An `Extract Archive` button can follow if it is ever wanted.

## Open questions

- The four water marks are chosen, not measured. Each LOW is bounded below by the backwards-walking readers; each HIGH only trades compaction frequency against loose-file disk.
