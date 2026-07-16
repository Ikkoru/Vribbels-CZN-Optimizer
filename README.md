# Vribbels CZN Optimizer (Ikkoru)

A fork of Vribbels, a Fribbels-inspired gear management and optimization tool for the mobile game **Chaos Zero Nightmare**. This tool helps you optimize your Memory Fragments to maximize your combatants' performance.

## Features

### Memory Fragment Optimizer

- **Smart Build Optimization**: Automatically finds the best Memory Fragment combinations for your characters.
- **Damage-Model Scoring**: Builds are scored using your per-combatant assumptions — Extra DMG / DoT shares, ATK/DEF split, shielding/healing weight, set-effect uptime, and average card damage / buffs. Every build is scored 0–100 against the best one found in the run. Comes with preset defaults.
- **Multi-Core Search**: Tune or switch off via `optimizer_workers` in `settings/config.json` (only if the automatic setting doesn't work for you).
- **Set Configuration**: Pick the sets you want and cap off-set slots with Maximum Flex Slots.
- **Have-at-Least Minimums**: Hard stat floors — builds that don't meet them are excluded. Measured the way the game's Potential 7 requirement checks measure them, so clearing a floor here means clearing it in-game.
- **Gear Score Calculation**: Evaluates fragments based on substats and potential, using per-combatant weight presets.

### Inventory Management

- **Memory Fragments Tab**: View and filter all your equipped and unequipped fragments.
- **Materials Tab**: Track your growth stone inventory.
- **Combatants Tab**: View all characters with levels, gear scores, and stats.

### Data Capture

- **Integrated mitmproxy Setup**: Built-in proxy configuration for capturing game data.
- **Automatic Data Extraction**: Captures Memory Fragments, character data, and inventory.
- **One-Click Capture**: Simple interface for extracting data from the game.

### Other Features

- **Friendship Bonus Tracking**: Accounts for character friendship stats.
- **Multi-Build Comparison**: Compare current vs. optimized builds side-by-side.

## Installation

### Requirements

- Windows.
- STOVE Client.

### Quick Start

1. Download the latest release from the [Releases page](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases).
2. Run `Vribbels_CZN_Optimizer_Ikkoru.exe`.
3. Navigate to the **Setup** tab and click **Generate & Install Cert**.

## Usage

### Capturing Game Data

1. Launch the application (run as Administrator on Windows for capture functionality).
2. Navigate to the **Capture** tab.
3. Click **"Start Capture"**.
4. Launch Chaos Zero Nightmare and navigate to the main menu.
5. In-game changes will be automatically tracked by the program.
6. Your data will be saved to `snapshots/memory_fragments_[timestamp].json` (next to the program).

### Optimizing Builds

1. Launch the app — the latest capture snapshot loads automatically (live captures refresh it while running).
2. Select a combatant from the dropdown — its assigned Gear Score preset is shown below it (assign presets in the **Combatants** tab; edit preset weights in the **Gear Score** tab).
3. Adjust the **Important Settings** to describe how the combatant deals damage: Extra DMG% / DoT% shares, ATK/DEF split, shielding/healing weight, and (optionally) force HP or Ego main stats on slots IV–VI.
4. Optionally set **Have at Least** minimums — builds that don't meet all of them are excluded.
5. Tick the sets you want under **Set Configuration**, set **Maximum Flex Slots** (how many of the 6 slots may sit outside your chosen sets), and fill in the set-effect uptime and (optionally) average card damage / buff assumptions.
6. Optionally untick combatants under **Exclude Combatant's MFs** to let the optimizer consider their equipped gear (all are excluded by default; the selected combatant's own gear is always available).
7. Click **"Start"** to begin optimization.
8. Review results — Scores are 0–100 with the run's best build at 100, and the build you already have equipped (when it makes the list) is tagged `(E)`. Select a row to compare stats side-by-side and see the required Memory Fragments; right-click the stats comparison for a full per-source breakdown.

### Viewing Materials

Navigate to the **Materials** tab to see your growth stone inventory.

## Contributing

Contributions are welcome! Feel free to:

- Report bugs via GitHub Issues.
- Submit character/partner data updates.
- Suggest new features.
- Improve documentation.

## Credits

Original by [Vorbroker](https://github.com/Vorbroker/Vribbels-CZN-Optimizer).

Inspired by [Fribbels Epic 7 Gear Optimizer](https://github.com/fribbels/Fribbels-Epic-7-Optimizer).

Thanks to [EpicSevenAssetRipper](https://github.com/CeciliaBot/EpicSevenAssetRipper) for asset extraction tools.

## Support

Currently not accepting donations.

You can send the original creator a thank you donation on [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/H2H21PHYKW) if you wish.

## License

MIT License - see [LICENSE](LICENSE) file for details.

Chaos Zero Nightmare and all related assets are property of their respective owners.

---

**Note**: This is a third-party tool and is not affiliated with or endorsed by the developers of Chaos Zero Nightmare.
