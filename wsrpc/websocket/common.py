# encoding: utf-8

import logging
import traceback
from tornado.log import app_log as log

def log_thread_exceptions(func):
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if log.getEffectiveLevel() == logging.DEBUG:
                log.debug('Exception: {exc}\n\tfunc: {func}\n\t*args: {args}\n\t**kwargs: {kw}\n{tr}'.format(
                    exc=repr(e), args=repr(args), kw=repr(kwargs), func=repr(func), tr=traceback.format_exc()
                ))
            raise
    return wrap
