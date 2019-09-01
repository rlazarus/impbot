import unittest
from unittest import mock

from impbot.core import base
from impbot.handlers import lambda_event


class LambdaHandlerTest(unittest.TestCase):

    def test(self):
        handler = lambda_event.LambdaHandler()
        run = mock.Mock()

        self.assertFalse(handler.typecheck(base.Event(None)))

        event = lambda_event.LambdaEvent(run=run)
        self.assertTrue(handler.typecheck(event))
        self.assertTrue(handler.check(event))
        handler.run(event)
        run.assert_called()