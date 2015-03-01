# encoding: utf-8
from multiprocessing.pool import ThreadPool
from multiprocessing import cpu_count
import zlib
import json
import logging
import traceback
import uuid
import tornado.websocket
import tornado.ioloop
import tornado.escape
import tornado.gen
import types
from functools import partial
from time import sleep
from tornado.log import app_log as log
from .route import WebSocketRoute
from .common import log_thread_exceptions


class Lazy(object):
    def __init__(self,func):
        self.func = func

    def __str__(self):
        return self.func()


def ping(obj, *args, **kwargs):
    return 'pong'


class WebSocket(tornado.websocket.WebSocketHandler):
    # Overlap this class property after import
    ROUTES = {
        'ping': ping
    }

    _CLIENTS = {}
    _KEEPALIVE_PING_TIMEOUT = 30
    _CLIENT_TIMEOUT = 10

    THREAD_POOL = ThreadPool(10 if cpu_count() < 10 else cpu_count() * 2)

    def _execute(self, transforms, *args, **kwargs):
        if self.authorize():
            return super(WebSocket, self)._execute(transforms, *args, **kwargs)
        else:
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 403 Forbidden\r\n\r\n"
                "Access deny to \"WebSocket\"."
            ))
            self.stream.close()
            return

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
        super(WebSocket, self).__init__(*args, **kwargs)
        self.__handlers = {}
        self.store = {}
        self.serial = 0
        self.locks = set([])
        self.extensions = self.request.headers.get('Sec-Websocket-Extensions', '')
        self._deflate = True if 'deflate' in self.extensions else False

    @classmethod
    def broadcast(cls, func, callback=WebSocketRoute.placebo, **kwargs):
        for client_id, client in cls._CLIENTS.iteritems():
            client.call(func, callback, **kwargs)

    @classmethod
    def _run_background(cls, func, callback, args=(), kwargs={}):
        cls.THREAD_POOL.apply_async(
            func, args, kwargs,
            lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(callback, future))
        )
        log.debug('Queued in thread pool "%r"', cls.THREAD_POOL)

    def _get_id(self):
        self.id = str(uuid.uuid4())

    def _log_client_list(self):
        log.debug(Lazy(lambda: 'CLIENTS: {0}'.format(''.join(['\n\t%r' % i for i in self._CLIENTS.values()]))))

    @classmethod
    def on_pong(self, data):
        log.info('Unexpected pong from "%r"', self)

    @classmethod
    def _cleanup(cls):
        def timeout_waiter(socket, timeout):
            flags = []

            def _ping_waiter(data):
                flags.append(True)
                log.debug('Socket "%r" ping OK', socket)

            def _timeout():
                if not flags:
                    try:
                        log.warning('Socket "%r" must be closed', socket)
                        socket.close()
                    except Exception as e:
                        log.debug(Lazy(lambda: traceback.format_exc()))
                        log.error("%r", e)
                if hasattr(socket, 'on_pong'):
                    delattr(socket, 'on_pong')

            tornado.ioloop.IOLoop.instance().call_later(timeout, _timeout)
            return _ping_waiter

        def do_ping(socket):
            if isinstance(socket.ws_connection, tornado.websocket.WebSocketProtocol13):
                socket.ping("\0" * 8)
                socket.on_pong = timeout_waiter(socket, cls._CLIENT_TIMEOUT)
            else:
                socket.call('ping', data="ping", callback=timeout_waiter(socket, cls._CLIENT_TIMEOUT))
                sleep(cls._CLIENT_TIMEOUT)

        for sid, socket in cls._CLIENTS.iteritems():
            try:
                do_ping(socket)
            except tornado.websocket.WebSocketClosedError:
                socket.close()
                log.warning('Auto close dead socket: %r', socket)
            except Exception as e:
                log.debug(Lazy(lambda: traceback.format_exc()))
                log.error('%r', e)

        log.debug('Cleanup loop is OK.')

    def _to_json(self, **kwargs):
        return json.dumps(kwargs, default=repr, sort_keys=False, indent=None, ensure_ascii=False, encoding='utf-8')

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
        tornado.ioloop.IOLoop.instance().call_later(0, lambda: log.info('Client connected: {0}'.format(self)))
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
        try:
            if self._CLIENTS.has_key(self.id):
                self._CLIENTS.pop(self.id)
            for name, obj in self.__handlers.iteritems():
                try:
                    obj._onclose()
                except:
                    if log.level == logging.DEBUG:
                        print traceback.format_exc()

            log.info('Client "{0}" disconnected'.format(self.id))
        except Exception as e:
            log.debug(Lazy(lambda : traceback.format_exc()))
            log.error(Lazy(lambda : repr(e)))

    def on_message(self, message):
        log.debug(Lazy(lambda: u'Client {0} send message: "{1}"'.format(self.id, message)))

        # deserialize message
        data = self._data_load(message)
        try:
            # get fields
            type = data.get('type', 'call')
            if type == 'call':
                self._local_call(data)
            elif type == 'callback':
                self._call_callback(data.get('data', None), data.get('serial', None))
            elif type == 'error':
                log.error('Client return error: \n\t{0}'.format(data.get('data', None)))
        except Exception as e:
            log.error(traceback.format_exc)
            return self._send(data=str(e), serial=data.get('serial', -1), type='error')

    def _call_callback(self, data, serial):
        if serial in self.locks:
            log.error('Duplicate serial call, callback droped.')
            return
        self.locks.add(serial)
        args = []
        kwargs = {}
        if isinstance(data, list):
            args.extend(data)
        if isinstance(data, dict):
            kwargs.update(data)
        else:
            args.append(data)

        cb = self.store.get(serial)
        if hasattr(cb, '__call__'):
            cb(*args, **kwargs)
        else:
            raise ValueError('Callback not callable')

        self.locks.remove(serial)

    def _local_call(self, data):
        serial = data.get('serial', -1)
        if serial >= 0:
            if serial in self.locks:
                log.error('Duplicate serial call, call droped.')
                return
            self.locks.add(serial)

        arguments = data.get('arguments', None)
        callback = data.get('call', None)
        if callback is None:
            # require argument not exist
            raise ValueError('Require argument "call" does\'t exist.')

        callee = self.resolver(callback)

        args = [] if hasattr(callee, '__self__') and isinstance(callee.__self__, WebSocketRoute) else [self, ]
        kwargs = {}

        # check type of arguments
        if isinstance(arguments, list):
            args.extend(arguments)
        elif isinstance(arguments, dict):
            kwargs = arguments
        elif isinstance(arguments, type(None)):
            pass
        else:
            raise ValueError('Arguments must be object or array.')

        self.async_response(callee, serial, args, kwargs)

    def async_response(self, func, serial, args, kwargs):
        def responder(data):
            if isinstance(data, Exception):
                log.error(repr(data))
                self.locks.remove(serial)
                return self._send(data=repr(data), serial=serial, type='error')
            elif isinstance(data, tornado.gen.Future):
                if data.running():
                    data.add_done_callback(response)
                else:
                    return responder(data.result())
            else:
                self.locks.remove(serial)
                return self._send(data=data, serial=serial, type='callback')

        self._run_background(
            log_thread_exceptions(func),
            responder,
            args=args,
            kwargs=kwargs
        )

    def _send(self, **kwargs):
        try:
            data = self._to_json(**kwargs)
            log.debug(Lazy(lambda: "Sending message to {0}: {1}".format(self.id, json.dumps(data))))
            log.info(Lazy(lambda: "Sending message {2} to {0} length {1}".format(self.id, len(data), kwargs.get('serial'))))
            self.write_message(data, binary=False)
        except tornado.websocket.WebSocketClosedError:
            self.close()


    def call(self, func, callback=WebSocketRoute.placebo, **kwargs):
        self.serial += 2
        self.store[self.serial] = callback
        self._send(serial=self.serial, type='call', call=func, arguments=kwargs)

    def __repr__(self):
        if hasattr(self, 'id'):
            return "<RPCWebSocket: ID[{0}]>".format(self.id)
        else:
            return "<RPCWebsocket: {0} (waiting)>".format(self.__hash__())

    def close(self):
        super(WebSocket, self).close()
        # Very strange. I think this is mistake of tornado developers. Correct me when I wasn't right.
        # TODO: TRY MAKE IT RIGHT!!! This is awful!!!
        try:
            self.on_close()
        except:
            pass

    @classmethod
    def cleapup_worker(cls):
        def run():
            cls.THREAD_POOL.apply_async(cls._cleanup)
            tornado.ioloop.IOLoop.instance().call_later(cls._KEEPALIVE_PING_TIMEOUT, run)
        tornado.ioloop.IOLoop.instance().call_later(0, run)
