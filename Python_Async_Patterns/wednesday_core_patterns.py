"""
PYTHON ASYNC PROGRAMMING - WEDNESDAY PRACTICE
Core Patterns for Interview Readiness

Topics Covered:
  1. Coroutines & Event Loop basics
  2. asyncio.gather  — fan-out / fan-in
  3. asyncio.Queue   — producer-consumer
  4. asyncio.Semaphore — rate-limiting / concurrency control
  5. asyncio.wait_for  — timeouts
  6. asyncio.create_task — background tasks

Run each section independently:
  python wednesday_core_patterns.py
"""

import asyncio
import random
import time


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 1: Coroutines & Event Loop
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: async def defines a *coroutine function*. Calling it returns a
# coroutine object — it does NOT run yet. The event loop drives execution.
# `await` suspends the current coroutine and yields control back to the loop.

# ── Problem 1.1 ──────────────────────────────────────────────────────────────
# Write a coroutine `fetch_data(name, delay)` that simulates a network call.
# Then run three fetches sequentially and compare to running them concurrently.

async def fetch_data(name: str, delay: float) -> str:
    print(f"  [START] {name}")
    await asyncio.sleep(delay)          # non-blocking wait — loop can do other work
    print(f"  [DONE]  {name}")
    return f"{name}: result"

async def demo_sequential():
    """Sequential: total time ≈ sum of all delays."""
    t0 = time.perf_counter()
    r1 = await fetch_data("A", 1.0)
    r2 = await fetch_data("B", 0.5)
    r3 = await fetch_data("C", 0.8)
    print(f"  Sequential total: {time.perf_counter() - t0:.2f}s -> {[r1,r2,r3]}\n")

async def demo_concurrent_gather():
    """Concurrent via gather: total time ≈ max(delays)."""
    t0 = time.perf_counter()
    results = await asyncio.gather(
        fetch_data("A", 1.0),
        fetch_data("B", 0.5),
        fetch_data("C", 0.8),
    )
    print(f"  Concurrent total: {time.perf_counter() - t0:.2f}s -> {results}\n")


# ── Problem 1.2 (Interview Question) ─────────────────────────────────────────
# Given a list of URLs and a fetch coroutine, return all results.
# Handle errors: if one URL fails, return None for that URL (don't crash all).

async def unreliable_fetch(url: str) -> str:
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if "bad" in url:
        raise ValueError(f"Failed: {url}")
    return f"OK({url})"

async def fetch_all_safe(urls: list[str]) -> list[str | None]:
    """
    Pattern: gather with return_exceptions=True.
    Replaces exceptions with None (or you can log them).
    """
    results = await asyncio.gather(
        *[unreliable_fetch(u) for u in urls],
        return_exceptions=True,         # KEY: exceptions become values, not raises
    )
    return [None if isinstance(r, Exception) else r for r in results]


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 2: asyncio.Queue — Producer-Consumer
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: asyncio.Queue is the async equivalent of queue.Queue.
# - put() / get() are coroutines (await them).
# - task_done() + join() provide a clean shutdown signal.
# - Use maxsize to add backpressure (producer blocks if queue is full).

# ── Problem 2.1 ──────────────────────────────────────────────────────────────
# Design a system with 1 producer generating 10 work items and 3 consumers
# processing them. Consumers should stop when production is done.

async def producer(queue: asyncio.Queue, n_items: int):
    for i in range(n_items):
        item = f"item-{i}"
        await queue.put(item)           # blocks if queue is full (backpressure)
        print(f"  Produced {item}")
    # Signal shutdown: one sentinel per consumer
    for _ in range(3):
        await queue.put(None)

async def consumer(name: str, queue: asyncio.Queue):
    while True:
        item = await queue.get()        # blocks until an item is available
        if item is None:                # sentinel value → clean shutdown
            print(f"  {name}: shutting down")
            break
        await asyncio.sleep(0.1)        # simulate work
        print(f"  {name}: processed {item}")

