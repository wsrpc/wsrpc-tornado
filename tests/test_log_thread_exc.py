#!/usr/bin/env python
# encoding: utf-8
from tornado.testing import AsyncTestCase
from wsrpc.websocket.common import log_thread_exceptions


class TestExc(Exception):
    pass


def exc_func():
    raise TestExc("Test")


def test():
    return True


class TestLogThreadException(AsyncTestCase):
    def test_exc(self):
        try:
            log_thread_exceptions(exc_func)()
        except TestExc:
            pass

    def test_func(self):
        log_thread_exceptions(test)()
