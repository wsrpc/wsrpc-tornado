#!/usr/bin/env python
# encoding: utf-8
from tornado.testing import AsyncTestCase
from wsrpc.websocket.handler import ping


class PingTest(AsyncTestCase):
    def test_ping(self):
        result = ping(None)
        self.assertEqual(
            result,
            'pong'
        )
