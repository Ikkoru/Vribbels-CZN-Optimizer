"""The Character card is exactly as wide as its widest line, at every
UI scale.

The panel's width is `char_content_px`: arithmetic over every line the
tables can produce -- each stop plus what follows it, each plain line
measured -- and the Text inside does not wrap. Arithmetic that comes
out SHORT clips that line mid-word with nothing to say so; arithmetic
that comes out LONG leaves the panel wider than the rule's distance to
its text.

So each of those lines is RENDERED, in a Text ruled the way the card is
(`rule_card_text`), and the widest has to land on `char_content_px` to
the pixel: every heading, every Affinity level's bonus, every set name,
the placeholders, a stat row, and a node row carrying the widest
wording any combatant's node has.

**Each UI scale is measured in a process of its own**: Tk caches a font
given as a tuple per display rather than per interpreter, so a second
root in one process lays some text out at the first root's size.
"""

import json
import subprocess
import sys

from ._harness import add_source_to_path, REPO_ROOT, Skip

NAME = "the Character card is as wide as its widest line at every scale"


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
        from ui.tabs.heroes_tab import (
            CHAR_NODE_TAG, CHAR_NODE_TAKEN, CHAR_SUBLIST_INDENT,
            char_card_plain_lines, char_content_px, rule_card_text,
            widest_node_wording)

        font = tkfont.nametofont("TkDefaultFont")
        text = tk.Text(root, wrap=tk.NONE, font=font, bd=0, padx=0,
                       highlightthickness=0)
        text.pack()
        rule_card_text(text, font)
        wording, _ = widest_node_wording(font.measure)
        lines = [(line, ()) for line in sorted(char_card_plain_lines())]
        lines.append((f"{CHAR_SUBLIST_INDENT}ATK\t1340\tCrit%\t67.2%", ()))
        lines.append((f"{CHAR_SUBLIST_INDENT}Node 5.1:\t{CHAR_NODE_TAKEN}"
                      f"\t{wording}", (CHAR_NODE_TAG,)))
        for line, tags in lines:
            text.insert(tk.END, line, tags)
            text.insert(tk.END, "\n")
        root.update_idletasks()

        rendered = []
        for number, (line, _tags) in enumerate(lines, start=1):
            got = text.count(f"{number}.0", f"{number}.end", "xpixels")
            rendered.append(((got[0] if isinstance(got, tuple) else got) or 0,
                             line))
        widest, which = max(rendered)
        room = char_content_px(font)
        if widest > room:
            return [f"At {scale_name} the Character card's line {which!r} "
                    f"renders {widest}px against the {room}px "
                    f"`char_content_px` sizes the panel for, and clips. The "
                    f"arithmetic there has missed how this line is laid out."]
        if widest < room:
            return [f"At {scale_name} `char_content_px` sizes the Character "
                    f"card for {room}px, and its widest line ({which!r}) "
                    f"renders {widest}px: the panel is wider than its text "
                    f"by the difference."]
        return []
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
