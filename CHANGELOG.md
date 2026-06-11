# Changelog

All notable changes to Vribbels CZN Optimizer (Ikkoru) will be
documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This fork was branched from [Vorbroker/Vribbels-CZN-Optimizer](https://github.com/Vorbroker/Vribbels-CZN-Optimizer)
at v1.7.0 (2026-02-07) and restarts versioning from v1.0.0. For the
pre-fork history, see the upstream repository's CHANGELOG.

## [1.1.0] - unreleased

Major Optimizer-tab overhaul. The Optimizer becomes hands-off for the
user: instead of dialling priority sliders per build, each character
carries a saved profile of build assumptions (damage-type shares,
ATK/DEF scaling, shielding/healing weight, set choices, stat biases),
and the engine works out the best gear combination on its own. Per-
character settings persist between launches, keyed by character `res_id`
so renames don't lose data.

### Added

- **Adelheid and Clara** added.
- **`docs/game_formulas.md`** — canonical reference for the in-game formulas the optimizer uses: Final ATK/DEF/HP, damage (ATK- and DEF-scaling variants), shield/heal, card multiplier, set effect application, main stat magnitudes, endgame stat benchmarks, and the v1.1.0 optimizer scoring formula. Future code disagreements with in-game math should be resolved by updating this file first, then propagating the change into code.
- **`MAIN_STAT_VALUES`** table in `game_data/constants.py` — maps `(slot, stat_name)` to the max main-stat value for a Legendary fragment. Reference data; the optimizer reads `fragment.main_stat.value` from captured snapshots, not this table.
- **`OptimizerSettingsManager`** (`optimizer_settings_manager.py`) — per-character optimizer-tab state, persisted to `presets/optimizer_settings.json`. Keyed by `res_id` (string) so character renames in `characters.py` don't lose data; bootstraps at startup by walking `CHARACTERS` and adding a default entry for every known character that doesn't have one yet. Carries the global "excluded gear chars" list too.
- **Element override dropdown** in the Optimizer tab — shown only when the selected character has `attribute == "Unknown"`. Lets the user manually pick an element for damage-calculation purposes until the character is properly added to `characters.py`. Once the character has a real attribute, the dropdown hides itself.
- **Per-character "Optimize for LVL" stepper** (60 / 61 / 62) in the Optimizer toolbar. Each character remembers its own setting; the value is treated as authoritative (no clamping to the character's actual `max_level`, since the optimizer is an endgame planning tool).
- **"Have at least" hard constraints** in the Optimizer tab — 8 spinboxes (ATK, DEF, HP, Ego, CRate, CDmg, Extra DMG%, DoT%) act as minimum thresholds on FINAL stat values. Builds that don't meet every minimum are excluded from results; if all candidates fail, the user gets a popup suggesting they lower a threshold.
- **All / None buttons** on the Exclude Combatant's Gear panel — toggle every character checkbox at once.
- **`compute_fragment_gs`** pure helper in `memory_fragment.py` — parallel to `compute_fragment_potential`. Scores a single fragment under given weights without touching its cached `fragment.gear_score`. Used by the Optimizer tab's detail-tree per-character GS column and by the slot pre-filter when a character has an assigned preset.
- **Bundled defaults system.** A new `default_settings/` folder ships canonical preset / per-character preset / optimizer-settings files; a startup reconciler (`defaults_sync.py`) merges them into the user's `settings/` folder on every launch in three stages: maintainer bootstrap (settings → defaults, one-time), new-user bootstrap (defaults → settings, on fresh install), and update merge (per-entity, only adding entries the user doesn't have). Tombstone sidecar `settings/.defaults_sync.json` records keys seen in defaults at the last sync, so user-deleted defaults don't silently reappear on update. First-sync grandfathering protects pre-tombstone deletions when upgrading from an older release. Documentation in `docs/how_to_maintain_default_settings.md`.
- **New combatants released in program updates auto-default to excluded** in the Optimizer's Exclude Combatant's MFs list. The defaults-merge path appends newly-merged res_ids to the user's `excluded_gear_chars`, and the per-tab bootstrap covers captured-but-unknown chars too — so the rule "all combatants excluded by default, including new ones" holds without maintainer intervention per release.
- **Restore Defaults UI** in the Setup tab. Three buttons (Presets / Combatant Presets / Combatant Settings) each open a modal dialog with Restore Missing + Replace Changed lists. Presets dialog adds an "Also Rename and Keep Current" option for keeping the user's custom version aside while accepting defaults' version under the original name. Lets users selectively bring back deleted defaults and pick up updated default values, overriding the tombstone gate. Dependent tabs (Combatants, Optimizer) auto-refresh after a restore.

### Changed

- **Optimizer tab fully overhauled.** The middle Configuration column is rebuilt around per-character persistent settings:
  * **Important Settings** (left side of top row): Extra% + DoT% sliders, ATK↔DEF scaling slider, Shielding/Healing weight slider, four force-main checkboxes (IV: HP / V: HP / VI: HP / VI: Ego).
  * **Have at Least** (right side of top row): 8 minimum-threshold spinboxes that act as hard constraints on build results.
  * **Set Configuration**: Maximum Flex Slots stepper, set-effect % slider, three Average buff spinboxes (Card DMG / Mult Buff / Add Buff), and a single combined checklist of all sets (4-piece sorted first, then 2-piece). The old separated 4-piece / 2-piece multi-selects are gone — select any usable sets and the optimizer (in Phase 4 of the v1.1.0 work) will figure out the best combination shapes.
  * Every per-character widget auto-persists to `optimizer_settings.json` on change. Re-selecting a character restores its saved state. New characters get a default entry the first time they're encountered.
- **`SLOT_MAIN_STATS`** corrected — DEF% previously listed as a main stat for slots 4 and 5; it only exists on slot 6. `MAIN_STAT_VALUES` updated to match.
- **Set `type` field: `"stat"` renamed to `"unconditional"`** in `sets.py` (4 affected sets: Tetra's Authority, Healer's Journey, Black Wing, Executioner's Tool). The old label was misleading — `"stat"` suggested a category distinct from `"conditional"` even though some conditional sets *also* contribute to Final stats (the Crit DMG / Crit Rate sets, just scaled by the set-effect slider). Updated everywhere the type field is read (`optimizer.py:calculate_build_stats`) and referenced (`docs/game_formulas.md`).
- **Optimizer-tab toolbar** redesigned: Combatant → Optimize-for-LVL stepper → Start → Stop. The status label sits on the right. A 3-line help-text strip sits directly below the toolbar (where Reset's space used to be).
- **Optimizer scoring formula rewritten** to match the in-game damage / shield-heal model. `calculate_build_stats` now also computes `Shield_Heal_DEF` (a Final-DEF variant where Partner_FLAT_DEF is pulled out of the inner multiplier) and applies conditional Crit DMG / Crit Rate set bonuses to Final_CDmg / Final_CRate, scaled by the set-effect-share slider. `optimize()` now scores builds via a new `_compute_optimizer_score` method that implements the blended damage / shield-heal formula from `docs/game_formulas.md` §8: ATK-scaling and DEF-scaling damage formulas blended by the ATK/DEF split slider, Extra DMG and DoT damage shares applied as ATK-formula multipliers, conditional DMG multi / DMG add set bonuses contributing to the damage card multiplier only, Element DMG% picked up from slot-5 main stats matching the character's attribute (or `element_override` for Unknown characters), CRate capped at 100%, and finally blended with shield/heal via the heal-share slider.
- **Optimizer's `Have at least` hard constraint moved inline** into the build enumeration loop. Builds that fail any minimum are skipped before scoring, saving the formula work. The optimizer also reports `last_optimize_stats` counters (`total_combinations`, `passed_set_reqs`, `passed_have_at_least`) that drive the "0 builds matched" popup messaging — distinguishes "no candidates satisfied set requirements" from "all candidates failed minimums".
- **`calculate_build_stats` signature**: added `set_effect_share` parameter (defaults to 0.0). When > 0, conditional Crit DMG / Crit Rate sets contribute to Final_CDmg / Final_CRate scaled by that share. Callers outside the optimizer (Heroes tab, etc.) leave it at 0 since the conditional bonuses aren't actually always active in-game.
- **`SET_STAT_NAME_MAP`** added in `optimizer.py` for translating `sets.py` stat names (`Crit DMG`, `Crit Rate`) to the program's internal vocabulary (`CDmg`, `CRate`).
- **Phase 4 — Set-combo search rewrite.** The optimizer's set-requirement check was replaced with a **unified locked-count rule** that subsumes all six combo shapes from the design spec:
  * 4+2 (chosen 4pc + chosen 2pc), 4+wild2, 2+2+2, 2+2+wild2, 2+wild4, wild6
  * Implementation: count slots locked into a satisfied chosen-set bonus; the build is valid iff `(6 - locked) <= max_flex_slots`. Mathematically equivalent to per-shape enumeration but avoids the partition combinatorics (no `C(6,4)` partition explosion per shape).
  * New `_count_locked_slots(combo, sets_selected)` helper does the counting; integer 0–6. Overflow pieces of the same set don't count beyond the bonus threshold (6 of a 4pc set still locks only 4 slots).
  * `sets_selected` and `max_flex_slots` now passed through from per-character settings; the legacy `four_piece_sets` / `two_piece_sets` fields stay in the settings dict but the new code uses `sets_selected` directly. Fallback path: if `sets_selected` is missing, the optimizer reconstructs it from the union of the legacy fields, so older callers keep working.
  * Candidate pool sizing: when `max_flex_slots == 0` (pure chosen-set build), the candidate pool is restricted to chosen sets for efficiency. When wildcards are allowed, the pool broadens to all sets and the locked-count rule filters invalid combos during enumeration.
- **`get_gear_by_slot` Top filter gains a 10-fragment floor.** Previously kept top `top_percent`% of candidates per slot, with no minimum — sparse inventories ended up with 1–2 candidates per slot, starving the optimizer. Now keeps `max(10, top_percent%)` per slot (capped at `len(candidates)`). Larger search space for sparse inventories; same behavior for typical / large inventories.
- **Phase 5 — Per-character preset wired into the Optimizer tab.** The Selected Build detail tree and the optimizer's slot pre-filter now both honor the character's assigned scoring preset (Combatants tab assignment) instead of the globally-active Scoring tab preset:
  * **Detail-tree GS / Potential columns** — recomputed per-build under the character's weights via the new `compute_fragment_gs` pure helper in `memory_fragment.py` (parallel to the existing `compute_fragment_potential`). Doesn't mutate `fragment.gear_score`, so the global cached value stays valid for tabs that share it.
  * **Slot pre-filter sort** — `get_gear_by_slot` gains a `score_weights` parameter. When supplied, the per-slot top-N candidates are picked by their score under those weights rather than by the globally-cached `fragment.gear_score`. With per-main-stat bounds caching so the per-slot loop stays cheap.
  * **Resolution order** in `_get_weights_for_character`: (1) character's assigned preset via `CharacterPresetManager.get_preset_for`, (2) currently-active preset (`PresetManager.selected_preset`), (3) empty dict = all-1.0 weights. Matches the Heroes / Combatants tab behavior. If the assigned preset name no longer exists in `PresetManager`, falls through silently.

- **Per-character preset wired into the slot pre-filter sort** (already described above) plus the Selected Build detail tree.
- **Polish round (15-item punchlist).** A batch of UI/data refinements after the Phase 1-5 overhaul:
  * **Mouse-wheel on all spinboxes.** The Gear Score tab's stat-weight spinboxes now respond to the scroll wheel (the Optimizer tab's already did). Shared `_spinbox_wheel` handler.
  * **Keyboard navigation on dropdowns.** The Optimizer tab Combatant selector and the Combatants tab preset-assignment dropdown now support type-to-jump (press a letter to cycle to the next matching entry). Explicit `_combobox_letter_jump` binding so behavior is consistent across platforms.
  * **Non-resizable panels.** The Gear Score, Combatants, and Optimizer tabs replaced their draggable `ttk.PanedWindow` splits with fixed-ratio grid layouts (50/50, 1:2, and 1:2:2 respectively). The sash can no longer be dragged.
  * **Set-effect % defaults to 100** for newly-initialized character settings (was 0); the live readout to the right of the slider already showed the current value.
  * **Auto-bump Maximum Flex Slots.** If the chosen sets can't lock enough slots to leave a valid build under the current flex cap (e.g. one 2-piece set with flex=2), the optimizer raises the cap to the minimum that works, persists it, updates the spinbox, and shows a "Not Enough Flex Slots. Increased to N." notice in parallel with starting the run. New `_max_lockable_slots` / `_maybe_bump_flex_slots` helpers.
  * **Stats Comparison panel reorganized.** Element% added to Totals (sum of slot-5 Element DMG% mains matching the character's attribute); Extra DMG%, DoT%, and Ego moved into Totals; the separate "Substats" section (and its ATK%/DEF%/HP% summed-bucket rows) removed.
  * **Results "Sets" column reformatted.** Now lists 4-piece active sets, then 2-piece active sets (alphabetical within each), then an "N Flex" token. Only sets meeting their piece requirement are named; names over 15 characters collapse to their first word.
  * **"Show all stat contributions" right-click breakdown** (new). Right-clicking the Stats Comparison tree opens a popup itemizing every source feeding each final stat (Base / Partner / MF% / Pot / MF Flat / Affection / Partner% / Other for ATK/DEF/HP; Base + MF Main + MF Sub Sum + Other for crit; plus Element%, Extra/DoT/Ego splits and the xDMG% / +DMG% buff totals). Backed by a new `compute_build_breakdown` method whose ATK/DEF/HP sums reconcile exactly with `calculate_build_stats`.
  * **Per-character level 61/62 stat bonuses.** `LEVEL_61_BONUS` / `LEVEL_62_BONUS` global placeholder dicts (added in v1.0.0) were replaced with optional per-character `level_61_bonus` / `level_62_bonus` keys in the `CHARACTERS` dict, since in-game data showed the gains differ per character. Heidemarie is the first confirmed entry (ATK +9, DEF +3, HP +7 at level 61). Characters without these keys fall back to their level-60 stats. `get_character_stats_at_level` reads the per-character keys.
  * **`CHARACTER_EXP_TABLE` levels 1-40 firmed up** from the in-game progression panel (every level now has a confirmed cumulative threshold; the old table had estimated round numbers for many sub-40 levels that were significantly off). Level-40 total (144000) unchanged.
- **Polish round 2 (Combatants tab + Optimizer tab + Memory Fragments refinements).** Continuation of the visual iteration after the 15-item punchlist:
  * **Combatants tab fixed-size detail panel.** Character / Partner / Build Stats / Equipped Memory Fragments frames are sized to data-driven maxima via font metrics over the entire captured roster, so switching combatants never resizes or shifts the layout. Partner fills the horizontal space to the right of Character (only its height is pinned, to match Character). Equipped Memory Fragments slot frames are individually static-sized (+20px wider, height reserves 2 wrap lines of set description + bottom padding) so long set descriptions wrap inside the fixed box rather than stretching it, and GS / Potential never clips.
  * **Combatants tab Build Stats** displays on two lines: GS + active set names + N Flex token on line 1; full stat list (ATK / DEF / HP / Crit% / CDMG% / Elem% / Extra% / DoT% / Ego) on line 2.
  * **Combatants list ~70px wider** (content-pane weight ratio shifted 1:2 → 5:8). Preset combobox width fixed to the label-text width at "Heidemarie". Combatant column trimmed to fit "Heidemarie" exactly.
  * **Memory Fragments tab set selector.** Set names and bracketed counts laid out as two grid columns per logical column — counts sit just past each column's own longest name (per-column alignment, never a column with counts stranded far right) and the brackets are right-aligned within their cell. "Highest GS / Potential: Assigned Presets Only" checkbox text spans two lines.
  * **Optimizer tab `Have at least` frame.** Right edge aligned with Set Configuration below; col 1 text at the LabelFrame's own left padding edge (matching the other config frames); col 1 label↔spinbox gap +5px; col 2 spinbox right-aligned within the frame; both spinboxes stay 4 chars wide.
  * **Set Configuration sets list.** 4-piece sets above 2-piece sets with a small vertical gap separating the two groups.
  * **`Not Enough Flex Slots` popup.** Message rewritten so the dialog is wide enough that the title ("Not Enough Flex Slots") no longer clips.
  * **Stat-label canonicalization on the Gear Score tab.** Stat Weight Configuration labels now go through `DISPLAY_NAMES` like the Optimizer / Memory Fragments tabs (`ATK Flat`, `Crit%`, `CDMG%`, `Extra%`, …). Spinboxes sit closer to their labels and the inter-column gap grew +5px.
- **Polish round 3 (round 9 iterations).** Final pass of UI refinements:
  * **Exclude Combatant's MFs converted to flow layout.** The fixed 8-column grid (every column scaled to the widest name "Heidemarie") replaced with a true flow layout: each row is its own frame, checkbuttons pack LEFT at their natural widths plus a 7px gap, and a new row starts when the next checkbutton wouldn't fit the remaining container width. Variable column widths per row, variable column count per row, debounced re-flow on `<Configure>`. Eliminates the wasted whitespace after shorter names.
  * **HAL note explaining threshold semantics.** A short reflowing note below the HAL grid: "Note: Input stats as you expect to see them in the in-game Combatants menu." Wraplength auto-updates on `<Configure>` so the note fills the HAL frame's content width and never clips. Avoids the previous ambiguity around whether CDmg/CRate thresholds include character base values (they do) and whether ATK/DEF/HP thresholds use Final vs inner values (inner — Partner% and Equipment excluded, matching in-game requirement checks).
  * **HAL frame finer geometry.** ipadx=10 widens the frame by 20px (the +20 transfers from Important Settings, which has expand=True and surrenders the space automatically). Col 1 label allocation widened by +1 char with no padx gap (anchor=W keeps the text left-aligned with the extra whitespace inside the label, spinbox flush against the label's right edge). Col 2 spinbox narrowed to 3 chars (its stats are %-bounded — 3 digits is enough). Cols container packs fill=tk.X with col 1 LEFT and col 2 RIGHT, so the +20px parks between the columns instead of pushing col 2 off its right alignment.
  * **Important Settings right-edge padding.** Slider readouts width 4 (was 5) + anchor=E so the visible text hugs the right edge symmetrically with the left. The last force-main checkbox drops its 8px right pad so the rightmost element sits flush with the frame's right padding edge (matching the left edge of the leading label).
  * **Memory Fragments "+Lv" column → "Level".** Column width 35 → 42; cell values changed from `f"+{f.level}"` to `f"{f.level}"` (the "+" prefix was redundant with the column being a level number).
  * **Selected Build slot column.** "+" prefix dropped from level values for consistency with the Memory Fragments tab; column width 101 → 94 to match the new content width.
  * **Heroes tab title row relocated.** The Character name (font 14 bold) + "Assign preset" dropdown group used to sit at the top of the detail panel (right column of content_pane). They now sit in user_frame's row 0 col 1, mirroring content_pane's weight=5/8 split below — so the right-side title group sits at the same Y as the user_info_label on the left, aligning visually with the top of the tab. Inside hero_detail_container, info_frame (Character + Partner) absorbs the vertical excess (fill=BOTH, expand=True); the Character LabelFrame keeps width-fixed but grows vertically (fill=Y); the Partner card grows both ways (fill=BOTH); Build Stats and Equipped MF frames sit at the bottom of the cavity naturally.
  * **Heroes tab Equipped MF frame final sizing.** Character frame +4px wider. Cells +12px wider (cell_w slack +20 → +32) and +10px taller (cell_h slack +40 → +50). PAD_W tightened 18 → 14 (-4 outer); PAD_H tightened 38 → 33 (-5 outer). Net outer: +20px wider, +25px taller. Build Stats frame gets +4px height slack so its second line doesn't clip after the PAD_H tightening.
  * **Optimizer tab initial-display layout-settling fix.** When the tab is first mapped, Tk used to run 2-3 layout passes in view of the user: col 2's exclude frame natural width started at 1 (its checkbutton content is built post-Map via a deferred `after(50ms)` callback in `_reflow_exclude_heroes`), and the grid re-balanced ~50ms after the tab painted — visibly shifting Important Settings, Set Configuration, and Selected Build leftward by ~56px and Exclude / Results the same to the right. Two-part fix: (1) a `<Map>` binding drains pending geometry idle events synchronously before the first paint, and (2) `exclude_heroes_frame.configure(width=694)` locks its requested width to the eventual flow-layout natural width, so col 2's minimum-size push is stable from creation rather than jumping 1 → 694 on the deferred reflow. The 694 is empirical to the current character roster at default window sizes and may need re-tuning if the roster grows substantially.
- **Optimizer Results score column normalized by per-character buff baseline.** Each displayed score is divided by `avg_card_dmg/100 * (1 + avg_mult_buff/100) + avg_add_buff/100` — a per-character constant identical for every build in that character's result list. Within a list, order and ratio gaps are preserved exactly. Across characters, the user-assumed external-buff inflation is divided out, so a low-scoring roster member genuinely reflects weaker MFs / sets rather than just lower assumed buffs (cross-character build-quality comparison becomes meaningful). Cross-character normalization is approximate when conditional DMG-multi / DMG-add set effects are active (those terms add into the multiplier rather than scaling it, so they don't fully cancel); within-list order and ratios remain exact regardless. The optimizer's RANKING is untouched — it still uses the real per-character settings for which builds win.

- **User-state folder renamed `presets/` → `settings/`** with all five user-state files moving together (`presets.json`, `character_preset.json`, `optimizer_settings.json`, `settings.json`, `level_data.json`). Bundled shipped defaults moved to a new sibling `default_settings/` folder. Existing installs migrate automatically on the first launch with this version — the user's files are renamed in place; no data lost.
- **`config.json` moved into `settings/`.** Previously at `<base>/config.json`; now at `<base>/settings/config.json`. The legacy location is moved automatically on first load, idempotent. Frozen-build path resolution also fixed — the previous code used `Path(__file__).parent`, which resolves into PyInstaller's read-only `_MEIPASS` and silently lost every save in frozen builds.
- **Combatant Preset Assignments storage rewritten to ID-keyed (v2 schema).** `character_preset.json` is now keyed by `res_id` (string), with a parallel `name_hints` dict for human-readable display names. The manager's API still accepts character names. Solves the captured-but-unknown → known transition: if you assigned a preset to a character captured as "1055" before they were added to `CHARACTERS` as "Adelheid", the assignment now stays put under id `1055` and only the cosmetic `name_hint` shifts when the character becomes known. v1 files migrate to v2 on first load (idempotent).
- **`OptimizerSettingsManager.load()` preserves unknown top-level keys** verbatim. Previously, anything beyond `version`/`excluded_gear_chars`/`characters` got silently dropped on load — which broke the round-trip of additive flags like `excluded_default_initialized`.

### Fixed

- **Duplicate placeholder keys in `partners.py` silently dropped a partner.** Clara, Bria, Janet, Marianne, and Scarlet (partners without known res_ids yet) all used overlapping negative dict keys (`-1`, `-1`, `-2`, `-3`, `-4`), so Python kept only the last entry per key and Clara was lost entirely. Renumbered to distinct keys (`-1` through `-5`). Verified `characters.py` and `partners.py` (both reordered by release date) have all-distinct keys and names.
- **Newly-released characters vanished when their gear was unequipped.** `_parse_character_data` skipped any captured character not yet in `characters.py` (its name resolved to "Unknown"), so such a character only appeared in the Combatants / Optimizer tabs via equipped gear and disappeared once unequipped. They now get a `CharacterInfo` keyed by their numeric res_id string (matching `get_character_name`), so they show up on capture and persist regardless of equipped gear.
- **Optimizer "Found N" progress counter jumped wildly.** The optimizer trims its in-flight results list periodically (keeping the top `max_results`), so the running count oscillated between `max_results` and ~10x that. The progress line no longer shows the running count — only search-space progress ("Checked X (Y%)"); the accurate final build count still appears when the run completes. (Note: results are capped at 100 builds, as before.)
- **Stale optimizer results after a fresh capture.** Loading new capture data now clears the Optimizer tab's results list, Results / Selected Build / Stats Comparison trees, and resets the progress label — the old result tuples referenced fragment objects from the previous capture.
- **Newly-released partners no longer show as character entries.** The capture snapshot lumps characters AND partner cards into one `characters.characters` roster array with no explicit type field. The previous logic used `partners.py` dict membership as the sole discriminator, so a partner without an entry yet (e.g. `30095`) would fall through and appear in the character list as a bare-res_id "Unknown". The classifier now combines four signals in precedence order: known character → known partner → instance-id referenced as some character's `partner_id` (catches equipped unknown partners — only characters equip partners, so anything a `partner_id` points at is definitionally a partner) → potential-node-data tie-break (characters carry a potential tree, partners don't), which catches owned-but-unequipped unknown partners too. A naive res_id range rule was deliberately avoided — some new characters also use 5-digit `30xxx` ids (they appear in character-only data like counseling / archive-gift / business-card showcase), so a range split would hide real characters.
- **Optimizer tab "Exclude Combatant's MFs" no longer blinks on combatant dropdown change.** Previously every Combatant-selector change tore down and rebuilt every checkbutton in the exclude panel just to update the strike-through / dim style on the previously-selected and newly-selected rows. Now there's a lighter "only the current marker changed" path that updates those two checkbuttons in place; the full rebuild only fires when the hero roster or excluded set actually changes.
- **Gear Score tab "How Gear Score Works" frame no longer flashes white on first load.** The internal frame and scrollbar of `scrolledtext.ScrolledText` defaulted to system white, briefly visible before the inner Text widget painted over it. Both now configured to the dark theme background at creation time. Same fix applied to the Setup tab's Setup Instructions frame.
- **Combatants tab load partially sped up.** `CharacterPresetManager._resolve_name_to_id` previously rebuilt the full `{character_name → res_id}` lookup table on every call — once per combatant per `refresh_heroes`. Now built lazily once per manager instance and cached. Removes ~30 redundant CHARACTERS scans per refresh.

### Removed

- **Optimizer tab: Stat Priority (-1 to 3) sliders** — replaced by per-character Important Settings. Priority-based scoring still lives in `optimizer.py` for backwards compatibility but is no longer driven from any UI; `recalculate_scores()` runs with all-zero priorities so the optimizer's slot pre-filter falls back to gear_score (the Scoring tab's preset GS).
- **Optimizer tab: Main Stats (Slots IV/V/VI) checkbox grid** — replaced by the force-main checkboxes in Important Settings (IV: HP, V: HP, VI: HP, VI: Ego) plus an internal heuristic in Phase 3 that picks the best Element DMG% / damage-related main stat per slot based on the character.
- **Optimizer tab: Top % Filter slider** — the top-fragments-per-slot filter is now an internal performance setting (currently 20% per slot, with no UI exposure). Phase 3+ may revisit if performance varies meaningfully with inventory size.
- **Optimizer tab: Include Equipped Items checkbox** — replaced by the per-character Exclude Combatant's Gear list. Equipped fragments are always available to the optimizer except those owned by characters in the exclude list. The current character's own equipped gear is always available.
- **Optimizer tab: Reset button** — each setting auto-persists per character now, so "reset" no longer has clear semantics (reset which character? reset to what?). The space is occupied by the new 3-line explanation text.
- *(unchanged from earlier)*

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