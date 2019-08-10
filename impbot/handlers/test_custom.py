from impbot.handlers import custom
from impbot.util import tests_util


class CustomCommandHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = custom.CustomCommandHandler()
        self.mod = tests_util.Moderator("mod")

    def testOnlyModsCanAdd(self):
        self.assert_error("!addcom !blame It's always Ms. Boogie's fault.",
                          "You can't do that.")

    def testPlain(self):
        self.assert_no_trigger("!blame")
        self.assert_response("!addcom !blame It's always Ms. Boogie's fault.",
                             "Added !blame.", self.mod)
        # Both mods and regular users should be able to use the custom command.
        self.assert_response("!blame", "It's always Ms. Boogie's fault.")
        self.assert_response("!blame", "It's always Ms. Boogie's fault.",
                             self.mod)
        # It should be case-insensitive.
        self.assert_response("!BlAmE", "It's always Ms. Boogie's fault.")
        self.assert_response("!editcom !blame It's still Ms. Boogie's fault.",
                             "Edited !blame.", self.mod)
        self.assert_response("!blame", "It's still Ms. Boogie's fault.")
        self.assert_response("!delcom blame", "Deleted !blame.", self.mod)
        self.assert_no_trigger("!blame")

    def testWithCount(self):
        self.assert_no_trigger("!sheep")
        self.assert_response("!addcom !sheep (count) sheep jumped the fence.",
                             "Added !sheep.", self.mod)
        self.assert_response("!sheep", "1 sheep jumped the fence.")
        self.assert_response("!sheep", "2 sheep jumped the fence.")
        self.assert_response("!sheep", "3 sheep jumped the fence.")
        self.assert_response("!resetcount !sheep",
                             "Reset !sheep counter to 0.", self.mod)
        self.assert_response("!sheep", "1 sheep jumped the fence.")
        self.assert_response("!resetcount !sheep 16",
                             "Reset !sheep counter to 16.", self.mod)
        self.assert_response("!sheep", "17 sheep jumped the fence.")
