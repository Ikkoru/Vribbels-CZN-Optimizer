"""Whether a UI scale's fonts fit: the two places that say so first.

Each scale above 100% draws its text at a pixel size chosen near its
100% metrics times the scale (`scaling.TEXT_SCALING`), and whole pixels
land a little over or under. Text a little too TALL or too WIDE for its
scale shows first in one place per axis, and this measures both:

* **Height -- the Character card.** The gear cells below it take the
  height their font needs (`heroes_tab._gear_cell_h`), and the card
  has what the window has left above them, with a fixed number of
  lines to hold. A line too tall runs the last of them off the panel.
  Both sides of that grow with the line height, which is why it goes
  first: one pixel size up clips it at 150% and 200% while every other
  tab still fits.

  The two stacks queued behind it are reported beside it, as the room
  left under each: the Materials tab, and Stats & Gacha History with
  its Banners list at the full `BANNER_ROWS`.
* **Width -- the Memory Fragments list's Main column.** Of the widths
  stated in pixels, the one with the least room beside its widest text
  (`Passion% 16.0%`), so the first a wider font clips. A width measured
  off its text, or grown with it (`scaling.text_px`), follows the font
  and is no gauge; telling the two apart is a matter of running two
  font sizes at one scale and seeing whose room moved.

  Every other place a width holds text is listed too -- a list's
  columns, an unwrapped text block's lines, a label or button held to a
  width, and a gear cell's first row, which wraps if it does not fit --
  as clips, and the nearest to clipping by their room as a share of
  their text. So is the longest set effect in a gear cell: the cell's
  height holds `GEAR_SET_ROWS` rows of it, and a face too wide wraps
  it to one more.

Run by `--font-gauge` on an app built and laid out at the scale asked
for (`--audit-scale`), rendered and never shown; `docs/font_gauge.py`
runs every scale. Prints a report and exits.
"""

import math
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from game_data.sets import SETS
from ui import scaling
from ui.tabs.heroes_tab import GEAR_SET_ROWS

# How many rows of slack to list beside the clips: enough to see which
# place is nearest, and the ones queued behind it.
NEAREST = 12

# The width gauge: the tab's name and the end of the list column's
# path, as the width rows carry them.
WIDTH_GAUGE = ("Memory Fragments", ":main")


def gauge(app):
    """Print the height and width reports for the running scale."""
    ratio = float(app.root.tk.call("tk", "scaling"))
    # Tk's own conversion on Windows: MulDiv(points, int(ratio * 72), 72).
    nine = math.floor(9 * int(ratio * 72) / 72 + 0.5)
    print(f"\n--- font gauge, {scaling.percent()}%, tk scaling {ratio:.3f}, "
          f"Segoe UI 9 at {nine}px ---")
    heroes = app.heroes_tab_instance
    app.notebook.select(heroes.frame)
    app.root.update()
    _card_height(heroes)
    _bottoms(app)
    app.notebook.select(heroes.frame)
    app.root.update()
    _set_rows(app, heroes)
    rows = []
    for tab_id in app.notebook.tabs():
        name = app.notebook.tab(tab_id, "text")
        app.notebook.select(tab_id)
        app.root.update()
        page = app.root.nametowidget(tab_id)
        rows.extend((name,) + row for row in _widths(page))
    _width_report(rows)


# ------------------------------------------------------------- height

def _count(text, start, end, what):
    got = text.count(start, end, what)
    return got[0] if isinstance(got, tuple) else (got or 0)


def _card_height(heroes):
    """The Character card's lines against the height its Text has."""
    text = heroes.hero_char_text
    text.update_idletasks()
    inset = (int(text.cget("bd")) + int(text.cget("highlightthickness"))
             + int(text.cget("pady")))
    room = text.winfo_height() - 2 * inset
    lines = int(text.index("end-1c").split(".")[0])
    need = _count(text, "1.0", "end", "ypixels")
    line = tkfont.Font(root=text, font=text.cget("font")).metrics(
        "linespace")
    print(f"height: Character card {'CLIPPED' if need > room else 'fits'}: "
          f"{room - need:+d}px beside its {lines} lines ({need} of {room}px, "
          f"{line}px a line)")


