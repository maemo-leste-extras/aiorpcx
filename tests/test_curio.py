from asyncio import get_event_loop, InvalidStateError
import time

import pytest

from aiorpcx.curio import *


def sum_all(*values):
    return sum(values)


async def my_raises(exc):
    raise exc


async def return_value(x, secs=0):
    if secs:
        await sleep(secs)
    return x


# Test exports
sleep
CancelledError
Event
Lock
Queue
Semaphore


@pytest.mark.asyncio
async def test_run_in_thread():
    assert await run_in_thread(sum_all) == 0
    assert await run_in_thread(sum_all, 1) == 1
    assert await run_in_thread(sum_all, 1, 2, 3) == 6


@pytest.mark.asyncio
async def test_next_done():
    t = TaskGroup()
    assert t.completed is None
    assert await t.next_done() is None
    assert await t.next_done() is None

    tasks = ()
    t = TaskGroup(tasks)
    assert t.completed is None
    assert await t.next_done() is None

    tasks = (await spawn(sleep, 0.01), await spawn(sleep, 0.02))
    t = TaskGroup(tasks)
    assert (await t.next_done(), await t.next_done()) == tasks
    assert t.completed is tasks[0]
    assert await t.next_done() is None

    tasks = (await spawn(sleep, 0), await spawn(sleep, 0.01))
    tasks[0].cancel()
    await sleep(0)
    t = TaskGroup(tasks)
    assert (await t.next_done(), await t.next_done()) == tasks
    assert await t.next_done() is None

    tasks = (await spawn(sleep(0.002)), await spawn(sleep, 0.001))
    t = TaskGroup(tasks)
    assert await t.next_done() == tasks[1]
    assert await t.next_done() == tasks[0]
    assert await t.next_done() is None
    assert t.completed is tasks[1]

    tasks = (await spawn(sleep, 0.02), await spawn(sleep, 0.01))
    for task in tasks:
        task.cancel()
    t = TaskGroup(tasks)
    assert await t.next_done() == tasks[0]
    assert await t.next_done() == tasks[1]
    assert await t.next_done() is None


@pytest.mark.asyncio
async def test_next_result():
    t = TaskGroup()
    with pytest.raises(RuntimeError):
        await t.next_result()

    tasks = ()
    t = TaskGroup(tasks)
    with pytest.raises(RuntimeError):
        await t.next_result()

    tasks = (await spawn(return_value(1)), await spawn(return_value(2)))
    t = TaskGroup(tasks)
    assert (await t.next_result(), await t.next_result()) == (1, 2)
    with pytest.raises(RuntimeError):
        await t.next_result()


@pytest.mark.asyncio
async def test_tg_spawn():
    t = TaskGroup()
    task = await t.spawn(sleep, 0.01)
    assert await t.next_done() == task
    assert await t.next_done() is None
    task = await t.spawn(sleep(0.01))
    assert await t.next_done() == task


@pytest.mark.asyncio
async def test_tg_cancel_remaining():
    tasks = [await spawn(sleep, x/200) for x in range(1, 4)]
    t = TaskGroup(tasks)
    assert await t.next_done()
    await t.cancel_remaining()
    assert not tasks[0].cancelled()
    assert all(task.cancelled() for task in tasks[1:])


@pytest.mark.asyncio
async def test_tg_aiter():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    t = TaskGroup(tasks)
    result = [task async for task in t]
    assert result == list(reversed(tasks))


@pytest.mark.asyncio
async def test_tg_join_no_arg():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    t = TaskGroup(tasks)
    await t.join()
    assert all(task.done() for task in tasks)
    assert not any(task.cancelled() for task in tasks)


@pytest.mark.asyncio
async def test_tg_cm_no_arg():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    async with TaskGroup(tasks) as t:
        pass
    assert all(task.done() for task in tasks)
    assert not any(task.cancelled() for task in tasks)
    assert t.completed is tasks[-1]


@pytest.mark.asyncio
async def test_tg_cm_all():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    async with TaskGroup(tasks, wait=all) as t:
        pass
    assert all(task.done() for task in tasks)
    assert not any(task.cancelled() for task in tasks)
    assert t.completed is tasks[-1]