async def demo_producer_consumer():
    queue = asyncio.Queue(maxsize=5)    # backpressure: producer pauses if queue full
    await asyncio.gather(
        producer(queue, 10),
        consumer("Worker-1", queue),
        consumer("Worker-2", queue),
        consumer("Worker-3", queue),
    )
    print()


# ── Problem 2.2 (Interview Question) ─────────────────────────────────────────
# Use queue.join() instead of sentinels. This is safer when consumer count
# is not fixed at producer time.

async def producer_v2(queue: asyncio.Queue, items: list):
    for item in items:
        await queue.put(item)

async def consumer_v2(name: str, queue: asyncio.Queue):
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            break                       # no new item in 1s → assume done
        await asyncio.sleep(0.05)
        print(f"  {name}: done {item}")
        queue.task_done()               # KEY: pair every get() with task_done()

async def demo_queue_join():
    queue = asyncio.Queue()
    tasks = [asyncio.create_task(consumer_v2(f"W{i}", queue)) for i in range(3)]
    await producer_v2(queue, [f"job-{i}" for i in range(9)])
    await queue.join()                  # blocks until every task_done() is called
    for t in tasks: t.cancel()
    print()


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 3: asyncio.Semaphore — Rate Limiting / Concurrency Control
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: Semaphore(N) means "at most N coroutines can hold this lock
# simultaneously." Essential for respecting API rate limits or thread budgets.

# ── Problem 3.1 ──────────────────────────────────────────────────────────────
# You must call an external API for 20 URLs but must not exceed 5 concurrent
# requests. How do you do it?

async def api_call(url: str, semaphore: asyncio.Semaphore) -> str:
    async with semaphore:               # acquires on enter, releases on exit
        await asyncio.sleep(random.uniform(0.05, 0.2))
        return f"response({url})"

async def demo_rate_limited_fetch(urls: list[str], max_concurrent: int = 5):
    sem = asyncio.Semaphore(max_concurrent)
    t0 = time.perf_counter()
    results = await asyncio.gather(*[api_call(u, sem) for u in urls])
    print(f"  Fetched {len(results)} URLs, max {max_concurrent} concurrent, "
          f"in {time.perf_counter()-t0:.2f}s")
    return results


# ── Problem 3.2 (Interview Question) ─────────────────────────────────────────
# Implement a token-bucket style rate limiter using a Semaphore + periodic
# release (sliding window approach).

class RateLimiter:
    """
    Allows at most `rate` calls per `period` seconds.
    Pattern: semaphore + background task that releases tokens.
    """
    def __init__(self, rate: int, period: float):
        self._sem = asyncio.Semaphore(rate)
        self._rate = rate
        self._period = period

    async def _refill(self):
        while True:
            await asyncio.sleep(self._period)
            for _ in range(self._rate):
                try:
                    self._sem.release()
                except ValueError:
                    pass               # already at max — ignore

    async def acquire(self):
        await self._sem.acquire()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *_):
        pass                           # token is consumed; refill is periodic


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 4: asyncio.wait_for — Timeouts
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: wrap any awaitable in wait_for(coro, timeout=N). On timeout,
# the inner coroutine is cancelled and TimeoutError is raised.

# ── Problem 4.1 ──────────────────────────────────────────────────────────────
# Implement retry-with-timeout: try a flaky operation up to 3 times with a
# 0.5s timeout each attempt. Return the result or raise after exhausting retries.

async def flaky_operation(attempt: int) -> str:
    delay = random.uniform(0.1, 0.7)
    await asyncio.sleep(delay)
    if delay > 0.5:
        raise RuntimeError(f"Slow on attempt {attempt}")
    return f"success on attempt {attempt}"

