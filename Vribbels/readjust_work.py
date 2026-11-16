"""The Substat Readjustment tab's work: every combatant's readings,
worked out in worker processes in the order the tab's choices give,
kept by what they were worked out from, and saved between launches.

**The order.** With one combatant chosen: that one, then the weighted
ones by weight, heaviest first, then everyone else. With several
weighted: the weighted by weight, then everyone else. Only a few jobs
wait in the workers at a time (`AHEAD` per worker), so a new choice is
taken up within a job or two.

**Two speeds** (`readjust.BACKGROUND`, `readjust.FULL`). The background
runs one worker at the lowest priority Windows has, which only gets
time nothing else wants, the game and the window included. Full speed
runs every core but one at normal priority, until everything is worked
out, and then goes back to the background.

**When it runs.** With Work out in the background on (`BACKGROUND_KEY`,
the default), from the moment a capture is loaded, for every combatant,
whether or not the tab has been opened. Off, only while the tab shows,
only for the combatants it shows, at full speed.

**What is kept.** An answer is kept by what it was worked out from:
the fragment's own rolls (`readjust.content`) and its combatant's
signature -- the preset's weights for the Gear Score, everything the
combatant's builds are made of for the build score
(`readjust.build_signature`), hashed. So a capture costs only what it
changed, and answers saved to `CACHE_NAME` in the data folder's cache
folder are good after a restart. `CACHE_VERSION` says which way of
working out wrote them.

No Tk on this module's import path: the app hands it `after`.
"""

import hashlib
import json
import os
import pickle
import time
from pathlib import Path

import readjust as rj
from optimizer.run_settings import saved_run_settings

# The settings the tab's controls are kept under (`settings_manager.
# LAYOUT`), read here so the work follows them with the tab unbuilt.
MEASURE_KEY = "readjust_measure"
MODE_KEY = "readjust_mode"
COMBATANT_KEY = "readjust_combatant"
WEIGHTS_KEY = "readjust_weights"
BACKGROUND_KEY = "readjust_background"

# How often the workers are asked whether a job is done, while any is.
TICK_MS = 50
# Jobs waiting in the workers per worker: enough to keep each busy,
# few enough that a new choice is taken up soon.
AHEAD = 2
# A job's fragments. A build-score fragment is two Optimizer runs and
# its sampling, a Gear Score one a few milliseconds.
CHUNK = 40
BUILD_CHUNK = 4
# Answers kept past this many are dropped, oldest signatures first.
KEEP_ANSWERS = 100000
# How long answers wait before they are saved, at most.
SAVE_EVERY = 30.0
CACHE_NAME = "readjust_answers.pickle"
CACHE_VERSION = 1
CACHEDIR_TAG = (b"Signature: 8a477f597d28d172789f06886806bc55\n"
                b"# Vribbels CZN Optimizer: worked-out answers it can "
                b"work out again.\n")


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ordered(names, mode, chosen, weights):
    """`names` in the order the work takes them: `chosen` first where
    `mode` is "one", then those with a weight above 0, heaviest first
    (by name within a weight), then the rest by name."""
    weighted = sorted((n for n in names if weights.get(n, 0) > 0),
                      key=lambda n: (-weights[n], n))
    head = [chosen] if mode == "one" and chosen in names else []
    seen = set(head)
    out = list(head)
    for name in weighted + sorted(names):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


class Status:
    """One combatant's readings under the measure in hand: `readings`
    {id: (now, plain, exclude)}, how many of the `total` fragments are
    `done` (read, or left unread: cut, or no build can wear them), and
    `reason` where none can be read at all."""

    def __init__(self, total):
        self.readings = {}
        self.done = 0
        self.total = total
        self.reason = None

    @property
    def complete(self):
        return self.done >= self.total


