from unittest import mock

import roulette
from tests_util import HandlerTest


class RouletteHandlerTest(HandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = roulette.RouletteHandler()

    @mock.patch("random.randint", autospec=True, return_value=0)
    def testLose(self, randint: mock.MagicMock):
        self.assert_response("!roulette 20", "username lost 20 points!")
        randint.assert_called_with(0, 1)

    @mock.patch("random.randint", autospec=True, return_value=1)
    def testWin(self, randint: mock.MagicMock):
        self.assert_response("!roulette 20", "username won 20 points!")
        randint.assert_called_with(0, 1)

    def testNonInt(self):
        self.assert_error("!roulette twenty", "Usage: !roulette <points>")

    def testNoArg(self):
        self.assert_error("!roulette", "Usage: !roulette <points>")