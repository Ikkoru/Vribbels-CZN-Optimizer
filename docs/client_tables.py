"""Read the game client's own data tables and English text. Reads only.

    python docs/client_tables.py                     what is installed
    python docs/client_tables.py --list REGEX        archived paths
    python docs/client_tables.py --table NAME        one table, as TSV
    python docs/client_tables.py --text REGEX        English text by id or words

`--table` takes a table's archived name without `db/` and `.db`, such
as `event@event` or `char_base@char_combatant`; `--out FILE` writes the
TSV there instead of printing it, `--rows N` prints only the first N,
and `--client DIR` names an install other than the default one. What
each table holds, and what was checked against it, is
`docs/client_data.md`.

Two formats, both read as the ripper reads them
(github.com/cznrip/Chaos-Zero-Nightmare-ASSet-Ripper, MIT), which is
the reference when a patch changes either:

* **The archive** (`Archive`): `manifest.ssra` indexes every file; a
  file is a zstd frame at an offset into its GROUP's stream, the
  group's `.ssrc` chunks laid end to end in chunk-id order.
* **A table** (`table`): XORed with a repeating 256-byte key, then a
  container of named blobs -- row count, column names, and a row's
  values separated by zero bytes. The key is READ OFF THE DATA rather
  than written here, so a patch that changes it changes nothing.

**Every structural assumption is checked and fails by name**: a
manifest version or a table header this was not written against stops
the run saying which, rather than reading garbage. Python 3.14 for
`compression.zstd`; nothing else outside the standard library.
"""

import argparse
import collections
import re
import struct
import sys
from pathlib import Path

from compression import zstd

# STOVE's default install. `--client` names another.
CLIENT = Path(r"C:\ProgramData\Smilegate\Games\ChaosZeroNightmare")
GAMERES = Path("bin") / "appdata" / "cznlive" / "gameres"

# The manifest layout this reads. A different version is a different
# layout until shown otherwise.
SSRA_VERSION = 4
SSRA_HEADER = "<4s5I5Q"      # magic, version, build, chunks, files,
                             # flags, then string table offset and size,
                             # chunk and file table offsets, one more
CHUNK_ENTRY = "<IHHQQQ"      # id, group, -, length, stored length, -
FILE_ENTRY = "<IIQIIIIBBHI"  # -, -, offset, stored, length, -, name,
                             # compressed, encrypted, group, flags
DELETED = 1                  # a file entry's flag bit

# A table's magic once decrypted, and its header's own stated size.
MAGIC = b"PLPcK"
TABLE_HEADER = "<5sBHBQIIBIQ"
TABLE_HEADER_SIZE = 0x26

# The table the key is read from: large enough that every one of the
# 256 positions holds thousands of bytes, most of them zero.
KEY_SOURCE = "text/en/text.db"
TEXT_TABLE = "text/en/text.db"


def _cstr(blob, offset):
    return blob[offset:blob.find(b"\0", offset)].decode("utf-8", "replace")


