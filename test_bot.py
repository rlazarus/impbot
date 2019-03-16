import unittest
from unittest import mock

import bot
import command


class FooHandler(command.CommandHandler):
    def run_foo(self):
        return "foo!"


class BarHandler(command.CommandHandler):
    def run_bar(self): pass


class AnotherFooHandler(command.CommandHandler):
    def run_foo(self): pass


class BotTest(unittest.TestCase):
    def init(self, handlers):
        conn: bot.Connection = mock.Mock(spec=bot.Connection)
        return bot.Bot("", [conn], handlers)

    def testInit(self):
        self.init([AnotherFooHandler()])
        self.init([FooHandler(), BarHandler()])
        self.assertRaises(ValueError, self.init,
                          [FooHandler(), AnotherFooHandler()])

    def testHandle(self):
        b = self.init([FooHandler(), BarHandler()])
        reply = mock.Mock()
        b.handle(bot.Message("username", "!foo", reply))
        reply.assert_called_with("foo!")

        reply.reset_mock()
        b.handle(bot.Message("username", "not !foo", reply))
        reply.assert_not_called()
