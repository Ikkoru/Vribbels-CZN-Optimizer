"""How large the program draws itself, and what Windows is told about it.

Two separate things, and both have to be right or the window is wrong on
a high-DPI screen.

**What Windows is told depends on the SCALE.** Undeclared, every window
is drawn at 96dpi and bitmap-stretched onto any scaled monitor -- soft
everywhere, including the one the program is developed on. Declared, it
is drawn in real device pixels.

Which declaration is right is not the same at every scale, and
`declare_dpi_awareness` is where that is argued: SYSTEM awareness at
100%, so the window keeps one physical size and a drag resizes
nothing; PER-MONITOR above it, so Windows does not scale text this
program has already scaled.

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
rounds; at 125% a 4 becomes exactly 5 while a 5 becomes 6, so two gaps
that stood in a fixed relation drift a pixel apart wherever a sum was
scaled part by part.

**A MEASURED distance must not go through `px` at all.** Anything read
off a font -- `font.measure(...)`, `winfo_reqheight()`, a Text's
`dlineinfo`, the width a `<Configure>` event carries -- has already
grown with the font scaling, and wrapping it scales it a second time. A
pad mixing the two takes `px` on its hardcoded part alone:
`px(INSET) + indent`, never `px(INSET + indent)`.
`checks/check_ui_scales.py` catches both halves of this, a pad that did
not grow and one that grew twice, and a wraplength worked out from an
event's width.

**The spacing audit reads every scale**, holding each gap to its 100%
target times the scale, rounded as `px` rounds (`spacing_audit.scaled`);
an audit run picks its scale with `--audit-scale` rather than through
`set_scale`'s saved setting (`audit_states.requested_scale`).
"""

import ctypes
import math

# What the dropdown offers, and what each is worth. 200% is the one
# whole multiple: every pixel doubles with no remainder, and the icon
# assets double by nearest neighbour without a resample. Between it and
# 100%, every distance rounds to a whole pixel (`px`), and the icons
# are resampled (`image_utils._resample`).
SCALE_CHOICES = ("100%", "125%", "150%", "175%", "200%")
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

# `tk scaling` above 100%, each a little under the scale times the 100%
# ratio. Windows fits every glyph and the line height to whole pixels
# separately at each size, so the faithful ratio (9pt as 24px at 200%)
# draws digits 8% wider and lines 2px taller than twice the 12px
# rendering. At these ratios each face lands on the pixel size nearest
# its 100% metrics times the scale -- at 200%, 9pt on 23px, 10 on 26,
# 11 on 29, 12 on 31, 14 on 36: line heights within two pixels, letters
# a few percent narrow.
#
# Searched, not derived: Tk on Windows asks for a font of
# MulDiv(points, int(scaling * 72), 72) pixels, so a ratio only ever
# picks one pixel size per face, and each candidate was scored on line
# height and widths across every face the app uses, weighted by how
# much of it is in each.
TEXT_SCALING = {1.25: 1.627, 1.5: 1.904, 1.75: 2.252, 2: 2.609}

# Set once, before any widget exists. A module-level factor is what
# lets `px` be reached from every call site in the app without
# threading a settings object through all of them; the cost is that it
# MUST be set before the first widget is built, because a widget takes
# its padding at construction and nothing revisits it.
_factor = 1


def parse(word):
    """The factor a choice word is worth: `200%` -> 2, `125%` -> 1.25.

    A whole factor comes back as an int, so 100% and 200% compute
    exactly as they always have. Anything this build does not offer is
    1: a settings file carrying an unknown scale draws at the size
    everything is measured at rather than stopping the launch.
    """
    spelled = str(word).strip()
    if spelled not in SCALE_CHOICES:
        return 1
    value = int(spelled.rstrip("%")) / 100
    return int(value) if value.is_integer() else value


def set_scale(word):
    """Fix the factor for this run. Call before building any widget."""
    global _factor
    _factor = parse(word)
    return _factor


def factor():
    """The active factor: 1 at 100%, 1.25 at 125%, 2 at 200%."""
    return _factor


def percent():
    """The active scale as a whole percent: 125 at 125%."""
    return round(_factor * 100)


def px(distance):
    """`distance` in device pixels at the active scale.

    Takes a number or a tuple or list of them, because half the
    distances in this app are `padx=(left, right)` pairs and a wrapper
    that only took scalars would need the pair pulled apart at every one
    of those call sites.

    A list is NOT a scalar here, though `*` takes one: `[10, 5] * 2` is
    `[10, 5, 10, 5]`, which a ttk `padding` reads as four sides at their
    100% values -- unscaled, and no error anywhere.

    **Always a whole pixel**, half rounding up: at a fractional scale a
    distance lands between pixels, and Tk -- like any arithmetic done
    on the result -- needs an int. Python's own `round` sends halves to
    the even neighbour, so 2.5 and 3.5 would round apart.

    Put this on the geometry call and not on the constant -- see the
    module docstring.
    """
    if isinstance(distance, (tuple, list)):
        return type(distance)(_pixel(value) for value in distance)
    return _pixel(distance)


def _pixel(value):
    """`value` times the factor, as a whole pixel, half rounding up."""
    return math.floor(value * _factor + 0.5)


