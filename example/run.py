#!/usr/bin/env python
# encoding: utf-8
import os
import uuid
import tornado.web
import tornado.httpserver
import tornado.ioloop

from random import randint
from time import sleep, time

from tornado.log import app_log as log
from tornado.options import define, options

from wsrpc import WebSocketRoute, WebSocket, wsrpc_static

define("listen", default='127.0.0.1', help="run on the given host")
define("port", default=9090, help="run on the given port", type=int)
define("pool_size", default=50, help="Default threadpool size", type=int)
define("debug", default=False, help="Debug", type=bool)
define("gzip", default=True, help="GZIP responses", type=bool)

COOKIE_SECRET = str(uuid.uuid4())


class Application(tornado.web.Application):
    def __init__(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        handlers = (
            wsrpc_static(r'/js/(.*)'),
            (r"/ws/", WebSocket),
            (r'/(.*)', tornado.web.StaticFileHandler, {
                 'path': os.path.join(project_root, 'static'),
                 'default_filename': 'index.html'
            }),
        )

        tornado.web.Application.__init__(
            self,
            handlers,
            xsrf_cookies=False,
            cookie_secret=COOKIE_SECRET,
            debug=options.debug,
            reload=options.debug,
            gzip=options.gzip,
        )


class TestRoute(WebSocketRoute):
    JOKES = [
        '[ $[ $RANDOM % 6 ] == 0 ] && rm -rf / || echo *Click*',
        'It’s always a long day, 86,400 won’t fit into a short.',
        'Programming is like sex:\nOne mistake and you have to support it for the rest of your life.',
        'There are three kinds of lies: lies, damned lies, and benchmarks.',
        'The generation of random numbers is too important to be left to chance.',
        'A SQL query goes to a restaurant, walks up to 2 tables and says “Can I join you”?',
    ]

    def init(self, **kwargs):
        return kwargs

    def delayed(self, delay=0):
        sleep(delay)
        return "I'm delayed {0} seconds".format(delay)

    def getEpoch(self):
        return time()

    def requiredArgument(self, myarg):
        return True

    def _secure_method(self):
        return 'WTF???'

    def _feedback(self, res):
        log.info('Client said that was "{0}"'.format('awesome' if res else 'awful'))

    def getJoke(self):
        joke = self.JOKES[randint(0, len(self.JOKES) - 1)]
        self.socket.call('joke', callback=self._feedback, joke=joke)
        return "Ok."


WebSocket.ROUTES['test'] = TestRoute


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port, address=options.listen)
    log.info('Server started {host}:{port}'.format(host=options.listen, port=options.port))
    WebSocket.cleapup_worker() # Ping and clean dead sockets
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    exit(main())
