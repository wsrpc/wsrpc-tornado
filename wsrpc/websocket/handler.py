# encoding: utf-8
import zlib
import time
import traceback
import uuid
import struct
import tornado.websocket
import tornado.ioloop
import tornado.escape
import tornado.gen
import types
import tornado.concurrent
from multiprocessing import cpu_count
from functools import partial
from tornado.log import app_log as log
from .route import WebSocketRoute
from .common import log_thread_exceptions


try:
    dict.iteritems
except AttributeError:
    # Python 3
    def itervalues(d):
        return iter(d.values())
    def iteritems(d):
        return iter(d.items())
else:
    # Python 2
    def itervalues(d):
        return d.itervalues()
    def iteritems(d):
        return d.iteritems()

import ujson as json

class Lazy(object):
    def __init__(self,func):
        self.func = func

    def __str__(self):
        return self.func()


def ping(obj, *args, **kwargs):
    return 'pong'


class LockError(Exception):
    pass


class Lock(object):
    def __init__(self, locks_set, lock):
        self.__partial = partial(locks_set.remove, lock)
        if lock in locks_set:
            raise LockError("Object %r already locked" % lock)
        locks_set.add(lock)

    def __enter__(self):
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb:
            log.error(traceback.format_exc(exc_tb))
        self.__partial()


class SetLocker(object):
    def __init__(self, locks_set=None):
        if locks_set is None:
            self.__locks = set([])
        else:
            assert isinstance(locks_set, set)
            self.__locks = locks_set

    def __call__(self, lock):
        return Lock(self.__locks, lock)


class ClientException(Exception):
    pass

class ConnectionClosed(Exception):
    pass

class PingTimeoutError(Exception):
    pass


