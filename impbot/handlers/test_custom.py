from unittest import mock

from impbot.handlers import custom
from impbot.util import tests_util


# Mock out the cooldowns so that we can test commands repeatedly without having
# to mock out the clock.
@mock.patch("impbot.util.cooldown.Cooldown.peek", return_value=True)
@mock.patch("impbot.util.cooldown.Cooldown.fire", return_value=True)
class CustomCommandHandlerTest(tests_util.DataHandlerTest):

    def setUp(self):
        super().setUp()
        self.handler = custom.CustomCommandHandler()
        self.mod = tests_util.Moderator("mod")

    def testOnlyModsCanAdd(self, mock_peek, mock_fire):
        self.assert_error("!addcom !blame It's always Ms. Boogie's fault.",
                          "You can't do that.")

    def testPlain(self, mock_peek, mock_fire):
        self.assert_no_trigger("!blame")
        self.assert_response("!addcom !blame It's always Ms. Boogie's fault.",
                             "Added !blame.", self.mod)
        # Both mods and regular users should be able to use the custom command.
        self.assert_response("!blame", "It's always Ms. Boogie's fault.")
        self.assert_response("!blame", "It's always Ms. Boogie's fault.",
                             self.mod)
        # It should be case-insensitive.
        self.assert_response("!BlAmE", "It's always Ms. Boogie's fault.")
        # Editing should work.
        self.assert_response("!editcom !blame It's still Ms. Boogie's fault.",
                             "Edited !blame.", self.mod)
        self.assert_response("!blame", "It's still Ms. Boogie's fault.")

        self.assert_response("!delcom blame", "Deleted !blame.", self.mod)
        self.assert_no_trigger("!blame")

    def testWithCount(self, mock_peek, mock_fire):
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

    def testAliases(self, mock_peek, mock_fire):
        self.assert_no_trigger("!ping")
        self.assert_response("!addcom !ping Pong!", "Added !ping.", self.mod)
        self.assert_response("!aliascom !test !ping",
                             "Added !test as an alias to !ping.", self.mod)
        self.assert_response("!test", "Pong!")
        # An alias to an alias should just be an alias of the original command.
        self.assert_response("!aliascom !meta !test",
                             "Added !meta as an alias to !ping.", self.mod)
        self.assert_response("!meta", "Pong!")
        # Editing the alias should edit the command.
        self.assert_response("!editcom !test Edited pong!", "Edited !test (alias to !ping).", self.mod)
        self.assert_response("!ping", "Edited pong!")
        self.assert_response("!test", "Edited pong!")
        self.assert_response("!meta", "Edited pong!")
        # Deleting the alias should leave the command (and the other alias).
        self.assert_response("!delcom !test", "Deleted !test. (It was an alias to !ping.)", self.mod)
        self.assert_no_trigger("!test")
        self.assert_response("!ping", "Edited pong!")
        self.assert_response("!meta", "Edited pong!")
        self.assert_response("!aliascom !test !ping", "Added !test as an alias to !ping.", self.mod)
        # Deleting the command should disable the alias.
        self.assert_response("!delcom ping", "Deleted !ping.", self.mod)
        self.assert_no_trigger("!ping")
        self.assert_no_trigger("!test")
        self.assert_no_trigger("!meta")
        # Restoring the command should restore the alias.
        self.assert_response("!addcom !ping Pong!", "Added !ping.", self.mod)
        self.assert_response("!test", "Pong!")
        self.assert_response("!meta", "Pong!")
