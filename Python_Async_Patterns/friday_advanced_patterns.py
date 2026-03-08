"""
PYTHON ASYNC PROGRAMMING - FRIDAY PRACTICE
Advanced Patterns for Interview Readiness

Topics Covered:
  1. asyncio.as_completed   — process results in arrival order
  2. asyncio.Event          — coroutine signaling
  3. asyncio.Lock           — mutual exclusion
  4. asyncio.Condition      — notify-and-wait coordination
  5. Async generators       — async for / async yield
  6. Async context managers — __aenter__ / __aexit__
  7. Task cancellation & shielding

Run each section:
  python friday_advanced_patterns.py
"""

import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 6: asyncio.as_completed — Process in Arrival Order
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: asyncio.gather() waits for ALL to finish then returns in
# *submission* order. asyncio.as_completed() yields futures as each one
# finishes — great for "show the fastest result first" patterns.

# ── Problem 6.1 ──────────────────────────────────────────────────────────────
# You query 5 replicas of a database. Return the FIRST successful result
# and cancel the rest (hedged requests pattern).

async def query_replica(replica_id: int) -> str:
    delay = random.uniform(0.1, 0.9)
    await asyncio.sleep(delay)
    if random.random() < 0.2:          # 20% chance of failure
        raise ConnectionError(f"Replica {replica_id} down")
    return f"data-from-replica-{replica_id} (took {delay:.2f}s)"

async def hedged_query(n_replicas: int = 5) -> str:
    """Return first successful replica response; cancel all others."""
    tasks = [asyncio.create_task(query_replica(i)) for i in range(n_replicas)]
    first_result = None
    first_error = None

    for coro in asyncio.as_completed(tasks):
        try:
            first_result = await coro
            break                       # got a good result — stop waiting
        except Exception as e:
            first_error = e             # record but keep trying others

    # Cancel remaining in-flight tasks
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)  # drain cancellations

    if first_result is None:
        raise first_error
    return first_result


# ── Problem 6.2 (Interview Question) ─────────────────────────────────────────
# Process N HTTP calls; print each response AS IT ARRIVES instead of waiting
# for all of them. Include arrival position.

async def slow_fetch(url: str) -> tuple[str, float]:
    delay = random.uniform(0.1, 1.0)
    await asyncio.sleep(delay)
    return url, delay

async def demo_as_completed(urls: list[str]):
    print("  Results streaming in:")
    t0 = time.perf_counter()
    for pos, coro in enumerate(asyncio.as_completed([slow_fetch(u) for u in urls]), 1):
        url, delay = await coro
        print(f"    #{pos} arrived: {url} (simulated {delay:.2f}s)")
    print(f"  Total wall time: {time.perf_counter()-t0:.2f}s\n")


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 7: asyncio.Event — One-shot Signaling
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: Event is a boolean flag coroutines can wait on.
# - set()   → flag True, all waiters are released
# - clear() → flag False again
# - wait()  → suspends until set() is called
# Use case: "start signal", "shutdown signal", "data-ready" notification.

# ── Problem 7.1 ──────────────────────────────────────────────────────────────
# Implement a startup barrier: a server should not accept requests until
# its database connection pool is "ready". Workers wait on a ready event.

async def init_db(ready_event: asyncio.Event):
    print("  DB: initializing connection pool...")
    await asyncio.sleep(0.5)           # simulate slow startup
    print("  DB: ready!")
    ready_event.set()                  # unblock all waiters at once

async def handle_request(name: str, ready_event: asyncio.Event):
    await ready_event.wait()           # blocks until event is set
    print(f"  {name}: processing request (DB is ready)")
    await asyncio.sleep(0.05)

async def demo_event():
    ready = asyncio.Event()
    await asyncio.gather(
        init_db(ready),
        handle_request("req-1", ready),
        handle_request("req-2", ready),
        handle_request("req-3", ready),
    )
    print()


# ── Problem 7.2 (Interview Question) ─────────────────────────────────────────
# Implement a graceful shutdown: a main loop runs until a shutdown event
# is set by a signal handler.

async def work_loop(shutdown: asyncio.Event):
    i = 0
    while not shutdown.is_set():
        i += 1
        print(f"  Loop iteration {i}")
        try:
            await asyncio.wait_for(
                asyncio.shield(shutdown.wait()),  # wait for event but with timeout
                timeout=0.2,
            )
        except asyncio.TimeoutError:
            pass                        # no shutdown yet, continue
    print("  Loop: received shutdown signal")

async def demo_graceful_shutdown():
    shutdown = asyncio.Event()
    loop_task = asyncio.create_task(work_loop(shutdown))
    await asyncio.sleep(0.7)           # simulate running for a while
    shutdown.set()                     # signal shutdown
    await loop_task
    print()


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 8: asyncio.Lock — Mutual Exclusion
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: asyncio.Lock is NOT a threading lock — it works within a single
# thread via cooperative multitasking. Only one coroutine holds it at a time.
# Use it to protect shared state that cannot be updated atomically.

