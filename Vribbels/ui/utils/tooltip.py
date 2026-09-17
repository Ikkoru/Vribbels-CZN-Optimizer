"""Hover tooltips.

A borderless Toplevel near the pointer after a short delay, torn down on
leave or on any click. Deliberately not a ttk widget: it has to sit above
everything, follow the pointer and disappear without leaving a hole, none
of which a themed widget does for free.

**A tip's content can be three things.** A string is the plain case. A
sequence of `(label, value)` pairs is drawn as two aligned columns --
see `ROW_GAP`. And a CALLABLE returning either is resolved when the tip
goes up rather than when it was bound, which is what lets a tip on
something that changes say what the thing says now: a binding made at
build time would otherwise hold the figures that were on screen then.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ui.scaling import px

# A two-column tip's label against its value. The columns are two
# Labels side by side, each as wide as its own widest line, so this is
# the gap from the LONGEST label -- every shorter one has more.
ROW_GAP = 5             # spacing: label ↔ its element -- label, label ↔

# What the pointer becomes over anything carrying a tip. The underline
# says there is more to read; the cursor says it arrives on hover.
HOVER_CURSOR = "question_arrow"

# How far the tip's corner sits from the pointer. Through `px()` at the
# call, like every other hardcoded distance: a fixed nudge is half a
# nudge at 200%.
OFFSET_X = 0
OFFSET_Y = 10

# How far outside the window a tip may sit. One pixel: enough that a
# tip beside a control at the very edge is not shoved back over the
# control it explains, and not so much that it reads as a loose window.
EDGE = 1


class Tooltip:
    """Lightweight hover tooltip, shared by every tab that needs one.

    One instance serves many widgets: bind(widget, text) attaches
    Enter/Leave handlers that schedule a borderless Toplevel near the
    pointer after a short hover delay and tear it down on leave/click.
    Moving between widgets of the same row restarts the delay (Tk fires
    Leave on the container when the pointer crosses onto a child, so
    each row binds its individual children).
    """
    DELAY_MS = 400
    WRAP_PX = 330

    def __init__(self, colors):
        self.colors = colors
        self._after_id = None
        self._owner = None
        self._tip = None
        # Whether Escape has been wired up yet. The tip window itself
        # cannot carry that binding -- `wm_overrideredirect` means it
        # never takes keyboard focus -- so the key is caught on the
        # window that does, once per Tooltip rather than once per tip.
        self._escape_bound = False
        # Underlined faces derived for the widgets marked through this
        # instance. See `mark` for why they are held.
        self._fonts = []
        # The font names this instance has already derived, so a tip
        # rebound on a refresh does not derive another.
        self._marked = set()

    def bind(self, widget, text):
        self.mark(widget)
        widget.bind("<Enter>",
                    lambda e, w=widget, t=text: self.schedule(w, t), add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        # Any click dismisses -- the tooltip shouldn't sit over the row
        # while the user is toggling checkboxes or editing the spinbox.
        widget.bind("<Button>", lambda e: self.hide(), add="+")

    def mark(self, widget):
        """Say that this widget HAS a tooltip, before anyone hovers it.

        A tip nobody knows about is a tip nobody reads. Two marks, both
        conventional: the words are underlined, and the pointer becomes
        `question_arrow` over them.

        Done here rather than at each call site so that binding a tip
        is the only thing a caller has to remember -- there is no way
        to add one and forget the mark.

        A widget with no `font` of its own -- a Treeview, a frame
        standing in for a row -- takes the cursor alone. Underlining is
        skipped rather than forced: a Treeview draws its own cells, and
        the font there is the style's for every row at once.
        """
        try:
            widget.configure(cursor=HOVER_CURSOR)
        except tk.TclError:
            pass
        try:
            spec = str(widget.cget("font"))
        except tk.TclError:
            return
        # **Already marked.** A tip rebound on every refresh -- the
        # archive readings are -- would otherwise derive a new named
        # font each time, and Tk keeps every one of them.
        if spec and spec in self._marked:
            return
        if not spec:
            # A ttk widget left on its style's font answers with "".
            spec = (ttk.Style().lookup(widget.winfo_class(), "font")
                    or "TkDefaultFont")
        try:
            marked = tkfont.Font(root=widget, font=spec)
        except tk.TclError:
            return
        marked.configure(underline=True)
        # **Held.** A `Font` is a Tcl named font that Tk deletes when
        # the Python object is collected, and the widget would fall
        # back to a default face mid-session.
        self._fonts.append(marked)
        self._marked.add(str(marked))
        try:
            widget.configure(font=marked)
        except tk.TclError:
            pass

    def bind_tag(self, text_widget, tag, text):
        """Same, for one tagged RANGE inside a Text rather than a widget.

        A Text drawing what would otherwise be several widgets has no
        separate window to hover, so the hover lives on the tag. The tip
        positions against the Text itself, which is close enough for a
        cell-sized widget.
        """
        # The same two marks as `mark`, in a Text's own vocabulary: the
        # range is underlined by its tag, and the CURSOR is a widget
        # option rather than a tag one, so it is swapped on the way in
        # and put back on the way out.
        text_widget.tag_configure(tag, underline=True)
        was = str(text_widget.cget("cursor"))

        def _enter(event, w=text_widget, t=text):
            try:
                w.configure(cursor=HOVER_CURSOR)
            except tk.TclError:
                pass
            self.schedule(w, t)

        def _leave(event, w=text_widget):
            try:
                w.configure(cursor=was)
            except tk.TclError:
                pass
            self.hide()

        text_widget.tag_bind(tag, "<Enter>", _enter, add="+")
        text_widget.tag_bind(tag, "<Leave>", _leave, add="+")
        text_widget.tag_bind(tag, "<Button>", lambda e: self.hide(), add="+")

    def schedule(self, widget, text):
        """Arm the tip for `text`, positioned against `widget`.

        Public because a hover target is not always a widget or a tag: a
        Treeview HEADING is neither, and the only way to give one a tip
        is to drive the delay from a `<Motion>` handler. Reaching for
        this is what the Memory Fragments tab does; before it existed
        that tab grew a second tooltip of its own.

        `text` may be a callable, and is not resolved here: a tip is
        armed on every hover and shown on few of them, so the content
        is worked out once the delay has run.
        """
        self.hide()
        self._owner = widget
        self._bind_escape(widget)
        try:
            self._after_id = widget.after(
                self.DELAY_MS, lambda: self.show(widget, text))
        except tk.TclError:
            self._after_id = None

    def _bind_escape(self, widget):
        """Wire Escape to `hide`, on the window holding the focus."""
        if self._escape_bound:
            return
        try:
            widget.winfo_toplevel().bind(
                "<Escape>", lambda e: self.hide(), add="+")
        except tk.TclError:
            return
        self._escape_bound = True

    def show(self, widget, text):
        """Put the tip up now, skipping the delay.

        `schedule` is the one hover uses. This is public for the two
        callers that already know they want it on screen: itself, once
        the delay has run, and the spacing audit, which has a window to
        photograph and no pointer to hover with.

        A callable `text` is resolved here, and one answering with
        nothing puts no tip up at all -- a tip with an empty box in it
        reads as a bug rather than as "nothing to say".
        """
        self._after_id = None
        text = self.content(text)
        if not text:
            self._tip = None
            return
        try:
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.attributes("-topmost", True)
            if isinstance(text, str):
                self._words(tip, text).pack()
            else:
                self._columns(tip, text).pack()
            self._place(tip, widget)
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _place(self, tip, widget):
        """Put the tip's BOTTOM-RIGHT corner beside the pointer.

        Above and left of the cursor rather than below and right of it,
        so the tip never covers what the pointer is about to move onto
        -- a row below the one being read, or the next control along.

        The content has to be packed first: the corner is placed by
        subtracting the tip's own width and height, and a Toplevel that
        has not been laid out reports 1 for both.

        Held inside the APP WINDOW rather than the screen. `winfo_screen*`
        reports the primary monitor, so on a second display to the left
        the pointer is at a negative x and clamping to zero throws the
        tip onto the other monitor entirely. The window is on whichever
        display the user is working on, which is the one the tip belongs
        on.
        """
        tip.update_idletasks()
        top = widget.winfo_toplevel()
        width, height = tip.winfo_width(), tip.winfo_height()
        x = widget.winfo_pointerx() - px(OFFSET_X) - width
        y = widget.winfo_pointery() - px(OFFSET_Y) - height
        left, upper = top.winfo_rootx(), top.winfo_rooty()
        # **The title bar counts as the window.** `winfo_rooty` is the
        # CLIENT area's top, and a tip beside a control in the first row
        # has nowhere to go above it without that strip. The height of
        # the decoration is the client top less the frame's own: for a
        # toplevel, `winfo_y` is the frame's position on screen while
        # `winfo_rooty` is the client area's.
        #
        # Plus `EDGE` all round, so a tip may sit a hair outside rather
        # than being shoved back over the control it explains.
        chrome = max(0, upper - top.winfo_y())
        x = max(left - EDGE,
                min(x, left + top.winfo_width() - width + EDGE))
        y = max(upper - chrome - EDGE,
                min(y, upper + top.winfo_height() - height + EDGE))
        tip.wm_geometry(f"+{x}+{y}")

    @staticmethod
    def content(text):
        """What a tip is to say, a callable payload resolved.

        Its own method so that the resolution can be exercised without
        a window: putting a tip up to find out whether it read its
        callable means a Toplevel on the maintainer's screen.
        """
        return text() if callable(text) else text

    def _words(self, tip, text):
        """The whole tip as one Label. The plain case."""
        # spacing: content frame -> content frame -- frame, label ↔↕
        # The tip's border against its own words. One value on all
        # four sides: a Label's `padx` reaches both sides at once
        # and so does its `pady`, so this is the whole of the tip's
        # inset -- the window is the Label and nothing else.
        return tk.Label(
            tip, text=text, justify=tk.LEFT,
            bg=self.colors["bg_lighter"], fg=self.colors["fg"],
            relief=tk.SOLID, borderwidth=px(1),
            font=("Segoe UI", 9), wraplength=px(self.WRAP_PX),
            padx=px(4), pady=px(4))

    def _columns(self, tip, rows):
        """`(label, value)` rows, as two aligned columns.

        Two Labels rather than a grid of them: each is as wide as its
        own widest line, so the values line up with nothing measured
        and no cell to size. **Neither wraps.** A wrapped cell would
        take one column out of step with the other and there would be
        nothing on screen to say which line belonged to which.
        """
        # spacing: content frame -> content frame -- frame, label ↔↕
        # As above: the frame's own border, and the inset from it.
        body = tk.Frame(tip, bg=self.colors["bg_lighter"],
                        relief=tk.SOLID, borderwidth=px(1),
                        padx=px(4), pady=px(4))
        for at, column in enumerate(zip(*rows)):
            # spacing: label ↔ its element -- label, label ↔
            tk.Label(
                body, text="\n".join(column), justify=tk.LEFT,
                bg=self.colors["bg_lighter"], fg=self.colors["fg"],
                font=("Segoe UI", 9),
            ).pack(side=tk.LEFT, anchor=tk.N,
                   padx=px((ROW_GAP, 0)) if at else 0)
        return body

    def hide(self):
        if self._after_id is not None and self._owner is not None:
            try:
                self._owner.after_cancel(self._after_id)
            except (tk.TclError, ValueError):
                pass
            self._after_id = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
