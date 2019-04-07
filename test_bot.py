import unittest
from typing import Callable
from unittest import mock

import bot
import command
from bot import Message


class FooHandler(command.CommandHandler):
    def run_foo(self):
        return "foo!"


class BarHandler(command.CommandHandler):
    def run_bar(self):
        pass


class AnotherFooHandler(command.CommandHandler):
    def run_foo(self):
        pass


class BotTest(unittest.TestCase):
    def init(self, handlers):
        conn: bot.Connection = mock.Mock(spec=bot.Connection)
        return bot.Bot("", None, [conn], handlers)

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

    def testQuit(self):
        class QuitConnection(bot.Connection):
            def say(self, text: str) -> None:
                pass

            def run(self, callback: Callable[[Message], None]) -> None:
                callback(None)

            def shutdown(self) -> None:
                pass
        handler = mock.Mock(spec=bot.Handler)
        b = bot.Bot("", None, [QuitConnection()], [handler])
        b.main()
        handler.check.assert_not_called()
