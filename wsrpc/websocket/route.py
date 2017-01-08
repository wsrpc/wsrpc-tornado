# encoding: utf-8
import logging


log = logging.getLogger("wsrpc")


class decorators(object):
    _NOPROXY = set([])

    @staticmethod
    def noproxy(func):
        decorators._NOPROXY.add(func)
        return func


class WebSocketRoute(object):
    _NOPROXY = []

    @classmethod
    def noproxy(cls, func):
        def wrap(*args, **kwargs):
            if not func in cls._NOPROXY:
                cls._NOPROXY.append(func)
                wrap(*args, **kwargs)

            return func(*args, **kwargs)
        return wrap

    def __init__(self, obj):
        self.socket = obj

    def _resolve(self, method):
        if method.startswith('_'):
            raise AttributeError('Trying to get private method.')

        if hasattr(self, method):
            func = getattr(self, method)
            if func in decorators._NOPROXY:
                raise NotImplementedError('Method not implemented')
            else:
                return func
        else:
            raise NotImplementedError('Method not implemented')

    def _onclose(self):
        pass

    @classmethod
    def placebo(*args, **kwargs):
        log.debug("PLACEBO IS CALLED!!! args: {0}, kwargs: {1}".format(repr(args), repr(kwargs)))
