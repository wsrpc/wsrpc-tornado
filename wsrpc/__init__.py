#!/usr/bin/env python
# encoding: utf-8
import os.path
import tornado.web
from .websocket import WebSocketRoute, WebSocket, WebSocketThreaded
from .websocket.route import decorators

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


def wsrpc_static(url):
    return (
        url,
        tornado.web.StaticFileHandler,
        {'path': STATIC_DIR}
    )
