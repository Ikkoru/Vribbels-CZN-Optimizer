# Vribbels CZN Optimizer (Ikkoru)

A fork of Vribbels, a Fribbels-inspired gear management and optimization tool for the game **Chaos Zero Nightmare**. It reads your Memory Fragments from the game and works out the best six for a combatant. Features a **Pull Tracker** that shows your luck.

## Installation & Usage

You need Windows and the STOVE client.

1. Download the latest release from the [Releases page](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases).
2. Run `Vribbels_CZN_Optimizer_Ikkoru.exe` as Administrator.
3. Open the **Setup & Settings** tab and click **Generate & Install Cert**.
4. Open the **Capture** tab and click Start Capture.
5. Launch the game. Keep the program open: in-game changes are captured LIVE.

## Optimizing

The latest snapshot loads on startup. Pick a combatant, fill in **Important Settings** (optional), then press Start.

Most of the settings are self-explanatory. These are the ones that aren't:

- **The three damage sliders** — Extra, Agony and Fracture — how much of the combatant's damage is of that type. Fracture slider includes Scorched. Based on your deck, not damage numbers: add up the `DMG%/turn` of each type and take the fractions. Everything left over counts as Card damage.

  > Don't stress about getting these super accurate. Dealing 3 more damage per turn isn't going to save you from the Nightmare.

- **Have at Least** floors are measured the way the game's Potential 7 checks measure them, so clearing one here means clearing it in-game. Builds that miss any floor are dropped entirely.

- **Maximum Flex Slots** is how many of the six slots may sit outside the sets you ticked.

- **A conditional set's percentage** is how much of this combatant's damage actually benefits from that set's effect. At 0 the fragments still count for their stats and only the effect is ignored.

- **Exclude Combatant's MFs** starts with everyone excluded. Unticking someone lets the optimizer take the gear they are wearing. The combatant you are optimizing is never excluded from their own gear.

In the results, scores run 0–100 with the run's best build at 100. `(E)` marks the build you already equipped. `(F)` marks a set the flex slots completed by accident rather than one you picked — its bonus counts either way. Click a row to compare it against your current build; right-click that comparison for a full breakdown of where every number comes from.

## Other things worth knowing

- **Gear Score** weights are per-combatant presets. Assign them on the **Combatants** tab, edit the weights on the **Gear Score** tab.
- **Double-click** or select a preset and press Apply in the **Gear Score** tab to change the GS and Potential values in the **Memory Fragments** tab. Useful for finding good MFs to level and bad MFs to dismantle.
- **The optimizer uses every CPU core.** Change that with **Optimizer cores** in the **Setup & Settings** tab's Settings panel. It applies on the next launch.
- **Affinity, potential nodes and Partner bonuses** are all counted in the stats the optimizer scores.
- **The Combatants tab lists every potential node**, and its `Nodes` column is a combatant's node levels summed against the maximum.
- **The Materials tab** counts your promotion and levelling material by class, and your growth stones by Element. Each row's figures are that row's own holdings in bottom-tier equivalents, then what share that is of what a target costs.
- **The Checklist tab** shows what resets when — daily, weekly, monthly and seasonal — and what is left to do on each, updating while the game is captured. Tick or untick a shop's products to track only what you actually buy: the shop's heading then reads what you hold against what clearing it costs, and hovering it says what that currency earns in a rotation.
- **The Stats & Gacha History tab** keeps every pull the game has listed, which the game itself does for only about half a year, and says how lucky each banner type has been against the game's published rates. Open each banner's Probability Info → Rescue Records in game while capturing to add them. The history lives in `snapshots/gacha_history/`, apart from the captures, with a `.bak` of the previous version beside each file. Beside the pulls' figures, your Sortie, Great Rift and Full-Scale Offensive standings, a column per season; the note beside each list says what to open while capturing to fill it.

## Contributing

Bug reports, character and partner data corrections, and feature ideas are all welcome via GitHub Issues.

## Credits

Original by [Vorbroker](https://github.com/Vorbroker/Vribbels-CZN-Optimizer).

Inspired by [Fribbels Epic 7 Gear Optimizer](https://github.com/fribbels/Fribbels-Epic-7-Optimizer).

Thanks to [EpicSevenAssetRipper](https://github.com/CeciliaBot/EpicSevenAssetRipper) for asset extraction tools.

The Stats & Gacha History tab's pull history takes its idea from [hub-czn](https://github.com/sostenesfreitas/hub-czn)'s Rescue Records, and reads its Export JSON.

## License

MIT License — see [LICENSE](LICENSE) file for details.

Chaos Zero Nightmare and all related assets are property of their respective owners.

---

**Note**: This is a third-party tool and is not affiliated with or endorsed by the developers of Chaos Zero Nightmare.