def _stack_room(page):
    """(room, where) for every widget on `page`, least room first: the
    page's foot less where the widget would END at the height it asks
    for. A widget a taller font has squeezed asks for more than it got,
    and its asked-for foot runs past the page's. A Text or a canvas is
    left out -- it asks for lines it is not meant to get, and its
    container's request already carries whatever it really holds."""
    foot = page.winfo_rooty() + page.winfo_height()
    out = []

    def walk(widget):
        for child in widget.winfo_children():
            if not child.winfo_ismapped():
                continue
            if child.winfo_class() not in ("Text", "Canvas", "Scrollbar",
                                           "TScrollbar"):
                out.append((foot - child.winfo_rooty()
                            - child.winfo_reqheight(), str(child)))
            walk(child)

    walk(page)
    return sorted(out)


def _bottoms(app):
    """The room under the Materials and Stats & Gacha History tabs'
    stacks, the Banners list at its full `BANNER_ROWS`."""
    from ui.tabs.gacha_history_tab import BANNER_ROWS
    for name, attr, extra in (
            ("Materials", "materials_tab_instance", ""),
            ("Stats & Gacha History", "gacha_tab_instance",
             f", {BANNER_ROWS} banners")):
        for tab_id in app.notebook.tabs():
            if app.notebook.tab(tab_id, "text") == name:
                app.notebook.select(tab_id)
        app.root.update()
        tab = getattr(app, attr)
        if attr == "gacha_tab_instance":
            tab._show_banner_rows(BANNER_ROWS)
            app.root.update()
        rows = _stack_room(tab.get_frame())
        room = rows[0][0] if rows else 0
        print(f"   behind it: {name}{extra} "
              f"{'CLIPPED' if room < 0 else 'fits'}: {room:+d}px")


# -------------------------------------------------------------- width

def _longest_set(widget):
    """The set line wrapped furthest: the set with the widest text."""
    face = tkfont.Font(root=widget, font=("Segoe UI", 9))
    texts = [f"{s['name']} ({s['pieces']}) {s.get('bonus', '')}"
             for s in SETS.values()]
    return max(texts, key=face.measure)


def _set_rows(app, heroes):
    """How many rows the longest set effect wraps to in a gear cell."""
    cells = list(getattr(heroes, "gear_cells", {}).values())
    if not cells:
        print("width: no gear cells built")
        return
    cell = cells[0]
    cell.config(state=tk.NORMAL)
    cell.delete("1.0", tk.END)
    # The shape every filled cell has: a top row, four substat rows,
    # and the set line -- the longest set effect in the game, wrapped
    # as the cell wraps it. The top row's width is the width report's.
    cell.insert(tk.END, "Flat HP  +36.6\tGS: 69\tIII Denial  +5",
                ("toprow",))
    for _ in range(4):
        cell.insert(tk.END, "\n\t100\tFlat DEF +13 (5 | +4, +4)",
                    ("subrow",))
    cell.insert(tk.END, "\n" + _longest_set(cell), ("set_live",))
    app.root.update_idletasks()
    # `displaylines` counts the breaks between a line's rows, not rows.
    rows = _count(cell, "6.0", "6.end", "displaylines") + 1
    print(f"width: gear cell {'CLIPPED' if rows > GEAR_SET_ROWS else 'fits'}"
          f": the longest set effect wraps to {rows} of {GEAR_SET_ROWS} rows")


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _style_font(widget, style, name, fallback):
    return tkfont.Font(root=widget,
                       font=style.lookup(name, "font") or fallback)