class ReadjustWork:
    """The work, for the whole app. `context` carries the optimizer and
    the managers; `after(ms, fn)` schedules on the window's loop;
    `cache_dir` is where answers are saved, None to keep none."""

    def __init__(self, context, after, cache_dir=None):
        self.context = context
        self._after = after
        self.cache_dir = Path(cache_dir) if cache_dir else None
        # {(signature, kind, content): answer}. Kind "read" is (now,
        # plain, exclude), or None for a fragment no build can wear;
        # kind "top", content None, a combatant's {"top": ids, "cut":
        # ids}, or None where the Optimizer finds no build.
        self.answers = {}
        # {job: (Future, speed, combatant)} and {answer key: job}.
        self._futures = {}
        self._inflight = {}
        # {(token, measure, combatant, settings): (signature, template)}
        self._sigs = {}
        self._lean = None
        self._token = None
        self.speed = rj.BACKGROUND
        # Whether the tab shows, and whether anything may run at all: a
        # check's or an audit's build leaves it off.
        self.visible = False
        self.enabled = False
        self.statuses = {}
        self.listeners = []
        self.error = None
        self._scheduled = False
        self._dirty = False
        self._saved_at = time.monotonic()
        self._load()

    # ------------------------------------------------------- the choices

    def _setting(self, key, default):
        manager = getattr(self.context, "settings_manager", None)
        value = manager.get(key) if manager is not None else None
        return default if value is None else value

    def background(self):
        return bool(self._setting(BACKGROUND_KEY, True))

    def measure(self):
        return self._setting(MEASURE_KEY, rj.GEAR)

    def mode(self):
        return self._setting(MODE_KEY, "one")

    def names(self):
        optimizer = getattr(self.context, "optimizer", None)
        if optimizer is None:
            return []
        return sorted(set(optimizer.characters)
                      | set(optimizer.character_info))

    def weights(self):
        stored = self._setting(WEIGHTS_KEY, {})
        names = set(self.names())
        return {n: w for n, w in (stored if isinstance(stored, dict)
                                  else {}).items()
                if n in names and w > 0}

    def chosen(self):
        names = self.names()
        name = self._setting(COMBATANT_KEY, "")
        return name if name in names else (names[0] if names else "")

    def shown(self):
        """The combatants the tab's list is read for."""
        if self.mode() == "weighted":
            return ordered(list(self.weights()), "weighted", "",
                           self.weights())
        return [self.chosen()] if self.chosen() else []

    def order(self):
        """Every combatant, in the order the work takes them."""
        return ordered(self.names(), self.mode(), self.chosen(),
                       self.weights())

    def groups(self):
        """{group: [combatant]} the progress counts: "one" (None with
        several weighted), "weighted", "all"."""
        weights = self.weights()
        return {"one": [self.chosen()] if self.mode() == "one" else None,
                "weighted": ordered(list(weights), "weighted", "", weights),
                "all": self.names()}

    # ---------------------------------------------------- the signatures

    def _signature(self, measure, name, rolls, stats):
        """(signature, job template), or (None, why) where `name` can
        have no readings under `measure`."""
        context = self.context
        if measure == rj.GEAR:
            presets = getattr(context, "preset_manager", None)
            assigned = context.character_preset_manager.get_preset_for(
                name) if getattr(context, "character_preset_manager",
                                 None) else None
            weights = presets.get_preset(assigned) \
                if assigned and presets else None
            if weights is None:
                return None, "no preset"
            sig = _hash(json.dumps([rj.GEAR, sorted(weights.items()), rolls],
                                   default=repr))
            return sig, {"measure": rj.GEAR, "weights": weights,
                         "stats": stats}
        optimizer = context.optimizer
        run = saved_run_settings(optimizer, context, name)
        held = (self._token, measure, name,
                json.dumps(run, sort_keys=True, default=str))
        if held not in self._sigs:
            self._sigs[held] = _hash(json.dumps(
                [rj.BUILD, rj.build_signature(optimizer, name, run), rolls],
                default=repr))
        if self._lean is None:
            self._lean = rj.lean_optimizer(optimizer)
        return self._sigs[held], {"measure": rj.BUILD,
                                  "optimizer": self._lean, "name": name,
                                  "settings": run, "stats": stats}

    def _forget(self, token, fragments):
        """A capture loaded: the signatures are worked out again, and the
        answers of fragments no longer held -- deleted, or readjusted to
        new rolls -- are dropped. Every other answer stays: one worked
        out from the same inputs is the same answer, whichever capture
        holds them. A Top build is a combatant's, not a fragment's, and
        its signature holds every fragment it could be made of."""
        if token == self._token:
            return
        self._token = token
        self._sigs.clear()
        self._lean = None
        live = {rj.content(f) for f in fragments}
        for key in [k for k in self.answers
                    if k[2] is not None and k[2] not in live]:
            del self.answers[key]

    # ---------------------------------------------------------- planning

    def _status(self, name, sig, template, fragments, keys, wanted):
        """`name`'s Status, and what it still needs added to `wanted` as
        (signature, template, combatant, kind, chunk)."""
        status = Status(len(fragments))
        size = CHUNK
        skip = set()
        if template["measure"] == rj.BUILD:
            top_key = (sig, "top", None)
            if top_key not in self.answers:
                if top_key not in self._inflight:
                    wanted.append((sig, template, name, "top", []))
                return status
            top = self.answers[top_key]
            if top is None:
                status.done = status.total
                status.reason = "no build"
                return status
            template = dict(template, top=top["top"])
            skip = set(top["cut"])
            size = BUILD_CHUNK
        todo = []
        for f in fragments:
            if f.id in skip:
                status.done += 1
                continue
            key = (sig, "read", keys[f.id])
            if key in self.answers:
                status.done += 1
                if self.answers[key] is not None:
                    status.readings[f.id] = self.answers[key]
            elif key not in self._inflight:
                todo.append(f)
        wanted.extend((sig, template, name, "read", todo[i:i + size])
                      for i in range(0, len(todo), size))
        return status

    def plan(self):
        """Every combatant's Status under the measure in hand, in work
        order, and the jobs to hand the workers, most wanted first."""
        optimizer = getattr(self.context, "optimizer", None)
        if optimizer is None or not optimizer.fragments:
            self.statuses = {}
            return []
        fragments = sorted((f for f in optimizer.fragments
                            if rj.readjustable(f)), key=lambda f: f.id)
        self._forget((id(optimizer.fragments), optimizer.capture_time,
                      len(optimizer.fragments)), fragments)
        keys = {f.id: rj.content(f) for f in fragments}
        measure = self.measure()
        stats = rj.stats_snapshot()
        rolls = sorted((k, list(v)) for k, v in stats.items())
        statuses, wanted = {}, []
        for name in self.order():
            sig, template = self._signature(measure, name, rolls, stats)
            if sig is None:
                status = Status(len(fragments))
                status.done = status.total
                status.reason = template
                statuses[name] = status
                continue
            statuses[name] = self._status(name, sig, template, fragments,
                                          keys, wanted)
        self.statuses = statuses
        return wanted

    # ----------------------------------------------------------- running

    def _may_run(self):
        return self.enabled and (self.background() or self.visible)

    def refresh(self):
        """A choice, a setting or the data changed: plan again and hand
        the workers what is most wanted. The tab hears of it."""
        wanted = self.plan()
        if self._may_run():
            self._ask(wanted)
        self._notify()

    def full_speed(self):
        """Every core but one until everything is worked out, or until
        `background_speed`."""
        self._set_speed(rj.FULL)

    def background_speed(self):
        """Back to the one idle-priority worker."""
        self._set_speed(rj.BACKGROUND)

    def _set_speed(self, speed):
        """Work at `speed`: the jobs not started yet move to its
        workers; the ones running finish where they are."""
        if self.speed == speed:
            return
        self.speed = speed
        self._cancel(lambda job, at, name: at != speed)
        self.refresh()

    def _cancel(self, which):
        for job, (future, speed, name) in list(self._futures.items()):
            if which(job, speed, name) and future.cancel():
                self._drop(job)

    def _ask(self, wanted):
        """Hand the workers the head of `wanted`, as many as keep each
        `AHEAD` deep; without the background, only the shown
        combatants', and nothing queued for anyone else."""
        if not self.background():
            shown = set(self.shown())
            self._cancel(lambda job, speed, name: name not in shown)
            wanted = [w for w in wanted if w[2] in shown]
            speed = rj.FULL
        else:
            speed = self.speed
        room = rj.workers(speed) * AHEAD - sum(
            1 for _f, s, _n in self._futures.values() if s == speed)
        for sig, template, name, kind, chunk in wanted[:max(0, room)]:
            # A Top build answers for no fragment: its one key's
            # content is None, as `_status` waits on it.
            pairs = ((None, None),) if kind == "top" else tuple(
                (f.id, rj.content(f)) for f in chunk)
            job = (sig, kind, pairs)
            if job in self._futures:
                continue
            payload = dict(template, kind=kind, fragments=chunk)
            self._futures[job] = (rj.submit(payload, speed), speed, name)
            for _fid, c in pairs:
                self._inflight[(sig, kind, c)] = job
        self._schedule()

    def _schedule(self):
        if self._futures and not self._scheduled:
            self._scheduled = True
            self._after(TICK_MS, self._tick)

    def _drop(self, job):
        """Forget a job: answered, failed or cancelled."""
        sig, kind, pairs = job
        self._futures.pop(job, None)
        for _fid, c in pairs:
            if self._inflight.get((sig, kind, c)) == job:
                del self._inflight[(sig, kind, c)]

    def _tick(self):
        """Take in what the workers have answered; where anything came
        in, plan again, hand out more and tell the tab."""
        self._scheduled = False
        came = False
        for job, (future, _speed, _name) in list(self._futures.items()):
            if not future.done():
                continue
            self._drop(job)
            if future.cancelled():
                continue
            try:
                answers = future.result()
            except Exception as e:                 # shown, not raised
                self.error = e
                continue
            sig, kind, pairs = job
            for fid, c in pairs:
                if fid in answers:
                    self.answers[(sig, kind, c)] = answers[fid]
                    came = self._dirty = True
        if came:
            self.refresh()
            if self.speed == rj.FULL and not self._futures \
                    and all(s.complete for s in self.statuses.values()):
                self.speed = rj.BACKGROUND
                self._notify()
        self._schedule()
        self._save_if_due()

    def _notify(self):
        for listener in list(self.listeners):
            listener()

    def busy(self):
        return bool(self._futures)

    # ---------------------------------------------------------- the disk

    def _path(self):
        return self.cache_dir / CACHE_NAME if self.cache_dir else None

    def _load(self):
        path = self._path()
        if path is None or not path.exists():
            return
        try:
            with open(path, "rb") as fh:
                saved = pickle.load(fh)
        except Exception:                          # unreadable: start over
            return
        if isinstance(saved, dict) and saved.get("version") == CACHE_VERSION:
            answers = saved.get("answers") or {}
            self.answers = dict(list(answers.items())[-KEEP_ANSWERS:])

    def _save_if_due(self):
        if self._dirty and time.monotonic() - self._saved_at > SAVE_EVERY:
            self.save()

    def save(self):
        """Write the answers to the cache folder, whole or not at all."""
        path = self._path()
        self._saved_at = time.monotonic()
        if path is None or not self._dirty:
            return
        self._dirty = False
        if len(self.answers) > KEEP_ANSWERS:
            self.answers = dict(list(self.answers.items())[-KEEP_ANSWERS:])
        path.parent.mkdir(parents=True, exist_ok=True)
        tag = path.parent / "CACHEDIR.TAG"
        if not tag.exists():
            tag.write_bytes(CACHEDIR_TAG)
        temp = path.with_suffix(".tmp")
        with open(temp, "wb") as fh:
            pickle.dump({"version": CACHE_VERSION, "answers": self.answers},
                        fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temp, path)
