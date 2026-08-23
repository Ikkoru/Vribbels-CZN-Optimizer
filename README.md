# Vribbels CZN Optimizer (Ikkoru)

A fork of Vribbels, a Fribbels-inspired gear management and optimization tool for the mobile game **Chaos Zero Nightmare**. It reads your Memory Fragments from the game and works out the best six for a combatant.

## Installation

You need Windows and the STOVE client.

1. Download the latest release from the [Releases page](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases).
2. Run `Vribbels_CZN_Optimizer_Ikkoru.exe`.
3. Open the **Setup** tab and click **Generate & Install Cert**.

## Capturing your data

Run the program as Administrator, start the capture on the **Capture** tab, then launch the game and go to the main menu. Your data is saved next to the program in `snapshots/`, and changes you make in-game are picked up while the capture is running.

## Optimizing

The latest snapshot loads on startup. Pick a combatant, fill in **Important Settings** (optional), then press Start.

Most of the settings are self-explanatory. These are the ones that aren't:

- **The three damage sliders** — Extra, Agony and Fracture — are the share of the combatant's damage that comes from each. Fracture and Scorched share the one slider. Work them out from your deck rather than from damage numbers: add up the DMG% of each source per turn and take the fractions. Everything left over counts as ordinary card damage.

  > Don't stress about getting these super accurate. Dealing 3 more damage per turn isn't going to save you from the Nightmare.

- **Have at Least** floors are measured the way the game's Potential 7 checks measure them, so clearing one here means clearing it in-game. Builds that miss any floor are dropped entirely.

- **Maximum Flex Slots** is how many of the six slots may sit outside the sets you ticked.

- **A conditional set's percentage** is how much of this combatant's damage actually benefits from that set's effect. At 0 the fragments still count for their stats and only the effect is ignored.

- **Exclude Combatant's MFs** starts with everyone excluded. Unticking someone lets the optimizer take the gear they are wearing. The combatant you are optimizing is never excluded from their own gear.

In the results, scores run 0–100 with the run's best build at 100. `(E)` marks the build you already equipped. `(F)` marks a set the flex slots completed by accident rather than one you picked — its bonus counts either way. Click a row to compare it against your current build; right-click that comparison for a full breakdown of where every number comes from.

## Other things worth knowing

- **Gear Score** weights are per-combatant presets. Assign them on the **Combatants** tab, edit the weights on the **Gear Score** tab.
- **Double-click** or select a preset and press Apply in the **Gear Score** tab to change the GS and Potetial values in the **Memory Fragments** tab. Useful for finding good MFs to level and bad MFs to dismantle.
- **The optimizer uses every CPU core.** If that causes trouble, close the program and change `optimizer_workers` in `settings/settings.json`.
- **Affinity, potential nodes and Partner bonuses** are all counted in the stats the optimizer scores.

## Contributing

Bug reports, character and partner data corrections, and feature ideas are all welcome via GitHub Issues.

## Credits

Original by [Vorbroker](https://github.com/Vorbroker/Vribbels-CZN-Optimizer).

Inspired by [Fribbels Epic 7 Gear Optimizer](https://github.com/fribbels/Fribbels-Epic-7-Optimizer).

Thanks to [EpicSevenAssetRipper](https://github.com/CeciliaBot/EpicSevenAssetRipper) for asset extraction tools.

## Support

Currently not accepting donations.

## License

MIT License — see [LICENSE](LICENSE) file for details.

Chaos Zero Nightmare and all related assets are property of their respective owners.

---

**Note**: This is a third-party tool and is not affiliated with or endorsed by the developers of Chaos Zero Nightmare.
