# -*- coding: utf-8 -*-
from collections import defaultdict
import json
from bson import ObjectId
from handlers.admin.common import Contstants
from handlers.admin.lib import renders
from handlers.common.websocket import WebSocketRoute
from tornado.log import app_log as log


class AuthWebSocketRoute(WebSocketRoute):
    @property
    def db(self):
        return self.socket.settings.get('db')

    @property
    def session(self):
        return self.socket.settings.get('session')

    @property
    def pubsub(self):
        return self.socket.settings.get('pubsub')


class Manager(AuthWebSocketRoute):
    MANAGERS = defaultdict(list)

    def init(self):
        token = self.socket.get_cookie(Contstants.COOKIE_NAME)
        if token:
            session = self.session.get(token)
            if session:
                session = json.loads(session)
                _id = session.get('_id')
                if _id:
                    user = self.db.managers.find_one({"_id": ObjectId(_id)})
                    if user:
                        self.socket.user = renders.manager(user)
                        self.MANAGERS[_id].append(self.socket)
                        #assignee_request(self.db, self.pubsub, manager_oid=ObjectId(self.socket.oid))
                        return "authenticated"

        return None

    def _onclose(self):
        self.MANAGERS[self.socket.oid].remove(self.socket)
        if not self.MANAGERS[self.socket.oid]:
            self.MANAGERS.pop(self.socket.oid)
