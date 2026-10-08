"""The Character card's widest line fits its panel at every UI scale.

The panel is a stated width that does not wrap (`CHAR_CONTENT_PX`), so a
line too wide for it is cut off with nothing to say so.
`check_tabs_build` holds the lines to it at 100%; above 100% the width
is grown with the text (`scaling.text_px`), by the most-grown of the
card's own line shapes (`CHAR_WIDE_LINES`). One mix of words grows
less than a line that is mostly digits, and the Affinity bonus line
clipped by a pixel at 125% when the panel was grown by such a mix.

Measured at each scale, against every line the tables can produce of
each shape: every combatant's details line, every Affinity level's
bonus, and every node's wording at the description stop.

**Each UI scale is measured in a process of its own**: Tk caches a font
given as a tuple per display rather than per interpreter, so a second
root in one process lays some text out at the first root's size.
"""

import json
import subprocess
import sys

from ._harness import add_source_to_path, REPO_ROOT, Skip

NAME = "the Character card's widest line fits at every scale"


def _measure(scale_name):
    """Every complaint at one UI scale. Run in a process of its own."""
    add_source_to_path()
    import tkinter as tk
    from tkinter import font as tkfont

    from ui import scaling
    scaling.set_scale(scale_name)
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    try:
        scaling.apply_font_scaling(root)
        from game_data.constants import FRIENDSHIP_BONUSES
        from ui.tabs.heroes_tab import (CHAR_NODE_TAB_DESC, CHAR_PANEL_BD,
                                        CHAR_TEXT_PADX, _char_panel_w)
        from checks.check_tabs_build import (_widest_details_line,
                                             _widest_node_wording)

        measure = tkfont.nametofont("TkDefaultFont").measure
        # The panel less its Text's inset and its border: what a line has.
        room = (_char_panel_w() - scaling.px(2 * CHAR_TEXT_PADX)
                - 2 * CHAR_PANEL_BD)
        bonus = max((f"  Bonus: ATK+{a}, DEF+{d}, HP+{h}"
                     for _level, a, d, h in FRIENDSHIP_BONUSES), key=measure)
        wording, wording_px = _widest_node_wording(measure)
        lines = [_widest_details_line(measure), (bonus, measure(bonus)),
                 (f"<description stop>{wording}",
                  scaling.text_px(CHAR_NODE_TAB_DESC) + wording_px)]
        return [
            f"At {scale_name} the Character card's line {line!r} is {width}px "
            f"against the {room}px `_char_panel_w` leaves a line, and clips. "
            f"Give CHAR_WIDE_LINES a line of this shape, so the panel grows "
            f"by what it grows by."
            for line, width in lines if width > room]
    finally:
        root.destroy()


def run():
    add_source_to_path()
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception as exc:                # noqa: BLE001
        raise Skip(f"Tk cannot open a display here ({exc})")
    from ui import scaling

    failures = []
    for scale_name in scaling.SCALE_CHOICES:
        done = subprocess.run(
            [sys.executable, "-m", __name__, scale_name], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        lines = done.stdout.strip().splitlines()
        if done.returncode != 0 or not lines:
            failures.append(
                f"Measuring the Character card at {scale_name} failed "
                f"(exit {done.returncode}): "
                f"{(done.stderr.strip() or done.stdout.strip())[-1200:]}")
            continue
        failures.extend(json.loads(lines[-1]))
    return failures


if __name__ == "__main__":
    print(json.dumps(_measure(sys.argv[1])))
