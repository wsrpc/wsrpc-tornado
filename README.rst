WSRPC
=====

Remote Procedure call through WebSocket between browser and tornado.

Add the backend side::

	from time import time
	from wsrpc import WebSocketRoute, WebSocket, wsrpc_static

	tornado.web.Application((
        wsrpc_static(r'/js/(.*)'),
        (r"/ws/", WebSocket),
        (r'/(.*)', tornado.web.StaticFileHandler, {
             'path': os.path.join(project_root, 'static'),
             'default_filename': 'index.html'
        }),
    ))

	class TestRoute(WebSocketRoute):
		def init(self, **kwargs):
			return kwargs

		def getEpoch(self):
			return time()

	# stateful request
	WebSocket.ROUTES['test1'] = TestRoute

	# stateless request
	WebSocket.ROUTES['test2'] = lambda *a, **kw: True

Add the frontend side::

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
