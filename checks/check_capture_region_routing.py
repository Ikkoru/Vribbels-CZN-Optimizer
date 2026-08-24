"""Both regions are redirected, and each connection goes to its own.

The Server Region used to pick which hostname got a `127.0.0.1` entry.
A game on the OTHER region never contacted that hostname, so its traffic
went straight past the proxy: no capture, no error, and -- until the
session-file fix -- a success line naming the previous run's snapshot.

So both hostnames are redirected now. That only works if each connection
is then forwarded to its own region's real server, because mitmproxy's
reverse mode has ONE upstream fixed at launch. The addon overrides it
per connection from the client's SNI.

Everything here drives the REAL generated addon, so a routing table that
stops being injected, or a hook that stops overriding, fails here rather
than by sending a global account to the asia server.
"""

import inspect
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture routes both regions"

GLOBAL_HOST = "live-g-czn-gamemjc2n1x.game.playstove.com"
ASIA_HOST = "live-czn-gamelksj2nmf.game.playstove.com"


class _Client:
    def __init__(self, sni):
        self.sni = sni


class _Server:
    def __init__(self):
        self.address = ("placeholder", 0)


class _HookData:
    def __init__(self, sni):
        self.client = _Client(sni)
        self.server = _Server()


def _build(tmp):
    """Generate and import the addon exactly as a capture would."""
    add_source_to_path()
    from capture.manager import CaptureManager

    mgr = CaptureManager(tmp, log_callback=lambda *a, **k: None)
    # Stand in for DNS so the check needs no network.
    mgr.game_server_ips = {GLOBAL_HOST: "10.0.0.1", ASIA_HOST: "10.0.0.2"}
    mgr.host_regions = {GLOBAL_HOST: "global", ASIA_HOST: "asia"}
    script = mgr._generate_addon_script(debug_mode=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location("_probe_region", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and hasattr(obj, "server_connect"):
            return mgr, mod, obj(Path(tmp))
    raise LookupError("no addon class with server_connect")


def run():
    failures = []
    tmp = tempfile.mkdtemp()
    try:
        mgr, mod, addon = _build(tmp)
    except Exception as e:
        return [f"could not build the addon: {type(e).__name__}: {e}"]

    logged = []
    addon.log_callback = lambda msg, *a, **k: logged.append(str(msg))

    if not getattr(mod, "REGION_ROUTES", None):
        return ["REGION_ROUTES was not injected into the addon. Without it "
                "every connection keeps mitmproxy's launch upstream, so one "
                "region reaches the wrong server."]

    for host, region, ip in ((GLOBAL_HOST, "global", "10.0.0.1"),
                             (ASIA_HOST, "asia", "10.0.0.2")):
        data = _HookData(host)
        addon.server_connect(data)
        if data.server.address[0] != ip:
            failures.append(
                f"SNI {host} was routed to {data.server.address[0]!r}, not "
                f"{ip!r}. A connection sent to the other region's server "
                f"cannot log in."
            )
        if addon.detected_region is None:
            failures.append(f"routing {host} recorded no detected region.")

    if addon.seen_regions != {"global", "asia"}:
        failures.append(
            f"both regions connected but seen_regions is "
            f"{addon.seen_regions!r}. Two games on different servers must "
            f"be noticed."
        )
    if not any("second server region" in m.lower() for m in logged):
        failures.append(
            f"two regions connected and nothing was logged: {logged!r}")

    # detected_region is what reaches the snapshot.
    if addon._detect_region() != addon.detected_region:
        failures.append(
            "_detect_region() no longer reports the observed region, so the "
            "snapshot's detected_region goes back to being always None.")

    # An unknown SNI leaves the launch upstream alone.
    data = _HookData("cdn.example.com")
    before = data.server.address
    addon.server_connect(data)
    if data.server.address != before:
        failures.append(
            "an unrecognised SNI was rerouted. Anything that is not a known "
            "game host must fall through to mitmproxy's launch upstream.")

    # No SNI at all must not raise.
    try:
        addon.server_connect(_HookData(None))
    except Exception as e:
        failures.append(
            f"a connection with no SNI raised {type(e).__name__}: {e}")

    # The hosts block covers every region.
    if "SERVERS.values()" not in inspect.getsource(mgr.modify_hosts_file):
        failures.append(
            "modify_hosts_file no longer redirects every region. Redirecting "
            "only the selected one is what let a game on the other region "
            "bypass the proxy entirely.")

    return failures
