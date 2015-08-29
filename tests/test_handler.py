#!/usr/bin/env python
# encoding: utf-8
import tornado.web
import socket
from io import BytesIO
from tornado.http1connection import HTTP1Connection
from tornado.iostream import IOStream
from tornado.httputil import HTTPServerRequest, HTTPHeaders, RequestStartLine
from tornado import testing
from tornado.httpserver import HTTPServer
from random import randint
from tornado.concurrent import Future
from tornado.testing import AsyncTestCase, gen_test
from wsrpc.websocket.handler import WebSocketBase
from wsrpc import WebSocket, WebSocketThreaded

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


class TestWebSocketBase(AsyncTestCase):
    def setUp(self):
        super(TestWebSocketBase, self).setUp()
        self.application = Application()
        self.server = HTTPServer(self.application)
        self.socket, self.port = testing.bind_unused_port()
        self.server.add_socket(self.socket)
        self.instance = WebSocketBase(self.application, HTTPServerRequest(
            method="GET",
            uri='/',
            version="HTTP/1.0",
            headers=HTTPHeaders(),
            body=BytesIO(),
            host=None,
            files=None,
            connection=HTTP1Connection(
                stream=IOStream(socket.socket()),
                is_client=False
            ),
            start_line=RequestStartLine(method='GET', path='/', version='HTTP/1.1'),
        ))
        self.instance.open()

    def test_configure(self):
        keepalive_timeout = randint(999, 9999)
        client_timeout = randint(999, 9999)
        WebSocketBase.configure(keepalive_timeout=keepalive_timeout, client_timeout=client_timeout)
        self.assertEqual(WebSocketBase._CLIENT_TIMEOUT, client_timeout)
        self.assertEqual(WebSocketBase._KEEPALIVE_PING_TIMEOUT, keepalive_timeout)

    def test_authorize(self):
        self.assertEqual(self.instance.authorize(), True)

    def test_execute(self):
        resp = self.instance._execute([])
        self.assertTrue(isinstance(resp, Future))

        resp = self.instance._execute(None)
        self.assertTrue(isinstance(resp, Future))

    def test_allowdraft76(self):
        self.assertEqual(self.instance.allow_draft76(), True)

    def send_message(self, msg):
        return self.instance.on_message(json.dumps(msg))

    @gen_test
    def test_on_message(self):
        try:
            yield self.send_message({})
        except Exception as e:
            self.assertEqual(type(e), AssertionError)

        result = yield self.send_message({'serial': 999, 'type': 'call'})
        result = yield self.send_message({'serial': 999, 'type': 'callback'})
        result = yield self.send_message({'serial': 999, 'type': 'error'})



