import unittest
from unittest import mock

import bot
import command


class FooHandler(command.CommandHandler):
    def run_foo(self): pass


class BarHandler(command.CommandHandler):
    def run_bar(self): pass


class AnotherFooHandler(command.CommandHandler):
    def run_foo(self): pass


class BotTest(unittest.TestCase):
    def testInit(self):
        def init(handlers):
            conn: bot.Connection = mock.Mock(spec=bot.Connection)
            return bot.Bot("", [conn], handlers)
        init([AnotherFooHandler()])
        init([FooHandler(), BarHandler()])
        self.assertRaises(ValueError, init, [FooHandler(), AnotherFooHandler()])