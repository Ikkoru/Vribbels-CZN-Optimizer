"""An Upgraded line says when a fragment beats what a combatant wears.

A preset's ceiling goes in the Mythic colour when the upgraded fragment,
at `MYTHIC_FROM_LEVEL` or past it, would score higher under that preset
than what the preset's ONE combatant wears in the same slot. Each rule
has a way to go wrong without anyone noticing -- a colour that is
simply absent, or present where it means nothing:

  * a preset on two combatants has no one wearer to compare with;
  * the combatant wearing THIS fragment is not beaten by it;
  * an empty slot marks nothing -- a combatant with nothing on is not
    in use, and every line would light up for every such combatant;
  * the comparison is between the numbers the line PRINTS, so a
    ceiling one decimal higher that prints the same is no find;
  * below the level, nothing is weighed at all.

`_beats_equipped` is the main window's, called here on a stand-in with
just the attributes it reads, and the scoring functions it calls are
replaced by a table -- the scoring is the Memory Fragments tab's, and
held elsewhere. What is held here is who is compared with what.
"""

from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "Upgraded line marks what beats the equipped"

SLOT = 4


def _fragment(fid, char=0, slot=SLOT, level=0):
    return SimpleNamespace(id=fid, equipped_char_id=char, slot_num=slot,
                           level=level, main_stat=SimpleNamespace(name="ATK%"))


def run():
    add_source_to_path()
    import czn_optimizer_gui as gui

    upgraded = _fragment(1, char=105, level=3)
    worn = [
        _fragment(2, char=101),                  # Solo wears 80.4
        _fragment(3, char=106),                  # Close wears 80.6
        _fragment(4, char=104, slot=SLOT - 1),   # Empty: another slot only
        upgraded,                                # Self wears the new one
        _fragment(5, char=102), _fragment(6, char=103),  # Shared
    ]
    ceilings = {2: 80.4, 3: 80.6, 4: 99.0, 5: 10.0, 6: 10.0, 1: 81.0}
    window = SimpleNamespace(
        optimizer=SimpleNamespace(fragments=worn),
        preset_manager=SimpleNamespace(get_preset=lambda name: {}),
        character_preset_manager=SimpleNamespace(assignments_by_id={
            "101": "Solo", "106": "Close", "104": "Empty",
            "105": "Self", "102": "Shared", "103": "Shared"}))
    scored = [(40.0, 81.0, name) for name in
              ("Solo", "Close", "Empty", "Self", "Shared", "Nobody")]

    saved = gui.compute_gs_bounds, gui.compute_fragment_potential
    gui.compute_gs_bounds = lambda weights, exclude_stat=None: (0, 1)
    gui.compute_fragment_potential = (
        lambda fragment, weights, bounds: (0.0, ceilings[fragment.id]))
    try:
        got = gui.OptimizerGUI._beats_equipped(window, upgraded, scored)
        upgraded.level = gui.MYTHIC_FROM_LEVEL - 1
        below = gui.OptimizerGUI._beats_equipped(window, upgraded, scored)
    finally:
        gui.compute_gs_bounds, gui.compute_fragment_potential = saved

    failures = []
    want = {"Solo"}
    if got != want:
        failures.append(
            f"a +{gui.MYTHIC_FROM_LEVEL} fragment reaching 81 is marked as "
            f"beating the wearers of {sorted(got)}, not {sorted(want)}: "
            f"`Solo` wears 80; `Empty` wears nothing in the slot; `Close` "
            f"wears 80.6, which prints as 81; `Self` wears this very "
            f"fragment; `Shared` has two combatants; `Nobody` has none.")
    if below:
        failures.append(
            f"a fragment below +{gui.MYTHIC_FROM_LEVEL} is marked as "
            f"beating {sorted(below)}. Nothing is weighed that early.")
    return failures
