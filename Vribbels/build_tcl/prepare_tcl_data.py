"""Unpack Tcl/Tk's library files for PyInstaller, when it cannot.

**Python 3.14 ships Tcl/Tk 9, whose library is a ZIP inside the DLL.**
`info library` answers `//zipfs:/lib/tcl/tcl_library` -- a path in Tcl's
own virtual filesystem, which nothing outside Tcl can stat. PyInstaller
6.20 asks that question, cannot find the directory, collects zero data
files, and then its own runtime hook raises at startup:

    FileNotFoundError: Tcl data directory
    "...\\_MEI597602\\_tcl_data" not found.

The build succeeds and the executable dies on its first line, which is
the worst place for this to surface.

The files themselves are on disk, as `tcl/libtcl9.*.zip` and
`tcl/libtk9.*.zip` beside the interpreter. This unpacks them to the two
directory names the runtime hook looks for, and `zCreate exe.bat` adds
them to the bundle.

**It does nothing when PyInstaller can collect them itself.** A newer
PyInstaller, or an older Python whose Tcl 8.6 keeps its library in a
real directory, needs no help -- and adding a second copy on top of the
one PyInstaller found would be two sources writing one destination. So
the output directories are REMOVED in that case, and the bat's `if
exist` is what reads the answer.
"""

import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The names PyInstaller's runtime hook looks for under `sys._MEIPASS`,
# and the directory inside each zip whose contents belong there.
TARGETS = (
    ("_tcl_data", "libtcl9*.zip", "tcl_library"),
    ("_tk_data", "libtk9*.zip", "tk_library"),
)


def library_dirs():
    """Where a Python install keeps its Tcl/Tk library zips."""
    seen, out = set(), []
    for prefix in (sys.base_prefix, sys.prefix, sys.base_exec_prefix):
        candidate = Path(prefix) / "tcl"
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def pyinstaller_collects_them():
    """True when PyInstaller finds the Tcl/Tk data on its own.

    Its answer, not a version check: what matters is whether the hook
    comes back with files, and that depends on the Tcl build as much as
    on PyInstaller.
    """
    try:
        from PyInstaller.utils.hooks.tcl_tk import tcltk_info
    except Exception as e:                    # not installed, or moved
        print(f"  cannot ask PyInstaller ({type(e).__name__}), unpacking "
              f"anyway")
        return False
    return bool(tcltk_info.data_files)


def unpack(zip_path, root, into):
    """Every member under `root/` in `zip_path`, written flat into `into`."""
    if into.exists():
        shutil.rmtree(into)
    written = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            if not parts or parts[0] != root:
                continue
            target = into.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            written += 1
    return written


def main():
    if pyinstaller_collects_them():
        print("PyInstaller collects Tcl/Tk itself; nothing to unpack.")
        for name, _pattern, _root in TARGETS:
            if (HERE / name).exists():
                shutil.rmtree(HERE / name)
        return 0

    searched = library_dirs()
    for name, pattern, root in TARGETS:
        found = next((match for folder in searched
                      for match in sorted(folder.glob(pattern))), None)
        if found is None:
            print(f"FAILED: no {pattern} in " +
                  ", ".join(str(f) for f in searched))
            return 1
        count = unpack(found, root, HERE / name)
        if not count:
            print(f"FAILED: {found.name} holds no {root}/ members")
            return 1
        print(f"  {found.name} -> {name} ({count} files)")

    # The two files Tcl and Tk each look for FIRST. Their absence is
    # what the executable would report, at startup, as a missing data
    # directory -- so it is worth failing here instead.
    for name, first in (("_tcl_data", "init.tcl"), ("_tk_data", "tk.tcl")):
        if not (HERE / name / first).exists():
            print(f"FAILED: {name}/{first} is missing; Tcl would not start")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