@pytest.mark.asyncio
async def test_tg_cm_any():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    async with TaskGroup(tasks, wait=any) as t:
        pass
    assert all(task.done() for task in tasks)
    assert not tasks[-1].cancelled()
    assert all(task.cancelled() for task in tasks[:-1])
    assert t.completed is tasks[-1]


@pytest.mark.asyncio
async def test_tg_join_object():
    tasks = [await spawn(return_value(None, 0.01)),
             await spawn(return_value(3, 0.02))]
    t = TaskGroup(tasks, wait=object)
    await t.join()
    assert tasks[0].result() == None
    assert tasks[1].result() == 3
    assert t.completed is tasks[1]

    tasks = [await spawn(return_value(None, 0.01)),
             await spawn(return_value(4, 0.02)),
             await spawn(return_value(2, 0.03))]
    t = TaskGroup(tasks, wait=object)
    await t.join()
    assert tasks[0].result() == None
    assert tasks[1].result() == 4
    assert tasks[2].cancelled()
    assert t.completed is tasks[1]


@pytest.mark.asyncio
async def test_tg_cm_object():
    tasks = [await spawn(return_value(None, 0.01)),
             await spawn(return_value(3, 0.02))]
    async with TaskGroup(tasks, wait=object) as t:
        pass
    assert tasks[0].result() == None
    assert tasks[1].result() == 3
    assert t.completed is tasks[1]

    tasks = [await spawn(return_value(None, 0.01)),
             await spawn(return_value(4, 0.02)),
             await spawn(return_value(2, 0.03))]
    async with TaskGroup(tasks, wait=object) as t:
        pass
    assert tasks[0].result() == None
    assert tasks[1].result() == 4
    assert tasks[2].cancelled()
    assert t.completed is tasks[1]


@pytest.mark.asyncio
async def test_tg_join_errored():
    for wait in (all, any, object):
        tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
        t = TaskGroup(tasks, wait=wait)
        bad_task = await t.spawn(my_raises(ArithmeticError))
        with pytest.raises(ArithmeticError):
            await t.join()
        assert all(task.cancelled() for task in tasks)
        assert bad_task.done() and not bad_task.cancelled()
        assert t.completed is None


@pytest.mark.asyncio
async def test_tg_cm_errored():
    for wait in (all, any, object):
        tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
        with pytest.raises(EOFError):
            async with TaskGroup(tasks, wait=wait) as t:
                bad_task = await t.spawn(my_raises(EOFError))
        assert all(task.cancelled() for task in tasks)
        assert bad_task.done() and not bad_task.cancelled()
        assert t.completed is None


@pytest.mark.asyncio
async def test_tg_join_errored_past():
    for wait in (all, any, object):
        tasks = [await spawn(my_raises, AttributeError) for n in range(3)]
        t = TaskGroup(tasks, wait=wait)
        tasks[1].cancel()
        await sleep(0.001)
        good_task = await t.spawn(return_value(3, 0.001))
        with pytest.raises(AttributeError):
            await t.join()
        assert good_task.cancelled()
        assert t.completed is None


@pytest.mark.asyncio
async def test_cm_join_errored_past():
    for wait in (all, any, object):
        tasks = [await spawn(my_raises, BufferError) for n in range(3)]
        with pytest.raises(BufferError):
            async with TaskGroup(tasks, wait=wait) as t:
                tasks[1].cancel()
                await sleep(0.001)
                good_task = await t.spawn(return_value(3, 0.001))
        assert good_task.cancelled()
        assert t.completed is None


@pytest.mark.asyncio
async def test_cm_raises():
    tasks = [await spawn(sleep, 0.01) for n in range(3)]
    with pytest.raises(ValueError) as e:
        async with TaskGroup(tasks) as t:
            raise ValueError
    assert all(task.cancelled() for task in tasks)


