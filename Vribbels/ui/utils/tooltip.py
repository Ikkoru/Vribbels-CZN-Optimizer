"""Hover tooltips.

A borderless Toplevel near the pointer after a short delay, torn down on
leave or on any click. Deliberately not a ttk widget: it has to sit above
everything, follow the pointer and disappear without leaving a hole, none
of which a themed widget does for free.
"""

import tkinter as tk


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
    WRAP_PX = 320

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

    def bind(self, widget, text):
        widget.bind("<Enter>",
                    lambda e, w=widget, t=text: self.schedule(w, t), add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        # Any click dismisses -- the tooltip shouldn't sit over the row
        # while the user is toggling checkboxes or editing the spinbox.
        widget.bind("<Button>", lambda e: self.hide(), add="+")

    def bind_tag(self, text_widget, tag, text):
        """Same, for one tagged RANGE inside a Text rather than a widget.

        A Text drawing what would otherwise be several widgets has no
        separate window to hover, so the hover lives on the tag. The tip
        positions against the Text itself, which is close enough for a
        cell-sized widget.
        """
        text_widget.tag_bind(
            tag, "<Enter>",
            lambda e, w=text_widget, t=text: self.schedule(w, t), add="+")
        text_widget.tag_bind(tag, "<Leave>", lambda e: self.hide(), add="+")
        text_widget.tag_bind(tag, "<Button>", lambda e: self.hide(), add="+")

    def schedule(self, widget, text):
        """Arm the tip for `text`, positioned against `widget`.

        Public because a hover target is not always a widget or a tag: a
        Treeview HEADING is neither, and the only way to give one a tip
        is to drive the delay from a `<Motion>` handler. Reaching for
        this is what the Memory Fragments tab does; before it existed
        that tab grew a second tooltip of its own.
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
        """
        self._after_id = None
        try:
            x = widget.winfo_pointerx() + 12
            y = widget.winfo_pointery() + 14
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.attributes("-topmost", True)
            # spacing: content frame -> content frame -- frame, label ↔↕
            # The tip's border against its own words. One value on all
            # four sides: a Label's `padx` reaches both sides at once
            # and so does its `pady`, so this is the whole of the tip's
            # inset -- the window is the Label and nothing else.
            tk.Label(
                tip, text=text, justify=tk.LEFT,
                bg=self.colors["bg_lighter"], fg=self.colors["fg"],
                relief=tk.SOLID, borderwidth=1,
                font=("Segoe UI", 9), wraplength=self.WRAP_PX,
                padx=4, pady=4,
            ).pack()
            self._tip = tip
        except tk.TclError:
            self._tip = None

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
