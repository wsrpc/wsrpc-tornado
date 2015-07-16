#!/usr/bin/env python
# encoding: utf-8
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


class Lazy(object):
    def __init__(self, func):
        self.func = func

    def __str__(self):
        return self.func()

