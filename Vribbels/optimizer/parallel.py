"""
Parallel enumeration path for the optimizer.

Splits an optimize() run across worker PROCESSES: worker i of N takes a
strided share of slot 1's candidate list ([i::N]) and enumerates the
full product against slots 2-6, keeping a local top-K. The parent merges
the workers' top-Ks (a union of per-partition top-Ks provably contains
the global top-K), re-sorts with the same deterministic key the
single-thread path uses, and sums the counters -- so results and
`last_optimize_stats` are identical to the sequential path on the same
inputs.

Why processes: the enumeration is pure-Python arithmetic (GIL-bound), so
threads give ~zero speedup.

Worker-side correctness note: workers import game_data fresh on spawn
and therefore DON'T see runtime mutations the parent applied (e.g.
level-data exp-table checkpoints). That's fine by construction: the
per-run ctx carries every character-derived number already resolved
PARENT-side (base stats at the effective level, partner, affection,
potential) -- core.evaluate_combo only touches ctx, the fragments, and
the static SETS table.

No Tk imports anywhere on this module's import path (worker processes
must never touch the GUI).
"""

import atexit
import itertools
import os
import queue as _queue
from concurrent.futures import ProcessPoolExecutor, wait

from game_data import SLOT_ORDER
from optimizer import core


# Runs smaller than this stay on the single-thread path: worker spawn +
# input pickling costs a fixed ~1-2s, which dwarfs the saving on small
# search spaces. At typical single-core throughput this threshold is a
# few seconds of sequential work.
PARALLEL_MIN_COMBOS = 100_000

# Workers poll the (Manager-proxied) cancel event only every N combos --
# each poll is an IPC round-trip, so per-iteration polling would dominate
# the loop. 4096 keeps Stop latency well under ~100ms per worker.
CANCEL_POLL_EVERY = 4096

# Progress-report granularity (combos per queue message per worker).
# Matches the single-thread path's callback cadence.
PROGRESS_EVERY = 5000


# ---------------------------------------------------------------------------
# Pool lifecycle: created lazily ONCE per app session and reused across
# runs -- worker spawn (especially from a frozen onefile exe) costs
# ~0.5-1.5s per process, so per-run pools would pay that every Start.
# ---------------------------------------------------------------------------

_pool = None
_pool_workers = 0
_manager = None


def resolve_worker_count(configured: int) -> int:
    """Map the config value onto an effective worker count.

    0 (auto) -> cpu_count - 1 (leave a core for the UI + the game client
    that's typically running alongside capture); 1 -> single-thread
    path; N -> N capped to cpu_count. Always at least 1.
    """
    cpu = os.cpu_count() or 1
    if configured <= 0:
        return max(1, cpu - 1)
    return max(1, min(int(configured), cpu))


def _get_pool(workers: int) -> ProcessPoolExecutor:
    global _pool, _pool_workers
    if _pool is not None and _pool_workers == workers:
        return _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
    _pool = ProcessPoolExecutor(max_workers=workers)
    _pool_workers = workers
    return _pool


def _get_manager():
    """Lazy multiprocessing.Manager -- its proxy Event/Queue objects are
    picklable (plain mp.Event/mp.Queue can't be passed to executor
    submissions). Created on first parallel run, reused after."""
    global _manager
    if _manager is None:
        import multiprocessing
        _manager = multiprocessing.Manager()
    return _manager


@atexit.register
def _shutdown_pool():
    global _pool, _manager
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
    if _manager is not None:
        try:
            _manager.shutdown()
        except Exception:
            pass
        _manager = None


# ---------------------------------------------------------------------------
# Worker entry point. MUST stay a module-level function (spawn can't
# pickle closures) and MUST NOT touch anything Tk-adjacent.
# ---------------------------------------------------------------------------