def px_spans(widths):
    """A row of distances laid end to end -- a list's columns -- each
    at the active scale, together exactly `px` of their sum.

    Scaled by their running EDGES rather than one by one: each width
    rounded alone can gain up to half a pixel, and across a dozen
    columns that adds up to a row wider than the space it was sized
    for. Exact either way at 100% and 200%.
    """
    spans, edge, total = [], 0, 0
    for width in widths:
        total += width
        spans.append(px(total) - edge)
        edge = px(total)
    return spans


# What a stated text width is grown against: the letters, digits and
# punctuation the app's text columns hold, in their usual mix.
TEXT_SAMPLE = "Node 5.1: Basics Improved  ATK 1340  Crit% 67.2%  Element"

_text_ratios = {}


def text_px(distance, face=("Segoe UI", 9)):
    """A stated distance that holds TEXT, at the active scale.

    Some widths were measured off the text they hold at 100% and
    written down -- a column of labels and values ruled by tab stops.
    Text does not grow by the scale: each face is hinted to whole
    pixels per size, and at 200% (`TEXT_SCALING`) Segoe UI 9 runs a
    few percent narrow of double. `px` would leave such a column wider
    than its text by that much; this grows it by what `face` grew by.

    The 100% width comes from the same face asked for in PIXELS, which
    `tk scaling` does not touch. Needs a Tk root. Nothing at 100%.
    """
    if _factor == 1:
        return distance
    if face not in _text_ratios:
        from tkinter import font as tkfont
        family, size, *style = face
        weight = "bold" if "bold" in style else "normal"
        then = tkfont.Font(family=family, weight=weight,
                           size=-round(size * POINTS_TO_PIXELS))
        _text_ratios[face] = (tkfont.Font(font=face).measure(TEXT_SAMPLE)
                              / then.measure(TEXT_SAMPLE))
    return math.floor(distance * _text_ratios[face] + 0.5)


# What each scale asks Windows for: PROCESS_SYSTEM_DPI_AWARE (1) at
# 100%, PROCESS_PER_MONITOR_DPI_AWARE (2) above it. See
# `declare_dpi_awareness` for why the choice follows the scale.
SYSTEM_AWARE = (1, "system")
PER_MONITOR_AWARE = (2, "per-monitor")

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, asked for in place of
# plain per-monitor awareness where Windows offers it (1703 and later).
# The same to this program's own drawing; what it adds is Windows'
# scaling of what Windows draws -- the title bar and frame, and native
# dialogs such as a message box -- which plain per-monitor awareness
# leaves at their 96dpi size on a 200% screen.
PER_MONITOR_V2 = -4


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
    * Above 100% -- PER-MONITOR awareness. The text is already scaled
      by this program, and a system-aware window would have Windows
      scale it AGAIN on a scaled screen. Per-monitor awareness turns
      that second scaling off. Asked for as `PER_MONITOR_V2` first, so
      Windows sizes its own title bar and dialogs for the screen. What
      comes with it is Windows resizing the window by the DPIs' ratio
      when it is dragged onto another monitor; `ui/dpi_hold.py` answers
      Windows' size query so the client area stays as it is.

    Before Tk opens its connection, and after `set_scale`: awareness is
    a property of the PROCESS and the first window fixes it. Failing is
    not fatal -- the program then draws the way it always did -- so this
    reports rather than raises.

    Returns what happened, for the caller to log.
    """
    level, word = SYSTEM_AWARE if _factor == 1 else PER_MONITOR_AWARE
    if level == 2:
        try:
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(
                    ctypes.c_void_p(PER_MONITOR_V2)):
                return "per-monitor v2"
        except Exception:               # noqa: BLE001 -- older Windows
            pass
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
    root.tk.call("tk", "scaling", TEXT_SCALING.get(
        _factor, POINTS_TO_PIXELS * _factor))
    if _factor == 1:
        return
    for widget_class, options in CLASSIC_PIXELS.items():
        for option, value in options.items():
            # The lowest priority there is: an option a widget is given
            # outright, already through `px`, always wins.
            root.option_add(f"*{widget_class}.{option}", px(value),
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
                style.configure(name, **{option: px(value)})
    # **What the theme states in POINTS**, restated as its 100% pixels
    # through `px`. `tk scaling` carries points, and above 100% it is set
    # for the fonts (`TEXT_SCALING`) a little under the scale -- so a
    # scrollbar's width or a tab's padding given in points would come
    # out a pixel or two short of its 100% size scaled.
    theme = style.theme_use()
    for name in style.tk.splitlist(style.tk.call(
            "ttk::style", "theme", "styles", theme)):
        for option, value in (style.configure(name) or {}).items():
            restated = _points_scaled(value)
            if restated is not None:
                style.configure(name, **{option: restated})
        for option, entries in (style.map(name) or {}).items():
            if not any(_points_scaled(entry[-1]) for entry in entries):
                continue
            style.map(name, **{option: [
                (*(str(state) for state in entry[:-1]),
                 _points_scaled(entry[-1]) or entry[-1])
                for entry in entries]})


def _points_scaled(value):
    """`value`, every part of which is in points, as its 100% pixels
    through `px` -- or None where any part is not in points. A bare 0
    counts as points: nothing is nothing in either unit, and clam writes
    its paddings that way (`1.5p 0 7.5p 0`)."""
    parts = str(value).split()
    if not any(part.endswith("p") for part in parts) or not all(
            part.endswith("p") or part == "0" for part in parts):
        return None
    try:
        return " ".join(str(px(round(float(part.rstrip("p"))
                                     * POINTS_TO_PIXELS)))
                        for part in parts)
    except ValueError:
        return None
