import unittest
from typing import Callable, Union
from unittest import mock

import bot
import command


class FooHandler(command.CommandHandler):
    def run_foo(self):
        return "foo!"


class BarHandler(command.CommandHandler):
    def run_bar(self):
        pass


class AnotherFooHandler(command.CommandHandler):
    def run_foo(self):
        pass


class OneEventConnection(bot.Connection):
    def __init__(self, event: Union[str, bot.Event]) -> None:
        if isinstance(event, str):
            event = bot.Message("username", event, self.say)
        self.event = event

    def say(self, text: str) -> None:
        pass

    def run(self, callback: Callable[[bot.Event], None]) -> None:
        callback(self.event)

    def shutdown(self) -> None:
        pass


class BotTest(unittest.TestCase):
    def init(self, handlers):
        conn: bot.Connection = mock.Mock(spec=bot.Connection)
        return bot.Bot(None, [conn], handlers)

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
        handler = mock.Mock(spec=bot.Handler)
        b = bot.Bot(None, [OneEventConnection(bot.Shutdown())], [handler])
        b.main()
        handler.check.assert_not_called()

    def testMultipleConnections(self):
        handler = mock.Mock(spec=bot.Handler)
        events = ["one", "two", bot.Shutdown()]
        b = bot.Bot(None, [OneEventConnection(e) for e in events], [handler])
        b.main()
        texts = [message.text for ((message,), _) in
                 handler.check.call_args_list]
        self.assertEqual(texts, events[:-1])
