"""Event names and Excursion type counts read off the game client.

Four ways this goes wrong with nothing to show for it:

1. **A join picks up the wrong row, or none.** The wire names an event
   by its schedule id, which turns up in a different column of the
   client's event table for each kind of event, and some kinds are
   named in other tables altogether. A miss reads as the id, which
   looks like the program before any of this; a wrong row reads as a
   plausible name for another event. Held on a synthetic client here.
2. **The cache outlives a patch.** It is good only for the install and
   the build it was read at, and a stale one shows last patch's names
   with nothing to say so.
3. **The shipped table falls behind the client**, so a player whose
   client the program cannot read sees an older patch's names. Held to
   the installed client where its build is the one the table states.
4. **A long name pushes the Checklist off the window.** The Other
   column is as wide as its widest row and the grid cannot shrink it,
   so a name wider than the room left runs the last column off the
   right edge. The widest name the client holds is put among the live
   events and the tab measured at the default window size, at every UI
   scale offered, each in a process of its own: Tk caches a font given
   as a tuple per display, so a second root in one process measures
   text at the first one's size. Fonts round differently at each scale,
   so the widest name and the room left are not the same at any two.

Skips the window half where Tk cannot open a display or no capture is
on hand, and the client half where no client is installed.
"""

import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from ._harness import (add_source_to_path, newest_snapshot, note,
                       REPO_ROOT, SOURCE_ROOT)

NAME = "event names and Excursion counts follow the game client"

# What the injected event is filed under. Any Checklist group would do:
# the label is what is measured, not the reading beside it.
WIDEST_GROUP = "EVENT_SCHEDULE"


class _FakeClient:
    """Just enough of `game_client.Client` for its readers."""

    def __init__(self, tables, texts):
        self.tables = tables
        self.texts = texts

    def rows(self, name):
        return self.tables.get(name, [])

    def text(self):
        return self.texts


def _event(row_id, title, deleted="NO", **links):
    row = {"id": row_id, "title": title, "delete_flag": deleted,
           "link_event_schedule_id": "none", "multiple_link": "none",
           "multiple_key": "none"}
    row.update(links)
    return row


def _joins(gc):
    """The readers on a synthetic client. Returns complaints."""
    out = []
    texts = {
        "t_director": "Memoirs of the <color_red>Chief</>",
        "t_old": "An Old Name", "t_new": "The New Name",
        "t_trial": "Virtual Tactical Simulation",
        "t_trauma": "Successor's Guiding Light",
        "t_return": "Visit the Festival", "t_carnival": "Nightmare Carnival",
        "t_wide": "Wide" + chr(0x1F600) + " name",
        gc.COMBATANT_NAME % "30117": "Olga",
        gc.COMBATANT_NAME % "1052": "Narja",
    }
    tables = {
        gc.EVENT_TABLE: [
            _event("event_153", "t_director",
                   link_event_schedule_id="event_schedule_director_002"),
            _event("event_1", "t_old", deleted="YES",
                   multiple_link="event_shared_01"),
            _event("event_2", "t_new", multiple_link="event_shared_01"),
            _event("event_134", "t_trial",
                   multiple_key="event_combatant_trial_14"),
            _event("event_98", "t_trauma", multiple_link="evn_trc_30048_1"),
            _event("event_9", "t_wide", multiple_key="event_wide"),
            _event("event_10", "t_missing", multiple_key="event_untexted"),
        ],
        gc.TRAUMA_CODE_TABLE: [
            {"id": "evn_trc_30048_1",
             "link_trauma_code_schedule_id": "schedule_trc_30048"}],
        gc.EVENT_NAME_TABLES[0][0]: [
            {"multiple_link": "event_return_daily_check_02",
             "title": "t_return"}],
        gc.EVENT_NAME_TABLES[1][0]: [
            {"id": "countdown_attendance_1st", "content_desc": "t_carnival"}],
        gc.TRIAL_TABLE: [
            {"id": "event_combatant_trial_14",
             gc.TRIAL_LEAD: "combatant_trial_1052_1"},
            {"id": "event_combatant_trial_17",
             gc.TRIAL_LEAD: "combatant_trial_30117"}],
        gc.VISIT_TABLE: (
            [{"group": "normal_visit_1003"}] * 7
            + [{"group": "normal_visit_30117"}] * 11
            + [{"group": "normal_visit_20001"}]),
    }
    client = _FakeClient(tables, texts)
    names = gc.event_names(client)
    want = {
        "event_schedule_director_002": "Memoirs of the Chief",
        "event_153": "Memoirs of the Chief",
        "event_shared_01": "The New Name",
        "schedule_trc_30048": "Successor's Guiding Light",
        "event_return_daily_check_02": "Visit the Festival",
        "countdown_attendance_1st": "Nightmare Carnival",
        "event_combatant_trial_14": "Virtual Tactical Simulation - Narja",
        "event_combatant_trial_17": "Virtual Tactical Simulation - Olga",
        "event_wide": "Wide name",
    }
    for key, name in want.items():
        if names.get(key) != name:
            out.append(
                f"the client reader names {key!r} {names.get(key)!r}, not "
                f"{name!r}. Each kind of event reaches its name its own "
                f"way (`game_client.event_names`), and a miss reads as the "
                f"bare id on the Checklist.")
    for key in ("event_untexted", "none"):
        if key in names:
            out.append(
                f"the client reader named {key!r} ({names[key]!r}). A row "
                f"with no English text, or the table's `none`, names "
                f"nothing; named, it reads as some other event's name.")
    visits = gc.excursion_types(client)
    if visits != {1003: 7, 30117: 11}:
        out.append(
            f"Excursion types read {visits}, not {{1003: 7, 30117: 11}}. A "
            f"partner's single placeholder row has to be left out, or a "
            f"combatant whose list is not out yet reads 'n/1'.")
    items = gc.item_names(_FakeClient({}, {
        "item@name@4020001": "<color_red>Event Coin</>",
        "item@name@4020002": "",
        "item@name@x1": "Not an item",
        "item@desc@4020001": "Not a name"}))
    if items != {4020001: "Event Coin"}:
        out.append(
            f"item names read {items}, not {{4020001: 'Event Coin'}}. Only "
            f"`item@name@<res_id>` with text names an item, markup taken "
            f"out; anything else lands a description or a blank where the "
            f"Capture Log shows an item.")
    return out


