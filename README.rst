WSRPC Tornado
=============

.. image:: https://travis-ci.org/mosquito/wsrpc.svg
    :target: https://travis-ci.org/mosquito/wsrpc

Remote Procedure call through WebSocket between browser and tornado.

Features
--------

* Initiating call client function from server side.
* Calling the server method from the client.
* Transferring any exceptions from a client side to the server side and vise versa.
* The frontend-library are well done for usage without any modification.
* Fully asynchronous server-side functions.
* Thread-based websocket handler for writing fully-synchronous code (for synchronous database drivers etc.)
* Protected server-side methods (starts with underline never will be call from clients-side directly)
* Asynchronous connection protocol. Server or client can call multiple methods with unpredictable ordering of answers.


Installation
------------

Install via pip::

    pip install wsrpc-tornado


Install ujson if you want::

    pip install ujson



Simple usage
------------

Add the backend side


.. code-block:: python

    from time import time
    ## If you want write async tornado code import it
    # from from wsrpc import WebSocketRoute, WebSocket, wsrpc_static
    ## else you should use thread-base handler
    from wsrpc import WebSocketRoute, WebSocketThreaded as WebSocket, wsrpc_static

    tornado.web.Application((
        # js static files will available as "/js/wsrpc.min.js".
        wsrpc_static(r'/js/(.*)'),
        # WebSocket handler. Client will connect here.
        (r"/ws/", WebSocket),
        # Serve other static files
        (r'/(.*)', tornado.web.StaticFileHandler, {
             'path': os.path.join(project_root, 'static'),
             'default_filename': 'index.html'
        }),
    ))

    # This class should be call by client.
    # Connection object will be have the instance of this class when will call route-alias.
    class TestRoute(WebSocketRoute):
        # This method will be executed when client will call route-alias first time.
        def init(self, **kwargs):
            # the python __init__ must be return "self". This method might return anything.
            return kwargs

        def getEpoch(self):
            # this method named by camelCase because the client can call it.
            return time()

    # stateful request
    # this is the route alias TestRoute as "test1"
    WebSocket.ROUTES['test1'] = TestRoute

    # stateless request
    WebSocket.ROUTES['test2'] = lambda *a, **kw: True

    # initialize ThreadPool. Needed when using WebSocketThreaded.
    WebSocket.init_pool()



Add the frontend side


.. code-block:: HTML

    <script type="text/javascript" src="/js/q.min.js"></script>
    <script type="text/javascript" src="/js/wsrpc.min.js"></script>
    <script>
        var url = window.location.protocol==="https:"?"wss://":"ws://" + window.location.host + '/ws/';
        RPC = WSRPC(url, 5000);
        RPC.addRoute('test', function (data) { return "Test called"; });
        RPC.connect();

        RPC.call('test1.getEpoch').then(function (data) {
            console.log(data);
        }, function (error) {
            alert(error);
        }).done();

        RPC.call('test2').then(function (data) { console.log(data); }).done();
    </script>



Example
+++++++

Example running there demo_.


.. _demo: http://wsrpc.mosquito.su/
