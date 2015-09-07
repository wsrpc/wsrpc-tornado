(function (global) {
	function WSRPCConstructor (URL, reconnectTimeout) {
		var self = this;
		self.serial = 1;
		self.eventId = 0;
		self.socketStarted = false;
		self.eventStore = {
			onconnect: {},
			onerror: {},
			onclose: {},
			onchange: {}
		};
		self.connectionNumber = 0;
		self.oneTimeEventStore = {
			onconnect: [],
			onerror: [],
			onclose: [],
			onchange: []
		};

		self.callQueue = [];
		
		var log = function (msg) {
			if (global.WSRPC.DEBUG) {
				if ('group' in console && 'groupEnd' in console) {
					console.group('WSRPC.DEBUG');
					console.debug(msg);
					console.groupEnd();
				} else {
					console.debug(msg);
				}
			}
		};

		var trace = function (msg) {
			if (global.WSRPC.TRACE) {
				if ('group' in console && 'groupEnd' in console && 'dir' in console) {
					console.group('WSRPC.TRACE');
					if ('data' in msg) {
						console.dir(JSON.parse(msg.data));
					} else {
						console.dir(msg)
					}
					console.groupEnd();
				} else {
					if ('data' in msg) {
						console.log('OBJECT DUMP: ' + msg.data);
					} else {
						console.log('OBJECT DUMP: ' + msg);
					}
				}
			}
		};

		var readyState = {
			0: 'CONNECTING',
			1: 'OPEN',
			2: 'CLOSING',
			3: 'CLOSED'
		};

		function reconnect(callEvents) {
			setTimeout(function () {
				try {
					self.socket = createSocket();
					self.serial = 1;
				} catch (exc) {
					callEvents('onerror', exc);
					delete self.socket;
					log(exc);
				}
			}, reconnectTimeout || 1000);
		}

		function createSocket (ev) {
			var ws = new WebSocket(URL);

			var rejectQueue = function () {
				self.connectionNumber++; // rejects incoming calls

				//reject all pending calls
				while (0 < self.callQueue.length) {
					var callObj = self.callQueue.shift();
					var deferred = self.store[callObj.serial];
					delete self.store[callObj.serial];

					if (deferred && deferred.promise.isPending()) {
						deferred.reject('WebSocket error occurred');
					}
				}

				// reject all from the store
				for (var key in self.store) {
					var deferred = self.store[key];

					if (deferred && deferred.promise.isPending()) {
						deferred.reject('WebSocket error occurred');
					}
				}
			};

			ws.onclose = function (err) {
				log('WSRPC: ONCLOSE CALLED (STATE: ' + self.public.state() + ')');
				trace(err);
				
				for (var serial in self.store) {
					if (self.store[serial].hasOwnProperty('reject') && self.store[serial].promise.isPending()) {
						self.store[serial].reject('Connection closed');
					}
				}

				rejectQueue();
				callEvents('onclose', ev);
				callEvents('onchange', ev);
				reconnect(callEvents);
			};

			ws.onerror = function (err) {
				log('WSRPC: ONERROR CALLED (STATE: ' + self.public.state() + ')');
				trace(err);
				
				rejectQueue();
				callEvents('onerror', err);
				callEvents('onchange', err);

				log(['WebSocket has been closed by error: ', err]);
			};

			function tryCallEvent(func, event) {
				try {
					return func(event);
				} catch (e) {
					if (e.hasOwnProperty('stack')) {
						log(e.stack);
					} else {
						log('Event function ' + func + ' raised unknown error: ' + e);
					}
				}
			}

			function callEvents(evName, event) {
				while (0 < self.oneTimeEventStore[evName].length) {
					var def = self.oneTimeEventStore[evName].shift();
					// TODO: проверить deferred ли это и state === pending
					if (def.hasOwnProperty('resolve') && def.promise.isPending()) {
						def.resolve();
					}
				}

				for (var i in self.eventStore[evName]) {
					var cur = self.eventStore[evName][i];
					tryCallEvent(cur, event);
				}
			}

			ws.onopen = function (ev) {
				log('WSRPC: ONOPEN CALLED (STATE: ' + self.public.state() + ')');
				trace(ev);

				while (0 < self.callQueue.length) {
					self.socket.send(JSON.stringify(self.callQueue.shift(), 0, 1));
				}

				callEvents('onconnect', ev);
				callEvents('onchange', ev);
			};

			ws.onmessage = function (message) {
				log('WSRPC: ONMESSAGE CALLED (' + self.public.state() + ')');
				trace(message);
				var data = null;
				if (message.type == 'message') {
					try {
						data = JSON.parse(message.data);
						log(data.data);
						if (data.hasOwnProperty('type') && data.type === 'call') {
							if (!self.routes.hasOwnProperty(data.call)) {
								throw Error('Route not found');
							}

							var connectionNumber = self.connectionNumber;
							Q(self.routes[data.call](data.arguments)).then(function(promisedResult) {
								if (connectionNumber == self.connectionNumber) {
									self.socket.send(JSON.stringify({
										serial: data.serial,
										type: 'callback',
										data: promisedResult
									}));
								}
							}).done();
						} else if (data.hasOwnProperty('type') && data.type === 'error') {
							if (!self.store.hasOwnProperty(data.serial)) {
								return log('Unknown callback');
							}
							var deferred = self.store[data.serial];
							if (typeof deferred === 'undefined') {
								return log('Confirmation without handler');
							}
							delete self.store[data.serial];
							log('REJECTING: ' + data.data);
							deferred.reject(data.data);
						} else {
							var deferred = self.store[data.serial];
							if (typeof deferred === 'undefined') {
								return log('Confirmation without handler');
							}
							delete self.store[data.serial];
							if (data.type === 'callback') {
								return deferred.resolve(data.data);
							} else {
								return deferred.reject(data.data);
							}
						}
					} catch (exception) {
						var err = {
							data: exception.message,
							type: 'error',
							serial: data?data.serial:null
						};

						self.socket.send(JSON.stringify(err));
						log(exception.stack);
					}
				}
			};

			return ws;
		}

		var makeCall = function (func, args, params) {
			self.serial += 2;
			var deferred = Q.defer();
			
			var callObj = {
				serial: self.serial,
				call: func,
				// type: 'callback', // By default.
				arguments: args
			};

			var state = self.public.state();

			if (state === 'OPEN') {
				self.store[self.serial] = deferred;
				self.socket.send(JSON.stringify(callObj));
			} else if (state === 'CONNECTING') {
				log('SOCKET IS: ' + state);
				self.store[self.serial] = deferred;
				self.callQueue.push(callObj);
			} else {
				log('SOCKET IS: ' + state);
				if (params && params.noWait) {
					deferred.reject('Socket is: ' + state);
				} else {
					self.store[self.serial] = deferred;
					self.callQueue.push(callObj);
				}
			}

			return deferred.promise;
		};

		self.routes = {};
		self.store = {};
		self.public = {
			call: function (func, args, params) {
				return makeCall(func, args, params);
			},
			init: function () {
				log('Websocket initializing..')
			},
			addRoute: function (route, callback) {
				self.routes[route] = callback;
			},
			addEventListener: function (event, func) {
				return self.eventStore[event][self.eventId++] = func;
			},
			onEvent: function (event) {
				var deferred = Q.defer();
				self.oneTimeEventStore[event].push(deferred);
				return deferred.promise;
			},
			removeEventListener: function (event, index) {
				if (index < self.eventStore[event].length) {
					self.eventStore[event].splice(index, 1);
					return true;
				} else {
					return false;
				}
			},
			deleteRoute: function (route) {
				return delete self.routes[route];
			},
			destroy: function () {
				function placebo () {}
				self.socket.onclose = placebo;
				self.socket.onerror = placebo;
				return self.socket.close();
			},
			state: function () {
				if (self.socketStarted && self.socket) {
					return readyState[self.socket.readyState];
				} else {
					return readyState[3];
				}
			},
			connect: function () {
				self.socketStarted = true;
				self.socket = createSocket();
			}
		};

		self.public.addRoute('log', function (argsObj) {
			console.info('Websocket sent: ' + argsObj);
		});

		self.public.addRoute('ping', function (data) {
			return data;
		});

		return self.public;
	}

	global.WSRPC = WSRPCConstructor;
	global.WSRPC.DEBUG = false;
	global.WSRPC.TRACE = false;
})(this);
