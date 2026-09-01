"""Type-ahead has to behave the way Windows Explorer does.

Every list and dropdown in the app seeks through one helper, and the
rules it follows are the kind nobody notices breaking: a search that
stops accumulating still finds SOMETHING on every keystroke, just the
wrong entry. Nothing raises, nothing looks wrong in a screenshot, and
the only symptom is that a name two keys long cannot be reached.

Exercising it needs no Tk -- the helper is a prefix and a clock -- so
the semantics are pinned here rather than left to a maintainer noticing
that typing `fe` lands on `Fabien`.
"""

import time

from ._harness import add_source_to_path

NAME = "type-ahead matches Explorer"

NAMES = ["Adelheid", "Arabella", "Fabien", "Fast Crit", "Fei", "Licinia"]


def _seek(TypeAhead, find, keys, start=-1, pause_before=None):
    """Type `keys` and return where the selection ends up."""
    seek = TypeAhead()
    current = start
    for i, char in enumerate(keys):
        if pause_before is not None and i == pause_before:
            time.sleep(1.2)
        hit = seek.key(char)
        if hit is None:
            continue
        index = find(NAMES, *hit, current=current)
        if index is not None:
            current = index
    return NAMES[current] if current >= 0 else None


def run():
    add_source_to_path()
    from ui.utils.type_ahead import TypeAhead, find

    failures = []

    def expect(keys, want, why, **kw):
        got = _seek(TypeAhead, find, keys, **kw)
        if got != want:
            failures.append(
                f"typing {keys!r} lands on {got!r}, not {want!r} -- {why}"
            )

    expect("a", "Adelheid", "one letter jumps to the first match")
    expect("aa", "Arabella",
           "the SAME letter again steps to the next match, which is what a "
           "single key did before there was a prefix at all")
    expect("aaa", "Adelheid", "and cycles back round")
    expect("fa", "Fabien", "a growing prefix keeps a match that still fits")
    expect("fas", "Fast Crit",
           "a growing prefix reaches PAST the first match -- if it cycled "
           "instead, no name sharing an initial could ever be reached")
    expect("fe", "Fei", "two letters skip the entry one letter found")
    expect("fast c", "Fast Crit",
           "a space inside a prefix is part of the name, not a separator")
    expect(" a", "Adelheid",
           "a LEADING space starts no search: it is a selection key in most "
           "lists, and a prefix beginning with one matches nothing")
    got = _seek(TypeAhead, find, "fa", pause_before=1)
    if got != "Adelheid":
        failures.append(
            f"typing 'f', pausing, then 'a' lands on {got!r}, not 'Adelheid' "
            f"-- the prefix has to expire, or a search abandoned minutes ago "
            f"silently prepends itself to the next one"
        )
    expect("zz", None, "no match leaves the selection where it was",
           start=-1)

    # The cycle flag is what separates the two behaviours, and reading it
    # directly is the only way to tell a correct answer from a lucky one.
    seek = TypeAhead()
    if seek.key("a") != ("a", True):
        failures.append("a fresh prefix must cycle: its match may be where "
                        "the selection already is")
    if seek.key("b") != ("ab", False):
        failures.append("a growing prefix must NOT cycle: the entry the "
                        "shorter prefix found has to stay reachable")

    return failures
