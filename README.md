# Vribbels CZN Optimizer (Ikkoru)

A fork of Vribbels, a Fribbels-inspired gear management and optimization tool for the mobile game **Chaos Zero Nightmare**. This tool helps you optimize your Memory Fragments to maximize your combatants' performance.

## Features

### Memory Fragment Optimizer
- **Smart Build Optimization**: Automatically finds the best Memory Fragment combinations for your characters
- **Stat Priority Weighting**: Customize stat priorities to match your build goals
- **Set Bonus Support**: Filter by 2-piece and 4-piece set bonuses
- **Gear Score Calculation**: Evaluates fragments based on substats and potential
- **Top X% Filtering**: Reduce search time by focusing on the best fragments

### Inventory Management
- **Memory Fragments Tab**: View and filter all your equipped and unequipped fragments
- **Materials Tab**: Track your growth stone inventory
- **Combatants Tab**: View all characters with levels, gear scores, and stats

### Data Capture
- **Integrated mitmproxy Setup**: Built-in proxy configuration for capturing game data
- **Automatic Data Extraction**: Captures Memory Fragments, character data, and inventory
- **One-Click Capture**: Simple interface for extracting data from the game

### Advanced Features
- **Potential Node Calculation**: Includes character progression bonuses
- **Partner Card Integration**: Calculates partner passive stat bonuses
- **Friendship Bonus Tracking**: Accounts for character friendship stats
- **Multi-Build Comparison**: Compare current vs. optimized builds side-by-side

## Installation

### Requirements
- Windows
- STOVE Client

### Quick Start

1. Download the latest release from the [Releases page](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases)
2. Run `Vribbels_CZN_Optimizer.exe`
3. Navigate to the **Setup** tab and click **Generate & Install Cert**

## Usage

### Capturing Game Data

1. Launch the application (run as Administrator on Windows for capture functionality)
2. Navigate to the **Capture** tab
3. Click **"Start Capture"**
4. Launch Chaos Zero Nightmare and navigate to the main menu
5. Click **"Stop Capture"**
6. Your data will be saved to `Vribbels/captures/memory_fragments_[timestamp].json`

### Optimizing Builds

1. Click **"Load Data"** and select your capture file
2. Select a combatant from the dropdown
3. Adjust **Stat Priorities** using the sliders (higher values = more important)
4. Select desired **Set Bonuses** (4-piece and/or 2-piece)
5. Choose **Main Stats** for slots 4, 5, and 6
6. Adjust **Top %** to control search space (lower = faster, fewer combinations)
7. Click **"Start"** to begin optimization
8. Review results showing stat improvements and required gear swaps

### Viewing Materials

Navigate to the **Materials** tab to see your growth stone inventory.

## Contributing

Contributions are welcome! Feel free to:
- Report bugs via GitHub Issues
- Submit character/partner data updates
- Suggest new features
- Improve documentation

## Credits

Original by [Vorbroker](https://github.com/Vorbroker/Vribbels-CZN-Optimizer)

Inspired by [Fribbels Epic 7 Gear Optimizer](https://github.com/fribbels/Fribbels-Epic-7-Optimizer)

Thanks to [EpicSevenAssetRipper](https://github.com/CeciliaBot/EpicSevenAssetRipper) for asset extraction tools

## Support

Currently not accepting donations.

You can send the original creator a thank you donation on [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/H2H21PHYKW) if you wish.

## License

MIT License - see [LICENSE](LICENSE) file for details.

Chaos Zero Nightmare and all related assets are property of their respective owners.

---

**Note**: This is a third-party tool and is not affiliated with or endorsed by the developers of Chaos Zero Nightmare.
