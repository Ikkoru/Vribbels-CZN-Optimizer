"""Define a ttk style once per Tk interpreter, and not again.

**Every `ttk.Style` change re-measures every themed widget in the
program.** Configuring, laying out or mapping any style -- even one no
widget uses yet -- sends `<<ThemeChanged>>` to them all, and each asks
its geometry manager for a new size. A tab laid out before that then
lays out again, and a Treeview whose stretching column has filled its
space asks for that space as its own: the Combatants list takes 6px
from the detail beside it, for the rest of the session.

So a style is defined at startup, before anything is laid out -- see
`OptimizerGUI.configure_styles` -- and a tab built later that asks for
the same style finds it defined and changes nothing. A tab built on its
own, as the checks build one, defines it on the first ask.

Per INTERPRETER rather than per process: the checks build several Tk
roots in one run, and each needs the styles defined in its own.
"""


def first_time(style, key):
    """True the first time `key` is asked about in `style`'s interpreter."""
    name = "::vribbels_styles(%s)" % key
    if int(style.tk.call("info", "exists", name)):
        return False
    style.tk.call("set", name, 1)
    return True
