"""How large the program draws itself, and what Windows is told about it.

Two separate things, and both have to be right or the window is wrong on
a high-DPI screen.

**Windows must be told to leave the window alone.** A process that has
not declared DPI awareness is drawn at 96dpi and then BITMAP-STRETCHED
onto a scaled monitor -- the right apparent size and every glyph soft,
because it is an upscale of a render rather than a render. Declaring
per-monitor awareness turns that off; the window is then drawn in real
device pixels and is crisp, and how large it comes out is entirely this
module's business.

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
`dlineinfo` -- has already grown with the font scaling, and wrapping it
scales it a second time. A pad mixing the two takes `px` on its
hardcoded part alone: `px(INSET) + indent`, never `px(INSET + indent)`.
`checks/check_ui_scales.py` catches both halves of this, a pad that did
not grow and one that grew twice.

**The spacing audit is 100%-only.** Its targets are physical pixels; at
200% every gap would read double and the run would be a wall of red
that means nothing. Nothing here changes that -- it is a statement
about which scale the audit is run at.
"""

import ctypes

# What the dropdown offers, and what each is worth. 200% is the only
# whole multiple: every pixel doubles with no remainder, and the icon
# assets double by nearest neighbour without a resample. See T15 for
# why the fractional steps are not here.
SCALE_CHOICES = ("100%", "200%")
DEFAULT_SCALE = "100%"

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

    Anything unrecognised is 1. A settings file carrying a scale this
    build no longer offers should draw at the size everything is
    measured at rather than refuse to start.
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

    Takes a number or a tuple of them, because half the distances in
    this app are `padx=(left, right)` pairs and a wrapper that only
    took scalars would need the pair pulled apart at every one of those
    call sites.

    Put this on the geometry call and not on the constant -- see the
    module docstring.
    """
    if isinstance(distance, tuple):
        return tuple(value * _factor for value in distance)
    return distance * _factor


def declare_dpi_awareness():
    """Ask Windows to stop scaling this process's windows.

    Before Tk opens its connection: awareness is a property of the
    process and the first window fixes it. Failing is not fatal -- the
    program then draws the way it always did, bitmap-stretched on a
    scaled screen -- so this reports rather than raises.

    Returns what happened, for the caller to log.
    """
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE. v1 rather than v2: Tk follows
        # no per-monitor change either way, and v2's non-client scaling
        # would leave the title bar disagreeing with the window.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception as exc:            # noqa: BLE001 -- not Windows, or refused
        return f"not declared ({exc})"


def hold_size_across_monitors(root):
    """Keep the window the size it was when it crosses a DPI boundary.

    A per-monitor-aware window DRAGGED onto a differently-scaled screen
    gets `WM_DPICHANGED` with a suggested rectangle, and Windows'
    default handling applies it -- so a 100% window moved onto a 200%
    monitor comes out twice the size. Nothing about that is this
    program's scale setting, which is fixed for the run and changes
    only on a restart.

    So the size is remembered and put back whenever the DPI UNDER the
    window changes. The position is left alone: where the window was
    dragged to is the user's answer, and only its size is the OS's.

    **The event has to be filtered to the root.** A toplevel's pathname
    is in the bind tags of every widget under it, so a `<Configure>`
    bound here fires for each of the hundreds of child widgets too, and
    an unfiltered handler would take a child's geometry for the
    window's.

    A move made by `geometry()` does not go through this at all --
    Windows sends no DPI change for one -- which is why the drag is the
    only way to see it.
    """
    try:
        user32 = ctypes.windll.user32
        user32.GetDpiForWindow.restype = ctypes.c_uint
    except Exception:                       # noqa: BLE001 -- not Windows
        return

    def dpi():
        try:
            return user32.GetDpiForWindow(root.winfo_id())
        except Exception:                   # noqa: BLE001
            return 0

    def measured():
        """The window's size, or None before Tk has laid it out."""
        width, height = root.winfo_width(), root.winfo_height()
        return (width, height) if width > 1 and height > 1 else None

    # Seeded here as well as from the events, for a window that is
    # already settled when this is called: nothing configures it again,
    # so nothing would ever record a size to put back.
    state = {"size": measured(), "dpi": dpi()}

    def on_configure(event):
        if event.widget is not root:
            return
        now = dpi()
        if now and now != state["dpi"]:
            state["dpi"] = now
            if state["size"]:
                width, height = state["size"]
                root.geometry("%dx%d+%d+%d" % (width, height,
                                               root.winfo_x(), root.winfo_y()))
            return
        state["size"] = measured() or state["size"]

    root.bind("<Configure>", on_configure, add="+")


def apply_font_scaling(root):
    """Scale every font by the active factor.

    Tk sizes a font from its POINT size and this ratio, so one call
    carries all of them -- and with them every distance the app derives
    from a font metric. Call before the first widget is built: a widget
    resolves its font once.
    """
    root.tk.call("tk", "scaling", POINTS_TO_PIXELS * _factor)