@pytest.mark.asyncio
async def test_cm_add_later():
    tasks = [await spawn(sleep, 0) for n in range(3)]
    with pytest.raises(LookupError):
        async with TaskGroup(tasks) as t:
            await sleep(0.001)
            task = await t.spawn(my_raises, LookupError)
    assert all(task.result() is None for task in tasks)
    assert t.completed in tasks


@pytest.mark.asyncio
async def test_tg_multiple_groups():
    task = await spawn(my_raises, FloatingPointError)
    t1 = TaskGroup([task])
    with pytest.raises(RuntimeError):
        TaskGroup([task])
    t3 = TaskGroup()
    with pytest.raises(RuntimeError):
        await t3.add_task(task)
    with pytest.raises(FloatingPointError):
        await task


@pytest.mark.asyncio
async def test_tg_closed():
    task = await spawn(return_value(3))
    for wait in (all, any, object):
        t = TaskGroup()
        assert not t.closed()
        await t.join()
        assert t.closed()
        with pytest.raises(RuntimeError):
            await t.spawn(my_raises, ImportError)
        with pytest.raises(RuntimeError):
            await t.add_task(task)
    await task


@pytest.mark.asyncio
async def test_tg_wait_bad():
    tasks = [await spawn(sleep, x/200) for x in range(5, 0, -1)]
    with pytest.raises(ValueError):
        TaskGroup(tasks, wait=None)
    assert not any(task.cancelled() for task in tasks)
    for task in tasks:
        await task


class MyLogger(object):
    def __init__(self):
        self.logged = False

    def error(self, msg, *args, **kwargs):
        self.logged = True


@pytest.mark.asyncio
async def test_logging(caplog):
    for report_crash in (True, False):
        # spawn
        task = await spawn(my_raises(TypeError), report_crash=report_crash)
        try:
            await task
            assert False
        except TypeError:
            pass

    assert any('TypeError' in record.message for record in caplog.records)


async def return_after_sleep(x, period=0.01):
    await sleep(period)
    return x


@pytest.mark.asyncio
async def test_timeout_after_coro_callstyles():
    async def t1(*values):
        return 1 + sum(values)

    assert await timeout_after(0.01, t1) == 1
    assert await timeout_after(0.01, t1()) == 1
    assert await timeout_after(0.01, t1(2, 8)) == 11
    assert await timeout_after(0.01, t1, 2, 8) == 11

    coro = t1()
    with pytest.raises(ValueError):
        await timeout_after(0, coro, 1)
    await coro

@pytest.mark.asyncio
async def test_timeout_after_zero():
    async def t1(*values):
        return 1 + sum(values)

    assert await timeout_after(0, t1) == 1
    assert await timeout_after(0, t1, 2) == 3
    assert await timeout_after(0, t1, 2, 8) == 11


@pytest.mark.asyncio
async def test_timeout_after_no_expire():
    async def t1(*values):
        return await return_after_sleep(1 + sum(values), 0.01)

    try:
        assert await timeout_after(0.02, t1, 1) == 2
    except TaskTimeout:
        assert False
    await sleep(0.02)
    assert True


@pytest.mark.asyncio
async def test_nested_after_no_expire_nested():
    async def coro1():
        pass

    async def child():
        await timeout_after(0.001, coro1())

    async def parent():
        await timeout_after(0.003, child())

    await parent()
    try:
        await sleep(0.005)
    except CancelledError:
        assert False


@pytest.mark.asyncio
async def test_nested_after_no_expire_nested2():
    async def coro1():
        pass

    async def child():
        await timeout_after(0.001, coro1())
        await sleep(0.005)

    async def parent():
        try:
            await timeout_after(0.003, child())
        except TaskTimeout:
            return
        assert False

    await parent()


@pytest.mark.asyncio
async def test_timeout_after_raises_IndexError():
    try:
        await timeout_after(0.01, my_raises, IndexError)
    except IndexError:
        return
    assert False


@pytest.mark.asyncio
async def test_timeout_after_raises_CancelledError():
    try:
        await timeout_after(0.01, my_raises, CancelledError)
    except CancelledError:
        return
    assert False


