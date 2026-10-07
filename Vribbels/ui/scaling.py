"""How large the program draws itself, and what Windows is told about it.

Two separate things, and both have to be right or the window is wrong on
a high-DPI screen.

**What Windows is told depends on the SCALE.** Undeclared, every window
is drawn at 96dpi and bitmap-stretched onto any scaled monitor -- soft
everywhere, including the one the program is developed on. Declared, it
is drawn in real device pixels.

Which declaration is right is not the same at both scales, and
`declare_dpi_awareness` is where that is argued: SYSTEM awareness at
100%, so the window keeps one physical size and a drag resizes
nothing; PER-MONITOR at 200%, so Windows does not double text this
program has already doubled.

**Tk does not adapt to per-monitor DPI**, in any version. It reports one
scaling for every screen and does not follow a window dragged between
them, so nothing here reads the monitor: the factor is the user's
setting and applies wherever the window is.

Two levers cover the whole app between them:

* `apply_font_scaling` sets Tk's point-to-pixel ratio, which carries
  every font -- and with them everything this app COMPUTES from font
  metrics, which is most of its layout.
* `px` carries what is left: the hardcoded distances.

**`px` goes on the geometry call, never on the constant.** A distance
built from parts (`label + gap + value`) has to be scaled once at the
end rather than per part -- scaling each addend rounds each one, and
the sum lands somewhere the single scaling does not. At 200% nothing
rounds, so today the rule costs nothing and buys the fractional steps
`tasks.md` T15 describes.

**A MEASURED distance must not go through `px` at all.** Anything read
off a font -- `font.measure(...)`, `winfo_reqheight()`, a Text's
`dlineinfo`, the width a `<Configure>` event carries -- has already
grown with the font scaling, and wrapping it scales it a second time. A
pad mixing the two takes `px` on its hardcoded part alone:
`px(INSET) + indent`, never `px(INSET + indent)`.
`checks/check_ui_scales.py` catches both halves of this, a pad that did
not grow and one that grew twice, and a wraplength worked out from an
event's width.

**The spacing audit reads both scales**, holding every gap at 200% to
exactly twice its 100% target (`spacing_audit.scaled`); an audit run
picks its scale with `--audit-scale` rather than through `set_scale`'s
saved setting (`audit_states.requested_scale`).
"""

import ctypes

# What the dropdown offers, and what each is worth. 200% is the only
# whole multiple: every pixel doubles with no remainder, and the icon
# assets double by nearest neighbour without a resample. See T15 for
# why the fractional steps are not here.
SCALE_CHOICES = ("100%", "200%")
DEFAULT_SCALE = "100%"

# The window a fresh launch opens, and the smallest it may be
# dragged to. At 100%, in device pixels -- `px` is what puts them
# at the active scale. Here rather than in the GUI module because
# the Setup & Settings tab's `Window Size` button restores the same number
# and two copies of it would drift.
WINDOW_W, WINDOW_H = 1550, 1000
WINDOW_MIN_W, WINDOW_MIN_H = 1300, 800

# Tk states font sizes in POINTS and Windows draws in pixels at 96 to
# the inch. That ratio is what `tk scaling` holds.
POINTS_TO_PIXELS = 96 / 72

# Set once, before any widget exists. A module-level factor is what
# lets `px` be reached from every call site in the app without
# threading a settings object through all of them; the cost is that it
# MUST be set before the first widget is built, because a widget takes
# its padding at construction and nothing revisits it.
_factor = 1