def _accessors(gc):
    """The client's facts over the shipped table, the shipped table over
    nothing. Returns complaints."""
    from game_data import from_client
    out = []
    shipped_key, shipped_name = next(iter(from_client.EVENT_NAMES.items()))
    try:
        gc.use({"event_names": {shipped_key: "From This Client",
                                "event_new_one_9": "Brand New"},
                "excursion_types": {"1003": 12}})
        if gc.event_name(shipped_key) != "From This Client":
            out.append(
                f"{shipped_key!r} reads {gc.event_name(shipped_key)!r} "
                f"where this machine's client says 'From This Client'. "
                f"The installed client is the newer source and has to win "
                f"over the shipped table.")
        if gc.event_name("event_new_one_12") != "Brand New":
            out.append(
                "a numbered schedule no table names did not take the name "
                "every other member of its kind shares "
                "(`game_client.family_name`).")
        if gc.visit_types(1003) != 12:
            out.append(
                f"combatant 1003 reads {gc.visit_types(1003)} Excursion "
                f"types where this machine's client says 12.")
        gc.use(None)
        if gc.event_name(shipped_key) != shipped_name:
            out.append(
                f"with no client read, {shipped_key!r} reads "
                f"{gc.event_name(shipped_key)!r}, not the shipped "
                f"{shipped_name!r}.")
        if gc.event_name("event_nobody_named_this") is not None:
            out.append("an id nothing names came back named, where the "
                       "Checklist needs None to fall back to the id.")
        out.extend(_item_precedence(gc))
    finally:
        gc.use(None)
    return out


