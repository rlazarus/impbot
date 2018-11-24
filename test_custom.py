import custom
import tests_util


class CustomCommandHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = custom.CustomCommandHandler()

    def testPlain(self):
        self.assert_no_trigger("!blame")
        self.assert_response("!addcom !blame It's always Ms. Boogie's fault.",
                             "Added !blame.")
        self.assert_response("!blame", "It's always Ms. Boogie's fault.")
        self.assert_response("!editcom !blame It's still Ms. Boogie's fault.",
                             "Edited !blame.")
        self.assert_response("!blame", "It's still Ms. Boogie's fault.")
        self.assert_response("!delcom blame", "Deleted !blame.")
        self.assert_no_trigger("!blame")

    def testWithCount(self):
        self.assert_no_trigger("!sheep")
        self.assert_response("!addcom !sheep (count) sheep jumped the fence.",
                             "Added !sheep.")
        self.assert_response("!sheep", "1 sheep jumped the fence.")
        self.assert_response("!sheep", "2 sheep jumped the fence.")
        self.assert_response("!sheep", "3 sheep jumped the fence.")
        self.assert_response("!resetcount !sheep 0",
                             "Reset !sheep counter to 0.")
        self.assert_response("!sheep", "1 sheep jumped the fence.")
        self.assert_response("!resetcount !sheep 16",
                             "Reset !sheep counter to 16.")
        self.assert_response("!sheep", "17 sheep jumped the fence.")