# ── Problem 8.1 ──────────────────────────────────────────────────────────────
# A shared counter is incremented by many coroutines. Without a lock the
# read-modify-write is not atomic across awaits. Protect it correctly.

class SharedCounter:
    def __init__(self):
        self._value = 0
        self._lock = asyncio.Lock()

    async def increment(self):
        async with self._lock:          # only one coroutine can be here at a time
            current = self._value
            await asyncio.sleep(0)      # simulate a yield point mid-update
            self._value = current + 1

    @property
    def value(self):
        return self._value

async def demo_lock():
    counter = SharedCounter()
    await asyncio.gather(*[counter.increment() for _ in range(100)])
    print(f"  Counter (with lock): {counter.value}  (expected 100)\n")

    # Without lock — race condition demonstration:
    bad_value = 0
    async def bad_increment():
        nonlocal bad_value
        current = bad_value
        await asyncio.sleep(0)          # yields here — others may also read `current`
        bad_value = current + 1

    await asyncio.gather(*[bad_increment() for _ in range(100)])
    print(f"  Counter (no lock):   {bad_value}  (likely less than 100 — race!)\n")


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 9: Async Generators — Lazy Async Streams
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: async def + yield = async generator. Iterate with `async for`.
# Use for paginated APIs, live data streams, or any "pull" model where data
# arrives over time.

# ── Problem 9.1 ──────────────────────────────────────────────────────────────
# Model a paginated API: each page fetch is async. Yield records lazily so
# the caller can stop early without fetching unnecessary pages.

async def paginated_api(total_pages: int = 5) -> AsyncIterator[list[str]]:
    """Async generator: yields one page of records at a time."""
    for page in range(1, total_pages + 1):
        await asyncio.sleep(0.1)       # simulate network call for each page
        records = [f"record-{page}-{i}" for i in range(3)]
        print(f"  Fetched page {page}")
        yield records                  # `yield` inside `async def` → async generator

async def demo_async_generator():
    # Consume all pages:
    all_records = []
    async for page_records in paginated_api(5):
        all_records.extend(page_records)
    print(f"  Total records: {len(all_records)}\n")

    # Early stop — only read first 2 pages:
    print("  Early stop after 2 pages:")
    async for page_records in paginated_api(5):
        print(f"    Got {len(page_records)} records")
        if len(page_records) > 0 and "2" in page_records[0]:
            break
    print()


# ── Problem 9.2 (Interview Question) ─────────────────────────────────────────
# Write an async generator that batches items from a source into chunks of N.

async def item_source(n: int) -> AsyncIterator[int]:
    for i in range(n):
        await asyncio.sleep(0.01)
        yield i

async def batched(source: AsyncIterator, batch_size: int) -> AsyncIterator[list]:
    """Wrap any async iterator to yield fixed-size batches."""
    batch = []
    async for item in source:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:                           # yield remaining partial batch
        yield batch