def _item_precedence(gc):
    """Item names: the program's tables over this machine's client, the
    client over the shipped table. Returns complaints."""
    from game_data import from_client
    from game_data.constants import NAMED_MATERIALS, item_names
    out = []
    own_id, (own_name, *_rest) = next(iter(NAMED_MATERIALS.items()))
    shipped_id = next(rid for rid in from_client.ITEM_NAMES
                      if rid not in item_names.__globals__["NAMED_MATERIALS"]
                      and rid not in item_names.__globals__["RECORDED_NAMES"])
    gc.use({"item_names": {"999999901": "Client Only Item",
                           str(shipped_id): "Client Over Shipped",
                           str(own_id): "Not The Program's"}})
    names = item_names()
    for rid, want, why in (
            (999999901, "Client Only Item",
             "an item only the client names has to be named, or the "
             "Capture Log shows its id"),
            (shipped_id, "Client Over Shipped",
             "this machine's client is newer than the shipped table"),
            (own_id, own_name,
             "a table of the program's own overrides the client; "
             "`--audit` lists where they disagree")):
        if names.get(rid) != want:
            out.append(f"item {rid} is named {names.get(rid)!r}, not "
                       f"{want!r}: {why}.")
    gc.use(None)
    if item_names().get(shipped_id) != from_client.ITEM_NAMES[shipped_id]:
        out.append(
            f"with no client read, item {shipped_id} is named "
            f"{item_names().get(shipped_id)!r}, not the shipped "
            f"{from_client.ITEM_NAMES[shipped_id]!r}: a player whose client "
            f"cannot be read sees its id in the Capture Log.")
    return out


def _manifest(folder, build, version=None):
    """A manifest header alone, which is all `build_of` reads."""
    import game_client as gc
    path = folder / gc.GAMERES / "manifest.ssra"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack(
        gc.SSRA_HEADER, b"SSRA", version or gc.SSRA_VERSION, build,
        0, 0, 0, 0, 0, 0, 0, 0))