@pytest.mark.asyncio
async def test_nested_timeout():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a timeout before the child.
    # Results in a TimeoutCancellationError instead of a normal TaskTimeout
    async def child():
        try:
            await timeout_after(0.05, coro1())
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            await timeout_after(0.01, child())
        except TaskTimeout:
            results.append('parent timeout')

    await parent()
    assert results == [
        'coro1 start',
        'coro1 timeout cancel',
        'coro2 start',
        'parent timeout'
    ]


@pytest.mark.asyncio
async def test_nested_context_timeout():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a timeout before the child.
    # Results in a TimeoutCancellationError instead of a normal TaskTimeout
    async def child():
        try:
            async with timeout_after(0.05) as ta:
                await coro1()
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        assert not ta.expired
        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            async with timeout_after(0.01) as ta:
                await child()
        except TaskTimeout:
            results.append('parent timeout')
        assert ta.expired

    await parent()
    assert results == [
        'coro1 start',
        'coro1 timeout cancel',
        'coro2 start',
        'parent timeout'
    ]


@pytest.mark.asyncio
async def test_nested_context_timeout2():
    async def coro1():
        try:
            async with timeout_after(1) as ta:
                await sleep(5)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            assert not ta.expired
            raise
        else:
            assert False

    async def coro2():
        try:
            async with timeout_after(1.5) as ta:
                await coro1()
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            assert not ta.expired
            raise
        else:
            assert False

    async def parent():
        try:
            async with timeout_after(0.01) as ta:
                await coro2()
        except (Exception, CancelledError) as e:
            assert isinstance(e, TaskTimeout)
        else:
            assert False
        assert ta.expired

    await parent()


@pytest.mark.asyncio
async def test_nested_context_timeout3():
    async def coro1():
        try:
            await timeout_after(1, sleep, 5)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def coro2():
        try:
            await timeout_after(1.5, coro1)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def parent():
        try:
            await timeout_after(0.001, coro2)
        except (Exception, CancelledError) as e:
            assert isinstance(e, TaskTimeout)
        else:
            assert False

    await parent()


@pytest.mark.asyncio
async def test_nested_timeout_again():
    try:
        async with timeout_after(0.01):
            raise TaskTimeout(1.0)
    except TaskTimeout:
        pass

@pytest.mark.asyncio
async def test_nested_timeout_uncaught():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(0.5)
        results.append('coro1 done')

    async def child():
        # This will cause a TaskTimeout, but it's uncaught
        await timeout_after(0.001, coro1())

    async def parent():
        try:
            await timeout_after(1, child())
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    await parent()
    assert results == [
        'coro1 start',
        'uncaught timeout'
    ]


@pytest.mark.asyncio
async def test_nested_context_timeout_uncaught():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(0.5)
        results.append('coro1 done')

    async def child():
        # This will cause a TaskTimeout, but it's uncaught
        async with timeout_after(0.001):
            await coro1()

    async def parent():
        try:
            async with timeout_after(1):
                await child()
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    await parent()
    assert results == [
        'coro1 start',
        'uncaught timeout'
    ]


@pytest.mark.asyncio
async def test_timeout_at_time():
    async def t1(*values):
        return 1 + sum(values)

    loop = get_event_loop()
    assert await timeout_at(loop.time(), t1) == 1
    assert await timeout_at(loop.time(), t1, 2, 8) == 11


@pytest.mark.asyncio
async def test_timeout_at_expires():
    async def slow():
        await sleep(0.02)
        return 2

    loop = get_event_loop()
    try:
        await timeout_at(loop.time() + 0.001, slow)
    except TaskTimeout:
        return
    assert False


@pytest.mark.asyncio
async def test_timeout_at_context():
    loop = get_event_loop()
    try:
        async with timeout_at(loop.time() + 0.001):
            await sleep(0.02)
    except TaskTimeout:
        return
    assert False


# Ignore


@pytest.mark.asyncio
async def test_ignore_after_coro_callstyles():
    async def t1(*values):
        return 1 + sum(values)

    assert await ignore_after(0.001, t1) == 1
    assert await ignore_after(0.001, t1()) == 1
    assert await ignore_after(0.001, t1(2, 8)) == 11
    assert await ignore_after(0.001, t1, 2, 8) == 11