def parse(word):
    """The factor a choice word is worth: `200%` -> 2.

    Anything unrecognised is 1: a settings file carrying a scale this
    build does not offer draws at the size everything is measured at
    rather than stopping the launch.
    """
    try:
        return max(1, int(str(word).strip().rstrip("%")) // 100)
    except (TypeError, ValueError):
        return 1


def set_scale(word):
    """Fix the factor for this run. Call before building any widget."""
    global _factor
    _factor = parse(word)
    return _factor


def factor():
    """The active factor: 1 at 100%, 2 at 200%."""
    return _factor


def px(distance):
    """`distance` in device pixels at the active scale.

    Takes a number or a tuple or list of them, because half the
    distances in this app are `padx=(left, right)` pairs and a wrapper
    that only took scalars would need the pair pulled apart at every one
    of those call sites.

    A list is NOT a scalar here, though `*` takes one: `[10, 5] * 2` is
    `[10, 5, 10, 5]`, which a ttk `padding` reads as four sides at their
    100% values -- unscaled, and no error anywhere.

    Put this on the geometry call and not on the constant -- see the
    module docstring.
    """
    if isinstance(distance, (tuple, list)):
        return type(distance)(value * _factor for value in distance)
    return distance * _factor


# What each scale asks Windows for. PROCESS_SYSTEM_DPI_AWARE is 1 and
# PROCESS_PER_MONITOR_DPI_AWARE is 2; see `declare_dpi_awareness` for
# why the choice follows the scale.
AWARENESS_BY_FACTOR = {1: (1, "system"), 2: (2, "per-monitor")}


def declare_dpi_awareness():
    """Tell Windows how much of the scaling this process is doing.

    **The answer depends on the UI scale**, because the two available
    ones each get one thing right and Tk cannot bridge them: it follows
    no per-monitor DPI in any version, so a window dragged between
    screens keeps whatever metrics it was built with.

    * At 100% -- SYSTEM awareness. Windows bitmap-scales the window on
      a screen whose DPI differs from the system's, so it keeps ONE
      PHYSICAL SIZE everywhere and is crisp at the system DPI. It
      sends no `WM_DPICHANGED` and resizes nothing, which is what
      stops a drag from doubling the window.
    * At 200% -- PER-MONITOR awareness. The text is already doubled by
      this program, and a system-aware window would have Windows
      double it AGAIN on a 200% screen. Per-monitor awareness turns
      that second scaling off. The cost is the `WM_DPICHANGED` that
      comes with it: a drag across a DPI boundary resizes the window's
      frame, which no cheap mechanism refuses -- a poll that puts the
      size back gets it re-applied and the two oscillate.

    Before Tk opens its connection, and after `set_scale`: awareness is
    a property of the PROCESS and the first window fixes it. Failing is
    not fatal -- the program then draws the way it always did -- so this
    reports rather than raises.

    Returns what happened, for the caller to log.
    """
    level, word = AWARENESS_BY_FACTOR.get(_factor, (1, "system"))
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(level)
        return word
    except Exception as exc:            # noqa: BLE001 -- not Windows, or refused
        return f"not declared ({exc})"


def apply_font_scaling(root):
    """Scale every font by the active factor, and the classic widgets'
    own pixel defaults with them (`CLASSIC_PIXELS`).

    Tk sizes a font from its POINT size and this ratio, so one call
    carries all of them -- and with them every distance the app derives
    from a font metric. Call before the first widget is built: a widget
    resolves its font, and its defaults, once.
    """
    root.tk.call("tk", "scaling", POINTS_TO_PIXELS * _factor)
    if _factor == 1:
        return
    for widget_class, options in CLASSIC_PIXELS.items():
        for option, value in options.items():
            # The lowest priority there is: an option a widget is given
            # outright, already through `px`, always wins.
            root.option_add(f"*{widget_class}.{option}", value * _factor,
                            "widgetDefault")


# **What Tk itself does not scale.** `tk scaling` reaches every size
# given in POINTS -- the fonts, and theme metrics clam states in points
# (`10.5p`) -- and nothing given in pixels. These are the pixel ones the
# app's widgets carry without saying so, as their 100% values. Left
# alone, each stays its 100% size at 200%: every label 4px short of
# twice its height, every button's text 1px nearer its border.
#
# A classic widget draws its border as thick as `bd` says, so its
# defaults all double here.
CLASSIC_PIXELS = {
    "Entry": {"borderWidth": 1, "insertWidth": 2},
    "Spinbox": {"borderWidth": 1, "insertWidth": 2},
    "Text": {"borderWidth": 1, "padX": 1, "padY": 1, "insertWidth": 2},
    "Button": {"borderWidth": 2, "highlightThickness": 1, "padX": 1,
               "padY": 1},
    "Label": {"borderWidth": 2, "padX": 1, "padY": 1},
    "Listbox": {"borderWidth": 1, "highlightThickness": 1},
    "Canvas": {"highlightThickness": 2},
}
# **A clam element draws its border 2px whatever `borderwidth` says** --
# a panel's, a button's, a combobox field's, measured at both scales --
# and `borderwidth` only reserves room inside the line. Doubling it puts
# 2px of nothing between line and content, so the borders keep their
# 100% values, the reserve equal to the line, and only what sits INSIDE
# the line doubles: then every distance from a border's inner edge is
# twice its 100% one. The line itself staying 2px is the theme's limit.
#
# A label's border is blank room, drawn as nothing, and doubles like
# any distance. It is clam's border ELEMENT default, 2 -- the style
# holds nothing -- and the label's padding is 0, so a label given a
# padding of its own keeps the full 2px of border on each side.
THEME_PIXELS = {
    "TLabel": {"borderwidth": 2},
    "TButton": {"focusthickness": 1},
    "TCombobox": {"padding": 1},
    "TEntry": {"padding": 1},
}


def scale_theme(style):
    """Restate `THEME_PIXELS` at the factor wherever a style still holds
    its 100% value, or none. Call after the app's styles are configured:
    an option the app set through `px` already reads scaled and is left
    be, where one it set to the bare 100% number is scaled like the
    theme's own. Nothing at 100%."""
    # Imported here: this module is read before the `ui` package that
    # holds the guard can be.
    from ui.utils.style_once import first_time
    if _factor == 1 or not first_time(style, "scale_theme"):
        return
    for name, options in THEME_PIXELS.items():
        for option, value in options.items():
            held = style.configure(name, option)
            if str(held if held is not None else "").strip() in ("",
                                                                  str(value)):
                style.configure(name, **{option: value * _factor})
