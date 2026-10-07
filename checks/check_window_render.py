"""The spacing audit reads a window it never shows.

`ui/utils/window_render.render` asks Windows to draw the window into a
bitmap rather than reading the screen, which is what lets the audit's
app stay at alpha 0 from launch to exit, and lay out at 200% as a
3100 x 2000 window no monitor here holds. Two ways that goes quietly
wrong, each reading as plausible numbers rather than as an error:

  * the rendering comes back empty, or only as much as the screen
    shows, for a transparent window or the part of one past the screen's
    edge -- every gap there measures against black;
  * a window the audit's scenarios open over the app (the contributions
    popup, the Restore Defaults dialog) appears on the maintainer's
    screen, because the app's own builders map it before handing it
    back. `spacing_audit.hide_new_windows` makes each start at alpha 0.

So a transparent window wider and taller than every screen is built,
with a known colour in its far corner and a word near its origin, and
rendered.
"""

import tkinter as tk

from ._harness import Skip, add_source_to_path

NAME = "the audit renders a window it never shows"

FAR = "#ff0000"


def _renders_past_the_screen(render):
    out = []
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise Skip(f"Tk will not start here ({exc})")
    try:
        root.attributes("-alpha", 0.0)
        width = root.winfo_screenwidth() + 300
        height = root.winfo_screenheight() + 200
        root.wm_maxsize(width, height)
        root.geometry(f"{width}x{height}+0+0")
        root.configure(bg="#1e1e2e")
        tk.Frame(root, bg=FAR, width=60, height=60).place(
            x=width - 80, y=height - 80)
        tk.Label(root, text="ATK", bg="#1e1e2e", fg="#ffffff").place(x=8, y=8)
        for _ in range(3):
            root.update()
        if (root.winfo_width(), root.winfo_height()) != (width, height):
            out.append(
                f"a window asked for {width}x{height} came out "
                f"{root.winfo_width()}x{root.winfo_height()}: Tk capped it "
                f"at the screen, and the audit at 200% would lay out an app "
                f"nobody sees. See `_hide_until_ready`'s maxsize.")
        image = render(root)
        if image.size != (root.winfo_width(), root.winfo_height()):
            out.append(f"the rendering is {image.size}, not the window's "
                       f"{root.winfo_width()}x{root.winfo_height()}")
        far = image.getpixel((root.winfo_width() - 50,
                              root.winfo_height() - 50))
        if far != (255, 0, 0):
            out.append(
                f"the far corner of a transparent window larger than the "
                f"screen renders as {far}, not the red placed there: the "
                f"audit would measure that part of the app against "
                f"nothing")
        word = image.crop((0, 0, 80, 40)).getcolors(4096) or []
        if len(word) < 3:
            out.append("the label near the window's origin rendered as "
                       "flat colour: no text reached the bitmap")
    finally:
        root.destroy()
    return out


def _new_windows_start_hidden(sa):
    out = []
    build = tk.Toplevel.__init__
    root = tk.Tk()
    try:
        root.attributes("-alpha", 0.0)
        sa.hide_new_windows()
        top = tk.Toplevel(root)
        alpha = float(top.attributes("-alpha"))
        top.destroy()
        if alpha != 0.0:
            out.append(
                f"a window opened under the audit starts at alpha {alpha}: "
                f"the scenarios' popups would show on the maintainer's "
                f"screen. See `spacing_audit.hide_new_windows`.")
    finally:
        # Put back for the checks after this one; the audit itself never
        # does, because the app exits when the run ends.
        tk.Toplevel.__init__ = build
        root.destroy()
    return out


def run():
    add_source_to_path()
    from ui import spacing_audit as sa
    from ui.utils.window_render import render
    failures = []
    failures.extend(_renders_past_the_screen(render))
    failures.extend(_new_windows_start_hidden(sa))
    return failures