class WebSocketBase(tornado.websocket.WebSocketHandler):
    # Overlap this class property after import
    ROUTES = {
        'ping': ping
    }

    _CLIENTS = {}
    _KEEPALIVE_PING_TIMEOUT = 30
    _CLIENT_TIMEOUT = 10

    def _execute(self, transforms, *args, **kwargs):
        if self.authorize():
            return super(WebSocketBase, self)._execute(transforms, *args, **kwargs)
        else:
            if self._transforms is None:
                self._transforms = []

            f = tornado.gen.Future()
            def resolve():
                f.set_result(self.send_error(403))
            tornado.ioloop.IOLoop.instance().add_callback(resolve)
            return f

    def authorize(self):
        return True

    def allow_draft76(self):
        return True

    def deflate(self, data, compresslevel=9):
        compress = zlib.compressobj(
                compresslevel,        # level: 0-9
                zlib.DEFLATED,        # method: must be DEFLATED
                -zlib.MAX_WBITS,      # window size in bits:
                                      #   -15..-8: negate, suppress header
                                      #   8..15: normal
                                      #   16..30: subtract 16, gzip header
                zlib.DEF_MEM_LEVEL,   # mem level: 1..8/9
                0                     # strategy:
                                      #   0 = Z_DEFAULT_STRATEGY
                                      #   1 = Z_FILTERED
                                      #   2 = Z_HUFFMAN_ONLY
                                      #   3 = Z_RLE
                                      #   4 = Z_FIXED
        )
        deflated = compress.compress(data)
        deflated += compress.flush()
        return deflated

    def inflate(self, data):
        decompress = zlib.decompressobj(
                -zlib.MAX_WBITS  # see above
        )
        inflated = decompress.decompress(data)
        inflated += decompress.flush()
        return inflated

    def __init__(self, *args, **kwargs):
        super(WebSocketBase, self).__init__(*args, **kwargs)
        self.__handlers = {}
        self.store = {}
        self.serial = 0
        self.lock = SetLocker()
        self.extensions = self.request.headers.get('Sec-Websocket-Extensions', '')
        self._deflate = True if 'deflate' in self.extensions else False
        self._ping = {}

    @classmethod
    def broadcast(cls, func, callback=WebSocketRoute.placebo, **kwargs):
        for client_id, client in iteritems(cls._CLIENTS):
            client.call(func, callback, **kwargs)

    def _get_id(self):
        self.id = str(uuid.uuid4())

    def _log_client_list(self):
        log.debug(Lazy(lambda: 'CLIENTS: {0}'.format(''.join(['\n\t%r' % i for i in self._CLIENTS.values()]))))

    def on_pong(self, data):
        future = self._ping.pop(data)
        future.set_result({'seq': struct.unpack('>q', data)[0]})

    @tornado.gen.coroutine
    def _send_ping(self):
        if self.ws_connection:
            ioloop = tornado.ioloop.IOLoop.instance()
            if isinstance(self.ws_connection, tornado.websocket.WebSocketProtocol13):
                future = tornado.gen.Future()
                seq = struct.pack(">q", int(time.time() * 1000))
                self._ping[seq] = future
                self.ping(seq)
            else:
                future = self.call('ping', seq=time.time())

            ioloop.call_later(
                self._KEEPALIVE_PING_TIMEOUT,
                lambda: self.close() if future.running() else None
            )

            resp = yield future
            ts = resp.get('seq', 0)
            delta = (time.time() - (ts/1000.))
            log.debug("%r Pong recieved: %.4f" % (self, delta))
            if delta > self._CLIENT_TIMEOUT:
                self.close()

            ioloop.call_later(self._KEEPALIVE_PING_TIMEOUT, self._send_ping)

    def _to_json(self, **kwargs):
        return json.dumps(kwargs, ensure_ascii=False)

    def _data_load(self, data_string):
        try:
            return json.loads(data_string)
        except Exception as e:
            log.debug(Lazy(lambda: traceback.format_exc()))
            log.error(Lazy(lambda: 'Parsing message error: {0}'.format(repr(e))))
            raise e

    def _unresolvable(self, *args, **kwargs):
        raise NotImplementedError('Callback function not implemented')

    def open(self):
        ioloop = tornado.ioloop.IOLoop.instance()
        ioloop.call_later(self._KEEPALIVE_PING_TIMEOUT, self._send_ping)
        ioloop.add_callback(lambda: log.info('Client connected: {0}'.format(self)))
        self._get_id()
        self._CLIENTS[self.id] = self
        self._log_client_list()

    def resolver(self, func_name):
        class_name, method = func_name.split('.') if '.' in func_name else (func_name, 'init')
        callee = self.ROUTES.get(class_name, self._unresolvable)
        if callee == self._unresolvable or (hasattr(callee, '__self__') and isinstance(callee.__self__, WebSocketRoute)) or \
                (not isinstance(callee, types.FunctionType) and issubclass(callee, WebSocketRoute)):
            if self.__handlers.get(class_name, None) is None:
                self.__handlers[class_name] = callee(self)

            return self.__handlers[class_name]._resolve(method)

        callee = self.ROUTES.get(func_name, self._unresolvable)
        if hasattr(callee, '__call__'):
            return callee
        else:
            raise NotImplementedError('Method call of {0} is not implemented'.format(repr(callee)))

    def on_close(self):
            ioloop = tornado.ioloop.IOLoop.instance()
            if self._CLIENTS.has_key(self.id):
                self._CLIENTS.pop(self.id)
            for name, obj in iteritems(self.__handlers):
                ioloop.add_callback(obj._onclose)

            log.info('Client "{0}" disconnected'.format(self.id))

    @tornado.gen.coroutine
    def on_message(self, message):
        log.debug(Lazy(lambda: u'Client {0} send message: "{1}"'.format(self.id, message)))

        # deserialize message
        data = self._data_load(message)
        serial = data.get('serial', -1)
        type = data.get('type', 'call')

        assert serial >= 0

        try:
            if type == 'call':
                with self.lock(serial):
                    args, kwargs = self._prepare_args(data.get('arguments', None))

                    callback = data.get('call', None)
                    if callback is None:
                        raise ValueError('Require argument "call" does\'t exist.')

                    callee = self.resolver(callback)
                    calee_is_route = hasattr(callee, '__self__') and isinstance(callee.__self__, WebSocketRoute)
                    args = args if calee_is_route else [self, ].extend(args)

                    try:
                        result = yield self._executor(partial(callee, *args, **kwargs))
                        self._send(data=result, serial=serial, type='callback')
                    except Exception as e:
                        log.exception(e)
                        self._send(data=repr(e), serial=serial, type='error')

            elif type == 'callback':
                serial = data.get('serial', -1)
                assert serial >= 0

                with self.lock(serial):
                    cb = self.store.get(serial)
                    cb.set_result(data.get('data', None))

            elif type == 'error':
                self._reject(data.get('serial', -1), data.get('data', None))
                log.error('Client return error: \n\t{0}'.format(data.get('data', None)))
        except Exception as e:
            self._send(data=repr(e), serial=serial, type='error')

    def _reject(self, serial, error):
        future = self.store.get(serial)
        if future:
            future.set_exception(ClientException(error))

    def _prepare_args(self, args):
        arguments = []
        kwargs = {}

        if isinstance(args, types.NoneType):
            return arguments, kwargs

        if isinstance(args, list):
            arguments.extend(args)
        elif isinstance(args, dict):
            kwargs.update(args)
        else:
            arguments.append(args)

        return arguments, kwargs

    def _executor(self, func):
        raise NotImplementedError(":-(")

    def _send(self, **kwargs):
        try:
            data = self._to_json(**kwargs)
            log.debug(
                "Sending message to %s serial %s: %s",
                Lazy(lambda: str(self.id)),
                Lazy(lambda: str(kwargs.get('serial'))),
                Lazy(lambda: str(data))
              )
            self.write_message(data, binary=False)
        except tornado.websocket.WebSocketClosedError:
            self.close()

    def call(self, func, callback=None, **kwargs):
        future = tornado.gen.Future()
        if callback is not None and not isinstance(callback, tornado.gen.Future):
            future.add_done_callback(callback)

        self.serial += 2
        self.store[self.serial] = future
        self._send(serial=self.serial, type='call', call=func, arguments=kwargs)

        if callback is None:
            return future

    def __repr__(self):
        if hasattr(self, 'id'):
            return "<RPCWebSocket: ID[{0}]>".format(self.id)
        else:
            return "<RPCWebsocket: {0} (waiting)>".format(self.__hash__())

    def close(self):
        super(WebSocketBase, self).close()
        ioloop = tornado.ioloop.IOLoop.instance()

        for future in self.store.values():
            ioloop.add_callback(partial(future.set_exception, ConnectionClosed))

        ioloop.add_callback(lambda: self.on_close() if self.ws_connection else None)

    @classmethod
    def cleanup_worker(cls):
        log.warning("Method 'cleanup_worker' deprecated")


class WebSocket(WebSocketBase):
    @tornado.gen.coroutine
    def _executor(self, func):
        result = func()
        if isinstance(result, tornado.gen.Future):
            result = yield result

        raise tornado.gen.Return(result)


class WebSocketThreaded(WebSocketBase):
    _thread_pool = None

    @classmethod
    def init_pool(cls, workers=cpu_count()):
        def init():
            cls._thread_pool = tornado.concurrent.futures.ThreadPoolExecutor(workers)

        tornado.ioloop.IOLoop.current().add_callback(init)

    def _executor(self, func):
        if not self._thread_pool:
            self.init_pool()

        return self._thread_pool.submit(log_thread_exceptions(func))
