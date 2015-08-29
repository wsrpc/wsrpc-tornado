#!/usr/bin/env python
# encoding: utf-8
import os
from tornado.gen import coroutine
import tornado.web
import wsrpc
from tornado import testing
from tornado.httpserver import HTTPServer
from tornado.testing import gen_test, AsyncTestCase
from wsrpc import wsrpc_static
from tornado.httpclient import AsyncHTTPClient


class Application(tornado.web.Application):
    def __init__(self):
        handlers = (
            wsrpc_static('/static/(.*)'),
        )

        tornado.web.Application.__init__(self, handlers)


class WebTest(AsyncTestCase):
    def setUp(self):
        super(WebTest, self).setUp()
        self.application = Application()
        self.server = HTTPServer(self.application)
        self.socket, self.port = testing.bind_unused_port()
        self.server.add_socket(self.socket)
        self.static_path = os.path.join(os.path.dirname(wsrpc.__file__), 'static')

    @coroutine
    def fetch(self, filename):
        response = yield AsyncHTTPClient().fetch("http://localhost:{0.port}/static/{1}".format(self, filename))
        self.assertTrue(response.code, 200)
        self.assertEqual(response.body, open(os.path.join(self.static_path, filename)).read())

    @gen_test
    def test_wsrpc_js(self):
        yield self.fetch('wsrpc.js')

    @gen_test
    def test_q_js(self):
        yield self.fetch('q.js')

    @gen_test
    def test_q_min_js(self):
        yield self.fetch('q.min.js')

    @gen_test
    def test_wsrpc_min_js(self):
        yield self.fetch('wsrpc.min.js')