@pytest.mark.asyncio
async def test_ignore_after_timeout_result():
    async def t1(*values):
        await sleep(0.01)
        return 1 + sum(values)

    assert await ignore_after(0.005, t1, timeout_result=100) == 100
    assert await ignore_after(0.005, t1, timeout_result=all) is all


@pytest.mark.asyncio
async def test_ignore_after_zero():
    async def t1(*values):
        return 1 + sum(values)

    assert await ignore_after(0, t1) == 1
    assert await ignore_after(0, t1, 2) == 3
    assert await ignore_after(0, t1, 2, 8) == 11


@pytest.mark.asyncio
async def test_ignore_after_no_expire():
    async def t1(*values):
        return await return_after_sleep(1 + sum(values), 0.001)

    assert await ignore_after(0.005, t1, 1) == 2
    await sleep(0.002)


@pytest.mark.asyncio
async def test_ignore_after_no_expire_nested():
    async def coro1():
        return 2

    async def child():
        return await ignore_after(0.001, coro1())

    async def parent():
        return await ignore_after(0.003, child())

    try:
        result = await parent()
        await sleep(0.005)
    except:
        assert False
    else:
        assert result == 2


@pytest.mark.asyncio
async def test_ignore_after_no_expire_nested2():
    async def coro1():
        return 5

    async def child():
        result = await ignore_after(0.001, coro1(), timeout_result=1)
        await sleep(0.005)
        return result

    async def parent():
        try:
            result = await ignore_after(0.003, child())
        except:
            assert False
        assert result is None

    await parent()


@pytest.mark.asyncio
async def test_ignore_after_raises_KeyError():
    try:
        await ignore_after(0.01, my_raises, KeyError)
    except KeyError:
        return
    assert False


@pytest.mark.asyncio
async def test_ignore_after_raises_CancelledError():
    try:
        await ignore_after(0.01, my_raises, CancelledError)
    except CancelledError:
        return
    assert False


@pytest.mark.asyncio
async def test_nested_ignore():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a ignore before the child.
    # Results in a TimeoutCancellationError instead of a normal TaskTimeout
    async def child():
        try:
            await ignore_after(0.005, coro1())
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            await ignore_after(0.001, child())
            results.append('parent success')
        except TaskTimeout:
            results.append('parent timeout')

    await parent()
    assert results == [
        'coro1 start',
        'coro1 timeout cancel',
        'coro2 start',
        'parent success'
    ]


@pytest.mark.asyncio
async def test_nested_ignore_context_timeout():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a timeout before the child.
    # Results in a TimeoutCancellationError instead of a normal ignore
    async def child():
        try:
            async with ignore_after(0.005):
                await coro1()
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            async with ignore_after(0.001):
                await child()
            results.append('parent success')
        except TaskTimeout:
            results.append('parent timeout')

    await parent()
    assert results == [
        'coro1 start',
        'coro1 timeout cancel',
        'coro2 start',
        'parent success'
    ]


@pytest.mark.asyncio
async def test_nested_ignore_context_timeout2():
    async def coro1():
        try:
            async with ignore_after(1):
                await sleep(5)
            assert False
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise

    async def coro2():
        try:
            async with ignore_after(1.5):
                await coro1()
            assert False
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise

    async def parent():
        try:
            async with ignore_after(0.001):
                await coro2()
        except:
            assert False

    await parent()


@pytest.mark.asyncio
async def test_nested_ignore_context_timeout3():
    async def coro1():
        try:
            await ignore_after(1, sleep, 5)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def coro2():
        try:
            await ignore_after(1.5, coro1)
            return 3
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def parent():
        try:
            result = await ignore_after(0.001, coro2)
        except Exception as e:
            assert False
        else:
            assert result is None

    await parent()


