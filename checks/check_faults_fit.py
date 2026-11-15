"""Every check's FAULTS still names code that exists.

A fault replaces an exact piece of a definition's source. When the code
it breaks is edited -- by hand, or by a lint's automatic fix -- the
piece no longer occurs, and `faults.py` refuses to run that check's
faults at all. Nothing else notices: the check itself still passes, and
the proof that it can fail has quietly gone. This runs the same anchor
test `faults.py` runs first, for every check, without running a fault.
"""

from ._harness import add_source_to_path

NAME = "every check's FAULTS still fits the code"


def run():
    add_source_to_path()
    from checks import faults
    out = []
    for check in faults._checks_with_faults():
        for fault in check.FAULTS:
            problem = faults.anchor_problems(fault)
            if problem:
                out.append(
                    f"{check.__name__.rsplit('.', 1)[-1]}: {problem}. "
                    f"`python checks/faults.py` will not run this check's "
                    f"faults until FAULTS names the code as it now is.")
    return out


def _an_anchor_gone_stale():
    """Another check's fault names text its code no longer holds, as an
    edit to the code would leave it."""
    from checks import check_login_hold
    name, where, _old, new, says = check_login_hold.FAULTS[0]
    check_login_hold.FAULTS[0] = (name, where, "text no code holds", new,
                                  says)


FAULTS = [
    ("a fault's anchor gone stale", _an_anchor_gone_stale, None, None,
     "will not run this check's faults"),
]