class Archive:
    """The client's archive: its index, and any file in it by path."""

    def __init__(self, client=CLIENT):
        self.root = Path(client) / GAMERES
        data = (self.root / "manifest.ssra").read_bytes()
        (magic, version, self.build, chunks, files, _flags, str_off,
         str_size, chunk_off, file_off, _extra) = struct.unpack_from(
            SSRA_HEADER, data, 0)
        if magic != b"SSRA":
            raise ValueError(f"manifest.ssra starts {magic!r}, not SSRA")
        if version != SSRA_VERSION:
            raise ValueError(
                f"manifest.ssra is version {version}; this reads "
                f"{SSRA_VERSION}. Compare the ripper's SSRArchive.cpp.")
        strings = data[str_off:str_off + str_size]
        self.groups = self._groups(data, str_off + str_size)
        self.streams = self._streams(data, chunk_off, chunks)
        self.files = {}
        for i in range(files):
            (_h, _u, offset, stored, length, _u2, name_off, compressed,
             encrypted, group, flags) = struct.unpack_from(
                FILE_ENTRY, data, file_off + i * struct.calcsize(FILE_ENTRY))
            if flags & DELETED:
                continue
            name = _cstr(strings, name_off).replace("\\", "/").strip("/")
            self.files[name] = (group, offset, stored, length,
                                bool(compressed), bool(encrypted))

    @staticmethod
    def _groups(data, at):
        """{group index: name}: `lang_en`, `base`, and so on. A chunk is
        named after its group, and only the groups the player installed
        have chunks on disk."""
        if data[at:at + 4] != b"GRPS":
            raise ValueError("no GRPS group table after the strings")
        count, _size = struct.unpack_from("<II", data, at + 4)
        names = at + 16 + count * 24
        return {idx: _cstr(data, names + name_off)
                for idx, name_off in (struct.unpack_from("<H2xI", data,
                                                         at + 16 + i * 24)
                                      for i in range(count))}

    def _streams(self, data, at, count):
        """{group: [(start, length, chunk file or None)]}. A chunk is
        matched to its file by STORED SIZE, not name: sizes are unique
        where names are not -- a group's chunk numbering skips where one
        is split in two parts."""
        by_size = collections.defaultdict(list)
        for path in (self.root / "chunks").glob("*.ssrc"):
            by_size[path.stat().st_size].append(path)
        laid = collections.defaultdict(list)
        size = struct.calcsize(CHUNK_ENTRY)
        for i in range(count):
            cid, group, _u, length, stored, _chk = struct.unpack_from(
                CHUNK_ENTRY, data, at + i * size)
            files = by_size.get(stored, [])
            laid[group].append((cid, length,
                                files[0] if len(files) == 1 else None))
        out = {}
        for group, chunks in laid.items():
            start, spans = 0, []
            for _cid, length, path in sorted(chunks):
                spans.append((start, length, path))
                start += length
            out[group] = spans
        return out

    def read(self, name):
        """The file's bytes, decompressed."""
        group, offset, stored, length, compressed, encrypted = \
            self.files[name]
        if encrypted:
            raise ValueError(f"{name} is encrypted, which this does not "
                             f"read")
        want = stored if compressed else length
        out = bytearray()
        for start, size, path in self.streams[group]:
            if start + size <= offset or offset + want <= start:
                continue
            if path is None:
                raise FileNotFoundError(
                    f"{name} is in group {self.groups.get(group)}, whose "
                    f"chunks are not installed")
            lo = max(offset, start) - start
            hi = min(offset + want, start + size) - start
            with open(path, "rb") as handle:
                handle.seek(lo)
                out += handle.read(hi - lo)
        blob = zstd.decompress(bytes(out)) if compressed else bytes(out)
        if len(blob) != length:
            raise ValueError(f"{name} read {len(blob)} bytes, its entry "
                             f"says {length}")
        return blob


def key_of(raw):
    """The repeating XOR key, aligned to `raw`'s start: the commonest
    byte at each of the 256 positions, a table being mostly zero bytes.
    Only a large table has enough of them at every position."""
    return bytes(collections.Counter(raw[k::256]).most_common(1)[0][0]
                 for k in range(256))


def _aligned(raw, key):
    """`key` turned to where `raw` starts: every table is XORed with the
    same 256 bytes, each from a position of its own."""
    for r in range(256):
        turned = key[r:] + key[:r]
        if all(raw[j] ^ turned[j] == MAGIC[j] for j in range(len(MAGIC))):
            return turned
    return None


