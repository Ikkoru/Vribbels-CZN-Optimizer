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
"""

import tkinter as tk


def combobox_letter_jump(event, combobox):
    """Letter-key navigation on a readonly Combobox: pressing 'A' jumps to
    the next value starting with 'A' (case-insensitive), cycling at the end.
    Non-alphanumeric keys fall through (return None) so Tk's default arrow
    handling still works.

    Fires <<ComboboxSelected>> on a successful jump so the bound handler
    (on_hero_select) reacts as if the user picked the entry with the mouse.

    Binds to <KeyRelease> instead of <KeyPress>: readonly ttk.Combobox's
    internal handler can swallow KeyPress before our binding sees it on
    some platforms; KeyRelease fires after Tk's default processing.

    
    """
    char = event.char
    if not char or not char.isalnum():
        return None
    char_lower = char.lower()

    values = list(combobox["values"])
    if not values:
        return "break"

    current = combobox.get()
    try:
        start = (values.index(current) + 1) % len(values)
    except ValueError:
        start = 0

    for offset in range(len(values)):
        idx = (start + offset) % len(values)
        if values[idx].lower().startswith(char_lower):
            combobox.set(values[idx])
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


def popdown_listbox_seek(combobox, listbox_path, char):
    """Type-ahead seek inside an OPEN combobox dropdown list.

    Moves the popdown listbox's highlight to the next entry starting with
    `char` (case-insensitive), cycling. Operates on the listbox via its Tcl
    path (it isn't a registered tkinter widget). Does NOT commit the value --
    that happens when the user presses Enter or clicks, same as native
    behavior; we only move the highlight.
    """
    if not char or not char.isalnum():
        return
    char_lower = char.lower()
    tkc = combobox.tk
    try:
        size = int(tkc.call(listbox_path, "size"))
    except tk.TclError:
        return
    if size == 0:
        return
    values = [str(tkc.call(listbox_path, "get", i)) for i in range(size)]
    try:
        cur = int(tkc.call(listbox_path, "index", "active"))
    except (tk.TclError, ValueError):
        cur = 0
    # Start one past the active entry so repeated presses cycle matches.
    for offset in range(1, size + 1):
        idx = (cur + offset) % size
        if values[idx].lower().startswith(char_lower):
            tkc.call(listbox_path, "selection", "clear", 0, "end")
            tkc.call(listbox_path, "selection", "set", idx)
            tkc.call(listbox_path, "activate", idx)
            tkc.call(listbox_path, "see", idx)
            return


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

    def _on_key(char):
        # Only alnum keys trigger a seek; everything else (arrows, Enter,
        # Escape) returns "" so Tk's own listbox bindings keep working.
        if not char or not char.isalnum():
            return ""
        try:
            popdown_listbox_seek(combobox, listbox_path, char)
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
