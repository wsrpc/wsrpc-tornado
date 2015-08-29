#!/usr/bin/env python
# encoding: utf-8
from tornado.gen import Return, Future, sleep, coroutine
import tornado.web
import exceptions
from tornado import testing, websocket
from tornado.httpserver import HTTPServer
from wsrpc import WebSocket, WebSocketThreaded

import async
import sync

try:
    import ujson as json
except ImportError:
    import json


class Application(tornado.web.Application):
    def __init__(self):
        handlers = (
            (r"/ws/async", WebSocket),
            (r"/ws/sync", WebSocketThreaded),
        )

        tornado.web.Application.__init__(self, handlers)


class TestBase(testing.AsyncTestCase):
    def setUp(self):
        super(TestBase, self).setUp()
        self._serial = 0
        self._futures = {}

        self.application = Application()
        self.server = HTTPServer(self.application)
        self.socket, self.port = testing.bind_unused_port()
        self.server.add_socket(self.socket)

        self.connection = None

        connection = websocket.websocket_connect('ws://localhost:{0.port}{0.URI}'.format(self))
        connection.add_done_callback(self._set_conn)

    def _set_conn(self, connection):
        self.connection = connection
        self.io_loop.add_callback(self._connection_loop)

    @coroutine
    def _connection_loop(self):
        if isinstance(self.connection, Future):
            self.connection = yield self.connection

        while self.connection.protocol is not None:
            message = json.loads((yield self.connection.read_message()))
            data = message.get('data')
            typ = message.get('type')

            f = self._futures.pop(message['serial'])

            if typ == 'callback':
                f.set_result(data)
            elif typ == 'error':
                f.set_exception(getattr(exceptions, data['type'], Exception)(data['message']))
            else:
                f.set_exception(TypeError('Unknown message type {0}'.format(typ)))

    @coroutine
    def tearDown(self):
        self.connection.close()

    def _get_serial(self):
        self._serial += 1
        return self._serial

    @coroutine
    def _call_coro(self, data):
        while self.connection is None:
            yield sleep(0.001)

        if isinstance(self.connection, Future):
            self.connection = yield self.connection

        self.io_loop.add_callback(
            self.connection.write_message,
            data
        )

    def call(self, func, **kwargs):
        assert isinstance(func, (basestring, unicode))

        serial = self._get_serial()

        self.io_loop.add_callback(
            self._call_coro,
            json.dumps({
                'call': func,
                'serial': serial,
                'arguments': kwargs
            })
        )

        f = Future()
        self._futures[serial] = f
        return f
