import unittest
from typing import Callable
from unittest import mock

import bot
import data


class DataTest(unittest.TestCase):
    def setUp(self):
        super().setUp()
        data.startup(":memory:")

    def tearDown(self):
        super().tearDown()
        data.shutdown()


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
