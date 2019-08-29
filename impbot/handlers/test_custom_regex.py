from impbot.handlers import custom_regex
from impbot.util import tests_util


class TestCustomRegex(tests_util.DataHandlerTest):
    def setUp(self):
        super().setUp()
        self.handler = custom_regex.CustomRegexHandler()

    def test_custom(self):
        self.handler.add_pattern("hi+", "Hi!")
        self.handler.add_pattern("hello+", "Hello!")
        self.handler.startup()
        self.assert_no_trigger("howdy")
        self.assert_response("hiiii", "Hi!")
        self.assert_response("hellooooo", "Hello!")
        self.assert_response("hi hello", "Hi!")