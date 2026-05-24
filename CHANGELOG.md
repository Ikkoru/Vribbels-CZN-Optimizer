# Changelog

All notable changes to Vribbels CZN Optimizer (Ikkoru) will be
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This fork was branched from [Vorbroker/Vribbels-CZN-Optimizer](https://github.com/Vorbroker/Vribbels-CZN-Optimizer)
at v1.7.0 (2026-02-07) and restarts versioning from v1.0.0. For the
pre-fork history, see the upstream repository's CHANGELOG.

## [1.0.0](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases/tag/v1.0.0) - 2026-05-24

Initial release of this fork.

### Added

- **Per-character Gear Score presets** — Combatants tab assigns a custom GS rubric per hero
  * `PresetManager` holds named weight presets (11 supported stats)
  * `CharacterPresetManager` maps character → preset (or `None` for default)
  * Equipped MFs frame and the character-list GS column use the per-character preset
- **Link-icon marker on assigned presets** — Scoring tab preset list shows a 🔗 in a dedicated left gutter column when at least one character points at that preset (cue that deleting or editing it will affect Combatants-tab GS for those characters)
- **Letter-key list navigation** — Windows-Explorer-style typing-ahead on the Scoring tab preset list and the Combatants tab character list; press a letter to jump to the next matching name, cycling at the end
- **Highest Pot. range on the upgrade log** — the Capture tab's "[LIVE] Upgraded" lines now end with the post-upgrade Highest Pot. range across every defined preset (mirrors the Memory Fragments tab column), e.g. `[proxy] [LIVE] Upgraded Line of Justice Denial (+3). Highest Pot.: 42-58`
- **"Unequip All" capture handler** — the in-game bulk-unequip action is now tracked; previously the addon silently ignored it because the server response shares its "pieces" key shape with the create flow, which the dedup logic mistook for already-existing pieces
- **Inventory tab "Highest GS" and "Highest Pot." columns** with per-preset bounds caching
  * "Assigned Presets Only" filter narrows the search to presets actually in use
  * Header tooltips on every column (custom Toplevel, since Treeview has no native support)
- **Main stat and set filters** on the Inventory tab
- **Memory Fragment lifecycle capture** — create and disassemble events tracked from WebSocket traffic
  * Equip / unequip / swap / upgrade already covered upstream; create / delete now complete the set
  * Batch operations supported (3-piece create and 3-id disassemble verified)
- **Right-click level checkpoints** — confirm in-game level for characters and partners
  * Persists to `presets/level_data.json` and anchors the exp → level lookup table
  * Characters: 1–62 range; partners: 1–60
- **`LevelDataManager`** — owns the checkpoint table and rewrites the active exp tables at startup
- **Character selection memory** — last-selected hero restored on next launch (via `SettingsManager`)
- **Single-instance lock** — second launch is rejected via `socket.bind(127.0.0.1:53117)`
- **Active preset auto-highlight** in the Scoring tab listbox
- **Level 62 infrastructure** — `LEVEL_61_BONUS` / `LEVEL_62_BONUS` dicts in `characters.py`, `effective_level` parameter on `calculate_build_stats` (placeholders until real bonus values land)
- **About tab self-contained update check** — direct urllib call to this fork's GitHub releases API, no third-party deps
  * `update_latest_version` and `update_last_checked` persisted via `SettingsManager`
  * No popup dialogs — all status shown in-tab
  * Cached result restored on next launch

### Changed

- **Damage formula overhauled** to layered Final ATK/DEF/HP
  * `inner = (Base + Partner_flat) × (1 + MF% + Potential%) + Gear_flat + Affection_flat`
  * `Final = inner × (1 + Partner% + Equipment%) + Equipment_flat`
  * Equipment legendary constants: ATK 82, DEF 31, HP 83
- **Gear Score normalized to 0–100** per preset (was raw weighted sum)
- **Gear Score normalization is per-fragment ("Philosophy B")** — each fragment's bounds exclude its own main stat from the substat pool, so 100 is reachable regardless of which main stat the fragment has. Two fragments with identical substats but different main stats can now score differently: the one whose main is more high-weighted under the active preset gets the higher GS, correctly reflecting that its main stat contributes real build value. `compute_gs_bounds()` gains an `exclude_stat` parameter; new `bounds_for_fragment()` convenience helper. All callers updated with per-main-stat bounds caching to keep performance flat.
- **`selected_preset` moved from `presets.json` to `settings.json`** — the active preset is per-user state, not shipping default. `PresetManager` reads/writes it through `SettingsManager` when one is wired up; legacy `presets.json` files with a top-level `selected_preset` key are migrated on first load (key copied to settings.json, then dropped from presets.json on the next write). Shipping `presets.json` no longer carries the field.
- **Partner card display** is now three-state — known partner / unknown res_id / no partner
- **Internal "friendship" renamed to "affection"** to match the in-game term
- **About tab links** repointed to this fork (Releases, Issues, README)
- **Scoring tab preset list switched from `tk.Listbox` to `ttk.Treeview`** so the assigned-preset link icon can live in a dedicated fixed-width gutter on the left, keeping preset names aligned across linked / unlinked rows. Treeview iids are set to the preset names, making selection-to-name lookups direct.
- **First launch defaults to the Setup tab** instead of the Optimizer tab — the program is useless without captured data, so the user lands on the proxy/cert installation flow before being asked to do anything else. After this fires once, a `first_launch_done` flag in settings.json keeps the default behavior (open at leftmost tab) on subsequent runs. Clearing settings.json re-triggers it, so "reset to factory state" works as expected.

### Fixed

- Partner data audited against prydwen.gg; corrections applied
- **CHARACTER_EXP_TABLE**: Amir 300000 → 320000
- **CHARACTER_EXP_TABLE**: levels 41–49, 55, and 61 firmed up from estimates to confirmed Amir checkpoints across multiple sessions; level 45 was 200000 → 213000, level 55 was 481000 → 480800, level 61 is new (778200)
- **PARTNER_EXP_TABLE**: Yvonne 110000 → 93500, Zatera 4000 → 1800, max 360000 → 346000
- Partner max level now correctly returns 60 at the cap (was rolling to 61)
- Elemental DMG% (Passion / Order / Justice / Void / Instinct) excluded from the substat roll pool — main-stat only
- Affection bonus at level 41+ uses closed-form ATK = 3·((N+1)//3), DEF = N//3, HP = 3·((N-1)//3)
- 5-digit potential node IDs parsed correctly (was hardcoded for 4-digit res_ids)
- Set name color reflects whether the equipped set is actually complete (was always lit when at least one piece was equipped)
- WebSocket addon-script writer forced to UTF-8 — fixes Windows cp932 codec error on non-ASCII paths
- Gear Score documentation corrected: "100" requires the fragment's substats to be the preset's top-4 weighted stats, not just any perfect roll
- **Optimizer tab refreshes after live capture** — the live-update path now calls `optimizer_tab.refresh_after_load()` (the manual `Load Data` path already did this; the live path skipped it, so newly-captured characters didn't appear in the Optimizer tab's hero combo until manual reload)
- **User-data persistence in frozen (PyInstaller) builds** — presets, level checkpoints, settings, and per-character preset assignments now persist across runs. Previously `Path(__file__).parent` resolved into PyInstaller's read-only `_MEIPASS` temp dir, which got wiped on exit, silently losing every save. New `_user_data_dir()` helper resolves to `sys.executable.parent` in frozen mode + `_bootstrap_user_data()` copies bundled defaults (`presets.json`, `character_preset.json`) on first run if the user dir is empty.

### Removed

- `update_checker.py` and all consumers (Ikkoru fork doesn't need the upstream's third-party update flow)
- Third-party dependencies `requests` and `packaging`
- Heuristic damage stats (EHP, Average Damage, Max Crit Damage, Bruiser) from optimization results — superseded by the new Final ATK/DEF/HP model
- `threading` and `queue` imports from `czn_optimizer_gui.py` (only the old update flow used them)
- **Load Data button from the Optimizer tab toolbar** — data loads automatically on app startup (`auto_load`) and after each live capture update (`_handle_live_update`), so the manual button was a vestige. The underlying `load_file_callback` is still in `AppContext` and can be re-exposed in another tab if a manual-load entry point is wanted later.
- `selected_preset` field from the bundled `presets.json` defaults — it's per-user state and now lives in `settings.json` (see Changed section).

### Refactored

- Substantial documentation pass: top-of-file orientation maps and inline cross-file conventions on `characters.py`, `partners.py`, `constants.py`, `memory_fragment.py`, `optimizer.py`, `czn_optimizer_gui.py`, `heroes_tab.py`, `inventory_tab.py`
- `compute_fragment_gs` / `compute_fragment_potential` extracted as module-level pure functions in `memory_fragment.py`; per-preset bounds precomputable once and reused across fragments
- `MemoryFragment.calculate_base_score` / `calculate_potential` delegate to the pure helpers