@pytest.mark.asyncio
async def test_nested_ignore_timeout_uncaught():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(0.5)
        results.append('coro1 done')

    async def child():
        # This will do nothing
        await ignore_after(0.001, coro1())
        results.append('coro1 ignored')
        return 1

    async def parent():
        try:
            if await ignore_after(0.002, child()) is None:
                results.append('child ignored')
            else:
                results.append('child succeeded')
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    await parent()
    assert results == [
        'coro1 start',
        'coro1 ignored',
        'child succeeded'
    ]


@pytest.mark.asyncio
async def test_nested_ignore_context_timeout_uncaught():
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(0.05)
        results.append('coro1 done')

    async def child():
        # This will be ignored
        async with ignore_after(0.001):
            await coro1()
        results.append('child succeeded')

    async def parent():
        try:
            async with ignore_after(0.1):
                await child()
                results.append('parent succeeded')
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    await parent()
    assert results == [
        'coro1 start',
        'child succeeded',
        'parent succeeded'
    ]


@pytest.mark.asyncio
async def test_ignore_at_time():
    async def t1(*values):
        return 1 + sum(values)

    loop = get_event_loop()
    assert await ignore_at(loop.time(), t1) == 1
    assert await ignore_at(loop.time(), t1, 2, 8) == 11


@pytest.mark.asyncio
async def test_ignore_at_expires():
    async def slow():
        await sleep(0.02)
        return 2

    loop = get_event_loop()
    try:
        result = await ignore_at(loop.time() + 0.001, slow())
    except:
        assert False
    assert result is None

    try:
        result = await ignore_at(loop.time() + 0.001, slow, timeout_result=1)
    except:
        assert False
    assert result == 1


@pytest.mark.asyncio
async def test_ignore_at_context():

    loop = get_event_loop()
    try:
        async with ignore_at(loop.time() + 0.001):
            await sleep(0.02)
            assert False
    except:
        assert False


#
# Task group tests snitched from curio
#

@pytest.mark.asyncio
async def test_task_group():
    async def child(x, y):
        return x + y

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child, 2, 2)
            t3 = await g.spawn(child, 3, 3)

        assert t1.result() == 2
        assert t2.result() == 4
        assert t3.result() == 6

    await main()


@pytest.mark.asyncio
async def test_task_group_existing():
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        t1 = await spawn(child, 1, 1)
        t2 = await spawn(child2, 2, 2)
        t3 = await spawn(child2, 3, 3)
        t4 = await spawn(child, 4, 4)
        await t1
        await t4

        async with TaskGroup([t1, t2, t3]) as g:
            evt.set()
            await g.add_task(t4)

        assert t1.result() == 2
        assert t2.result() == 4
        assert t3.result() == 6
        assert t4.result() == 8

    await main()


@pytest.mark.asyncio
async def test_task_any_cancel():
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        async with TaskGroup(wait=any) as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child2, 2, 2)
            t3 = await g.spawn(child2, 3, 3)

        assert t1.result() == 2
        assert t1 == g.completed
        assert t2.cancelled()
        assert t3.cancelled()

    await main()


@pytest.mark.asyncio
async def test_task_any_error():
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        try:
            async with TaskGroup(wait=any) as g:
                t1 = await g.spawn(child, 1, '1')
                t2 = await g.spawn(child2, 2, 2)
                t3 = await g.spawn(child2, 3, 3)
        except TypeError as e:
            assert e == t1.exception()
        else:
            assert False
        assert t2.cancelled()
        assert t3.cancelled()

    await main()


@pytest.mark.asyncio
async def test_task_group_iter():
    async def child(x, y):
        return x + y

    async def main():
        results = set()
        async with TaskGroup() as g:
            await g.spawn(child, 1, 1)
            await g.spawn(child, 2, 2)
            await g.spawn(child, 3, 3)
            async for task in g:
                results.add(task.result())

        assert results == { 2, 4, 6 }

    await main()


@pytest.mark.asyncio
async def test_task_group_error():
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, 1, 1)
                t2 = await g.spawn(child, 2, 2)
                t3 = await g.spawn(child, 3, 'bad')
        except TypeError as e:
            assert e == t3.exception()
        else:
            assert False
        assert t1.cancelled()
        assert t2.cancelled()

    await main()