def evaluate_partition(slot_candidates_share: dict, ctx: dict,
                       max_results: int, cancel_event, progress_queue,
                       worker_id: int):
    """Enumerate one partition of the search space.

    Mirrors the single-thread loop in GearOptimizer.optimize() exactly:
    same evaluate_combo call, same counter mapping (duplicates / set
    failures increment only total_combinations; HAL failures additionally
    count as passed_set_reqs; OK counts in both), same in-flight trim at
    max_results * 10 using the same deterministic sort key.

    Returns (topK_results, counters, checked, cancelled).
    """
    counters = {
        "total_combinations": 0,
        "passed_set_reqs": 0,
        "passed_have_at_least": 0,
    }
    results = []
    checked = 0
    unreported = 0
    cancelled = False

    lists = [slot_candidates_share[s] for s in SLOT_ORDER]
    for combo in itertools.product(*lists):
        checked += 1
        unreported += 1
        counters["total_combinations"] += 1

        if cancel_event is not None and checked % CANCEL_POLL_EVERY == 0:
            try:
                if cancel_event.is_set():
                    cancelled = True
                    break
            except Exception:
                # Manager connection lost (parent exiting) -- stop work.
                cancelled = True
                break

        status, score, stats = core.evaluate_combo(combo, ctx)
        if status != core.COMBO_DUPLICATE and status != core.COMBO_SET_FAIL:
            counters["passed_set_reqs"] += 1
            if status == core.COMBO_OK:
                counters["passed_have_at_least"] += 1
                results.append((list(combo), score, stats))
                if len(results) > max_results * 10:
                    results.sort(key=core.result_sort_key)
                    results = results[:max_results]

        if unreported >= PROGRESS_EVERY and progress_queue is not None:
            try:
                progress_queue.put((worker_id, unreported))
            except Exception:
                pass
            unreported = 0

    if unreported and progress_queue is not None:
        try:
            progress_queue.put((worker_id, unreported))
        except Exception:
            pass

    results.sort(key=core.result_sort_key)
    return results[:max_results], counters, checked, cancelled


# ---------------------------------------------------------------------------
# Parent-side orchestration. Runs on the caller's (non-UI) thread inside
# GearOptimizer.optimize(); communicates outward through the exact same
# progress_callback / cancel_flag interface the single-thread path uses,
# so neither the tab nor optimize()'s signature needs to know which path
# ran.
# ---------------------------------------------------------------------------

def optimize_parallel(slot_candidates: dict, ctx: dict, max_results: int,
                      workers: int, total_perms: int,
                      progress_callback=None, cancel_flag=None):
    """Run the enumeration across `workers` processes.

    Returns (results, counters, checked_total). NOTE: the returned gear
    lists reference PICKLED COPIES of the parent's MemoryFragment
    objects (they crossed a process boundary twice) -- the caller must
    remap them onto its own fragment objects by id to restore identity.

    Raises on unrecoverable pool failure; the caller is expected to
    catch and fall back to the single-thread path.
    """
    pool = _get_pool(workers)
    mgr = _get_manager()
    cancel_event = mgr.Event()
    progress_queue = mgr.Queue()

    first_slot = SLOT_ORDER[0]
    slot1 = slot_candidates[first_slot]
    # Strided partitioning of slot 1's (score-sorted) candidate list
    # balances load: the best candidates cluster at the top, and striding
    # deals them round-robin instead of giving worker 0 all the
    # heavy-hitters. Never more partitions than slot-1 candidates.
    n = max(1, min(workers, len(slot1)))
    futures = []
    for i in range(n):
        share = dict(slot_candidates)
        share[first_slot] = slot1[i::n]
        futures.append(pool.submit(
            evaluate_partition, share, ctx, max_results,
            cancel_event, progress_queue, i,
        ))

    checked_total = 0
    last_reported = -1
    pending = set(futures)
    while pending:
        _done, pending = wait(pending, timeout=0.1)
        # Drain progress deltas.
        while True:
            try:
                _wid, delta = progress_queue.get_nowait()
            except (_queue.Empty, Exception):
                break
            checked_total += delta
        if progress_callback and checked_total != last_reported:
            # `found` isn't tracked globally (each worker trims its own
            # list); the tab deliberately doesn't display a running found
            # count anyway, so 0 is passed for shape-compatibility.
            progress_callback(checked_total, total_perms, 0)
            last_reported = checked_total
        # Relay a Stop press to the workers.
        if cancel_flag and cancel_flag[0] and not cancel_event.is_set():
            cancel_event.set()

    # Final drain -- deltas posted just before a worker returned may
    # still be in the queue after its future completed.
    while True:
        try:
            _wid, delta = progress_queue.get_nowait()
        except (_queue.Empty, Exception):
            break
        checked_total += delta
    if progress_callback and checked_total != last_reported:
        progress_callback(checked_total, total_perms, 0)

    merged = []
    counters = {
        "total_combinations": 0,
        "passed_set_reqs": 0,
        "passed_have_at_least": 0,
    }
    checked_sum = 0
    for f in futures:
        part_results, part_counters, part_checked, _cancelled = f.result()
        merged.extend(part_results)
        for k in counters:
            counters[k] += part_counters[k]
        checked_sum += part_checked

    merged.sort(key=core.result_sort_key)
    return merged[:max_results], counters, checked_sum
