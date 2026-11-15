"""Whether a wanted reload runs now or waits for a login to go quiet.

A login saves the snapshot many times in a few seconds: the addon starts
each game with little of the account and saves as soon as the inventory
lands, then again as each table arrives. A window reloading on every one
of those shows a snapshot that is not whole yet, so its tabs go
backwards and then forwards. The addon keeps saving every frame, which
keeps a crash mid-login from losing anything; it is the RELOAD that
waits, until the saves have stopped for `LOGIN_QUIET_S` or the login
has run for `LOGIN_MAX_S`.

No toolkit here: the window that polls the capture asks this and does
what it says, so a different window can ask it the same way.
"""

# Seconds without a save after which a login counts as finished. A
# login's saves come under a second apart; a gap this long means the
# burst is over.
LOGIN_QUIET_S = 1.5

# Seconds after a login began at which the reload runs anyway, quiet or
# not: a game that keeps saving must not keep the window on the last
# session's data.
LOGIN_MAX_S = 10.0

HOLD = "hold"
RELOAD = "reload"


def decide(now, login_began, last_save_at):
    """HOLD or RELOAD, for a reload that has been asked for.

    `login_began` is when the newest login was announced, None with no
    login pending; `last_save_at` when the newest save was announced.
    With no login pending a save reloads at once, as it would with no
    hold at all.
    """
    if login_began is None:
        return RELOAD
    if now - login_began >= LOGIN_MAX_S:
        return RELOAD
    if last_save_at is not None and now - last_save_at >= LOGIN_QUIET_S:
        return RELOAD
    return HOLD
