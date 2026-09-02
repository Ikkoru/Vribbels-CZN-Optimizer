# Settings architecture

Read before touching any `*_manager.py`, `defaults_sync.py`, or the Setup tab's Restore Defaults panel. Runtime behaviour only — the maintainer side (what ships, how it is regenerated) is `how_to_maintain_default_settings.md`.

## Where state lives

User state in `Vribbels/settings/` (gitignored); shipped defaults in `Vribbels/default_settings/` (tracked). Reconciliation is `defaults_sync.py`, which runs in `OptimizerGUI.__init__` BEFORE any manager calls `load()`.

| File                      | Bundled default? | Holds                                                                                                    |
| ------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------- |
| `presets.json`            | Yes              | Gear Score scoring presets: name → {stat: weight}                                                        |
| `character_preset.json`   | Yes              | Combatant → preset assignment. Id-keyed v2 schema, below                                                 |
| `optimizer_settings.json` | Yes              | Per-combatant optimizer config keyed by `str(res_id)`, plus the top-level keys below                     |
| `settings.json`           | No               | Flat key-value user state: server region, worker count, optimizer filters, upgrade-log filters, `debug_perf_log`, last selections, update timestamps. **Canonical key order and defaults are `SettingsManager.LAYOUT`** — add new keys there so `apply_layout` materializes them into the file |
| `log_presets.json`        | No               | Capture-tab Log Presets flags: res_id → bool. Absent id = selected                                       |
| `perf_log.txt`            | No               | Diagnostics (`perf_log.py`), written only while `debug_perf_log` is true. Not settings; safe to delete   |

`config.json` is legacy. `SettingsManager.apply_layout` absorbs values from either historical location for keys not already in `settings.json`; the file is then left on disk and ignored. Consumers read through `context.config` — `AppConfig` (config.py), an attribute view over `SettingsManager` whose property setters persist immediately.

## Three-stage sync

`defaults_sync.sync_defaults(user_dir, defaults_dir)`:

1. **Maintainer bootstrap** — `default_settings/` empty but `settings/` populated → copy settings to defaults. Fires once on the maintainer's machine; inert once `default_settings/` is committed.
2. **New-user bootstrap** — a defaultable file missing from `settings/` but present in defaults → copy across.
3. **Update merge with tombstones** — the sidecar `settings/.defaults_sync.json` records which keys were in defaults at the last sync. Entries new since then are added to the user's file if missing. **Tombstoned entries — in the last sync AND in current defaults but absent from the user file — are NOT re-added**, which is what respects user deletions. When the sidecar does not yet exist, all current defaults are treated as already-known, protecting pre-tombstone deletions on upgrade.

Stage 3 merge keys: `presets.json` by name; `character_preset.json` by character key; `optimizer_settings.json` by `res_id`. **The user's existing value always wins.** A newly merged character in `optimizer_settings.json` is also appended to `excluded_gear_chars` — the "new combatants default to excluded" rule.

## Top-level keys in `optimizer_settings.json`

`excluded_gear_chars`, `version`, `excluded_default_initialized`, `exclude_seen_rids` and `optimize_level_seen` are NEVER touched by the merge; user values are authoritative.

- **`exclude_seen_rids`** — res_ids the exclude bootstrap has processed. A res_id absent from it is new to the exclude system and gets auto-excluded once (`_ensure_captured_chars_have_settings`). Tracked separately from "has a settings entry" because `bootstrap_known_characters` eagerly creates entries for every known character, which would otherwise mask a newly-added one.
- **`optimize_level_seen`** — the highest level each combatant has been observed at, which makes `optimize_for_level` follow a level-up exactly once rather than overriding the user's choice on every load.

All of these are per-user, so the shipped copy must not carry the maintainer's. `default_settings/normalize/normalize_defaults.py` empties the collections, sets `excluded_default_initialized` false and resets `optimize_for_level`; `zCreate exe.bat` runs it before building. Empty and absent behave identically; the script ships them empty so the shape stays visible. It is idempotent, keeps unrecognised keys, and leaves curated per-combatant values alone.

**`OptimizerSettingsManager.load()` preserves unknown top-level keys verbatim.** A `load()` that re-reads only `version`/`excluded_gear_chars`/`characters` and drops the rest breaks the flag round-trip. Pinned by a check. Don't undo it.

## Character preset assignment: id-keyed v2 schema

```
{"version": 2,
 "assignments": {res_id_str: preset_name | null},
 "name_hints":  {res_id_str: display_name}}
```

Keyed by `str(res_id)`, NOT by name; `name_hints` exists purely for readability when inspecting the file. The manager API still takes names (`get_preset_for`, `set_preset_for`) and resolves them internally.

**Why id-keyed:** a captured-but-unknown character is displayed as `"1055"` and later becomes `"Adelheid"`. Under name keys the user's assignment is silently lost at that moment; under id keys the res_id is stable and only the hint changes. For still-unknown characters the name-to-id resolver falls through to "if it looks numeric, use it".

`character_preset_manager.normalize_to_v2()` is IDEMPOTENT, so it runs on every load and every sync rather than being gated on a version check: numeric keys keep their value, name keys resolve via `CHARACTERS`, and a character carrying both resolves to whichever assignment is non-null. Mixed-version pairs normalize before the per-key merge, and both files are rewritten in v2 so later loads skip it.

## Restore Defaults

Three buttons on the Setup tab, one per defaultable file, all opening a generalized modal (`_open_restore_dialog(kind)` in `setup_tab.py`, dispatched via `_RESTORE_KIND_META`). It brings back deleted defaults and picks up updated values at per-entry granularity, **overriding the tombstone gate** that normally suppresses re-adds.

Two frames: "Restore Missing" (defaults the user has not taken) and "Replace Changed" (same key, different value), each row with a checkbox defaulting to checked. The Presets kind also gets a Rename column, so the user can keep their customized version under a new name while accepting the default under the original; rename text must be non-empty and must not collide with an existing preset or another rename in the same dialog.

**Bucket semantics for `character_preset`** (the non-obvious part — `None` means "no opinion"):

- defaults' value `None` → skip, nothing to recommend
- user `None`/absent AND defaults non-null → Missing
- both non-null and differing → Changed
- both match → skip

Without the first two rules, every combatant reset to Default Preset shows up in Replace Changed against defaults' non-null entries — noise.

**For `optimizer_settings`:** missing = rid absent from the user's `characters` dict; changed = rid present but the per-char dict differs, with `name_hint` excluded from the comparison since it is cosmetic and auto-refreshes on the next bootstrap.

The dialog does NOT update the tombstone sidecar — it mutates the user's file through the manager. The sidecar still tracks last-seen default keys, so a restored entry simply reads as "present" on later syncs.

After Restore, `_refresh_dependent_tabs(kind)` fires the cross-tab refresh: `presets` / `character_preset` → `heroes_tab.refresh_heroes()` plus a scoring-tab list refresh; `optimizer_settings` → `optimizer_tab.refresh_after_load()`.

## Manager behaviour worth knowing

- `OptimizerSettingsManager.ensure_character` updates `name_hint` automatically when called with a non-empty new name that differs from the stored one, so captured-but-unknown combatants get a proper name once `CHARACTERS` is updated.
- `CharacterPresetManager` caches the name↔id lookup tables lazily and keeps them for the manager's lifetime. If game data ever reloads at runtime (it does not today), call `invalidate_name_cache()`.
