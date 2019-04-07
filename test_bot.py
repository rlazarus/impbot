import unittest
from typing import Callable, Optional
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


class OneMessageConnection(bot.Connection):
    def __init__(self, text: Optional[str]) -> None:
        if text is not None:
            self.message = bot.Message("username", text, self.say)
        else:
            self.message = None

    def say(self, text: str) -> None:
        pass

    def run(self, callback: Callable[[bot.Message], None]) -> None:
        callback(self.message)

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
        b = bot.Bot(None, [OneMessageConnection(None)], [handler])
        b.main()
        handler.check.assert_not_called()


    def testMultipleConnections(self):
        handler = mock.Mock(spec=bot.Handler)
        messages = ["one", "two", None]
        b = bot.Bot(None, [OneMessageConnection(m) for m in messages], [handler])
        b.main()
        texts = [message.text for ((message,), _) in
                 handler.check.call_args_list]
        self.assertEqual(texts, messages[:-1])
