"""Asking before a save replaces a settings file that would not read.

A manager whose file failed to load (`is_corrupted()`) refuses every
write, so the first save after that has to say what becomes of the old
file, and on a yes `quarantine()` it: renamed beside itself by
`json_file.set_aside`, and the manager left empty for a fresh one.
"""

from tkinter import messagebox


def confirm_quarantine(manager, title, what, fresh):
    """Whether a save through `manager` may go ahead.

    Yes at once where the file read. Otherwise the user is asked, and
    the broken file set aside on a yes. `what` names the file ("presets
    file"), `fresh` what the new one starts with ("this preset").
    """
    if not manager.is_corrupted():
        return True
    if not messagebox.askyesno(
            title,
            f"The {what} is corrupted:\n\n"
            f"{manager.corruption_error}\n\n"
            f"Saving will rename the broken file (adding '_corrupted' to "
            f"its filename) and create a fresh one with {fresh}.\n\n"
            f"Continue?"):
        return False
    try:
        manager.quarantine()
    except Exception as e:
        messagebox.showerror(
            "Error", f"Failed to back up the broken file: {e}")
        return False
    return True
