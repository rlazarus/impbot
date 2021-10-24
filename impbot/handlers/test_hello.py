from impbot.handlers import hello
from impbot.util import tests_util


class HelloHandlerTest(tests_util.HandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = hello.HelloHandler()

    def test(self):
        self.assert_no_trigger('bleep bloop')
        self.assert_no_trigger('')
        self.assert_no_trigger(' ')
        self.assert_response('!hello', 'Hello, world!')

    def testExtraArgsOkay(self):
        self.assert_response('!hello there', 'Hello, world!')