def _widths(page):
    """(where, what, room, need) for every stated width holding text."""
    style = ttk.Style()
    out = []
    for widget in _walk(page):
        if not widget.winfo_ismapped():
            continue
        cls = widget.winfo_class()
        if cls == "Treeview":
            out.extend(_tree(widget, style))
        elif cls == "Text":
            out.extend(_text(widget))
        elif cls in ("TLabel", "Label", "TButton", "Button",
                     "Checkbutton", "TCheckbutton"):
            try:
                if int(str(widget.cget("wraplength")) or 0) > 0:
                    continue
            except (tk.TclError, ValueError):
                pass
            text = _text_of(widget)
            # A widget at its own width has no slack to report: only
            # one squeezed below what it asks for says anything.
            if text and widget.winfo_width() < widget.winfo_reqwidth():
                out.append((str(widget), text[:40], widget.winfo_width(),
                            widget.winfo_reqwidth()))
    return out


def _text_of(widget):
    try:
        text = widget.cget("text")
    except tk.TclError:
        return ""
    return text if isinstance(text, str) else ""


def _tree(tree, style):
    body = _style_font(tree, style, tree.cget("style") or "Treeview",
                       "TkDefaultFont")
    head = _style_font(tree, style, "Heading", "TkHeadingFont")
    columns = tree["displaycolumns"]
    if columns in ("#all", ("#all",)):
        columns = tree["columns"]
    items = tree.get_children("")
    out = []
    for index, column in enumerate(tree["columns"]):
        if column not in columns:
            continue
        width = int(tree.column(column, "width"))
        if width <= 1:
            continue
        heading = str(tree.heading(column, "text"))
        widest, text = head.measure(heading), heading
        for item in items:
            values = tree.item(item, "values")
            if index < len(values):
                value = str(values[index])
                w = body.measure(value)
                if w > widest:
                    widest, text = w, value
        out.append((f"{tree}:{column}", text[:40], width, widest))
    return out


def _text(text):
    """Unwrapped lines against the box, and a gear cell's first row."""
    inner = (text.winfo_width()
             - 2 * (int(text.cget("bd")) + int(text.cget("highlightthickness"))
                    + int(text.cget("padx"))))
    if inner <= 1:
        return []
    out = []
    wrap = str(text.cget("wrap"))
    lines = int(text.index("end-1c").split(".")[0])
    if wrap == "none":
        widest, which = 0, ""
        for n in range(1, lines + 1):
            span = text.count(f"{n}.0", f"{n}.end", "xpixels")
            span = span[0] if isinstance(span, tuple) else (span or 0)
            if span > widest:
                widest, which = span, text.get(f"{n}.0", f"{n}.end")
        if widest:
            out.append((str(text), which.strip()[:40], inner, widest))
    elif "toprow" in text.tag_names():
        rows = text.count("1.0", "1.end", "displaylines")
        rows = rows[0] if isinstance(rows, tuple) else rows
        if rows and rows > 1:
            out.append((str(text) + ":toprow", text.get("1.0", "1.end")[:40],
                        0, 1))
    return out


def _width_report(rows):
    for tab, where, what, room, need in rows:
        if tab == WIDTH_GAUGE[0] and where.endswith(WIDTH_GAUGE[1]):
            print(f"width: Main column {'CLIPPED' if need > room else 'fits'}"
                  f": {room - need:+d}px, {100 * (room - need) / need:+.1f}% "
                  f"beside {what!r} ({need} of {room}px)")
            break
    else:
        print("width: the Main column was not found")
    clips = [r for r in rows if r[4] > r[3]]
    print(f"width: {len(clips)} clipped, of {len(rows)} measured")
    for tab, where, what, room, need in clips:
        print(f"   CLIPPED {tab}: {where[-48:]} {what!r} needs {need}, "
              f"has {room}")
    # A width that fits its text EXACTLY was measured off it, and grows
    # with any font: it cannot be the first to clip.
    nearest = sorted((r for r in rows if 0 < r[4] < r[3]),
                     key=lambda r: (r[3] - r[4]) / r[4])[:NEAREST]
    print("   nearest to clipping (room beside the widest text):")
    for tab, where, what, room, need in nearest:
        print(f"   {100 * (room - need) / need:5.1f}% {room - need:+4d}px  "
              f"({need} of {room})  {tab}: {where[-48:]} {what!r}")
