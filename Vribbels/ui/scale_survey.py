"""The app at 200% against twice the app at 100%, widget by widget.

The spacing audit reads the gaps it has registered; this reads
everything else. Each scale is a launch of its own, rendered and never
shown like the audit's (`--scale-survey`, with `--audit-scale`), which
writes every mapped widget's place and size, and an image of every tab,
to `_tmp/scale_survey/<scale>/`. `compare` then holds the 200% build
to twice the 100% one: a 200% screen should show what a 100% one does,
so a widget whose size is not twice its 100% size is a distance that
did not scale, and one whose content no longer fits is clipped.

    python docs/scale_survey.py          runs both launches and compares

Widgets are matched by their Tk path, which the same build at either
scale names alike: the app constructs the same widgets in the same
order whatever the scale.
"""

import json
import time
from pathlib import Path

import audit_states
from ui import scaling
from ui.utils.window_render import render

SURVEY_DIR = Path(__file__).resolve().parents[2] / "_tmp" / "scale_survey"
CACHEDIR_TAG = (b"Signature: 8a477f597d28d172789f06886806bc55\n"
                b"# The scale survey's output: rebuilt by every run. See "
                b"Vribbels/ui/scale_survey.py.\n")

# How far a size may sit from twice its 100% value before it counts:
# text sized by the font does not double to the pixel, its glyphs
# being hinted at each size. A pixel either way, or a sliver of the
# size on a long string.
SLACK_PX = 2
SLACK_SHARE = 0.03


def run_dir(factor, state=None):
    """Where one launch's survey goes."""
    name = f"{round(factor * 100)}" + (f"_{state}" if state else "")
    return SURVEY_DIR / name


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _words(widget):
    """What a widget says, for naming it in a report."""
    try:
        if widget.winfo_class() == "Text":
            return widget.get("1.0", "1.end")[:40]
        return str(widget.cget("text"))[:40]
    except Exception:                                     # noqa: BLE001
        return ""


def _panel_of(widget, page):
    """The title of the nearest panel holding `widget`, or ''."""
    while widget is not None and widget is not page:
        if widget.winfo_class() == "TLabelframe":
            title = str(widget.cget("text"))
            if title:
                return title
        widget = widget.master
    return ""


def survey(app):
    """Write every tab's widgets and image at the running scale."""
    factor = scaling.factor()
    out = run_dir(factor, audit_states.requested())
    out.mkdir(parents=True, exist_ok=True)
    tag = SURVEY_DIR / "CACHEDIR.TAG"
    if not tag.exists():
        tag.write_bytes(CACHEDIR_TAG)
    root, notebook = app.root, app.notebook
    data = {"factor": factor,
            "window": [root.winfo_width(), root.winfo_height()],
            "tabs": {}}
    for tab_id in notebook.tabs():
        name = notebook.tab(tab_id, "text")
        notebook.select(tab_id)
        root.update()
        # The compositor's copy lags the paint; see `Capture.of_window`.
        time.sleep(0.3)
        root.update()
        page = root.nametowidget(tab_id)
        ox, oy = root.winfo_rootx(), root.winfo_rooty()
        rows = []
        for widget in _walk(page):
            if not widget.winfo_ismapped():
                continue
            rows.append({
                "id": str(widget), "cls": widget.winfo_class(),
                "x": widget.winfo_rootx() - ox,
                "y": widget.winfo_rooty() - oy,
                "w": widget.winfo_width(), "h": widget.winfo_height(),
                "rw": widget.winfo_reqwidth(), "rh": widget.winfo_reqheight(),
                "text": _words(widget), "panel": _panel_of(widget, page)})
        data["tabs"][name] = rows
        render(root).save(out / f"{_file_name(name)}.png")
    (out / "widgets.json").write_text(json.dumps(data), encoding="utf-8")
    print(f"scale survey: {len(data['tabs'])} tabs at {factor * 100}% "
          f"-> {out}")


def _file_name(tab):
    return "".join(c if c.isalnum() else "_" for c in tab)


def _off(at_high, at_one, factor):
    """How far a scaled size sits from `factor` times its 100% one, in
    whole pixels, or 0 where that is within the slack text sizes
    carry."""
    want = at_one * factor
    miss = at_high - want
    return (0 if abs(miss) <= max(SLACK_PX, want * SLACK_SHARE)
            else round(miss))


def compare(low_dir, high_dir):
    """Report lines: per tab and panel, each widget the higher scale
    sizes other than `factor` times the lower, and each it clips."""
    low = json.loads((low_dir / "widgets.json").read_text(encoding="utf-8"))
    high = json.loads((high_dir / "widgets.json").read_text(encoding="utf-8"))
    factor = high["factor"] / low["factor"]
    lines = [f"{round(high['factor'] * 100)}% against {factor:g} x "
             f"{round(low['factor'] * 100)}%: window {high['window']} "
             f"against {[round(v * factor) for v in low['window']]}"]
    for tab, rows in high["tabs"].items():
        before = {row["id"]: row for row in low["tabs"].get(tab, [])}
        found = []
        for row in rows:
            was = before.get(row["id"])
            if was is None or was["w"] <= 1 or was["h"] <= 1:
                continue
            dw = _off(row["w"], was["w"], factor)
            dh = _off(row["h"], was["h"], factor)
            clipped = []
            for side, size, req, was_size, was_req in (
                    ("wide", row["w"], row["rw"], was["w"], was["rw"]),
                    ("tall", row["h"], row["rh"], was["h"], was["rh"])):
                if req > size + 1 and not was_req > was_size + 1:
                    clipped.append(f"clipped {side}: shows {size} of {req}")
            if dw or dh or clipped:
                found.append((row["panel"], row, was, dw, dh, clipped))
        ids = {row["id"] for row in rows}
        only_low = sum(1 for key in before if key not in ids)
        only_high = sum(1 for key in ids if key not in before)
        lines.append("")
        lines.append(f"== {tab}: {len(found)} widgets off"
                     + (f", {only_low} mapped at the lower scale only"
                        if only_low else "")
                     + (f", {only_high} at the higher only"
                        if only_high else ""))
        for panel, row, was, dw, dh, clipped in sorted(
                found, key=lambda f: (f[0], f[1]["y"], f[1]["x"])):
            what = []
            if dw:
                what.append(f"w {row['w']} for {round(was['w'] * factor)} "
                            f"({dw:+d})")
            if dh:
                what.append(f"h {row['h']} for {round(was['h'] * factor)} "
                            f"({dh:+d})")
            what.extend(clipped)
            lines.append(f"  [{panel or '-'}] {row['cls']} "
                         f"{row['text']!r:.36} at {row['x']},{row['y']}: "
                         + "; ".join(what))
    return lines


def side_by_side(low_dir, high_dir, out_dir):
    """For each tab, the lower scale's image over the higher's shrunk to
    match, for reading by eye."""
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for high in sorted(high_dir.glob("*.png")):
        low = low_dir / high.name
        if not low.exists():
            continue
        a = Image.open(low)
        b = Image.open(high).resize(a.size, Image.LANCZOS)
        pair = Image.new("RGB", (a.width, a.height * 2 + 8), (255, 0, 255))
        pair.paste(a, (0, 0))
        pair.paste(b, (0, a.height + 8))
        target = out_dir / high.name
        pair.save(target)
        made.append(target)
    return made
