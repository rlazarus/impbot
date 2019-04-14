import sqlite3
import unittest
from typing import Callable
from unittest import mock

import bot
import data


class HandlerTest(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.reply: Callable[[str], None] = mock.Mock()
        self.handler: bot.Handler = None

    def _message(self, input):
        return bot.Message("username", input, self.reply)

    def assert_no_trigger(self, input: str) -> None:
        self.assertFalse(self.handler.check(self._message(input)))

    def assert_response(self, input: str, output: str) -> None:
        message = self._message(input)
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), output)

    def assert_error(self, input: str, output: str):
        message = self._message(input)
        self.assertTrue(self.handler.check(message))
        with self.assertRaises(bot.UserError) as ar:
            self.handler.run(message)
        self.assertEqual(str(ar.exception), output)


class DataHandlerTest(HandlerTest):
    def setUp(self):
        super().setUp()
        # We use this URI filename instead of just ":memory:" so that the
        # in-memory database is shared between connections -- that way, when
        # data.startup() creates the impbot table, the Handlers' connections
        # will see it.
        db = "file:testdb?mode=memory&cache=shared"
        # The shared database is deleted when the last connection is closed, so
        # we hold one open here (before data.startup, when the table is created)
        # for the duration of the test.
        self.conn = sqlite3.connect(db, uri=True)
        data.startup(db)

    def tearDown(self):
        super().tearDown()
        data.shutdown()
        self.conn.close()