"""Type-ahead seek, the way Windows Explorer does it.

One letter jumps to the next entry starting with it. Keep typing and the
letters ACCUMULATE into a prefix, so `fa` finds `Fast Crit` past
`Fabien` -- and press the same letter again and it steps through the
entries starting with it instead, which is the behaviour a single key
had before there was a buffer.

The buffer expires: after `RESET_MS` of no typing the next key starts a
new search. Without that, a search begun minutes ago would silently
prepend itself to the next one and nothing on screen would say why.

Every list and dropdown in the app seeks through this, so they behave
alike and a rule about matching is written once. Each widget needs its
OWN `TypeAhead` -- a shared buffer would let a keystroke in the
combatant list narrow the preset list's search.

    seek = TypeAhead()
    ...
    hit = seek.key(event.char)
    if hit is None:
        return None                      # not a seek key: let Tk have it
    index = find(labels, *hit, current=selected)
"""

import time


# How long a partial prefix stays live, in milliseconds. Windows uses
# about a second; longer makes an abandoned search surprise the next one,
# shorter makes a two-word name impossible to type.
RESET_MS = 1000


class TypeAhead:
    """The accumulated prefix for one widget."""

    def __init__(self, reset_ms=RESET_MS):
        self._reset_ms = reset_ms
        self._buffer = ""
        self._last = 0.0

    def key(self, char):
        """Feed one character.

        Returns `(prefix, cycle)`, or None when the character is not a
        seek key and the caller should let Tk handle it.

        `cycle` says to start the search PAST the current entry rather
        than at it. A fresh prefix cycles, so pressing `a` twice moves to
        the second `a` entry; a GROWING prefix does not, so the entry the
        shorter prefix just found stays put while the longer one is still
        typed.
        """
        if not char or not char.isprintable():
            return None
        # A leading space is a selection key in most lists and starts no
        # useful search; inside a prefix it is part of a name.
        if char == " " and not self._buffer:
            return None

        now = time.monotonic() * 1000
        if now - self._last > self._reset_ms:
            self._buffer = ""
        self._last = now
        self._buffer += char

        # `aaa` is not a prefix anybody means -- it is the same key
        # pressed three times to reach the third match.
        if len(self._buffer) > 1 and len(set(self._buffer)) == 1:
            return self._buffer[0], True
        return self._buffer, len(self._buffer) == 1

    def reset(self):
        """Drop the prefix, for a widget that has lost focus."""
        self._buffer = ""


def find(labels, prefix, cycle, current=-1):
    """Index of the entry `prefix` selects, or None.

    `current` is where the selection is now; -1 for none. Matching is
    case-insensitive and wraps, so a search never fails because it began
    below its own answer.
    """
    total = len(labels)
    if not total or not prefix:
        return None
    if current < 0:
        start = 0
    elif cycle:
        start = (current + 1) % total
    else:
        start = current % total
    lowered = prefix.lower()
    for offset in range(total):
        index = (start + offset) % total
        if str(labels[index]).lower().startswith(lowered):
            return index
    return None


def attach(widget):
    """The widget's own `TypeAhead`, created on first use.

    For the helpers that take a widget rather than owning one -- a free
    function cannot hold per-widget state, and a dict keyed by widget
    would outlive the widgets in it.
    """
    seek = getattr(widget, "_type_ahead", None)
    if seek is None:
        seek = TypeAhead()
        widget._type_ahead = seek
    return seek
