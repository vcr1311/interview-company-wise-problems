"""
PYTHON ASYNC CHEATSHEET
Quick reference for interview prep — all patterns at a glance.
"""

# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVES
# ─────────────────────────────────────────────────────────────────────────────

import asyncio

# --- Entry Point ---
async def main(): ...
asyncio.run(main())                          # Python 3.7+ standard entry point

# --- Coroutine basics ---
async def coro(): return 42
result = await coro()                        # await inside another async def

# --- Create & schedule a task (runs concurrently) ---
task = asyncio.create_task(coro())          # schedules immediately
result = await task                          # wait for completion
task.cancel()                               # request cancellation

# ─────────────────────────────────────────────────────────────────────────────
# GATHER vs AS_COMPLETED vs WAIT
# ─────────────────────────────────────────────────────────────────────────────

# gather: run all, return results in SUBMISSION order
results = await asyncio.gather(coro(), coro(), coro())
results = await asyncio.gather(*coros, return_exceptions=True)  # errors as values

# as_completed: iterate futures as they FINISH (arrival order)
for fut in asyncio.as_completed(coros):
    result = await fut

# wait: fine-grained control — split into done/pending sets
done, pending = await asyncio.wait(
    tasks,
    return_when=asyncio.FIRST_COMPLETED,    # or ALL_COMPLETED, FIRST_EXCEPTION
    timeout=5.0,
)
for t in pending: t.cancel()

# ─────────────────────────────────────────────────────────────────────────────
# SYNCHRONIZATION PRIMITIVES
# ─────────────────────────────────────────────────────────────────────────────

lock = asyncio.Lock()
async with lock: ...                        # mutual exclusion

sem = asyncio.Semaphore(5)
async with sem: ...                         # at most 5 concurrent holders

event = asyncio.Event()
await event.wait()                          # block until set()
event.set()                                 # unblock all waiters
event.clear()                               # reset to unset

cond = asyncio.Condition()
async with cond:
    await cond.wait()                       # release lock, sleep until notified
    cond.notify()                           # wake one waiter
    cond.notify_all()                       # wake all waiters

# ─────────────────────────────────────────────────────────────────────────────
# QUEUE
# ─────────────────────────────────────────────────────────────────────────────

q = asyncio.Queue(maxsize=10)              # maxsize=0 → unbounded
await q.put(item)                          # blocks if full
item = await q.get()                       # blocks if empty
q.task_done()                              # signal one item processed
await q.join()                             # block until all task_done() called

# Also: asyncio.LifoQueue, asyncio.PriorityQueue

# ─────────────────────────────────────────────────────────────────────────────
# TIMEOUTS
# ─────────────────────────────────────────────────────────────────────────────

try:
    result = await asyncio.wait_for(coro(), timeout=5.0)
except asyncio.TimeoutError:
    ...

# Python 3.11+ — asyncio.timeout context manager (preferred)
# async with asyncio.timeout(5.0):
#     result = await coro()

# ─────────────────────────────────────────────────────────────────────────────
# SHIELD — Protect inner coro from outer cancellation
# ─────────────────────────────────────────────────────────────────────────────

await asyncio.shield(coro())               # inner coro NOT cancelled if outer is

# ─────────────────────────────────────────────────────────────────────────────
# ASYNC GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

async def async_gen():
    for i in range(10):
        await asyncio.sleep(0)
        yield i

async for item in async_gen(): ...

# Wrap sync iterable as async:
async def to_async(iterable):
    for item in iterable:
        yield item

# ─────────────────────────────────────────────────────────────────────────────
# ASYNC CONTEXT MANAGERS
# ─────────────────────────────────────────────────────────────────────────────

class MyResource:
    async def __aenter__(self):
        await self._setup()
        return self
    async def __aexit__(self, exc_type, exc, tb):
        await self._teardown()

# OR use decorator (simpler for one-offs):
from contextlib import asynccontextmanager

@asynccontextmanager
async def managed_resource():
    resource = await acquire()
    try:
        yield resource
    finally:
        await release(resource)

async with managed_resource() as r: ...

# ─────────────────────────────────────────────────────────────────────────────
# CANCELLATION — RULES
# ─────────────────────────────────────────────────────────────────────────────

async def safe_task():
    try:
        await long_running()
    except asyncio.CancelledError:
        await cleanup()                 # do cleanup
        raise                           # ALWAYS re-raise

# Check if cancelled without raising:
task = asyncio.create_task(coro())
task.cancelled()                        # True if cancelled and raised

# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS & FUTURES (low level, rarely needed)
# ─────────────────────────────────────────────────────────────────────────────

task.add_done_callback(lambda t: print(t.result()))
loop = asyncio.get_event_loop()
future = loop.run_in_executor(None, blocking_fn, arg)  # run in thread pool

# ─────────────────────────────────────────────────────────────────────────────
# KEY PATTERNS TABLE
# ─────────────────────────────────────────────────────────────────────────────

"""
┌─────────────────────┬───────────────────────────┬──────────────────────────────┐
│ Scenario            │ Tool                      │ Key Code                     │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Run N coros, get    │ asyncio.gather()           │ results = await gather(*c)   │
│ all results         │                           │                              │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Process results as  │ asyncio.as_completed()     │ for f in as_completed(c):    │
│ they arrive         │                           │     r = await f              │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ First result wins   │ as_completed + break       │ break after first success    │
│ (hedged requests)   │                           │ cancel remaining tasks       │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Producer-Consumer   │ asyncio.Queue              │ put() / get() / task_done()  │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Rate limit (N       │ asyncio.Semaphore(N)       │ async with sem: ...          │
│ concurrent)         │                           │                              │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Timeout             │ asyncio.wait_for()         │ wait_for(coro, timeout=5)    │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ One-shot broadcast  │ asyncio.Event              │ event.set() / await .wait()  │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Shared state guard  │ asyncio.Lock               │ async with lock: ...         │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Lazy async stream   │ async generator            │ async def f(): yield ...     │
│                     │                           │ async for x in f(): ...      │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Resource lifecycle  │ async context manager      │ async with Resource() as r:  │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Background task     │ create_task + cancel()     │ t = create_task(coro())      │
│                     │                           │ t.cancel(); await t          │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Protect from cancel │ asyncio.shield()           │ await shield(coro())         │
├─────────────────────┼───────────────────────────┼──────────────────────────────┤
│ Run blocking code   │ run_in_executor            │ await loop.run_in_executor(  │
│ (CPU/IO)            │                           │     None, blocking_fn, arg)  │
└─────────────────────┴───────────────────────────┴──────────────────────────────┘
"""

# ─────────────────────────────────────────────────────────────────────────────
# PITFALLS — MEMORIZE THESE
# ─────────────────────────────────────────────────────────────────────────────

"""
1. time.sleep() blocks the thread → use await asyncio.sleep()
2. Forgot `await` → get a coroutine object, not the result
3. Task GC'd → task may be silently cancelled; always keep a reference
4. gather without return_exceptions → one failure cancels all
5. task_done() missing → queue.join() hangs forever
6. Not re-raising CancelledError → masks cancellation, loop never exits
7. asyncio.Lock is NOT thread-safe → use threading.Lock for threads
8. CPU-bound work in async def → blocks event loop; use run_in_executor
"""
