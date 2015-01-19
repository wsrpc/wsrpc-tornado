# encoding: utf-8
from __future__ import absolute_import, print_function

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


__version__ = '0.1.0'
__author__ = 'Dmitry Orlov <me@mosquito.su>'


setup(
    name='wsrpc',
    version=__version__,
    author=__author__,
    author_email='me@mosquito.su',
    license="LGPLv3",
    description="WSRPC WebSocket RPC for tornado",
    platforms="all",
    url="http://github.com/mosquito/wsrpc",
    classifiers=[
        'Environment :: Console',
        'Programming Language :: Python',
    ],
    long_description=open('README.rst').read(),
    packages=['wsrpc', 'wsrpc.websocket',],
    install_requires = ['tornado'],
)