def _decrypt(raw, key):
    key = _aligned(raw, key) if key else None
    key = key or key_of(raw)
    whole = (key * (len(raw) // 256 + 1))[:len(raw)]
    plain = (int.from_bytes(raw, "little")
             ^ int.from_bytes(whole, "little")).to_bytes(len(raw), "little")
    if not plain.startswith(MAGIC):
        raise ValueError("no rotation of the key turns this into a "
                         "PLPcK table: the cipher has changed")
    return plain


def _blobs(plain):
    """{name: data} of a decrypted table: a hash table of 40-bit
    offsets, each the head of a chain of (name, data) entries."""
    (_magic, _version, size, _u, _u1, _default, slots, hi, lo,
     _u5) = struct.unpack_from(TABLE_HEADER, plain, 0)
    if size != TABLE_HEADER_SIZE:
        raise ValueError(f"table header says {size:#x} bytes, not "
                         f"{TABLE_HEADER_SIZE:#x}: compare the ripper's "
                         f"DBParser.cpp")
    at = (hi << 32) + lo
    root_size, kind = struct.unpack_from("<IB", plain, at)
    if kind != 1 or root_size != 5 * (slots + 1):
        raise ValueError("a table's root entry is not its hash table")
    out = {}
    for i in range(slots):
        hi, lo = struct.unpack_from("<BI", plain, at + 5 + i * 5)
        entry = (hi << 32) + lo
        while entry:
            (_s, _k, name_len, data_len, nhi,
             nlo) = struct.unpack_from("<IBBIBI", plain, entry)
            start = entry + 15
            out[plain[start:start + name_len]] = plain[
                start + name_len:start + name_len + data_len]
            entry = (nhi << 32) + nlo
    return out


def table(raw, key=None):
    """(column names, rows as {column: text}) of a table's bytes. `key`
    is the master key (`key_of` a large table): a small table has too
    few bytes at each position to give its own."""
    blobs = _blobs(_decrypt(raw, key))
    count = struct.unpack_from("<I", blobs[b"\trows"])[0]
    width = struct.unpack_from("<I", blobs[b"\tcols"])[0]
    columns = [blobs[b"\t%d" % i].rstrip(b"\0").decode("utf-8", "replace")
               for i in range(width)]
    rows = []
    for r in range(count):
        values = blobs.get(blobs.get(b"\t\t%d" % r), b"").split(b"\0")
        rows.append({column: values[i].decode("utf-8", "replace")
                     if i < len(values) else ""
                     for i, column in enumerate(columns)})
    return columns, rows


class Client:
    """The archive, the master key and the English text, read once."""

    def __init__(self, client=CLIENT):
        self.archive = Archive(client)
        self.key = key_of(self.archive.read(KEY_SOURCE))
        self._text = None

    def table(self, name):
        """`name` as the archive names it without `db/` and `.db`."""
        return table(self.archive.read(f"db/{name}.db"), self.key)

    def text(self):
        """{text id: English}. A text id is `<table>@<column>@<row id>`,
        and a table's own text columns hold exactly that id."""
        if self._text is None:
            _columns, rows = table(self.archive.read(TEXT_TABLE), self.key)
            self._text = {row["id"]: row["text"] for row in rows}
        return self._text


def _tsv(columns, rows):
    clean = str.maketrans({"\t": " ", "\n": " ", "\r": " "})
    yield "\t".join(columns)
    for row in rows:
        yield "\t".join(row[c].translate(clean) for c in columns)


def main(argv=None):
    # The text holds characters a cp932 console cannot encode, and the
    # failure would land as a UnicodeEncodeError from print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--client", default=str(CLIENT))
    parser.add_argument("--list", metavar="REGEX")
    parser.add_argument("--table", metavar="NAME")
    parser.add_argument("--text", metavar="REGEX")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    client = Client(args.client)
    archive = client.archive
    if args.list:
        pattern = re.compile(args.list, re.I)
        for name in sorted(archive.files):
            if pattern.search(name):
                print(name)
    elif args.table:
        columns, rows = client.table(args.table)
        lines = list(_tsv(columns, rows[:args.rows] if args.rows else rows))
        if args.out:
            Path(args.out).write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
            print(f"{len(rows)} rows to {args.out}")
        else:
            print("\n".join(lines))
    elif args.text:
        pattern = re.compile(args.text, re.I)
        for key, value in client.text().items():
            if pattern.search(key) or pattern.search(value):
                print(f"{key}\t{value}")
    else:
        installed = sorted({archive.groups[g] for g, spans
                            in archive.streams.items()
                            if all(path for _s, _l, path in spans)})
        tables = sum(1 for n in archive.files if n.startswith("db/"))
        print(f"build {archive.build}, groups installed: "
              f"{', '.join(installed)}; {len(archive.files)} files, "
              f"{tables} tables, {len(client.text())} English texts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
