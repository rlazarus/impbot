from typing import Optional, cast
from unittest import mock

from impbot.connections import twitch
from impbot.core import base
from impbot.handlers import blacklist
from impbot.util import tests_util


class TestBlacklistModerationHandler(tests_util.DataHandlerTest):
    def setUp(self):
        super().setUp()
        self.handler = blacklist.BlacklistModerationHandler()
        # For now, the handler rejects everything that didn't come from a Twitch
        # connection, because the moderation API isn't general yet. So we need
        # the mock to pass isinstance().
        self.reply_conn = mock.Mock(spec=twitch.TwitchChatConnection)
        self.handler.add("bee+p", blacklist.Action.PERMABAN, "No beeping!")
        self.handler.add("beeeep", blacklist.Action.ALLOW)
        self.handler.add("boop", blacklist.Action.DELETE)

    def assert_ban(self, input: str, output: Optional[str] = None) -> None:
        mock_conn = cast(mock.Mock, self.reply_conn)
        mock_conn.reset_mock()
        user = base.User("username")
        message = twitch.TwitchMessage(self.reply_conn, user, input, "")
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), None)
        mock_conn.permaban.assert_called_with(user, output)

    def assert_delete(self, input: str, output: Optional[str] = None) -> None:
        mock_conn = cast(mock.Mock, self.reply_conn)
        mock_conn.reset_mock()
        id = "abc-123-def"
        message = twitch.TwitchMessage(self.reply_conn, base.User("username"),
                                       input, id)
        self.assertTrue(self.handler.check(message))
        self.assertEqual(self.handler.run(message), None)
        mock_conn.delete.assert_called_with(message, output)

    def test_blacklist(self):
        self.assert_no_trigger("message message")
        self.assert_ban("beep", "No beeping!")
        self.assert_ban("beeep", "No beeping!")
        self.assert_no_trigger("beeeep")  # Whitelisted!
        self.assert_ban("beeeeep", "No beeping!")

        # One instance being whitelisted shouldn't stop another from triggering.
        self.assert_ban("beep beeeep", "No beeping!")
        self.assert_ban("beeeep beep", "No beeping!")

        self.assert_delete("boop")
