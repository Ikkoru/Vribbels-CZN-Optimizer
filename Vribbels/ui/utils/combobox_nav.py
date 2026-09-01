"""Keyboard navigation for readonly ttk Comboboxes.

Tk gives a readonly Combobox almost no keyboard behaviour: letters do
nothing, and Up/Down open the dropdown instead of stepping through it.
These four helpers implement the Windows-native pattern instead, and are
shared by every tab that shows one.

Bind them together -- they are three halves of one behaviour:

    combo.bind("<KeyRelease>", lambda e: combobox_letter_jump(e, combo))
    combo.bind("<Down>", lambda e: combobox_arrow_nav(e, combo, +1))
    combo.bind("<Up>", lambda e: combobox_arrow_nav(e, combo, -1))
    bind_popdown_seek(combo)

`combobox_letter_jump` and `combobox_arrow_nav` act on the CLOSED combo;
`bind_popdown_seek` reaches into the open dropdown, which is not a
registered tkinter widget and has to be bound through Tcl.

Seeking goes through `ui/utils/type_ahead.py`, which is what makes a
dropdown and a list behave alike: a letter jumps, more letters narrow
the search, and the same letter again steps to the next match.
"""

import tkinter as tk

from .type_ahead import TypeAhead, attach, find


def combobox_letter_jump(event, combobox):
    """Type-ahead on a CLOSED readonly Combobox.

    A letter jumps to the next value starting with it, more letters
    narrow the same search, and the same letter again steps to the next
    match. `ui/utils/type_ahead.py` holds the timing and the rules.

    Keys that are not a seek fall through (return None) so Tk's default
    arrow handling still works.

    Fires <<ComboboxSelected>> on a successful jump so the bound handler
    reacts as if the user picked the entry with the mouse.

    Binds to <KeyRelease> instead of <KeyPress>: readonly ttk.Combobox's
    internal handler can swallow KeyPress before our binding sees it on
    some platforms; KeyRelease fires after Tk's default processing.
    """
    hit = attach(combobox).key(event.char)
    if hit is None:
        return None

    values = [str(v) for v in combobox["values"]]
    if not values:
        return "break"
    try:
        current = values.index(combobox.get())
    except ValueError:
        current = -1

    index = find(values, *hit, current=current)
    if index is not None:
        combobox.set(values[index])
        # readonly Combobox doesn't auto-select the displayed text
        # after a programmatic set(); force a full selection so the
        # whole name is highlighted, not just part.
        try:
            combobox.selection_clear()
            combobox.selection_range(0, "end")
        except tk.TclError:
            pass
        combobox.event_generate("<<ComboboxSelected>>")
    return "break"


def combobox_arrow_nav(event, combobox, direction):
    """Up / Down arrow navigation on a readonly Combobox.

    Tk's default behavior on a readonly ttk.Combobox: pressing Down OPENS
    the dropdown popup. This handler implements the Windows-native pattern
    where Up / Down step through entries in place WITHOUT opening the popup:
      * `direction` is +1 for Down, -1 for Up.
      * No wrap at the ends: at the first entry, Up does nothing; at the
        last entry, Down does nothing. Either way return "break" so Tk's
        default open-popup binding is suppressed.
      * Forces a full text selection after moving so the whole name is
        highlighted rather than partially.
      * `<<ComboboxSelected>>` is fired so the bound on_hero_select runs
        as if the user had clicked the entry.
    """
    values = list(combobox["values"])
    if not values:
        return "break"
    current = combobox.get()
    try:
        idx = values.index(current)
    except ValueError:
        # No current selection yet -- land on the first or last entry.
        idx = -1 if direction > 0 else len(values)
    new_idx = idx + direction
    # No wrap-around. Out of range -> stay put.
    if new_idx < 0 or new_idx >= len(values):
        return "break"
    combobox.set(values[new_idx])
    try:
        combobox.selection_clear()
        combobox.selection_range(0, "end")
    except tk.TclError:
        pass
    combobox.event_generate("<<ComboboxSelected>>")
    return "break"


def popdown_listbox_seek(combobox, listbox_path, hit):
    """Type-ahead seek inside an OPEN combobox dropdown list.

    `hit` is what `TypeAhead.key` returned. Moves the popdown listbox's
    highlight and does NOT commit the value -- that happens on Enter or a
    click, same as native behaviour.

    Operates on the listbox through its Tcl path: the popdown is not a
    registered tkinter widget, so nothing here can go through `.bind` or
    a widget method.
    """
    tkc = combobox.tk
    try:
        size = int(tkc.call(listbox_path, "size"))
    except tk.TclError:
        return
    if size == 0:
        return
    values = [str(tkc.call(listbox_path, "get", i)) for i in range(size)]
    try:
        current = int(tkc.call(listbox_path, "index", "active"))
    except (tk.TclError, ValueError):
        current = -1

    index = find(values, *hit, current=current)
    if index is None:
        return
    tkc.call(listbox_path, "selection", "clear", 0, "end")
    tkc.call(listbox_path, "selection", "set", index)
    tkc.call(listbox_path, "activate", index)
    tkc.call(listbox_path, "see", index)


def bind_popdown_seek(combobox):
    """Enable type-ahead seek on a readonly Combobox's OPEN dropdown list.

    Tk's ttk combobox popdown doesn't implement letter-seek while open; its
    internal listbox lives at "<popdown>.f.l". We obtain the popdown via
    ttk::combobox::PopdownWindow (which creates it on demand, so this can run
    at setup time) and bind at the Tcl level -- the popdown listbox is not a
    registered tkinter widget, so a normal .bind() can't reach it.

    The whole thing is wrapped in try/except so that on any Tk build where
    the internal widget path differs, it silently no-ops: the open-list seek
    just won't work, while the closed-combo letter-jump (_combobox_letter_
    jump) and arrow-nav keep functioning. 
    """
    try:
        popdown = combobox.tk.call("ttk::combobox::PopdownWindow", combobox)
    except tk.TclError:
        return
    listbox_path = f"{popdown}.f.l"

    # The OPEN list keeps its own prefix. It is a different search from
    # the closed combo's: what is highlighted here has not been committed,
    # so the two are looking at different current entries.
    seek = TypeAhead()

    def _on_key(char):
        # Anything that is not a seek key -- arrows, Enter, Escape --
        # returns "" so Tk's own listbox bindings keep working.
        hit = seek.key(char)
        if hit is None:
            return ""
        try:
            popdown_listbox_seek(combobox, listbox_path, hit)
        except tk.TclError:
            pass
        return "break"

    try:
        cmd = combobox.register(_on_key)
        # "+" appends to Tk's built-in listbox bindings rather than
        # replacing them; we run our command and issue a Tcl `break` only
        # when it returns "break" (i.e. a seek key was handled).
        script = f"+if {{[{cmd} %A] eq {{break}}}} {{ break }}"
        combobox.tk.call("bind", listbox_path, "<KeyPress>", script)
    except tk.TclError:
        pass
