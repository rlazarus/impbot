import hello
from tests_util import HandlerTest


class HelloHandlerTest(HandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = hello.HelloHandler()

    def test(self):
        self.assert_no_trigger("bleep bloop")
        self.assert_response("!hello", "Hello, world!")

    def testExtraArgsOkay(self):
        self.assert_response("!hello there", "Hello, world!")