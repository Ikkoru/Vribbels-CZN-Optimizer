#!/usr/bin/env python3
"""Show that a check catches what it guards: break the code it guards
one fault at a time, and run the check against each.

    python checks/faults.py check_x [fault ...]  its faults, or those named
    python checks/faults.py --all                every check listing faults
    python checks/faults.py --list [check_x]     the checks, or its faults

`check_` may be left off a check's name. A check lists its faults in
`FAULTS`, beside its `run`, one tuple each:

    (name, where, old, new, says)

- `where` is "module:qualname", the module as `run` imports it and the
  name of a function, a method ("Class.method"), a class or a
  module-level assignment in it: "defaults_sync:_decide",
  "ui.defaults_notice:show". The fault replaces `old`, which must occur
  exactly once in that definition's source, with `new`; given lists of
  each, it makes every replacement in turn.
- Or `where` is a function of the check's own module that breaks
  something itself, such as a data file the check reads, with `old`
  and `new` None.
- `says` is a piece of the complaint the check must make. A complaint
  saying something else does not count: the fault was caught by luck,
  for another reason, and would not be next time.

Each fault runs in a process of its own, after a clean run that must
pass, each with a bytecode cache of its own. Nothing is written to the
source: the definition is compiled from its patched text and bound in
place of the old one, in its module and wherever a loaded module holds
it, so there is no stale bytecode to clear afterwards and an interrupted
run leaves nothing broken. A fault whose text no longer occurs exactly
once stops the run before anything runs: update FAULTS with the code it
breaks.

Out of reach this way: a method using zero-argument `super()`, which
has no class cell once compiled outside its class, and a number or a
short string another module copied with `from x import NAME` (those
are shared objects, so the copy is not rebound). Break those with a
function in the check instead.

Exit 0 when the clean run passes and every fault is caught -- a fault
that crashes the check counts, as run_all reports it as an error, but
is listed apart, since a check should say what broke rather than raise.
"""

import argparse
import ast
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Complaints quote the program's text, arrows and all; a cp932 console
# cannot print those.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from checks import run_all                                    # noqa: E402
from checks._harness import Skip, add_source_to_path, take_notes  # noqa: E402

# A fault's process ends on this, then its verdict as JSON.
VERDICT = "@@fault-verdict "
TIMEOUT_S = 900


# -------------------- finding and breaking a definition --------------------

def _defines(node, name):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                         ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name
                   for t in node.targets)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == name
    return False


def source_of(module_name):
    """(path, text) of a module under `Vribbels/`, without importing it."""
    add_source_to_path()
    spec = importlib.util.find_spec(module_name)
    if spec is None or not spec.origin:
        raise LookupError(f"no module {module_name}")
    path = Path(spec.origin)
    return path, path.read_text(encoding="utf-8")


def definition(source, qualname):
    """(first line, text) of the statement defining `qualname` in
    `source`, decorators and all; the last one where it is defined twice,
    as that is the one in force."""
    body, node = ast.parse(source).body, None
    for part in qualname.split("."):
        found = [n for n in body if _defines(n, part)]
        if not found:
            raise LookupError(f"nothing defines {qualname}")
        node = found[-1]
        body = getattr(node, "body", [])
    first = min([node.lineno] + [d.lineno for d in
                                 getattr(node, "decorator_list", [])])
    lines = source.splitlines(keepends=True)
    return first, "".join(lines[first - 1:node.end_lineno])


def _pairs(old, new):
    if isinstance(old, str):
        return [(old, new)]
    return list(zip(old, new))


def anchor_problems(fault):
    """Why `fault` cannot be applied as written, or None."""
    name, where, old, new, _says = fault
    if callable(where):
        return None
    module_name, _, qualname = where.partition(":")
    try:
        _path, source = source_of(module_name)
        _first, text = definition(source, qualname)
    except (LookupError, SyntaxError, OSError, ImportError) as exc:
        return f"{name}: {where}: {exc}"
    for part, _ in _pairs(old, new):
        count = text.count(part)
        if count != 1:
            return (f"{name}: {where} holds {part!r} {count} times, not "
                    f"once: update the fault with the code it breaks")
    return None


def _shared(value):
    """Whether `value` may be the same object as an unrelated one -- a
    small number, a short string, an empty tuple -- so that holding it
    proves nothing about where it came from."""
    if value is None or isinstance(value, (bool, int, float, complex)):
        return True
    if isinstance(value, (str, bytes)):
        return len(value) < 64
    if isinstance(value, (tuple, frozenset)):
        return not value
    return False


def _rebind(old, new):
    """Every loaded module's name for `old`, now `new`: a module that ran
    `from x import f` holds f itself, not the way to it."""
    for module in list(sys.modules.values()):
        space = getattr(module, "__dict__", None)
        if not isinstance(space, dict):
            continue
        for key, value in list(space.items()):
            if value is old:
                space[key] = new


def apply(fault, check_module):
    """Break what `fault` names, in this process."""
    _name, where, old, new, _says = fault
    if callable(where):
        getattr(check_module, where.__name__, where)()
        return
    module_name, _, qualname = where.partition(":")
    path, source = source_of(module_name)
    first, text = definition(source, qualname)
    for part, replacement in _pairs(old, new):
        text = text.replace(part, replacement, 1)
    # Padded to its own line numbers, so a traceback points into the file.
    code = compile("\n" * (first - 1) + textwrap.dedent(text), str(path),
                   "exec")
    module = importlib.import_module(module_name)
    *outer, name = qualname.split(".")
    owner = module
    for part in outer:
        owner = getattr(owner, part)
    held = (owner.__dict__ if isinstance(owner, type) else
            vars(owner)).get(name)
    if owner is module:
        exec(code, module.__dict__)
        made = module.__dict__[name]
    else:
        space = {}
        exec(code, module.__dict__, space)
        made = space[name]
        setattr(owner, name, made)
    if held is not None and not _shared(held) and made is not held:
        _rebind(held, made)


