import asyncio

import pytest
import websockets

from aiorpcx import *

from test_session import MyServerSession

# This runs all the tests one with plain asyncio, then again with uvloop
@pytest.fixture(scope="session", autouse=True, params=(False, True))
def use_uvloop(request):
    if request.param:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


@pytest.fixture
def ws_server(unused_tcp_port, event_loop):
    coro = serve_ws(MyServerSession, 'localhost', unused_tcp_port, loop=event_loop)
    server = event_loop.run_until_complete(coro)
    yield f'ws://localhost:{unused_tcp_port}'
    if hasattr(asyncio, 'all_tasks'):
        tasks = asyncio.all_tasks(event_loop)
    else:
        tasks = asyncio.Task.all_tasks(loop=event_loop)
    async def close_all():
        server.close()
        await server.wait_closed()
        if tasks:
            await asyncio.wait(tasks)
    event_loop.run_until_complete(close_all())


@pytest.mark.filterwarnings("ignore:'with .*:DeprecationWarning")
class TestWSTransport:

    @pytest.mark.asyncio
    async def test_send_request(self, ws_server):
        async with connect_ws(ws_server) as session:
            assert await session.send_request('echo', [23]) == 23

    @pytest.mark.asyncio
    async def test_basics(self, ws_server):
        async with connect_ws(ws_server) as session:
            assert session.proxy() is None
            remote_address = session.remote_address()
            assert isinstance(remote_address, NetAddress)
            assert str(remote_address.host) in ('localhost', '::1', '127.0.0.1')
            assert ws_server.endswith(str(remote_address.port))

    @pytest.mark.asyncio
    async def test_is_closing(self, ws_server):
        async with connect_ws(ws_server) as session:
            assert not session.is_closing()
            await session.close()
            assert session.is_closing()

        async with connect_ws(ws_server) as session:
            assert not session.is_closing()
            await session.abort()
            assert session.is_closing()