@pytest.mark.asyncio
async def test_task_group_error_block():
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, 1, 1)
                t2 = await g.spawn(child, 2, 2)
                t3 = await g.spawn(child, 3, 3)
                raise RuntimeError()
        except RuntimeError:
            assert True
        else:
            assert False
        assert t1.cancelled()
        assert t2.cancelled()
        assert t3.cancelled()

    await main()


@pytest.mark.asyncio
async def test_task_group_multierror():
    evt = Event()
    async def child(exctype):
        if exctype:
            raise exctype('Died')
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, RuntimeError)
                t2 = await g.spawn(child, MemoryError)
                t3 = await g.spawn(child, None)
                await sleep(0)
                evt.set()
        except (RuntimeError, MemoryError) as e:
            assert isinstance(t1.exception(), RuntimeError)
            assert isinstance(t2.exception(), MemoryError)
        else:
            assert False

    await main()


@pytest.mark.asyncio
async def test_task_group_cancel():
    evt = Event()
    evt2 = Event()
    async def child():
        try:
            await evt.wait()
        except CancelledError:
            assert True
            raise
        else:
            raise False

    async def coro():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child)
                t2 = await g.spawn(child)
                t3 = await g.spawn(child)
                evt2.set()
        except CancelledError:
            assert t1.cancelled()
            assert t2.cancelled()
            assert t3.cancelled()
            raise
        else:
            assert False

    async def main():
        t = await spawn(coro)
        await evt2.wait()
        t.cancel()
        try:
            await t
        except CancelledError:
            pass

    await main()


@pytest.mark.asyncio
async def test_task_group_timeout():
    evt = Event()
    async def child():
        try:
            await evt.wait()
        except CancelledError:
            assert True
            raise
        else:
            raise False

    async def coro():
        try:
            async with timeout_after(0.01):
                try:
                    async with TaskGroup() as g:
                        t1 = await g.spawn(child)
                        t2 = await g.spawn(child)
                        t3 = await g.spawn(child)
                except CancelledError:
                    assert t1.cancelled()
                    assert t2.cancelled()
                    assert t3.cancelled()
                    raise
        except TaskTimeout:
            assert True
        else:
            assert False

    await coro()


@pytest.mark.asyncio
async def test_task_group_cancel_remaining():
    evt = Event()
    async def child(x, y):
        return x + y

    async def waiter():
        await evt.wait()

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(waiter)
            t3 = await g.spawn(waiter)
            t = await g.next_done()
            assert t == t1
            await g.cancel_remaining()

        assert t2.cancelled()
        assert t3.cancelled()

    await main()


@pytest.mark.asyncio
async def test_task_group_cancel_remaining_waits():
    async def sleep_soundly():
        try:
            await sleep(0.01)
        except CancelledError:
            await sleep(0.01)

    task = await spawn(sleep_soundly)
    with pytest.raises(CancelledError):
        async with TaskGroup([task]) as g:
            await sleep(0)  # ensure the tasks are scheduled
            raise CancelledError
    assert task.done()


@pytest.mark.asyncio
async def test_task_group_use_error():
    async def main():
         async with TaskGroup() as g:
              t1 = await g.spawn(sleep, 0)
              with pytest.raises(RuntimeError):
                  await g.add_task(t1)

         with pytest.raises(RuntimeError):
             await g.spawn(sleep, 0)

         t2 = await spawn(sleep, 0)
         with pytest.raises(RuntimeError):
             await g.add_task(t2)
         await t2

    await main()

@pytest.mark.asyncio
async def test_task_group_object_cancel():
    try:
        async with TaskGroup(wait=object) as g:
            task1 = await g.spawn(sleep, 1)
            task2 = await g.spawn(sleep, 2)
            await sleep(0.001)
            task1.cancel()
    except CancelledError:
        assert False
    else:
        assert task1.cancelled()
        assert task2.cancelled()
        assert g.completed is None


def test_TaskTimeout_str():
    t = TaskTimeout(0.5)
    assert str(t) == 'task timed out after 0.5s'