# -------------------- one fault's process --------------------

def _verdict(kind, detail):
    print(VERDICT + json.dumps({"kind": kind, "detail": detail}))
    return 0


def run_one(check, index):
    """Run `check` with fault `index` applied (-1: none), in this
    process, and print the verdict for the parent."""
    add_source_to_path()
    module = importlib.import_module(f"checks.{check}")
    fault = module.FAULTS[index] if index >= 0 else None
    try:
        if fault is not None:
            apply(fault, module)
        found = module.run()
    except Skip as why:
        return _verdict("skipped", str(why))
    except Exception as exc:                            # noqa: BLE001
        return _verdict("crashed", f"{type(exc).__name__}: {exc}")
    finally:
        take_notes()
    if fault is None:
        return _verdict("clean" if not found else "complained",
                        list(found[:3]))
    says = fault[4]
    hits = [p for p in found if says in p]
    if hits:
        return _verdict("caught", hits[0])
    return _verdict("missed", list(found[:2]))


# -------------------- the runner --------------------

def _spawn(check, index, work):
    cache = tempfile.mkdtemp(prefix="pyc-", dir=work)
    env = dict(os.environ, PYTHONPYCACHEPREFIX=cache,
               PYTHONIOENCODING="utf-8", TEMP=str(work), TMP=str(work))
    env[run_all.RUN_TEMP_ENV] = str(work)
    try:
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--one", check,
             str(index)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"kind": "crashed", "detail": f"timed out after {TIMEOUT_S}s"}
    for line in reversed(done.stdout.splitlines()):
        if line.startswith(VERDICT):
            return json.loads(line[len(VERDICT):])
    tail = (done.stderr or done.stdout).strip().splitlines()[-3:]
    return {"kind": "crashed", "detail": " / ".join(tail) or
            f"exit {done.returncode}"}


def _short(text, width=200):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 3] + "..."


def run_check(check, names, work):
    """Every fault of `check` (or those named). Returns (caught,
    crashed, missed), or None where it cannot run."""
    module = importlib.import_module(f"checks.{check}")
    faults = list(enumerate(getattr(module, "FAULTS", None) or ()))
    if names:
        faults = [(i, f) for i, f in faults if f[0] in names]
        unknown = set(names) - {f[0] for _, f in faults}
        if unknown:
            print(f"{check}: no fault named {', '.join(sorted(unknown))}")
            return None
    if not faults:
        print(f"{check}: lists no FAULTS")
        return None
    problems = [p for p in (anchor_problems(f) for _, f in faults) if p]
    if problems:
        print(f"{check}: the faults no longer fit the code; nothing ran")
        for problem in problems:
            print(f"  {problem}")
        return None
    clean = _spawn(check, -1, work)
    if clean["kind"] != "clean":
        print(f"{check}: the clean run did not pass ({clean['kind']}): "
              f"{_short(clean['detail'])}")
        return None
    print(f"{check}: the clean run passes; {len(faults)} fault(s)")
    caught = crashed = missed = 0
    for index, fault in faults:
        verdict = _spawn(check, index, work)
        kind = verdict["kind"]
        if kind == "caught":
            caught += 1
            print(f"  caught   {fault[0]}")
        elif kind == "crashed":
            crashed += 1
            print(f"  crashed  {fault[0]} -- {_short(verdict['detail'])}")
        else:
            missed += 1
            detail = verdict["detail"]
            if kind == "skipped":
                why = f"the check skipped: {detail}"
            elif not detail:
                why = "no complaint"
            else:
                why = (f"no complaint says {fault[4]!r}; first: "
                       f"{_short(detail[0])}")
            print(f"  MISSED   {fault[0]} -- {why}")
    print(f"  {caught} caught, {crashed} crashed, {missed} missed")
    return caught, crashed, missed


def _checks_with_faults():
    return [m for m in run_all.CHECKS if getattr(m, "FAULTS", None)]


def _work_folder():
    """A folder for the faults' processes and their temporary files,
    beside run_all's own and named like them, so a run killed before
    removing it is cleared by a later run_all."""
    parent = run_all.RUN_TEMP_PARENT
    parent.mkdir(exist_ok=True)
    tag = parent / "CACHEDIR.TAG"
    if not tag.exists():
        tag.write_text(run_all.CACHEDIR_TAG, encoding="ascii")
    return Path(tempfile.mkdtemp(prefix="run-faults-", dir=parent))


def _name(check):
    return check if check.startswith("check_") else f"check_{check}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("check", nargs="?")
    ap.add_argument("faults", nargs="*", help="only these faults")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--one", nargs=2, metavar=("CHECK", "INDEX"),
                    help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.one:
        return run_one(args.one[0], int(args.one[1]))
    if args.list:
        if args.check:
            module = importlib.import_module(f"checks.{_name(args.check)}")
            for fault in getattr(module, "FAULTS", None) or ():
                print(f"  {fault[0]}")
        else:
            for module in _checks_with_faults():
                print(f"  {run_all._module(module):<36} "
                      f"{len(module.FAULTS)} fault(s)")
        return 0
    if args.all:
        checks = [run_all._module(m) for m in _checks_with_faults()]
    elif args.check:
        checks = [_name(args.check)]
    else:
        ap.print_usage()
        return 2
    work = _work_folder()
    failed = False
    try:
        for check in checks:
            result = run_check(check, args.faults, work)
            failed |= result is None or result[2] > 0
    finally:
        run_all._remove_tree(work)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
