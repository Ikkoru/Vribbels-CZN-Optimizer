"""Every game build's client data, kept for when a patch makes the
client unreadable.

The launch read (`game_client`) keeps only the facts the program uses.
This keeps everything the reader decodes -- every table and the English
text -- once per build, so `docs/client_tables.py`, research and the
program's own fallbacks can still read the last build that was
readable. It holds the game's own data: nothing here is shipped or
pushed.

**Opt-in by the folder's existence.** The program archives a build only
where `client_archive/` exists in its data folder; `python
docs/client_tables.py --archive` creates it and archives the installed
build. `docs/client_data.md`, *The archive*, is the reader's guide.

Two files, the newest build apart from the rest:

* `latest.zip` -- the newest build archived: `build.json`, one deflated
  entry per table (`tables/<name>.json`) and per text group
  (`text/<group>.json`, the text ids sharing what comes before their
  first `@`). Read a table at a time.
* `history.xz` -- every older build, in one file at xz's strongest
  setting (LZMA2, preset 9 extreme). One xz stream per build, appended
  when a newer build takes its place in `latest.zip`. A stream is JSON
  lines: every blob no earlier stream holds (`sha`, `data`), then the
  build's manifest (`build`, `read_at`, `undecoded`, and `tables` and
  `text`, each name to its blob's sha256). A table no patch touched is
  stored once, whatever the number of builds.

`history_index.json` lists the builds and blob hashes `history.xz`
holds, so an append need not read the archive back; it is rebuilt from
`history.xz` when missing or unreadable.

Each blob is written and read one at a time, so a whole build is never
in memory at once. Every file is written beside itself and moved into
place in one step, so a crash or a kill mid-write leaves the old file
whole.
"""

import hashlib
import json
import lzma
import os
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from json_file import write_json

FOLDER = "client_archive"
LATEST = "latest.zip"
HISTORY = "history.xz"
INDEX = "history_index.json"
# xz's strongest setting. Measured on one build's 194 MB of decoded
# tables and text: 9.2 MB in a minute, where zstd at level 19 with long
# matching gave 10.1 MB, and at level 22 9.4 MB in three.
PRESET = 9 | lzma.PRESET_EXTREME
# The text group for the text ids with no `@`, which no table name is.
NO_GROUP = "(none)"
# The English text, as `game_client` reads it.
TEXT_TABLE = "text/en/text.db"
# How a blob line of `history.xz` starts, and where its hash ends.
BLOB_HEAD = '{"sha":"'
SHA_END = len(BLOB_HEAD) + 64


def folder_of(data_dir):
    """Where the archive lives, under the program's data folder."""
    return Path(data_dir) / FOLDER


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value, sort_keys=False):
    """One blob as stored: compact, so a JSON line never breaks."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=sort_keys)


def _client_blobs(client, undecoded):
    """(kind, name, JSON text) for every table the reader decodes, then
    every text group, one at a time. The db files it could not decode
    are added to `undecoded`."""
    for path in sorted(client.archive.files):
        if not (path.startswith("db/") and path.endswith(".db")):
            continue
        name = path[3:-3]
        try:
            columns, rows = client.table(name)
        except Exception:                                # noqa: BLE001
            # Most of these are stubs with no rows to them; a table a
            # patch made unreadable is named in the build's record.
            undecoded.append(name)
            continue
        yield "tables", name, _json({"columns": columns, "rows": rows})
    groups = defaultdict(dict)
    for key, value in client.text().items():
        groups[key.split("@", 1)[0] if "@" in key else NO_GROUP][key] = value
    for group in sorted(groups):
        yield "text", group, _json(groups[group], sort_keys=True)


def latest_build(folder):
    """The build `latest.zip` holds, or None."""
    try:
        with zipfile.ZipFile(Path(folder) / LATEST) as z:
            return json.loads(z.read("build.json"))["build"]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def needs(folder, build):
    """Whether the program should archive `build`: the folder exists
    (the opt-in) and its newest build is another."""
    folder = Path(folder)
    return (build is not None and folder.is_dir()
            and latest_build(folder) != build)


def _history_lines(folder):
    """Every line of `history.xz`, across all its streams, as text."""
    path = Path(folder) / HISTORY
    if not path.exists():
        return
    with lzma.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield line


def _manifests(folder):
    """Every build's manifest in `history.xz`, oldest first."""
    for line in _history_lines(folder):
        if not line.startswith(BLOB_HEAD):
            yield json.loads(line)


