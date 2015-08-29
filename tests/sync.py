#!/usr/bin/env python
# encoding: utf-8
from time import sleep
from wsrpc import WebSocketRoute, WebSocketThreaded


class TestRoute(WebSocketRoute):
    def init(self):
        sleep(0.1)
        return True

    def simple_method(self, **kwargs):
        return kwargs

    def simple_async_method(self, *args, **kwargs):
        sleep(0.1)
        return args, kwargs


WebSocketThreaded.ROUTES['sync'] = TestRoute


def sync_func(socket, **kwargs):
    return kwargs


WebSocketThreaded.ROUTES['sync_func'] = sync_func