async def demo_batched_generator():
    async for batch in batched(item_source(17), batch_size=5):
        print(f"  Batch: {batch}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 10: Async Context Managers
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: Implement __aenter__ / __aexit__ (or use @asynccontextmanager)
# for resources that require async setup/teardown (DB connections, HTTP sessions).

# ── Problem 10.1 ──────────────────────────────────────────────────────────────
# Build a simple async connection pool as a context manager.

class AsyncDBConnection:
    """Simulate an async database connection."""
    def __init__(self, conn_id: int):
        self.id = conn_id

    async def query(self, sql: str) -> str:
        await asyncio.sleep(0.05)
        return f"[conn-{self.id}] result of '{sql}'"

    async def close(self):
        await asyncio.sleep(0.01)
        print(f"  Connection {self.id} closed")


class AsyncConnectionPool:
    def __init__(self, size: int):
        self._size = size
        self._pool: asyncio.Queue[AsyncDBConnection] = asyncio.Queue()
        self._initialized = False

    async def start(self):
        for i in range(self._size):
            conn = AsyncDBConnection(i)
            await self._pool.put(conn)
        self._initialized = True
        print(f"  Pool started with {self._size} connections")

    async def stop(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

    async def __aenter__(self) -> "AsyncConnectionPool":
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()

    # Borrow a connection using a nested context manager:
    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[AsyncDBConnection]:
        conn = await self._pool.get()   # borrow
        try:
            yield conn
        finally:
            await self._pool.put(conn)  # return — even if an exception occurred


async def demo_connection_pool():
    async with AsyncConnectionPool(size=3) as pool:
        # Run 6 queries with only 3 connections — pool provides backpressure
        async def run_query(query_id: int):
            async with pool.acquire() as conn:
                result = await conn.query(f"SELECT {query_id}")
                print(f"  Query {query_id}: {result}")

        await asyncio.gather(*[run_query(i) for i in range(6)])
    print()


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 11: Task Cancellation & asyncio.shield
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: task.cancel() schedules CancelledError to be thrown into the
# coroutine at the next await point. Always re-raise CancelledError after
# cleanup. asyncio.shield() protects an inner coroutine from cancellation.

# ── Problem 11.1 ──────────────────────────────────────────────────────────────
# Implement a task with cleanup that runs even if the task is cancelled.

async def important_work_with_cleanup(name: str):
    print(f"  {name}: starting")
    try:
        await asyncio.sleep(10)        # long operation
        print(f"  {name}: completed normally")
    except asyncio.CancelledError:
        print(f"  {name}: cancelled! Running cleanup...")
        await asyncio.sleep(0.1)       # cleanup (cannot be cancelled while here)
        print(f"  {name}: cleanup done")
        raise                          # MUST re-raise so caller knows it was cancelled

async def demo_cancellation():
    task = asyncio.create_task(important_work_with_cleanup("Task-A"))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("  Task-A was cancelled (confirmed by caller)")
    print()


# ── Problem 11.2 (Interview Question) ─────────────────────────────────────────
# asyncio.shield: protect a critical save operation from outer cancellation.
# If the outer task is cancelled, the save still completes.

async def critical_save(data: str):
    print(f"  Saving '{data}'...")
    await asyncio.sleep(0.3)
    print(f"  Saved '{data}'!")

async def main_with_shield():
    try:
        task = asyncio.create_task(critical_save("user-data"))
        # shield wraps task so cancelling us doesn't cancel task
        await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
    except asyncio.TimeoutError:
        print("  Outer operation timed out, but save continues in background")
        await task                     # wait for the shielded task to finish
    print()


# ─────────────────────────────────────────────────────────────────────────────
# ADVANCED INTERVIEW: Combining Patterns
# ─────────────────────────────────────────────────────────────────────────────

# ── Problem: Async Pipeline ───────────────────────────────────────────────────
# Build a 3-stage pipeline: fetch → transform → save.
# Each stage runs concurrently with bounded queues for backpressure.

async def pipeline_fetch(out: asyncio.Queue, n: int):
    for i in range(n):
        await asyncio.sleep(0.05)
        item = {"id": i, "raw": f"data-{i}"}
        await out.put(item)
        print(f"    Fetched {item['id']}")
    await out.put(None)                 # sentinel

async def pipeline_transform(inp: asyncio.Queue, out: asyncio.Queue):
    while True:
        item = await inp.get()
        if item is None:
            await out.put(None)
            break
        await asyncio.sleep(0.03)
        item["processed"] = item["raw"].upper()
        await out.put(item)
        print(f"    Transformed {item['id']}")

async def pipeline_save(inp: asyncio.Queue, results: list):
    while True:
        item = await inp.get()
        if item is None:
            break
        await asyncio.sleep(0.02)
        results.append(item)
        print(f"    Saved {item['id']}: {item['processed']}")

async def demo_pipeline():
    q1 = asyncio.Queue(maxsize=3)
    q2 = asyncio.Queue(maxsize=3)
    results = []
    await asyncio.gather(
        pipeline_fetch(q1, 5),
        pipeline_transform(q1, q2),
        pipeline_save(q2, results),
    )
    print(f"  Pipeline complete. {len(results)} items processed.\n")


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_all():
    random.seed(7)

    print("=" * 60)
    print("PATTERN 6: as_completed — Hedged Requests")
    print("=" * 60)
    try:
        result = await hedged_query(5)
        print(f"  Hedged result: {result}")
    except Exception as e:
        print(f"  All replicas failed: {e}")
    print()

    print("--- as_completed streaming ---")
    await demo_as_completed(["api.com/a", "api.com/b", "api.com/c", "api.com/d"])

    print("=" * 60)
    print("PATTERN 7: Event — Signaling")
    print("=" * 60)
    print("--- Startup barrier ---")
    await demo_event()
    print("--- Graceful shutdown ---")
    await demo_graceful_shutdown()

    print("=" * 60)
    print("PATTERN 8: Lock — Mutual Exclusion")
    print("=" * 60)
    await demo_lock()

    print("=" * 60)
    print("PATTERN 9: Async Generators")
    print("=" * 60)
    print("--- Paginated API ---")
    await demo_async_generator()
    print("--- Batched generator ---")
    await demo_batched_generator()

    print("=" * 60)
    print("PATTERN 10: Async Context Managers — Connection Pool")
    print("=" * 60)
    await demo_connection_pool()

    print("=" * 60)
    print("PATTERN 11: Cancellation & Shield")
    print("=" * 60)
    print("--- Cleanup on cancel ---")
    await demo_cancellation()
    print("--- Shield critical save ---")
    await main_with_shield()

    print("=" * 60)
    print("COMBINED: Async Pipeline (fetch → transform → save)")
    print("=" * 60)
    await demo_pipeline()


if __name__ == "__main__":
    asyncio.run(run_all())