def _index(folder):
    """{"builds": [...], "blobs": set}: the index, or one rebuilt from
    `history.xz` where it is missing or unreadable."""
    path = Path(folder) / INDEX
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        return {"builds": list(held["builds"]), "blobs": set(held["blobs"])}
    except (OSError, KeyError, TypeError, ValueError):
        pass
    builds, blobs = [], set()
    for line in _history_lines(folder):
        if line.startswith(BLOB_HEAD):
            blobs.add(line[len(BLOB_HEAD):SHA_END])
        else:
            builds.append(json.loads(line)["build"])
    return {"builds": builds, "blobs": blobs}


def _save_index(folder, index):
    write_json(Path(folder) / INDEX,
               {"builds": index["builds"], "blobs": sorted(index["blobs"])},
               indent=None)


def builds(folder):
    """Every build archived, oldest first: history's, then latest's."""
    held = list(_index(folder)["builds"])
    newest = latest_build(folder)
    if newest is not None and newest not in held:
        held.append(newest)
    return held


def _latest_record(folder):
    """latest.zip's `build.json`."""
    with zipfile.ZipFile(Path(folder) / LATEST) as z:
        return json.loads(z.read("build.json"))


def _latest_blobs(folder):
    """latest.zip's (kind, name, text), one at a time. The zip stays open
    only while this is drawn on: Windows will not replace an open file."""
    with zipfile.ZipFile(Path(folder) / LATEST) as z:
        for info in z.infolist():
            kind, _, rest = info.filename.partition("/")
            if kind in ("tables", "text") and rest.endswith(".json"):
                yield kind, rest[:-5], z.read(info).decode("utf-8")


def _replace(path, write):
    """Write `path` by way of a copy beside it: `write(handle)` fills the
    copy, which then takes the file's place in one step."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as out:
        write(out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)


def _roll_into_history(folder):
    """Append latest.zip's build to history.xz, storing only the blobs
    history lacks. A build history already holds is left alone."""
    folder = Path(folder)
    record = _latest_record(folder)
    index = _index(folder)
    if record["build"] in index["builds"]:
        return False
    manifest = {"build": record["build"], "read_at": record.get("read_at"),
                "undecoded": record.get("undecoded", []),
                "tables": {}, "text": {}}
    path = folder / HISTORY

    def write(out):
        if path.exists():
            with open(path, "rb") as old:
                while chunk := old.read(1 << 20):
                    out.write(chunk)
        # One stream per build: xz reads streams laid end to end as one
        # file, so an append is a stream written after the rest.
        packer = lzma.LZMACompressor(format=lzma.FORMAT_XZ, preset=PRESET)
        for kind, name, text in _latest_blobs(folder):
            sha = _sha(text)
            manifest[kind][name] = sha
            if sha not in index["blobs"]:
                index["blobs"].add(sha)
                line = BLOB_HEAD + sha + '","data":' + text + "}\n"
                out.write(packer.compress(line.encode("utf-8")))
        out.write(packer.compress((_json(manifest) + "\n").encode("utf-8")))
        out.write(packer.flush())

    _replace(path, write)
    index["builds"].append(record["build"])
    _save_index(folder, index)
    return True


def _write_latest(folder, client):
    """latest.zip for the client's build, in place of the old one.
    Returns how many blobs it holds and the db files left undecoded."""
    undecoded, count = [], 0

    def write(out):
        nonlocal count
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as z:
            for kind, name, text in _client_blobs(client, undecoded):
                z.writestr(f"{kind}/{name}.json", text)
                count += 1
            # Last, so the record names every db file left undecoded.
            z.writestr("build.json", _json({
                "build": client.archive.build,
                "read_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                "undecoded": undecoded}))

    _replace(Path(folder) / LATEST, write)
    return count, undecoded


def archive(client, folder):
    """Archive the client's build: the build latest.zip held moves into
    history.xz, and this one takes its place. Returns what was done, in
    words; a build already the newest is left as it is."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    build = client.archive.build
    held = latest_build(folder)
    if held == build:
        return f"build {build} is already archived"
    rolled = held is not None and _roll_into_history(folder)
    count, undecoded = _write_latest(folder, client)
    done = f"build {build} archived: {count} tables and text groups"
    if undecoded:
        done += f", {len(undecoded)} db files undecoded"
    if rolled:
        done += f"; build {held} moved into {HISTORY}"
    return done


