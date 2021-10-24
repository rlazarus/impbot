import unittest
from typing import Dict

from impbot.handlers import hello
from impbot.core import web


class WebTest(unittest.TestCase):
    def setUp(self):
        self.conn = web.WebServerConnection('127.0.0.1', 9999, '127.0.0.1:9999')

    def tearDown(self):
        self.conn.flask_server.server_close()

    def testRoutes(self):
        self.conn.init_routes([], [hello.HelloHandler()])
        actual_map: Dict[str, str] = {}
        for rule in self.conn.flask.url_map.iter_rules():
            actual_map[str(rule)] = rule.endpoint
        self.assertEqual(actual_map, {
            '/static/<path:filename>': 'static',
            '/hello': 'HelloHandler.web',
        })
