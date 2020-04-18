import io
import logging
import unittest

from impbot.connections import twitch_webhook
from impbot.core import base
from impbot.observers import log


class TestConnection(base.ChatConnection):

    def say(self, text: str) -> None:
        raise NotImplemented

    def run(self, on_event: base.EventCallback) -> None:
        raise NotImplemented

    def shutdown(self) -> None:
        raise NotImplemented


class LoggingObserverTest(unittest.TestCase):
    def setUp(self):
        logger = logging.Logger("test_log")
        self.buffer = io.StringIO()
        logger.addHandler(logging.StreamHandler(self.buffer))
        self.observer = log.LoggingObserver(logger)

    def testMessage(self):
        message = base.Message(
            reply_connection=TestConnection(), user=base.User("Alicia"),
            text="hi there")
        self.observer.observe(message)
        self.assertEqual(self.buffer.getvalue(), "[Test] <Alicia> hi there\n")

    def testEvent(self):
        event = twitch_webhook.StreamStartedEvent(
            reply_connection=None, title="Hello world!", game="Just Chatting")
        self.observer.observe(event)
        self.assertEqual(
            self.buffer.getvalue(),
            "StreamStartedEvent(reply_connection=None, title='Hello world!', "
            "game='Just Chatting')\n")
