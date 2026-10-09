"""A gap made of two parts is the whole gap scaled once, at every scale.

Most gaps in the app are two pads meeting -- a frame's trailing 2 and
its neighbour's leading 2 -- or a pad meeting a widget's own inset.
Each part through `px` rounds its half up, and at 125%, 150% and 175%
two halves make a whole pixel: two 2s are 3 + 3 at 125% where the 4
they make is 5. Nothing reports it but a spacing audit at that scale.

The levers that keep such a gap whole:

* `px_after(before, distance)` -- the SECOND part of a gap, taking what
  `before` leaves of the whole;
* `px_inset` -- an inset inside a widget, rounding its half down so the
  pad beside it can round its own up;
* a default checkbox's side inset, set through `px_inset`, and the pads
  `pad_between` and `pad_beside_label` give it neighbours.

Each is held here to the gap it promises, at every scale offered.
"""

from ._harness import add_source_to_path, Skip

NAME = "a gap of two parts is the gap scaled once"


def _arithmetic(scaling, checkbox, scale):
    out = []
    px, after, inset = scaling.px, scaling.px_after, scaling.px_inset
    for a in range(0, 13):
        for b in range(0, 13):
            if px(a) + after(a, b) != px(a + b):
                out.append(f"At {scale} px({a}) + px_after({a}, {b}) is "
                           f"{px(a) + after(a, b)}, not px({a + b}) = "
                           f"{px(a + b)}.")
            # An inset and a pad that both land on a half: the two have
            # to round apart.
            f = scaling.factor()
            if (a * f) % 1 == 0.5 and (b * f) % 1 == 0.5 \
                    and inset(a) + px(b) != px(a + b):
                out.append(f"At {scale} px_inset({a}) + px({b}) is "
                           f"{inset(a) + px(b)}, not px({a + b}) = "
                           f"{px(a + b)}: an inset and a pad on halves "
                           f"have to round their halves apart.")
    side = inset(checkbox.SIDE_INSET)
    for d in (0, 2, 4, 8):
        got = 2 * side + checkbox.pad_between(d)
        want = px(2 * checkbox.SIDE_INSET + d)
        if got != want:
            out.append(f"At {scale} two checkboxes {d} apart make a gap of "
                       f"{got}, not {want}.")
        label = inset(checkbox.LABEL_INK_INSET)
        got = side + checkbox.pad_beside_label(d) + label
        want = px(checkbox.SIDE_INSET + d + checkbox.LABEL_INK_INSET)
        if got != want:
            out.append(f"At {scale} a checkbox {d} from a label makes a gap "
                       f"of {got}, not {want}.")
    return out


def _checkbox_inset(checkbox, scale):
    """The inset `make_checkbox` actually sets is the one the pads are
    worked out against: `pad_between` assumes `px_inset(SIDE_INSET)`."""
    import tkinter as tk
    from ui import scaling
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    try:
        colours = {k: "#000000" for k in ("bg", "fg", "bg_light")}
        box = checkbox.make_checkbox(root, colours, text="x")
        side = int(box.cget("padx")) + checkbox.FOCUS_INSET
        want = scaling.px_inset(checkbox.SIDE_INSET)
        if side != want:
            return [f"At {scale} a default checkbox's side inset is {side}, "
                    f"not px_inset(SIDE_INSET) = {want}: every gap "
                    f"`pad_between` and `pad_beside_label` work out is off "
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
    from ui.utils import checkbox

    failures = []
    try:
        for scale in scaling.SCALE_CHOICES:
            scaling.set_scale(scale)
            failures.extend(_arithmetic(scaling, checkbox, scale))
            failures.extend(_checkbox_inset(checkbox, scale))
    finally:
        scaling.set_scale(scaling.DEFAULT_SCALE)
    return failures
