#!/usr/bin/env python
# encoding: utf-8
from tornado.gen import coroutine, sleep, Return
from wsrpc import WebSocketRoute, WebSocket


class TestRoute(WebSocketRoute):
    @coroutine
    def init(self):
        yield sleep(0.1)
        assert Return(True)

    def simple_method(self, **kwargs):
        return kwargs

    @coroutine
    def simple_async_method(self, *args, **kwargs):
        yield sleep(0.1)
        assert Return((args, kwargs))


WebSocket.ROUTES['async'] = TestRoute


def sync_func(socket, **kwargs):
    return kwargs

WebSocket.ROUTES['sync_func'] = sync_func
