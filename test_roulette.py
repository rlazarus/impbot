from unittest import mock

import roulette
import tests_util


class RouletteHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = roulette.RouletteHandler()

    @mock.patch("random.randint", autospec=True, return_value=0)
    def testLose(self, randint: mock.MagicMock):
        self.handler.data.set("username", "100")
        self.assert_response("!roulette 20",
                             "username lost 20 points and now has 80 points.")
        randint.assert_called_with(0, 1)

    @mock.patch("random.randint", autospec=True, return_value=1)
    def testWin(self, randint: mock.MagicMock):
        self.handler.data.set("username", "100")
        self.assert_response("!roulette 20",
                             "username won 20 points and now has 120 points!")
        randint.assert_called_with(0, 1)

    def testNonInt(self):
        self.assert_error("!roulette twenty", "Usage: !roulette <points>")

    def testNoArg(self):
        self.assert_error("!roulette", "Usage: !roulette <points>")

    def testNoPoints(self):
        self.handler.data.set("username", "0")
        self.assert_error("!roulette 20", "You don't have any points!")

    def testInsufficientPoints(self):
        self.handler.data.set("username", "5")
        self.assert_error("!roulette 20", "You only have 5 points.")