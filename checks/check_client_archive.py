"""The client archive keeps every build whole, and gives each one back.

`client_archive` is insurance: it is read only once a patch has made
the game client unreadable, which is exactly when a fault in it would
first show, with the builds it lost no longer installed anywhere. Held
on a synthetic client of three builds:

1. **A build comes back exactly as it went in**: every table, every
   text, from `latest.zip` for the newest and from `history.xz` for the
   rest.
2. **History stores a table once** however many builds share it, and
   tables identical within a build once between them, each still given
   back under its own name.
3. **A build is archived once**: the newest again changes nothing, and
   history never holds the newest.
4. **The index can go**: `builds` rebuilds it from `history.xz`.
5. **The opt-in holds**: nothing is wanted without the folder.
6. **A leftover copy from a killed write** does not stop the next one.
"""

import lzma
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "the client archive gives every archived build back whole"


class _Client:
    """Just enough of `game_client.Client` for `client_archive`."""

    def __init__(self, build, tables, text, stubs=()):
        self._tables = tables
        self._text = text
        self._stubs = set(stubs)
        files = {f"db/{name}.db": None for name in [*tables, *stubs]}
        files["text/en/text.db"] = None
        self.archive = SimpleNamespace(build=build, files=files)

    def table(self, name):
        if name in self._stubs:
            raise IndexError("a stub the reader cannot decode")
        return self._tables[name]

    def text(self):
        return dict(self._text)


def _builds():
    """Three builds: a table and a text group change at each step, one
    table and one group never do, and two tables are identical."""
    same = (["id", "v"], [{"id": "1", "v": "same"}])
    twin = (["id"], [{"id": "twin"}])
    base_text = {"ui@a": "Unchanged", "plain_key": "No group"}
    one = _Client(1, {"same@same": same, "moves@moves": (["id"], [{"id": "a"}]),
                      "twin_a@t": twin, "twin_b@t": twin},
                  {**base_text, "card@name@x": "First"}, stubs=["stub"])
    two = _Client(2, {"same@same": same, "moves@moves": (["id"], [{"id": "b"}]),
                      "twin_a@t": twin, "twin_b@t": twin},
                  {**base_text, "card@name@x": "Second"}, stubs=["stub"])
    three = _Client(3, {"same@same": same, "moves@moves": (["id"], [{"id": "c"}]),
                        "twin_a@t": twin, "twin_b@t": twin},
                    {**base_text, "card@name@x": "Third"}, stubs=["stub"])
    return one, two, three


def _same(archived, client):
    """Where an archived build differs from the client it came from."""
    out = []
    for name in client._tables:
        columns, rows = archived.table(name)
        if (columns, rows) != (list(client._tables[name][0]),
                               list(client._tables[name][1])):
            out.append(f"table {name}")
    if archived.text() != client._text:
        out.append("the text")
    names = {n[3:-3] for n in archived.archive.files if n.startswith("db/")}
    if names != set(client._tables):
        out.append(f"the table list ({sorted(names)})")
    return out


def run():
    add_source_to_path()
    import client_archive as ca

    out = []
    one, two, three = _builds()
    work = Path(tempfile.mkdtemp())
    folder = work / ca.FOLDER
    try:
        if ca.needs(folder, 1):
            out.append("an archive was wanted with no `client_archive/` "
                       "folder: the folder is the opt-in, and without it "
                       "every player's program would keep the game's data.")
        ca.archive(one, folder)
        if ca.latest_build(folder) != 1 or (folder / ca.HISTORY).exists():
            out.append("the first build archived did not land in latest.zip "
                       "alone.")
        if ca.needs(folder, 1) or not ca.needs(folder, 2):
            out.append("`needs` asked for the build the archive holds, or "
                       "not for a new one: a launch would archive every time, "
                       "or never again.")
        if "already" not in ca.archive(one, folder):
            out.append("archiving the newest build again did something.")
        (folder / (ca.HISTORY + ".tmp")).write_bytes(b"a killed write")
        ca.archive(two, folder)
        ca.archive(three, folder)
        held = ca.builds(folder)
        if held != [1, 2, 3]:
            out.append(f"the archive lists builds {held}, not [1, 2, 3].")
        lzma.decompress((folder / ca.HISTORY).read_bytes())
        for build, client in ((1, one), (2, two), (3, three)):
            try:
                archived = ca.open_build(folder, build)
            except KeyError as exc:
                out.append(f"build {build} could not be opened: {exc}")
                continue
            for what in _same(archived, client):
                out.append(f"build {build}'s {what} came back changed from "
                           f"the archive: the insurance would hand a later "
                           f"reader the wrong data.")
        lines = [line for line in lzma.decompress(
            (folder / ca.HISTORY).read_bytes()).decode("utf-8").splitlines()
                 if line.startswith(ca.BLOB_HEAD)]
        # Build 1: same, moves, the twins once, and its three text
        # groups; build 2 adds only its moves and its card text.
        if len(lines) != 3 + 3 + 2:
            out.append(f"history.xz holds {len(lines)} blobs for builds 1 and "
                       f"2, where 8 cover them: a table no patch touched, or "
                       f"two identical ones, are being stored again.")
        manifests = list(ca._manifests(folder))
        if [m["build"] for m in manifests] != [1, 2]:
            out.append("history.xz holds the newest build, or not every older "
                       "one.")
        if manifests and manifests[0].get("undecoded") != ["stub"]:
            out.append("a db file the reader could not decode went unrecorded: "
                       "a patch that breaks one table would go unseen.")
        (folder / ca.INDEX).unlink()
        if ca.builds(folder) != [1, 2, 3]:
            out.append("with its index gone, the archive did not rebuild it "
                       "from history.xz.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("the index forgets every blob", "client_archive:_index",
     ['return {"builds": list(held["builds"]), "blobs": set(held["blobs"])}',
      'return {"builds": builds, "blobs": blobs}'],
     ['return {"builds": [], "blobs": set()}',
      'return {"builds": [], "blobs": set()}'],
     "are being stored again"),
    ("a text lost on the way back", "client_archive:Archived.text",
     "merged.update(json.loads(self._load(held)))",
     "merged.update({k: v for k, v in json.loads(self._load(held)).items() "
     "if k != 'plain_key'})",
     "came back changed from the archive"),
    ("the opt-in ignored", "client_archive:needs",
     "return (build is not None and folder.is_dir()\n"
     "            and latest_build(folder) != build)",
     "return True", "the folder is the opt-in"),
]
