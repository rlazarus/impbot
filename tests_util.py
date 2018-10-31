import unittest
from typing import Callable
from unittest import mock

import bot


class HandlerTest(unittest.TestCase):

    def setUp(self):
        self.reply: Callable[[str], None] = mock.MagicMock(autospec=bot.Connection.say)
        self.handler: bot.Handler = None

    def assert_no_trigger(self, input: str) -> None:
        message = bot.Message("username", input, self.reply)
        self.assertFalse(self.handler.check(message))

    def assert_response(self, input: str, output: str) -> None:
        message = bot.Message("username", input, self.reply)
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), output)