class Archived:
    """One archived build, read the way `game_client.Client` is: `table`,
    `rows`, `text`, and `archive.build` and `archive.files` for code
    that lists the tables.

    `tables` and `text` map a name to its JSON text, or to a callable
    returning it, so a build in latest.zip is read a table at a time."""

    def __init__(self, build, tables, text):
        self._tables = tables
        self._text_groups = text
        self._text = None
        files = {f"db/{name}.db": None for name in tables}
        files[TEXT_TABLE] = None
        self.archive = SimpleNamespace(build=build, files=files)

    @staticmethod
    def _load(held):
        return held() if callable(held) else held

    def table(self, name):
        held = self._tables.get(name)
        if held is None:
            raise KeyError(f"build {self.archive.build} has no table {name!r}")
        value = json.loads(self._load(held))
        return value["columns"], value["rows"]

    def rows(self, name):
        return self.table(name)[1]

    def text(self):
        if self._text is None:
            merged = {}
            for held in self._text_groups.values():
                merged.update(json.loads(self._load(held)))
            self._text = merged
        return self._text


def _zip_reader(path, entry):
    def read():
        with zipfile.ZipFile(path) as z:
            return z.read(entry).decode("utf-8")
    return read


def open_build(folder, build=None):
    """An archived build as an `Archived`; None for the newest. Raises
    KeyError for a build the archive does not hold."""
    folder = Path(folder)
    newest = latest_build(folder)
    if build is None or build == newest:
        if newest is None:
            raise KeyError("the archive holds no build")
        path = folder / LATEST
        found = {"tables": {}, "text": {}}
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                kind, _, rest = info.filename.partition("/")
                if kind in found and rest.endswith(".json"):
                    found[kind][rest[:-5]] = _zip_reader(path, info.filename)
        return Archived(newest, found["tables"], found["text"])
    manifest = next((m for m in _manifests(folder) if m.get("build") == build),
                    None)
    if manifest is None:
        raise KeyError(f"the archive holds no build {build}")
    # One hash can stand for several names: identical tables are stored
    # once.
    wanted = defaultdict(list)
    for kind in ("tables", "text"):
        for name, sha in manifest[kind].items():
            wanted[sha].append((kind, name))
    found = {"tables": {}, "text": {}}
    for line in _history_lines(folder):
        if line.startswith(BLOB_HEAD):
            sha = line[len(BLOB_HEAD):SHA_END]
            if sha in wanted:
                # The blob is the line between `"data":` and its last `}`.
                text = line[SHA_END + len('","data":'):].rstrip()[:-1]
                for kind, name in wanted[sha]:
                    found[kind][name] = text
    missing = sum(len(names) for names in wanted.values()) \
        - len(found["tables"]) - len(found["text"])
    if missing:
        raise KeyError(f"build {build}: {missing} blobs missing from {HISTORY}")
    return Archived(build, found["tables"], found["text"])