async def retry_with_timeout(max_retries: int = 3, timeout: float = 0.5) -> str:
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.wait_for(
                flaky_operation(attempt),
                timeout=timeout,
            )
            print(f"  Succeeded on attempt {attempt}")
            return result
        except (asyncio.TimeoutError, RuntimeError) as e:
            last_err = e
            print(f"  Attempt {attempt} failed: {e}")
    raise RuntimeError(f"All {max_retries} retries exhausted") from last_err


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN 5: asyncio.create_task — Background Tasks
# ─────────────────────────────────────────────────────────────────────────────
# KEY INSIGHT: create_task() schedules a coroutine to run *concurrently*
# without awaiting it immediately. You get a Task object you can await later,
# cancel, or attach callbacks to.
# WARNING: Always keep a reference to tasks — garbage collection can cancel them!

# ── Problem 5.1 ──────────────────────────────────────────────────────────────
# Run a "heartbeat" background task while doing main work.
# Cancel the heartbeat cleanly when main work is done.

async def heartbeat(interval: float = 0.3):
    try:
        count = 0
        while True:
            count += 1
            print(f"  ♥ heartbeat #{count}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        print("  ♥ heartbeat stopped")
        raise                           # re-raise: important for clean shutdown

async def main_work(steps: int = 3):
    for i in range(steps):
        print(f"  Main work step {i+1}")
        await asyncio.sleep(0.4)

async def demo_background_task():
    hb_task = asyncio.create_task(heartbeat(0.3))  # starts immediately
    await main_work(3)
    hb_task.cancel()
    try:
        await hb_task                   # wait for cancellation to propagate
    except asyncio.CancelledError:
        pass
    print()


# ─────────────────────────────────────────────────────────────────────────────
# INTERVIEW QUICKFIRE — Common Pitfalls
# ─────────────────────────────────────────────────────────────────────────────

PITFALLS = """
Common Async Pitfalls to Know for Interviews:
──────────────────────────────────────────────
1. Blocking the event loop
   BAD:  time.sleep(1)          # freezes the loop!
   GOOD: await asyncio.sleep(1)

2. Forgetting `await`
   BAD:  result = fetch_data()  # returns a coroutine object, not the result
   GOOD: result = await fetch_data()

3. Not keeping Task references (silent cancellation)
   BAD:  asyncio.create_task(work())  # task may be GC'd immediately
   GOOD: task = asyncio.create_task(work())  # keep reference

4. Using gather without return_exceptions — one error kills all
   BAD:  await asyncio.gather(*coros)
   GOOD: await asyncio.gather(*coros, return_exceptions=True)

5. Forgetting task_done() in Queue patterns → join() hangs forever

6. Re-raising CancelledError in cleanup
   Always `raise` after catching CancelledError so cancellation propagates.
"""


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_all():
    print("=" * 60)
    print("PATTERN 1: Coroutines & gather")
    print("=" * 60)
    print("--- Sequential ---")
    await demo_sequential()
    print("--- Concurrent (gather) ---")
    await demo_concurrent_gather()
    urls = ["site.com/a", "site.com/bad-url", "site.com/b", "site.com/c"]
    results = await fetch_all_safe(urls)
    print(f"  Safe fetch results: {results}\n")

    print("=" * 60)
    print("PATTERN 2: Producer-Consumer (Queue)")
    print("=" * 60)
    print("--- Sentinel shutdown ---")
    await demo_producer_consumer()
    print("--- join() shutdown ---")
    await demo_queue_join()

    print("=" * 60)
    print("PATTERN 3: Semaphore (Rate Limiting)")
    print("=" * 60)
    urls_20 = [f"api.com/{i}" for i in range(20)]
    await demo_rate_limited_fetch(urls_20, max_concurrent=5)
    print()

    print("=" * 60)
    print("PATTERN 4: Timeouts & Retry")
    print("=" * 60)
    random.seed(42)
    try:
        result = await retry_with_timeout(max_retries=4, timeout=0.5)
        print(f"  Final result: {result}")
    except RuntimeError as e:
        print(f"  Gave up: {e}")
    print()

    print("=" * 60)
    print("PATTERN 5: Background Tasks")
    print("=" * 60)
    await demo_background_task()

    print(PITFALLS)


if __name__ == "__main__":
    asyncio.run(run_all())
