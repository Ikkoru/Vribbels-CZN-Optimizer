"""At 200% the pixels Tk does not scale are scaled by the app.

`tk scaling` reaches sizes given in points and nothing given in pixels,
so the theme's own borders and padding and a classic widget's defaults
stay their 100% size at 200%: every label 4px short of twice its height,
every button's text nearer its border. `ui/scaling.py` restates them --
`scale_theme` for the clam styles, `apply_font_scaling` for the classic
widgets' option defaults -- and at 100% does nothing at all, which is
what keeps the 100% layout from moving.

Each scale is built in a process of its own: a font resolves its size
once per display, so two scales in one process measure one of them
wrong.
"""

import json
import subprocess
import sys

from ._harness import SOURCE_ROOT, Skip

NAME = "Tk's unscaled pixels are scaled at 200%"

# The style options that hold distances in pixels, read off every style
# the theme knows once the app has configured it -- the app's own
# derived styles included. One the app set without `px` stays its 100%
# size at 200%, and nothing else notices: the widget still draws.
PIXEL_OPTIONS = ("padding", "labelmargins", "tabmargins", "focusthickness",
                 "arrowsize", "sliderlength", "indicatormargin",
                 "indicatorsize", "sashthickness", "indent")

PROBE = r"""
import json, sys
from types import SimpleNamespace
sys.path.insert(0, ".")
from ui import scaling
scaling.set_scale(sys.argv[1])
PIXEL_OPTIONS = json.loads(sys.argv[2])
import tkinter as tk
from tkinter import ttk
root = tk.Tk()
root.withdraw()
scaling.apply_font_scaling(root)
style = ttk.Style()
style.theme_use("clam")
import czn_optimizer_gui as gui
gui.OptimizerGUI.configure_styles(SimpleNamespace(
    style=style, colors=dict(gui.COLORS)))
theme = {f"{name}.{opt}": str(style.configure(name, opt))
         for name, opts in scaling.THEME_PIXELS.items() for opt in opts}
classic = {}
for cls, opts in scaling.CLASSIC_PIXELS.items():
    widget = getattr(tk, cls)(root)
    for opt in opts:
        classic[f"{cls}.{opt}"] = str(widget.cget(opt.lower()))
styles = {}
for name in root.tk.splitlist(root.tk.call("ttk::style", "theme",
                                           "styles", "clam")):
    for opt, value in (style.configure(name) or {}).items():
        if value not in (None, ""):
            styles[f"{name}.{opt}"] = str(value)
    for opt, entries in (style.map(name) or {}).items():
        if opt in PIXEL_OPTIONS:
            for n, entry in enumerate(entries):
                styles[f"{name}.map.{opt}.{n}"] = str(entry[-1])
print(json.dumps({"theme": theme, "classic": classic, "styles": styles,
                  "tables": [scaling.THEME_PIXELS, scaling.CLASSIC_PIXELS]}))
root.destroy()
"""


def _read(scale):
    run = subprocess.run([sys.executable, "-c", PROBE, scale,
                          json.dumps(PIXEL_OPTIONS)],
                         cwd=str(SOURCE_ROOT), capture_output=True,
                         text=True, stdin=subprocess.DEVNULL, timeout=120)
    if run.returncode:
        tail = (run.stderr.strip().splitlines() or ["?"])[-1]
        if "TclError" in tail and "display" in tail:
            raise Skip(f"Tk will not start here ({tail})")
        return None, tail
    return json.loads(run.stdout.strip().splitlines()[-1]), ""


def run():
    low, err = _read("100%")
    if low is None:
        return [f"building the styles at 100% raised: {err}"]
    high, err = _read("200%")
    if high is None:
        return [f"building the styles at 200% raised: {err}"]
    theme, classic = high["tables"]
    out = []
    for name, opts in theme.items():
        for opt, value in opts.items():
            key = f"{name}.{opt}"
            if high["theme"][key] != str(value * 2):
                out.append(
                    f"at 200% the {key} of the theme reads "
                    f"{high['theme'][key]!r}, not {value * 2}: it stays its "
                    f"100% size and every widget of that class sits that "
                    f"much tighter than twice its 100% layout. See "
                    f"`ui/scaling.py` THEME_PIXELS.")
            if low["theme"][key] == str(value * 2):
                out.append(f"at 100% the {key} reads doubled: the 100% "
                           f"layout moved")
    for cls, opts in classic.items():
        for opt, value in opts.items():
            key = f"{cls}.{opt}"
            if high["classic"][key] != str(value * 2):
                out.append(
                    f"at 200% a classic {cls}'s {opt} defaults to "
                    f"{high['classic'][key]}, not {value * 2}: it stays its "
                    f"100% size. See `ui/scaling.py` CLASSIC_PIXELS.")
            if low["classic"][key] != str(value):
                out.append(f"at 100% a classic {cls}'s {opt} defaults to "
                           f"{low['classic'][key]}, not Tk's own {value}: the "
                           f"table no longer says what Tk does, or the 100% "
                           f"layout moved")
    for key, was in sorted(low["styles"].items()):
        # A distance: a pixel option, or anything the theme gives in
        # points. Every other option is a colour, a count or a width in
        # characters, and doubles nothing.
        option = key.split(".map.")[-1].split(".")[0] if ".map." in key \
            else key.rsplit(".", 1)[1]
        if option not in PIXEL_OPTIONS and not any(
                part.endswith("p") for part in was.split()):
            continue
        now = high["styles"].get(key)
        one, two = _pixels(was), _pixels(now)
        if one is None:
            continue                     # not a distance at all
        if two != [2 * value for value in one]:
            out.append(f"at 200% the style option {key} reads {now!r} "
                       f"where 100% reads {was!r}: not twice it, so "
                       f"everything it spaces sits off its 100% distance "
                       f"doubled. A pixel value takes `px`; one in points "
                       f"is restated by `scaling.scale_theme`, `tk "
                       f"scaling` being set for the fonts at 200%.")
    return out


def _pixels(value):
    """`value`'s components in pixels, points converted as Tk does at
    100%, or None when any part is neither."""
    out = []
    for part in str(value).replace("{", " ").replace("}", " ").split():
        try:
            out.append(round(float(part[:-1]) * 96 / 72)
                       if part.endswith("p") else int(part))
        except ValueError:
            return None
    return out or None