def _cache(gc):
    """The cache answers only for the install and build it was read at.
    Returns complaints."""
    out = []
    work = Path(tempfile.mkdtemp())
    try:
        install, other = work / "game", work / "elsewhere"
        _manifest(install, 88)
        _manifest(other, 88)
        settings = work / "settings"
        settings.mkdir()
        facts = {"format": gc.CACHE_FORMAT, "install": str(install),
                 "build": 88, "event_names": {"a": "A"},
                 "excursion_types": {}}
        (settings / gc.CACHE_FILE).write_text(json.dumps(facts),
                                              encoding="utf-8")
        if gc.cached(settings, install) != facts:
            out.append("a cache read off this install at its current build "
                       "was not used, so every launch reads the client.")
        if gc.cached(settings, other) is not None:
            out.append("a cache read off another install was used.")
        _manifest(install, 89)
        if gc.cached(settings, install) is not None:
            out.append(
                "a cache read at build 88 was used for build 89. A patch "
                "has to outdate it, or the names stay last patch's.")
        _manifest(install, 88, version=gc.SSRA_VERSION + 1)
        if gc.build_of(install) is not None:
            out.append("a manifest of a version this was not written "
                       "against stated a build, where it should state "
                       "none and leave the shipped names standing.")
        _manifest(install, 88)
        (settings / gc.CACHE_FILE).write_text("{not json", encoding="utf-8")
        if gc.cached(settings, install) is not None:
            out.append("an unreadable cache was used.")
        if gc.find_install(str(install)) != install:
            out.append("a folder the user named, holding a manifest, was "
                       "not the install found.")
        if gc.find_install(str(work / "nothing")) == work / "nothing":
            out.append("a named folder with no manifest was taken as the "
                       "install.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _shipped(gc):
    """The shipped table: drawable, and current with the installed
    client where both state the same build. Returns complaints."""
    from game_data import from_client
    out = []
    path = SOURCE_ROOT / "game_data" / "from_client.py"
    text = path.read_text(encoding="utf-8")
    if any(ord(ch) > 127 for ch in text):
        out.append(f"{path.name} holds a character past ASCII. "
                   f"`docs/client_tables.py --ship` writes escapes.")
    for key, name in from_client.EVENT_NAMES.items():
        if gc.clean(name) != name:
            out.append(f"{path.name} names {key!r} {name!r}, which "
                       f"`game_client.clean` would change: markup, or a "
                       f"character Tk stalls on.")
            break
    install = gc.find_install()
    if install is None:
        note("no game client installed, so the shipped names were not "
             "held to one")
        return out
    build = gc.build_of(install)
    if build != from_client.BUILD:
        note(f"the shipped names are from build {from_client.BUILD} and "
             f"the installed client is build {build}: "
             f"`python docs/client_tables.py --ship` brings them level")
        return out
    spec = importlib.util.spec_from_file_location(
        "client_tables", REPO_ROOT / "docs" / "client_tables.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    if tool.shipped_source(gc.Client(install)) != text:
        out.append(
            f"{path.name} says build {build}, and the installed client of "
            f"that build reads differently. Rerun `python "
            f"docs/client_tables.py --ship` and review the diff; a hand "
            f"edit there is overwritten by the next one.")
    return out


def _build_checklist(scale_name, work, snap):
    """The Checklist at `scale_name` over `snap`, mapped at alpha 0."""
    import tkinter as tk
    from tkinter import ttk

    from ui import scaling
    scaling.set_scale(scale_name)

    import czn_optimizer_gui as gui
    import ui.tabs as tabs_pkg
    from ui.context import AppContext
    from optimizer.optimizer import GearOptimizer
    from config import AppConfig
    import settings_manager, preset_manager, character_preset_manager
    import optimizer_settings_manager, log_presets_manager
    import checklist_manager

    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    scaling.apply_font_scaling(root)
    style = ttk.Style()
    style.theme_use("clam")
    gui.OptimizerGUI.configure_styles(SimpleNamespace(
        style=style, colors=dict(gui.COLORS)))

    def load(cls):
        manager = cls(work)
        manager.load()
        return manager

    optimizer = GearOptimizer()
    optimizer.load_data(snap)
    sm = load(settings_manager.SettingsManager)
    notebook = ttk.Notebook(root)
    context = AppContext(
        root=root, notebook=notebook, optimizer=optimizer,
        capture_manager=None, config=AppConfig(sm), colors=dict(gui.COLORS),
        style=style, load_data_callback=None, refresh_callback=None,
        inventory_tab=None, heroes_tab=None, scoring_tab=None,
        optimizer_tab=None, recompute_upgrade_line_callback=None,
        settings_manager=sm,
        preset_manager=load(preset_manager.PresetManager),
        character_preset_manager=load(
            character_preset_manager.CharacterPresetManager),
        optimizer_settings_manager=load(
            optimizer_settings_manager.OptimizerSettingsManager),
        log_presets_manager=load(log_presets_manager.LogPresetsManager),
        checklist_manager=load(checklist_manager.ChecklistManager),
    )
    tab = tabs_pkg.ChecklistTab(notebook, context)
    notebook.add(tab.get_frame(), text="Checklist")
    notebook.pack(fill=tk.BOTH, expand=True)
    root.geometry("%dx%d" % (scaling.px(scaling.WINDOW_W),
                             scaling.px(scaling.WINDOW_H)))
    root.deiconify()
    return root, tab, optimizer


def _widest_name():
    """(schedule id, name) of the widest name the shipped table holds,
    in the Checklist's row font. Needs a Tk root."""
    import tkinter.font as tkfont
    from game_data import from_client
    from ui.tabs.checklist_tab import ROW_FONT
    font = tkfont.Font(font=ROW_FONT)
    return max(from_client.EVENT_NAMES.items(),
               key=lambda item: (font.measure(item[1]), item[0]))


def _measure(scale_name):
    """Every complaint about the widest name at one UI scale. Run in a
    process of its own."""
    add_source_to_path()
    from ui.tabs import checklist_tab as mod
    from ui.utils.presettle import _drain

    failures = []
    work = Path(tempfile.mkdtemp())
    live = SOURCE_ROOT / "settings"
    if live.exists():
        # A COPY: a refresh records event totals into checklist.json.
        shutil.copytree(live, work / "settings")
    try:
        root, tab, optimizer = _build_checklist(
            scale_name, work, newest_snapshot())
        try:
            key, name = _widest_name()
            now = time.time()
            groups = optimizer.raw_data.setdefault("event_schedules", {})
            groups.setdefault(WIDEST_GROUP, {})[key] = {
                "start_time": int(now - 3600),
                "end_time": int(now + 3 * 86400)}
            _drain(root, time.monotonic() + 30)
            tab.refresh_checklist()
            _drain(root, time.monotonic() + 30)
            failures.extend(_fits(root, tab, mod, key, name, scale_name))
        finally:
            root.destroy()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return failures


def _fits(root, tab, mod, key, name, scale):
    """The row naming `name` is drawn whole, and the tab still fits
    the default window. Returns complaints."""
    out = []
    row_key = mod.EVENT_KEY_PREFIX + key
    holder = None
    for title, (text, rows) in tab.column_texts.items():
        for each, label, _widest in rows:
            if each == row_key:
                holder = (title, text, label)
    if holder is None:
        return [f"At {scale} the injected event {key!r} drew no Checklist "
                f"row, so nothing about its width was measured."]
    title, text, label = holder
    if label != name:
        # Cut to fit: the whole name has to be one hover away.
        if tab._event_tips.get(row_key) != name:
            out.append(
                f"At {scale} the {key!r} row reads {label!r} and its "
                f"tooltip {tab._event_tips.get(row_key)!r}: a name cut "
                f"to fit has to keep the whole of itself in the tip, or "
                f"the rest of it is nowhere on the tab.")
        if not label.startswith(name[:3]):
            return out + [
                f"At {scale} the {key!r} row reads {label!r}, which is "
                f"not {name!r} cut short: the label is not the client's "
                f"name, so the widest case was not the one measured."]
        try:
            marked = bool(int(text.tag_cget(
                mod.EVENT_TIP_PREFIX + row_key, "underline") or 0))
        except (ValueError, Exception):              # noqa: BLE001
            marked = False
        if not marked:
            out.append(
                f"At {scale} the cut {label!r} is not underlined, so "
                f"nothing on screen says its whole name is a hover away.")
    at = text.search(label, "1.0", "end")
    if not at:
        return out + [f"At {scale} the {key!r} row's words {label!r} are "
                      f"not in the {title!r} column's text."]
    last = text.index(f"{at} lineend -1c")
    box = text.bbox(last)
    inside = text.winfo_width() - int(text.cget("borderwidth")) \
        - int(text.cget("padx"))
    if box is None or box[0] + box[2] > inside:
        out.append(
            f"At {scale} the {title!r} column's row for {name!r} runs "
            f"off its right end ({box} against {inside}px of Text). The "
            f"column is fitted to its widest label, so a row running off "
            f"it is that fitting gone wrong.")
    columns = sorted((frame for frame in tab._column_frames
                      if frame.winfo_ismapped()),
                     key=lambda w: w.winfo_rootx())
    if not columns:
        return out + [f"At {scale} no Checklist column mapped, so the fit "
                      f"was not measured."]
    edge = root.winfo_rootx() + root.winfo_width()
    over = columns[-1].winfo_rootx() + columns[-1].winfo_width() - edge
    if over > 0:
        out.append(
            f"At {scale}, with {name!r} among the live events, the "
            f"Checklist's last column runs {over}px past the right edge of "
            f"a default-sized window. The Other column is as wide as its "
            f"widest row and the grid cannot shrink it: a name wider than "
            f"`checklist_tab.EVENT_NAME_ROOM` is cut to that, so the room "
            f"is more than the tab has to give.")
    for left, right in zip(columns, columns[1:]):
        gap = right.winfo_rootx() - (left.winfo_rootx() + left.winfo_width())
        if gap < 0:
            out.append(f"At {scale}, with {name!r} live, two Checklist "
                       f"columns overlap by {-gap}px.")
    return out


def run():
    add_source_to_path()
    import game_client as gc

    failures = []
    failures.extend(_joins(gc))
    failures.extend(_accessors(gc))
    failures.extend(_cache(gc))
    failures.extend(_shipped(gc))

    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception as exc:                # noqa: BLE001
        note(f"Tk cannot open a display here ({type(exc).__name__}), so "
             f"the widest name was not measured")
        return failures
    if newest_snapshot() is None:
        note("no snapshot in Vribbels/snapshots/, so the widest name was "
             "not measured on a Checklist")
        return failures
    from ui import scaling
    for scale_name in scaling.SCALE_CHOICES:
        done = subprocess.run(
            [sys.executable, "-m", __name__, scale_name], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        lines = done.stdout.strip().splitlines()
        if done.returncode != 0 or not lines:
            failures.append(
                f"Measuring the Checklist at {scale_name} failed (exit "
                f"{done.returncode}): "
                f"{(done.stderr.strip() or done.stdout.strip())[-1200:]}")
            continue
        # The last line: whatever the app prints while it builds comes
        # before it.
        failures.extend(json.loads(lines[-1]))
    return failures


if __name__ == "__main__":
    print(json.dumps(_measure(sys.argv[1])))
