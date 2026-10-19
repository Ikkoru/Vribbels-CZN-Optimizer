"""The notice of what a launch changed in the user's settings.

The startup sync brings every setting the user never changed to the
release's new default, and the re-work of the presets for a game patch's
substat rolls does the same to the presets (`defaults_sync`). Neither
asks first, so this says afterwards what moved, what was left though its
default moved, and where the files went before they changed -- with
Undo, which puts them back.

`notice_text` is the words, apart from any widget, so a check can read
them; `show` the dialog.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .scaling import px
from .title_bar import apply_title_bar
from .utils.button_width import BUTTON_W_LARGE, BUTTON_W_SMALL
from .utils.escape import close_on_escape
from .utils.scrolled_text import make_scrolled_text

TITLE = "Settings updated"

# Each kind of entry as the notice names it, in the order it lists them.
GROUP_WORDS = {
    "presets": "Gear Score presets",
    "reworked": "Gear Score presets, for the game's new substat rolls",
    "character_preset": "Combatant presets",
    "optimizer_settings": "Combatant settings",
    "settings": "Settings",
}

# An Optimizer setting as the Optimizer tab labels it.
FIELD_WORDS = {
    "optimize_for_level": "Optimize for LVL",
    "extra_pct": "Extra share",
    "dot_pct": "Agony share",
    "fracture_pct": "Fracture/Scorched share",
    "atk_def_split": "ATK/DEF split",
    "shielding_healing_weight": "Shielding & Healing",
    "force_main": "Force on a Slot",
    "have_at_least": "Have at least",
    "sets_selected": "Sets",
    "max_flex_slots": "Max Flex Slots",
    "set_effect_pcts": "set effect shares",
    "avg_card_dmg_pct": "average Card DMG",
    "avg_mult_buff_pct": "average buffs",
    "avg_add_buff_pct": "average buffs",
    "element_override": "Element override",
}

KEPT_HEADER = ("Left as they are, though their defaults changed (Restore "
               "Defaults offers the new ones):")

# The Setup & Settings switch, as its label reads on one line
# (`setup_tab.FOLLOW_TEXT`).
SWITCH_WORDS = "Update unchanged settings to new defaults"

# The text's font, as the app's other text panels set it, and its size:
# characters across, and the most lines it shows before it scrolls.
FONT = ("Segoe UI Variable Small", 11)
WIDTH = 80
MAX_LINES = 18


def _entries(entries):
    """{group: [what, ...]} in `GROUP_WORDS`' order, an Optimizer entry
    with the settings that moved after its name."""
    out = {}
    for entry in entries:
        what = str(entry.get("label"))
        fields = entry.get("fields")
        if fields:
            words = []
            for field in fields:
                word = FIELD_WORDS.get(field, field)
                if word not in words:
                    words.append(word)
            what = f"{what} ({', '.join(words)})"
        out.setdefault(entry.get("kind"), []).append(what)
    return {kind: out[kind] for kind in GROUP_WORDS if kind in out}


def notice_text(report, folder_word="settings"):
    """What `report` (`defaults_sync.report`) says, as the notice's
    lines: the backup first, where it is found if anything went wrong,
    then what was updated and what was left. "" where it says
    nothing."""
    if not report:
        return ""
    lines = []
    updated, kept = _entries(report.updated), _entries(report.kept)
    if updated:
        lines.append("Settings you never changed now have this version's "
                     "defaults.")
    if report.backup is not None:
        lines.append("Your files as they were: "
                     f"{folder_word}\\{report.backup.parent.name}\\"
                     f"{report.backup.name}")
    for header, groups in ((None, updated), (KEPT_HEADER, kept)):
        if not groups:
            continue
        if lines:
            lines.append("")
        if header:
            lines.append(header)
        lines += [f"{GROUP_WORDS[kind]}: {', '.join(names)}"
                  for kind, names in groups.items()]
    if updated:
        lines += ["", f"Setup & Settings turns this off: {SWITCH_WORDS}."]
    return "\n".join(lines)


def _wrapped_lines(text, font, width):
    """How many lines `text` takes in a Text `width` characters wide that
    wraps at words. Measured, because a Text wraps only once it is shown:
    before then it counts every character as a line."""
    room = font.measure("0") * width
    space = font.measure(" ")
    count = 0
    for line in text.split("\n"):
        count += 1
        used = 0
        for word in line.split(" "):
            size = font.measure(word)
            if used and used + size > room:
                count += 1
                used = 0
            used += size + space
    return count


def show(root, colors, report, *, on_undo, on_open):
    """Show the notice for `report`, centred on `root`, and return the
    dialog. `on_undo` is called by Undo, which is there only where a
    backup was made and something updated, and the dialog closes after
    it; `on_open` opens the backup folder."""
    dlg = tk.Toplevel(root)
    dlg.title(TITLE)
    dlg.transient(root)
    close_on_escape(dlg)
    try:
        dlg.configure(bg=colors["bg"])
    except tk.TclError:
        pass

    # spacing: content frame -> content frame -- frame, frame ↔↕
    outer = ttk.Frame(dlg, padding=px(4))
    outer.pack(fill=tk.BOTH, expand=True)

    text = notice_text(report)
    lines = _wrapped_lines(text, tkfont.Font(root=dlg, font=FONT), WIDTH)
    # No inset above the first line: this face's own line box carries
    # it, as in the Capture log.
    body = make_scrolled_text(outer, colors, wrap=tk.WORD, width=WIDTH,
                              height=min(MAX_LINES, max(4, lines)),
                              font=FONT, pady=0)
    body.insert("1.0", text)
    body.config(state=tk.DISABLED)
    body.pack(fill=tk.BOTH, expand=True)

    # spacing: content frame -> content frame -- text, button ↕
    # A button row under the text and inside no panel of its own, as in
    # the Restore Defaults dialog.
    buttons = ttk.Frame(outer)
    buttons.pack(fill=tk.X, pady=px((4, 0)))
    ttk.Button(buttons, text="OK", width=BUTTON_W_SMALL,
               command=dlg.destroy).pack(side=tk.RIGHT)
    if report.backup is not None:
        # spacing: button -> button -- button, button ↔
        ttk.Button(buttons, text="Open Backup Folder", width=BUTTON_W_LARGE,
                   command=on_open).pack(side=tk.RIGHT, padx=px((0, 4)))
        if report.updated:
            def undo():
                dlg.destroy()
                on_undo()
            # spacing: button -> button -- button, button ↔
            ttk.Button(buttons, text="Undo", width=BUTTON_W_SMALL,
                       command=undo).pack(side=tk.RIGHT, padx=px((0, 4)))

    dlg.update_idletasks()
    # Mapped by the line above, so its frame exists to colour.
    apply_title_bar(dlg, colors["fg"])
    try:
        width, height = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    return dlg
